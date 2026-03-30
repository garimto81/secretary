"""
Alert 모델 - 알림 데이터 타입 정의
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UrgentAlert:
    """긴급 메시지 알림"""
    message_id: str
    sender_name: str
    source_channel: str
    channel_id: str
    text_preview: str
    priority: str = "urgent"
    timestamp: datetime = field(default_factory=datetime.now)

    def format_slack(self) -> str:
        """Slack 메시지 포맷"""
        preview = self.text_preview[:200] if self.text_preview else "(내용 없음)"
        return (
            f":rotating_light: *[긴급]* 새 메시지\n"
            f"*발신자:* {self.sender_name} ({self.source_channel})\n"
            f"*내용:* {preview}"
        )


@dataclass
class DraftNotification:
    """초안 생성 알림"""
    draft_id: int
    project_id: str
    sender_name: str
    source_channel: str
    match_confidence: float
    match_tier: str
    timestamp: datetime = field(default_factory=datetime.now)

    def format_slack(self) -> str:
        """Slack 메시지 포맷"""
        return (
            f":memo: *새 응답 초안*\n"
            f"*프로젝트:* {self.project_id}\n"
            f"*발신자:* {self.sender_name} ({self.source_channel})\n"
            f"*신뢰도:* {self.match_confidence:.2f} ({self.match_tier})\n"
            f"*CLI:* `python scripts/intelligence/cli.py drafts approve {self.draft_id}`"
        )
