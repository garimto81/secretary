"""
SlackTracker - Slack 증분 수집기

lib.slack.SlackClient를 사용하여 채널별 새 메시지를 수집합니다.
oldest 파라미터를 활용한 증분 조회.
"""

import asyncio
import hashlib

from ...context_store import IntelligenceStorage
from ..analysis_state import AnalysisStateManager


class SlackTracker:
    """Slack 증분 수집기"""

    def __init__(self, storage: IntelligenceStorage, state_manager: AnalysisStateManager):
        self.storage = storage
        self.state_manager = state_manager
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from lib.slack import SlackClient
            self._client = SlackClient()

    async def fetch_new(
        self,
        project_id: str,
        channels: list[str],
    ) -> int:
        """
        프로젝트의 Slack 채널에서 새 메시지 수집

        Args:
            project_id: 프로젝트 ID
            channels: 채널 ID 목록

        Returns:
            수집된 항목 수
        """
        total = 0

        for channel_id in channels:
            count = await self._fetch_channel(project_id, channel_id)
            total += count

        return total

    async def _fetch_channel(self, project_id: str, channel_id: str) -> int:
        """단일 채널에서 새 메시지 수집 (페이지네이션 + 스레드 지원)

        최초 수집 (last_ts is None): cursor 기반 무제한 전체 페이지네이션 + 파일 수집
        증분 수집 (last_ts 있음): 500건 캡, oldest 기반 신규만 수집
        """
        await asyncio.to_thread(self._ensure_client)

        last_ts = await self.state_manager.get_slack_last_ts(project_id, channel_id)
        is_initial = last_ts is None

        all_messages = []

        if is_initial:
            # 최초 수집: cursor 기반 전체 페이지네이션 (무제한)
            cursor = None
            while True:
                messages, next_cursor = await asyncio.to_thread(
                    self._client.get_history_with_cursor,
                    channel_id,
                    100,
                    None,   # oldest=None (전체)
                    cursor,
                )

                if not messages:
                    break

                all_messages.extend(messages)

                if not next_cursor:
                    break

                cursor = next_cursor
                # Slack API rate limit 준수
                await asyncio.sleep(1.0)
        else:
            # 증분 수집: oldest=last_ts, 500건 캡 유지
            current_last_ts = last_ts
            max_messages = 500

            while len(all_messages) < max_messages:
                messages = await asyncio.to_thread(
                    self._client.get_history,
                    channel_id,
                    100,
                    current_last_ts,
                )

                if not messages:
                    break

                all_messages.extend(messages)

                if len(messages) < 100:
                    break

                current_last_ts = messages[-1].ts

                if len(all_messages) >= max_messages:
                    all_messages = all_messages[:max_messages]
                    break

        if not all_messages:
            return 0

        max_ts = last_ts
        count = 0

        for msg in all_messages:
            if last_ts and msg.ts <= last_ts:
                continue

            if max_ts is None or msg.ts > max_ts:
                max_ts = msg.ts

            entry_id = hashlib.sha256(f"slack:{channel_id}:{msg.ts}".encode()).hexdigest()[:16]

            await self.storage.save_context_entry({
                "id": entry_id,
                "project_id": project_id,
                "source": "slack",
                "source_id": msg.ts,
                "entry_type": "message",
                "title": f"Slack #{channel_id}",
                "content": msg.text or "",
                "metadata": {
                    "channel_id": channel_id,
                    "user": msg.user,
                    "ts": msg.ts,
                    "thread_ts": msg.thread_ts,
                },
            })
            count += 1

            # 최초 수집 시 파일 첨부 수집
            if is_initial and hasattr(msg, 'files') and msg.files:
                count += await self._save_file_entries(
                    project_id, channel_id, msg.ts, msg.files
                )

            # Fetch thread replies if this message has replies
            if hasattr(msg, 'thread_ts') and msg.thread_ts and msg.thread_ts != msg.ts:
                try:
                    replies = await asyncio.to_thread(
                        self._client.get_replies,
                        channel_id,
                        msg.thread_ts,
                    )
                    if replies:
                        for reply in replies:
                            reply_entry_id = hashlib.sha256(
                                f"slack:{channel_id}:thread:{reply.ts}".encode()
                            ).hexdigest()[:16]

                            await self.storage.save_context_entry({
                                "id": reply_entry_id,
                                "project_id": project_id,
                                "source": "slack",
                                "source_id": reply.ts,
                                "entry_type": "thread_reply",
                                "title": f"Slack #{channel_id} (thread)",
                                "content": reply.text or "",
                                "metadata": {
                                    "channel_id": channel_id,
                                    "user": reply.user,
                                    "ts": reply.ts,
                                    "thread_ts": msg.thread_ts,
                                    "parent_ts": msg.ts,
                                },
                            })
                            count += 1
                except (AttributeError, Exception):
                    # get_replies() method not available or request failed - skip gracefully
                    pass

        if max_ts and max_ts != last_ts:
            await self.state_manager.save_slack_last_ts(project_id, channel_id, max_ts, count)

        return count

    async def _save_file_entries(
        self,
        project_id: str,
        channel_id: str,
        msg_ts: str,
        files: list[dict],
    ) -> int:
        """메시지에 첨부된 파일 메타데이터를 context entry로 저장"""
        count = 0
        for file_obj in files:
            file_id = file_obj.get("id", "")
            if not file_id:
                continue

            name = file_obj.get("name") or file_obj.get("title") or "(이름 없음)"
            filetype = file_obj.get("filetype") or file_obj.get("pretty_type") or ""
            preview = file_obj.get("plain_text") or file_obj.get("preview") or ""
            title = file_obj.get("title") or name

            content = f"[파일] {name}"
            if filetype:
                content += f" ({filetype})"
            if preview:
                content += f"\n{preview[:2000]}"

            entry_id = hashlib.sha256(
                f"slack:file:{channel_id}:{file_id}".encode()
            ).hexdigest()[:16]

            await self.storage.save_context_entry({
                "id": entry_id,
                "project_id": project_id,
                "source": "slack",
                "source_id": file_id,
                "entry_type": "file",
                "title": f"Slack #{channel_id} 파일: {title}",
                "content": content,
                "metadata": {
                    "channel_id": channel_id,
                    "msg_ts": msg_ts,
                    "file_id": file_id,
                    "filetype": filetype,
                    "file_name": name,
                },
            })
            count += 1

        return count
