"""
GmailTracker - Gmail 증분 수집기

lib.gmail.GmailClient를 사용하여 History API 기반 증분 수집.
historyId 만료 시 messages.list fallback.
"""

import asyncio
import hashlib
from datetime import datetime, timedelta

from ...context_store import IntelligenceStorage
from ..analysis_state import AnalysisStateManager


class GmailTracker:
    """Gmail 증분 수집기"""

    def __init__(self, storage: IntelligenceStorage, state_manager: AnalysisStateManager):
        self.storage = storage
        self.state_manager = state_manager
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from lib.gmail import GmailClient
            self._client = GmailClient()

    async def fetch_new(
        self,
        project_id: str,
        gmail_queries: list[str],
    ) -> int:
        """
        프로젝트 관련 Gmail 메시지 증분 수집

        Args:
            project_id: 프로젝트 ID
            gmail_queries: Gmail 검색 쿼리 목록

        Returns:
            수집된 항목 수
        """
        if not gmail_queries:
            return 0

        await asyncio.to_thread(self._ensure_client)

        last_history_id = await self.state_manager.get_gmail_history_id(project_id)

        if last_history_id:
            count = await self._fetch_via_history(project_id, last_history_id)
        else:
            # 최초 수집: 날짜 필터 없이 전체 수집
            count = await self._fetch_via_list(project_id, gmail_queries, initial=True)

        return count

    async def _fetch_via_history(self, project_id: str, history_id: str) -> int:
        """History API로 증분 수집"""
        try:
            history = await asyncio.to_thread(
                self._client.list_history,
                history_id,
                ["messageAdded"],
            )
        except Exception:
            return await self._fetch_via_list(project_id, [])

        new_history_id = history.get("historyId")
        history_records = history.get("history", [])

        if not history_records:
            if new_history_id:
                await self.state_manager.save_gmail_history_id(project_id, str(new_history_id), 0)
            return 0

        message_ids = set()
        for record in history_records:
            for msg_added in record.get("messagesAdded", []):
                msg = msg_added.get("message", {})
                msg_id = msg.get("id")
                if msg_id:
                    message_ids.add(msg_id)

        count = 0
        for msg_id in message_ids:
            try:
                email = await asyncio.to_thread(self._client.get_email, msg_id)
                await self._save_email_entry(project_id, email)
                count += 1
            except Exception:
                continue

        if new_history_id:
            await self.state_manager.save_gmail_history_id(project_id, str(new_history_id), count)

        return count

    async def _fetch_via_list(self, project_id: str, queries: list[str], initial: bool = False) -> int:
        """messages.list fallback

        Args:
            initial: True 시 날짜 필터 없이 전체 수집 (limit=500).
                     False 시 최근 7일 + 20건 제한 (기존 동작).
        """
        query = " OR ".join(queries) if queries else "is:inbox"

        if initial:
            # 최초 수집: 날짜 필터 없이 전체 매칭 메일 수집
            fetch_limit = 500
        else:
            # 증분 수집: 최근 7일만
            seven_days_ago_epoch = int((datetime.now() - timedelta(days=7)).timestamp())
            query = f"after:{seven_days_ago_epoch} {query}"
            fetch_limit = 20

        emails = await asyncio.to_thread(
            self._client.list_emails,
            query,
            fetch_limit,
        )

        count = 0
        for email in emails:
            await self._save_email_entry(project_id, email)
            count += 1

        profile = await asyncio.to_thread(self._client.get_profile)
        new_history_id = str(profile.get("historyId", ""))
        if new_history_id:
            await self.state_manager.save_gmail_history_id(project_id, new_history_id, count)

        return count

    async def _save_email_entry(self, project_id: str, email) -> None:
        """이메일을 context entry로 저장"""
        entry_id = hashlib.sha256(f"gmail:{email.id}".encode()).hexdigest()[:16]
        body = email.body_text or email.snippet or ""
        if len(body) > 4000:
            body = body[:4000] + "..."

        await self.storage.save_context_entry({
            "id": entry_id,
            "project_id": project_id,
            "source": "gmail",
            "source_id": email.id,
            "entry_type": "email",
            "title": email.subject or "(제목 없음)",
            "content": body,
            "metadata": {
                "sender": email.sender,
                "to": email.to,
                "thread_id": email.thread_id,
                "date": email.date.isoformat() if email.date else None,
                "is_unread": email.is_unread,
            },
        })
