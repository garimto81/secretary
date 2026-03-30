"""
Digest Report - 일일 요약 보고서 생성
"""

from datetime import datetime
from typing import Any


class DigestReport:
    """일일 요약 보고서 데이터 집계 및 포맷"""

    def __init__(self, gateway_storage, intel_storage):
        self.gateway_storage = gateway_storage
        self.intel_storage = intel_storage

    async def generate(self, since: datetime | None = None,
                       project_id: str | None = None) -> dict[str, Any]:
        """Digest 데이터 집계 (project_id로 필터 가능)"""
        if since is None:
            since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        data = {
            "date": datetime.now().strftime("%m/%d"),
            "project_id": project_id,
            "since": since.isoformat(),
            "messages": await self._count_messages(since, project_id),
            "drafts": await self._count_drafts(since),
            "pending_matches": await self._count_pending_matches(),
            "actions": await self._count_actions(since, project_id),
        }

        return data

    async def _count_messages(self, since: datetime,
                              project_id: str | None = None) -> dict[str, Any]:
        """메시지 수 집계 (project_id 필터 지원)"""
        try:
            if not self.gateway_storage or not self.gateway_storage._connection:
                return {"total": 0, "urgent": 0, "high": 0}

            conn = self.gateway_storage._connection
            proj_clause = " AND project_id = ?" if project_id else ""
            params_base = [since.isoformat()] + ([project_id] if project_id else [])

            async with conn.execute(
                f"SELECT COUNT(*) as c FROM messages WHERE timestamp >= ?{proj_clause}",
                params_base,
            ) as cursor:
                row = await cursor.fetchone()
                total = row["c"] if row else 0

            async with conn.execute(
                f"SELECT COUNT(*) as c FROM messages WHERE timestamp >= ? AND priority = 'urgent'{proj_clause}",
                params_base,
            ) as cursor:
                row = await cursor.fetchone()
                urgent = row["c"] if row else 0

            async with conn.execute(
                f"SELECT COUNT(*) as c FROM messages WHERE timestamp >= ? AND priority = 'high'{proj_clause}",
                params_base,
            ) as cursor:
                row = await cursor.fetchone()
                high = row["c"] if row else 0

            return {"total": total, "urgent": urgent, "high": high}
        except Exception:
            return {"total": 0, "urgent": 0, "high": 0}

    async def _count_drafts(self, since: datetime) -> dict[str, Any]:
        """초안 수 집계"""
        try:
            if not self.intel_storage or not self.intel_storage._connection:
                return {"total": 0, "pending": 0, "approved": 0}

            conn = self.intel_storage._connection

            async with conn.execute(
                "SELECT COUNT(*) as c FROM draft_responses WHERE created_at >= ?",
                (since.isoformat(),),
            ) as cursor:
                row = await cursor.fetchone()
                total = row["c"] if row else 0

            async with conn.execute(
                "SELECT COUNT(*) as c FROM draft_responses WHERE status = 'pending'",
            ) as cursor:
                row = await cursor.fetchone()
                pending = row["c"] if row else 0

            async with conn.execute(
                "SELECT COUNT(*) as c FROM draft_responses WHERE created_at >= ? AND status = 'approved'",
                (since.isoformat(),),
            ) as cursor:
                row = await cursor.fetchone()
                approved = row["c"] if row else 0

            return {"total": total, "pending": pending, "approved": approved}
        except Exception:
            return {"total": 0, "pending": 0, "approved": 0}

    async def _count_pending_matches(self) -> int:
        """미매칭 메시지 수"""
        try:
            if not self.intel_storage or not self.intel_storage._connection:
                return 0

            async with self.intel_storage._connection.execute(
                "SELECT COUNT(*) as c FROM draft_responses WHERE match_status = 'pending_match'"
            ) as cursor:
                row = await cursor.fetchone()
                return row["c"] if row else 0
        except Exception:
            return 0

    async def _count_actions(self, since: datetime,
                             project_id: str | None = None) -> int:
        """감지된 액션 수 (project_id 필터 지원)"""
        try:
            if not self.gateway_storage or not self.gateway_storage._connection:
                return 0

            proj_clause = " AND project_id = ?" if project_id else ""
            params = [since.isoformat()] + ([project_id] if project_id else [])

            async with self.gateway_storage._connection.execute(
                f"SELECT COUNT(*) as c FROM messages WHERE timestamp >= ? AND has_action = 1{proj_clause}",
                params,
            ) as cursor:
                row = await cursor.fetchone()
                return row["c"] if row else 0
        except Exception:
            return 0

    def format_slack(self, data: dict[str, Any]) -> str:
        """Slack 메시지 포맷"""
        msgs = data["messages"]
        drafts = data["drafts"]
        project_label = f" [{data['project_id']}]" if data.get("project_id") else ""

        return (
            f":clipboard: *일일 요약*{project_label} ({data['date']})\n"
            f"- 총 메시지: {msgs['total']}건"
            f" (긴급 {msgs['urgent']}, 높음 {msgs['high']})\n"
            f"- 생성 초안: {drafts['total']}건"
            f" (대기 {drafts['pending']}, 승인 {drafts['approved']})\n"
            f"- 미매칭: {data['pending_matches']}건\n"
            f"- 감지 액션: {data['actions']}건"
        )
