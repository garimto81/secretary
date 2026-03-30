"""
FeedbackStore - 피드백 데이터 저장소

approve/reject 리뷰 시 사유 및 수정 내용을 저장하여
향후 패턴 분석 및 프롬프트 개선에 활용.

설계: IntelligenceStorage의 connection을 공유 (독립 연결 금지)
"""

from typing import Any

try:
    from scripts.intelligence.context_store import IntelligenceStorage
except ImportError:
    try:
        from intelligence.context_store import IntelligenceStorage
    except ImportError:
        from .context_store import IntelligenceStorage


REASON_CHOICES = ["부정확함", "어조부적절", "누락정보", "반복", "기타"]


class FeedbackStore:
    """
    피드백 데이터 저장소.

    IntelligenceStorage의 connection을 공유하여 WAL write lock 경합 방지.
    독립 DB 연결 절대 금지.
    """

    def __init__(self, storage: "IntelligenceStorage"):
        self._storage = storage

    @property
    def _conn(self):
        return self._storage._connection

    async def save_feedback(
        self,
        draft_id: int,
        decision: str,
        reason: str | None = None,
        modification_summary: str | None = None,
    ) -> int:
        """
        피드백 저장.

        Args:
            draft_id: draft_responses.id
            decision: 'approved' | 'rejected'
            reason: 거부/승인 사유 (선택)
            modification_summary: 수정 내용 요약 (선택)

        Returns:
            생성된 feedback_responses.id
        """
        cursor = await self._conn.execute(
            """INSERT INTO feedback_responses
            (draft_id, decision, reason, modification_summary)
            VALUES (?, ?, ?, ?)""",
            (draft_id, decision, reason, modification_summary),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_feedback_by_draft(self, draft_id: int) -> dict[str, Any] | None:
        """draft_id로 피드백 조회"""
        async with self._conn.execute(
            "SELECT * FROM feedback_responses WHERE draft_id = ?",
            (draft_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def list_feedback(
        self,
        decision: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """피드백 목록 조회 (created_at DESC)"""
        query = "SELECT * FROM feedback_responses WHERE 1=1"
        params: list = []

        if decision:
            query += " AND decision = ?"
            params.append(decision)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
