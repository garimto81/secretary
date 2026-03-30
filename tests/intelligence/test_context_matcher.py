"""
ContextMatcher 테스트

3-tier 매칭 (Channel, Keyword, Sender) 검증.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.response.context_matcher import ContextMatcher, MatchResult


class TestContextMatcher:
    """ContextMatcher 3-tier 매칭 테스트"""

    @pytest.fixture
    def mock_registry(self):
        registry = AsyncMock()
        registry.find_by_channel = AsyncMock(return_value=None)
        registry.find_by_keyword = AsyncMock(return_value=[])
        registry.find_by_contact = AsyncMock(return_value=None)
        return registry

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage.save_draft = AsyncMock(return_value=1)
        return storage

    @pytest.fixture
    def matcher(self, mock_registry, mock_storage):
        return ContextMatcher(mock_registry, mock_storage)

    # ==========================================
    # Tier 1: Channel Match
    # ==========================================

    @pytest.mark.asyncio
    async def test_tier1_channel_match(self, matcher, mock_registry):
        """Tier 1: 채널 ID로 프로젝트 매칭"""
        mock_registry.find_by_channel = AsyncMock(return_value={
            "id": "secretary",
            "name": "Secretary",
        })

        result = await matcher.match(
            channel_id="C09N8J3UJN9",
            text="아무 텍스트",
            sender_id="U12345",
        )

        assert result.matched is True
        assert result.project_id == "secretary"
        assert result.confidence == 0.9
        assert result.tier == "channel"

    @pytest.mark.asyncio
    async def test_tier1_empty_channel_id(self, matcher):
        """Tier 1: 빈 channel_id는 매칭 실패"""
        result = await matcher._tier1_channel("")
        assert result.matched is False

    # ==========================================
    # Tier 2: Keyword Match
    # ==========================================

    @pytest.mark.asyncio
    async def test_tier2_keyword_match_single(self, matcher, mock_registry):
        """Tier 2: 단일 키워드 매칭 (confidence 0.6)"""
        mock_registry.find_by_keyword = AsyncMock(return_value=[
            {"id": "wsoptv", "name": "WSOP TV", "_match_score": 1}
        ])

        result = await matcher.match(
            channel_id="",
            text="wsop 방송 관련 문의",
            sender_id="U99999",
        )

        assert result.matched is True
        assert result.project_id == "wsoptv"
        assert result.confidence == 0.6
        assert result.tier == "keyword"

    @pytest.mark.asyncio
    async def test_tier2_keyword_match_multiple(self, matcher, mock_registry):
        """Tier 2: 다중 키워드 매칭 (confidence 증가)"""
        mock_registry.find_by_keyword = AsyncMock(return_value=[
            {"id": "wsoptv", "name": "WSOP TV", "_match_score": 3}
        ])

        result = await matcher.match(
            channel_id="",
            text="wsop 방송 자막 작업",
            sender_id="U99999",
        )

        assert result.matched is True
        assert result.confidence == 0.8  # score 3 → 0.8 cap

    @pytest.mark.asyncio
    async def test_tier2_keyword_match_high_score(self, matcher, mock_registry):
        """Tier 2: 높은 점수도 0.8 cap"""
        mock_registry.find_by_keyword = AsyncMock(return_value=[
            {"id": "wsoptv", "name": "WSOP TV", "_match_score": 5}
        ])

        result = await matcher.match(
            channel_id="",
            text="wsop 방송 자막 영상 작업",
            sender_id="U99999",
        )

        assert result.confidence == 0.8  # cap at 0.8

    @pytest.mark.asyncio
    async def test_tier2_empty_text(self, matcher):
        """Tier 2: 빈 텍스트는 매칭 실패"""
        result = await matcher._tier2_keyword("")
        assert result.matched is False

    # ==========================================
    # Tier 3: Sender Match
    # ==========================================

    @pytest.mark.asyncio
    async def test_tier3_sender_match(self, matcher, mock_registry):
        """Tier 3: 발신자 ID로 프로젝트 매칭"""
        mock_registry.find_by_contact = AsyncMock(return_value={
            "id": "secretary",
            "name": "Secretary",
        })

        result = await matcher.match(
            channel_id="",
            text="일반 메시지",
            sender_id="U12345",
        )

        assert result.matched is True
        assert result.project_id == "secretary"
        assert result.confidence == 0.5
        assert result.tier == "sender"

    @pytest.mark.asyncio
    async def test_tier3_empty_sender(self, matcher):
        """Tier 3: 빈 sender_id는 매칭 실패"""
        result = await matcher._tier3_sender("")
        assert result.matched is False

    # ==========================================
    # 전체 매칭 흐름
    # ==========================================

    @pytest.mark.asyncio
    async def test_no_match(self, matcher):
        """전체 tier 실패 시 unmatched 결과"""
        result = await matcher.match(
            channel_id="unknown-channel",
            text="관련 없는 메시지",
            sender_id="unknown-user",
        )

        assert result.matched is False
        assert result.project_id is None
        assert result.confidence == 0.0
        assert result.tier is None

    @pytest.mark.asyncio
    async def test_tier_priority_channel_first(self, matcher, mock_registry):
        """Channel match가 Keyword보다 우선"""
        mock_registry.find_by_channel = AsyncMock(return_value={
            "id": "secretary",
            "name": "Secretary",
        })
        mock_registry.find_by_keyword = AsyncMock(return_value=[
            {"id": "wsoptv", "name": "WSOP TV", "_match_score": 3}
        ])

        result = await matcher.match(
            channel_id="C09N8J3UJN9",
            text="wsop 방송 관련",
            sender_id="U12345",
        )

        # Channel match가 우선
        assert result.project_id == "secretary"
        assert result.tier == "channel"
        assert result.confidence == 0.9

    # ==========================================
    # match_and_store_pending
    # ==========================================

    @pytest.mark.asyncio
    async def test_match_and_store_pending_saves_on_failure(self, matcher, mock_storage):
        """매칭 실패 시 pending_match로 DB 저장"""
        result = await matcher.match_and_store_pending(
            channel_id="",
            text="미매칭 메시지",
            sender_id="U99999",
            sender_name="Unknown",
            source_channel="slack",
            source_message_id="msg-999",
        )

        assert result.matched is False
        mock_storage.save_draft.assert_called_once()
        saved = mock_storage.save_draft.call_args[0][0]
        assert saved["match_status"] == "pending_match"
        assert saved["project_id"] is None

    @pytest.mark.asyncio
    async def test_match_and_store_pending_no_save_on_success(self, matcher, mock_registry, mock_storage):
        """매칭 성공 시 DB 저장하지 않음"""
        mock_registry.find_by_channel = AsyncMock(return_value={
            "id": "secretary",
            "name": "Secretary",
        })

        result = await matcher.match_and_store_pending(
            channel_id="C09N8J3UJN9",
            text="secretary 관련",
            sender_id="U12345",
            sender_name="User",
            source_channel="slack",
        )

        assert result.matched is True
        mock_storage.save_draft.assert_not_called()


class TestMatchResult:
    """MatchResult dataclass 테스트"""

    def test_default_values(self):
        result = MatchResult(matched=False)
        assert result.project_id is None
        assert result.confidence == 0.0
        assert result.tier is None

    def test_matched_result(self):
        result = MatchResult(
            matched=True,
            project_id="test",
            confidence=0.9,
            tier="channel",
        )
        assert result.matched is True
        assert result.project_id == "test"
