"""
GmailAdapter - Gmail 채널 어댑터 (lib.gmail 기반)

lib.gmail.GmailClient를 사용하여 Gmail 수신 메시지를 감지합니다.
historyId 기반 증분 조회로 새 메시지만 처리합니다.

Features:
- 60초 polling 기반
- historyId 증분 조회 (History API)
- Fallback: messages.list (historyId 만료 시)
"""

import asyncio
import base64
from email.mime.text import MIMEText
import json
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.models import NormalizedMessage, ChannelType, MessageType
    from scripts.gateway.adapters.base import ChannelAdapter, SendResult
except ImportError:
    try:
        from gateway.models import NormalizedMessage, ChannelType, MessageType
        from gateway.adapters.base import ChannelAdapter, SendResult
    except ImportError:
        from ..models import NormalizedMessage, ChannelType, MessageType
        from .base import ChannelAdapter, SendResult


class GmailAdapter(ChannelAdapter):
    """
    Gmail 채널 어댑터

    lib.gmail.GmailClient를 사용하여 새 이메일을 감지합니다.
    """

    EXCLUDED_LABELS: set = {"SPAM", "TRASH"}
    SYSTEM_LABELS: set = {
        "UNREAD", "IMPORTANT", "STARRED",
        "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_UPDATES",
        "CATEGORY_PROMOTIONS", "CATEGORY_FORUMS",
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.channel_type = ChannelType.EMAIL
        self._client = None
        self._polling_interval: int = config.get("polling_interval", 60)
        self._last_history_id: Optional[str] = None
        self._seen_ids: set = set()

        # Deprecated config 경고
        if "label_filter" in config:
            print(f"[GmailAdapter] Warning: 'label_filter' config is deprecated. All labels are now scanned automatically (excluding SPAM/TRASH).")

    async def connect(self) -> bool:
        """Gmail 연결 (lib.gmail 사용)"""
        try:
            from lib.gmail import GmailClient
            self._client = await asyncio.to_thread(GmailClient)

            profile = await asyncio.to_thread(self._client.get_profile)
            self._last_history_id = str(profile.get("historyId", ""))
            email = profile.get("emailAddress", "unknown")

            self._connected = True
            print(f"[GmailAdapter] 연결 성공 ({email})")
            return True

        except Exception as e:
            print(f"[GmailAdapter] 연결 실패: {e}")
            return False

    async def disconnect(self) -> None:
        """연결 해제"""
        self._connected = False
        self._client = None

    async def listen(self) -> AsyncIterator[NormalizedMessage]:
        """
        Gmail 메시지 polling (60초 간격)

        Yields:
            NormalizedMessage
        """
        while self._connected:
            try:
                messages = await self._poll_new_messages()
                for msg in messages:
                    yield msg
            except Exception as e:
                print(f"[GmailAdapter] polling 오류: {e}")

            await asyncio.sleep(self._polling_interval)

    async def send(self, message) -> SendResult:
        """이메일 전송

        confirmed=False: 로컬 draft 파일만 저장 (기존 동작)
        confirmed=True: Gmail Draft로 생성 (Gmail UI에서 최종 확인 후 전송 가능)
        """
        if not message.confirmed:
            # Draft 모드: 로컬 파일만 저장
            draft_dir = Path(r"C:\claude\secretary\data\drafts")
            draft_dir.mkdir(parents=True, exist_ok=True)
            draft_path = draft_dir / f"gmail_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            draft_path.write_text(
                f"To: {message.to}\n\n{message.text}",
                encoding="utf-8",
            )
            return SendResult(success=True, draft_path=str(draft_path))

        # Gmail Draft 생성 모드 (실제 전송 아님, Gmail UI에서 확인 후 전송)
        if not self._client:
            return SendResult(success=False, error="GmailAdapter not connected. Call connect() first.")

        try:
            result = await self._create_gmail_draft(
                to=message.to,
                subject=message.subject or '',
                body=message.text,
            )
            return SendResult(
                success=True,
                message_id=result.get("id"),
                sent_at=datetime.now(),
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))

    async def _create_gmail_draft(self, to: str, subject: str, body: str) -> dict:
        """Gmail Draft API 직접 호출 (lib.gmail에 create_draft 미지원)"""
        def _sync_create():
            mime = MIMEText(body)
            mime["to"] = to
            if subject:
                mime["subject"] = subject
            raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            return self._client.service.users().drafts().create(
                userId="me",
                body={"message": {"raw": raw}},
            ).execute()

        return await asyncio.to_thread(_sync_create)

    async def get_status(self) -> dict:
        """상태 조회"""
        return {
            "connected": self._connected,
            "last_history_id": self._last_history_id,
            "polling_interval": self._polling_interval,
            "seen_messages": len(self._seen_ids),
        }

    async def _poll_new_messages(self) -> list:
        """새 메시지 조회 (History API + fallback)"""
        if not self._client or not self._last_history_id:
            return []

        try:
            history = await asyncio.to_thread(
                self._client.list_history,
                self._last_history_id,
                ["messageAdded"],
                None,  # 전체 라벨 스캔
            )
        except Exception:
            return await self._fallback_poll()

        new_history_id = history.get("historyId")
        if new_history_id:
            self._last_history_id = str(new_history_id)

        history_records = history.get("history", [])
        if not history_records:
            return []

        message_ids = {}  # msg_id -> label_ids 매핑
        for record in history_records:
            for msg_added in record.get("messagesAdded", []):
                msg = msg_added.get("message", {})
                msg_id = msg.get("id")
                label_ids = set(msg.get("labelIds", []))

                # SPAM/TRASH 제외
                if self.EXCLUDED_LABELS & label_ids:
                    continue

                if msg_id and msg_id not in self._seen_ids:
                    message_ids[msg_id] = label_ids

        normalized = []
        for msg_id, label_ids in message_ids.items():
            try:
                email = await asyncio.to_thread(self._client.get_email, msg_id)
                self._seen_ids.add(msg_id)

                body = email.body_text or email.snippet or ""
                if len(body) > 2000:
                    body = body[:2000] + "..."

                # 라벨에서 channel_id 추출
                channel_id = self._extract_primary_label(label_ids)

                normalized.append(NormalizedMessage(
                    id=f"gmail_{msg_id}",
                    channel=ChannelType.EMAIL,
                    channel_id=channel_id,
                    sender_id=email.sender or "unknown",
                    sender_name=email.sender,
                    text=f"[{email.subject}] {body}",
                    message_type=MessageType.TEXT,
                    timestamp=email.date or datetime.now(),
                    is_group=len(email.to) > 1 if email.to else False,
                    raw_json=json.dumps({
                        "id": email.id,
                        "thread_id": email.thread_id,
                        "subject": email.subject,
                        "label_ids": list(label_ids),
                    }, ensure_ascii=False),
                ))
            except Exception as e:
                print(f"[GmailAdapter] 메시지 조회 실패 ({msg_id}): {e}")

        return normalized

    async def _fallback_poll(self) -> list:
        """Fallback: messages.list로 최근 메시지 조회"""
        if not self._client:
            return []

        try:
            emails = await asyncio.to_thread(
                self._client.list_emails,
                "is:unread",
                5,
                None,  # 전체 라벨 스캔
                False,  # include_spam_trash=False
            )

            profile = await asyncio.to_thread(self._client.get_profile)
            self._last_history_id = str(profile.get("historyId", ""))

            normalized = []
            for email in emails:
                if email.id in self._seen_ids:
                    continue
                self._seen_ids.add(email.id)

                body = email.body_text or email.snippet or ""
                if len(body) > 2000:
                    body = body[:2000] + "..."

                normalized.append(NormalizedMessage(
                    id=f"gmail_{email.id}",
                    channel=ChannelType.EMAIL,
                    channel_id="all",
                    sender_id=email.sender or "unknown",
                    sender_name=email.sender,
                    text=f"[{email.subject}] {body}",
                    message_type=MessageType.TEXT,
                    timestamp=email.date or datetime.now(),
                    is_group=len(email.to) > 1 if email.to else False,
                    raw_json=json.dumps({
                        "id": email.id,
                        "thread_id": email.thread_id,
                        "subject": email.subject,
                    }, ensure_ascii=False),
                ))

            return normalized
        except Exception as e:
            print(f"[GmailAdapter] fallback 조회 실패: {e}")
            return []

    def _extract_primary_label(self, label_ids: set) -> str:
        """라벨 집합에서 대표 라벨 추출하여 channel_id로 사용"""
        meaningful = label_ids - self.SYSTEM_LABELS - self.EXCLUDED_LABELS
        if not meaningful:
            return "unknown"

        # 사용자 정의 라벨 우선 (대문자가 아닌 것)
        user_labels = [l for l in meaningful if not l.isupper()]
        if user_labels:
            return user_labels[0].lower()

        # 시스템 라벨 중 의미 있는 것
        for label in ["INBOX", "SENT", "DRAFT"]:
            if label in meaningful:
                return label.lower()

        return next(iter(meaningful)).lower()
