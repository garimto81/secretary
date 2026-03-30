"""
ContextMatcher - 3-tier 메시지-프로젝트 매칭

Tier 1: Channel Match (confidence 0.9)
  Slack 채널 ID가 프로젝트의 slack_channels에 포함 → 즉시 매칭

Tier 2: Keyword Match (confidence 0.6~0.8)
  메시지 텍스트에 프로젝트명, 키워드 포함 → 매칭

Tier 3: Sender Match (confidence 0.5)
  발신자가 프로젝트 관련 연락처 → 매칭

[매칭 실패] → pending_match 상태로 DB 저장
"""

from dataclasses import dataclass

from ..context_store import IntelligenceStorage
from ..project_registry import ProjectRegistry


@dataclass
class MatchResult:
    """매칭 결과"""
    matched: bool
    project_id: str | None = None
    project_name: str | None = None
    confidence: float = 0.0
    tier: str | None = None
    reason: str = ""


class ContextMatcher:
    """
    3-tier 메시지-프로젝트 매칭기

    순서대로 Tier 1→2→3을 시도하며, 첫 매칭에서 반환.
    모두 실패 시 pending_match로 기록.
    """

    def __init__(self, registry: ProjectRegistry, storage: IntelligenceStorage):
        self.registry = registry
        self.storage = storage

    async def match(
        self,
        channel_id: str,
        text: str,
        sender_id: str,
        source_channel: str = "slack",
    ) -> MatchResult:
        """
        메시지를 프로젝트에 매칭

        Args:
            channel_id: 채널 ID (Slack channel ID 등)
            text: 메시지 텍스트
            sender_id: 발신자 ID
            source_channel: 소스 채널 ('slack', 'gmail')

        Returns:
            MatchResult
        """
        # Tier 1: Channel Match
        result = await self._tier1_channel(channel_id)
        if result.matched:
            return result

        # Tier 2: Keyword Match
        result = await self._tier2_keyword(text)
        if result.matched:
            return result

        # Tier 3: Sender Match
        result = await self._tier3_sender(sender_id)
        if result.matched:
            return result

        # 매칭 실패
        return MatchResult(
            matched=False,
            confidence=0.0,
            tier=None,
            reason="No matching project found",
        )

    async def match_and_store_pending(
        self,
        channel_id: str,
        text: str,
        sender_id: str,
        sender_name: str | None,
        source_channel: str,
        source_message_id: str | None = None,
    ) -> MatchResult:
        """
        매칭 시도 후, 실패 시 pending_match로 DB 저장

        Returns:
            MatchResult
        """
        result = await self.match(channel_id, text, sender_id, source_channel)

        if not result.matched:
            await self.storage.save_draft({
                "project_id": None,
                "source_channel": source_channel,
                "source_message_id": source_message_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "original_text": text[:4000] if text else "",
                "draft_text": None,
                "draft_file": None,
                "match_confidence": 0.0,
                "match_tier": None,
                "match_status": "pending_match",
                "status": "pending",
            })

        return result

    async def _tier1_channel(self, channel_id: str) -> MatchResult:
        """Tier 1: Channel Match (confidence 0.9)"""
        if not channel_id:
            return MatchResult(matched=False)

        project = await self.registry.find_by_channel(channel_id)
        if project:
            return MatchResult(
                matched=True,
                project_id=project["id"],
                project_name=project["name"],
                confidence=0.9,
                tier="channel",
                reason=f"Channel {channel_id} belongs to project",
            )
        return MatchResult(matched=False)

    async def _tier2_keyword(self, text: str) -> MatchResult:
        """Tier 2: Keyword Match (confidence 0.6~0.8 based on score)"""
        if not text:
            return MatchResult(matched=False)

        projects = await self.registry.find_by_keyword(text)
        if projects:
            best = projects[0]
            score = best.get("_match_score", 1)
            # Confidence: 0.6 for 1 match, 0.7 for 2, 0.8 for 3+
            confidence = min(0.6 + (score - 1) * 0.1, 0.8)
            return MatchResult(
                matched=True,
                project_id=best["id"],
                project_name=best["name"],
                confidence=confidence,
                tier="keyword",
                reason=f"Keyword match (score={score}) for project '{best['name']}'",
            )
        return MatchResult(matched=False)

    async def _tier3_sender(self, sender_id: str) -> MatchResult:
        """Tier 3: Sender Match (confidence 0.5)"""
        if not sender_id:
            return MatchResult(matched=False)

        project = await self.registry.find_by_contact(sender_id)
        if project:
            return MatchResult(
                matched=True,
                project_id=project["id"],
                project_name=project["name"],
                confidence=0.5,
                tier="sender",
                reason=f"Sender {sender_id} is a contact of project '{project['name']}'",
            )
        return MatchResult(matched=False)
