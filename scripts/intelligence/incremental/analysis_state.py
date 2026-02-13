"""
AnalysisStateManager - 증분 분석 체크포인트 관리

각 소스별 마지막 분석 위치를 관리합니다:
- Gmail: historyId
- Slack: 채널별 last_ts
- GitHub: 마지막 이벤트 timestamp
"""

from typing import Optional, Dict, Any

from ..context_store import IntelligenceStorage


class AnalysisStateManager:
    """증분 분석 상태 관리"""

    def __init__(self, storage: IntelligenceStorage):
        self.storage = storage

    async def get_checkpoint(
        self,
        project_id: str,
        source: str,
        key: str,
    ) -> Optional[str]:
        """체크포인트 값 조회"""
        state = await self.storage.get_analysis_state(project_id, source, key)
        if state:
            return state.get("checkpoint_value")
        return None

    async def save_checkpoint(
        self,
        project_id: str,
        source: str,
        key: str,
        value: str,
        entries_collected: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """체크포인트 저장"""
        await self.storage.save_analysis_state(
            project_id=project_id,
            source=source,
            checkpoint_key=key,
            checkpoint_value=value,
            entries_collected=entries_collected,
            error_message=error,
        )

    async def get_gmail_history_id(self, project_id: str) -> Optional[str]:
        """Gmail historyId 조회"""
        return await self.get_checkpoint(project_id, "gmail", "history_id")

    async def save_gmail_history_id(
        self, project_id: str, history_id: str, entries: int = 0
    ) -> None:
        """Gmail historyId 저장"""
        await self.save_checkpoint(project_id, "gmail", "history_id", history_id, entries)

    async def get_slack_last_ts(self, project_id: str, channel_id: str) -> Optional[str]:
        """Slack 채널별 last_ts 조회"""
        return await self.get_checkpoint(project_id, "slack", f"last_ts:{channel_id}")

    async def save_slack_last_ts(
        self, project_id: str, channel_id: str, ts: str, entries: int = 0
    ) -> None:
        """Slack 채널별 last_ts 저장"""
        await self.save_checkpoint(project_id, "slack", f"last_ts:{channel_id}", ts, entries)

    async def get_github_since(self, project_id: str) -> Optional[str]:
        """GitHub 마지막 이벤트 timestamp 조회"""
        return await self.get_checkpoint(project_id, "github", "since")

    async def save_github_since(
        self, project_id: str, since: str, entries: int = 0
    ) -> None:
        """GitHub since timestamp 저장"""
        await self.save_checkpoint(project_id, "github", "since", since, entries)
