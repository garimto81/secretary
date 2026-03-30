"""
EnrichedMessage 모델 테스트
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.gateway.models import (
    ChannelType,
    EnrichedMessage,
    NormalizedMessage,
    Priority,
)


class TestEnrichedMessage:
    """EnrichedMessage 테스트"""

    def test_wraps_original(self):
        """원본 메시지를 래핑"""
        msg = NormalizedMessage(
            id="test-1",
            channel=ChannelType.SLACK,
            channel_id="ch-1",
            sender_id="user-1",
            text="hello",
        )
        enriched = EnrichedMessage(original=msg)

        assert enriched.original is msg
        assert enriched.message is msg
        assert enriched.priority is None
        assert enriched.has_action is False
        assert enriched.actions == []

    def test_original_immutable(self):
        """EnrichedMessage에 priority 설정해도 원본 NormalizedMessage는 불변"""
        msg = NormalizedMessage(
            id="test-2",
            channel=ChannelType.SLACK,
            channel_id="ch-1",
            sender_id="user-1",
            text="긴급 메시지",
        )
        enriched = EnrichedMessage(original=msg)
        enriched.priority = Priority.URGENT
        enriched.has_action = True
        enriched.actions = ["action_request:확인"]

        # 원본은 변경되지 않음
        assert msg.priority is None
        assert msg.has_action is False

        # enriched에만 기록됨
        assert enriched.priority == Priority.URGENT
        assert enriched.has_action is True
        assert "action_request:확인" in enriched.actions

    def test_to_dict(self):
        """직렬화"""
        msg = NormalizedMessage(
            id="test-3",
            channel=ChannelType.EMAIL,
            channel_id="inbox",
            sender_id="user-1",
            text="test",
        )
        enriched = EnrichedMessage(
            original=msg,
            priority=Priority.HIGH,
            has_action=True,
            actions=["deadline:오늘까지"],
        )

        d = enriched.to_dict()
        assert d["priority"] == "high"
        assert d["has_action"] is True
        assert d["actions"] == ["deadline:오늘까지"]
        assert d["original"]["id"] == "test-3"

    def test_message_property(self):
        """message 속성이 original과 동일"""
        msg = NormalizedMessage(
            id="test-4",
            channel=ChannelType.SLACK,
            channel_id="chat-1",
            sender_id="user-1",
        )
        enriched = EnrichedMessage(original=msg)
        assert enriched.message is enriched.original
