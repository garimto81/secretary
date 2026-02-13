"""
SlackTracker - Slack 증분 수집기

lib.slack.SlackClient를 사용하여 채널별 새 메시지를 수집합니다.
oldest 파라미터를 활용한 증분 조회.
"""

import asyncio
import hashlib
from typing import List, Dict, Any, Optional

from ..analysis_state import AnalysisStateManager
from ...context_store import IntelligenceStorage


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
        channels: List[str],
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
        """단일 채널에서 새 메시지 수집 (페이지네이션 + 스레드 지원)"""
        await asyncio.to_thread(self._ensure_client)

        last_ts = await self.state_manager.get_slack_last_ts(project_id, channel_id)

        # Pagination: fetch up to 500 messages total
        all_messages = []
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

            # If we got fewer than 100, no more messages available
            if len(messages) < 100:
                break

            # Update cursor for next fetch (use last message's ts)
            current_last_ts = messages[-1].ts

            # Stop if we've reached the cap
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
