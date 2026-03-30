"""
SlackAdapter - Slack 채널 어댑터 (lib.slack 기반)

lib.slack.SlackClient를 사용하여 Slack 채널 메시지를 수신합니다.
asyncio.to_thread()로 동기 API를 비동기로 브릿지합니다.

Features:
- 5초 polling 기반 메시지 수신
- 채널별 last_ts 추적 (증분 조회)
- lib.slack Browser OAuth 토큰 자동 로드
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.adapters.base import ChannelAdapter, SendResult
    from scripts.gateway.models import ChannelType, MessageType, NormalizedMessage
except ImportError:
    try:
        from gateway.adapters.base import ChannelAdapter, SendResult
        from gateway.models import ChannelType, MessageType, NormalizedMessage
    except ImportError:
        from ..models import ChannelType, MessageType, NormalizedMessage
        from .base import ChannelAdapter, SendResult


class SlackAdapter(ChannelAdapter):
    """
    Slack 채널 어댑터

    lib.slack.SlackClient를 사용하여 Slack 메시지를 polling합니다.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.channel_type = ChannelType.SLACK
        self._client = None
        self._channels: list = config.get("channels", [])
        self._polling_interval: int = config.get("polling_interval", 5)
        self._last_ts: dict[str, str] = {}
        self._user_cache: dict[str, str] = {}

    async def connect(self) -> bool:
        """Slack 연결 (lib.slack 사용)"""
        try:
            from lib.slack import SlackClient
            self._client = await asyncio.to_thread(SlackClient)

            valid = await asyncio.to_thread(self._client.validate_token)
            if not valid:
                print("[SlackAdapter] 토큰 검증 실패")
                return False

            self._connected = True

            if not self._channels:
                print("[SlackAdapter] 감시 채널이 설정되지 않았습니다.")
                print("[SlackAdapter] 'python server.py start'로 재시작하여 채널을 선택하세요.")
                self._connected = False
                return False

            # 서버 시작 시점 이후 메시지만 처리 (기존 메시지 무시)
            import time
            start_ts = f"{time.time():.6f}"
            for channel_id in self._channels:
                if channel_id not in self._last_ts:
                    self._last_ts[channel_id] = start_ts

            print(f"[SlackAdapter] 연결 성공 ({len(self._channels)}개 채널, 시작 기준: {start_ts})")
            return True

        except Exception as e:
            print(f"[SlackAdapter] 연결 실패: {e}")
            return False

    async def disconnect(self) -> None:
        """연결 해제"""
        self._connected = False
        self._client = None

    async def listen(self) -> AsyncIterator[NormalizedMessage]:
        """
        Slack 메시지 polling (5초 간격)

        Yields:
            NormalizedMessage
        """
        while self._connected:
            try:
                for channel_id in self._channels:
                    messages = await self._poll_channel(channel_id)
                    for msg in messages:
                        yield msg
            except Exception as e:
                print(f"[SlackAdapter] polling 오류: {e}")

            await asyncio.sleep(self._polling_interval)

    async def send(self, message) -> SendResult:
        """메시지 전송

        confirmed=False: draft 파일만 저장 (기존 동작)
        confirmed=True: lib.slack.SlackClient.send_message()로 실제 전송
        """
        if not message.confirmed:
            # Draft 모드: 파일만 저장
            draft_dir = Path(r"C:\claude\secretary\data\drafts")
            draft_dir.mkdir(parents=True, exist_ok=True)
            draft_path = draft_dir / f"slack_{message.to}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            draft_path.write_text(message.text, encoding="utf-8")
            return SendResult(success=True, draft_path=str(draft_path))

        # 실제 전송 모드
        if not self._client:
            return SendResult(success=False, error="SlackAdapter not connected. Call connect() first.")

        try:
            slack_result = await asyncio.to_thread(
                self._client.send_message,
                channel=message.to,
                text=message.text,
                thread_ts=getattr(message, 'reply_to', None),
            )
            return SendResult(
                success=True,
                message_id=slack_result.ts,
                sent_at=datetime.now(),
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def get_status(self) -> dict:
        """상태 조회"""
        return {
            "connected": self._connected,
            "channels": len(self._channels),
            "polling_interval": self._polling_interval,
            "tracked_channels": list(self._last_ts.keys()),
        }

    async def _poll_channel(self, channel_id: str) -> list:
        """단일 채널에서 새 메시지 조회"""
        if not self._client:
            return []

        oldest = self._last_ts.get(channel_id)

        try:
            slack_messages = await asyncio.to_thread(
                self._client.get_history,
                channel_id,
                100,
                oldest,
            )
        except Exception:
            return []

        if not slack_messages:
            return []

        max_ts = oldest
        normalized = []

        for msg in slack_messages:
            if oldest and msg.ts <= oldest:
                continue

            if max_ts is None or msg.ts > max_ts:
                max_ts = msg.ts

            sender_name = await self._resolve_user(msg.user) if msg.user else None

            normalized.append(NormalizedMessage(
                id=f"slack_{channel_id}_{msg.ts}",
                channel=ChannelType.SLACK,
                channel_id=channel_id,
                sender_id=msg.user or "unknown",
                sender_name=sender_name,
                text=msg.text or "",
                message_type=MessageType.TEXT,
                timestamp=msg.timestamp or datetime.now(),
                is_group=True,
                is_mention=bool(re.search(r'<@U[A-Z0-9]+>', msg.text or "")),
                reply_to_id=msg.thread_ts if msg.thread_ts != msg.ts else None,
                raw_json=json.dumps({"ts": msg.ts, "channel": channel_id}),
            ))

        if max_ts:
            self._last_ts[channel_id] = max_ts

        return normalized

    async def _resolve_user(self, user_id: str) -> str | None:
        """User ID → 이름 변환 (캐시 포함)"""
        if user_id in self._user_cache:
            return self._user_cache[user_id]

        if not self._client:
            return None

        try:
            user = await asyncio.to_thread(self._client.get_user, user_id)
            name = user.real_name or user.display_name or user.name
            self._user_cache[user_id] = name
            return name
        except Exception:
            return None
