"""
Pipeline 테스트
"""

import asyncio
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.gateway.models import NormalizedMessage, ChannelType, MessageType, Priority
from scripts.gateway.storage import UnifiedStorage
from scripts.gateway.pipeline import MessagePipeline, PipelineResult


@pytest.fixture
def temp_db():
    """임시 DB 경로 생성"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def storage(temp_db):
    """스토리지 픽스처 (동기)"""
    storage = UnifiedStorage(temp_db)
    return storage


@pytest.fixture
def pipeline(storage):
    """파이프라인 픽스처"""
    return MessagePipeline(storage)


class TestPriority:
    """우선순위 분석 테스트"""

    @pytest.mark.asyncio
    async def test_urgent_keyword(self, storage, pipeline):
        """긴급 키워드 감지"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-urgent-1",
                channel=ChannelType.KAKAO,
                channel_id="chat-001",
                sender_id="user-001",
                text="긴급! 바로 확인해주세요",
            )

            result = await pipeline.process(msg)
            assert result.priority == "urgent"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_asap_keyword(self, storage, pipeline):
        """ASAP 키워드 감지"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-asap-1",
                channel=ChannelType.SLACK,
                channel_id="channel-001",
                sender_id="user-001",
                text="Please check this ASAP",
            )

            result = await pipeline.process(msg)
            assert result.priority == "urgent"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_mention_high_priority(self, storage, pipeline):
        """멘션 시 높은 우선순위"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-mention-1",
                channel=ChannelType.SLACK,
                channel_id="channel-001",
                sender_id="user-001",
                text="안녕하세요",
                is_mention=True,
            )

            result = await pipeline.process(msg)
            assert result.priority == "high"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_deadline_high_priority(self, storage, pipeline):
        """마감일 포함 시 높은 우선순위"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-deadline-1",
                channel=ChannelType.EMAIL,
                channel_id="inbox",
                sender_id="user-001",
                text="2/15까지 완료 부탁드립니다",
            )

            result = await pipeline.process(msg)
            assert result.priority == "high"
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_normal_message(self, storage, pipeline):
        """일반 메시지"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-normal-1",
                channel=ChannelType.KAKAO,
                channel_id="chat-001",
                sender_id="user-001",
                text="안녕하세요. 점심 뭐 먹을까요?",
            )

            result = await pipeline.process(msg)
            assert result.priority == "normal"
        finally:
            await storage.close()


class TestActionDetection:
    """액션 감지 테스트"""

    @pytest.mark.asyncio
    async def test_action_request(self, storage, pipeline):
        """액션 요청 감지"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-action-1",
                channel=ChannelType.KAKAO,
                channel_id="chat-001",
                sender_id="user-001",
                text="보고서 검토 부탁드립니다",
            )

            result = await pipeline.process(msg)
            assert result.has_action == True
            assert any("부탁" in a for a in result.actions)
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_deadline_detection(self, storage, pipeline):
        """마감일 감지"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-deadline-2",
                channel=ChannelType.EMAIL,
                channel_id="inbox",
                sender_id="user-001",
                text="오늘 중으로 확인해주세요",
            )

            result = await pipeline.process(msg)
            assert result.has_action == True
            assert any("deadline" in a for a in result.actions)
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_question_detection(self, storage, pipeline):
        """질문 감지"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-question-1",
                channel=ChannelType.SLACK,
                channel_id="channel-001",
                sender_id="user-001",
                text="이거 어떻게 하면 될까요?",
            )

            result = await pipeline.process(msg)
            assert result.has_action == True
            assert "question" in result.actions
        finally:
            await storage.close()


class TestStorage:
    """스토리지 연동 테스트"""

    @pytest.mark.asyncio
    async def test_message_saved(self, storage, pipeline):
        """메시지 저장 확인"""
        await storage.connect()
        try:
            msg = NormalizedMessage(
                id="test-save-1",
                channel=ChannelType.KAKAO,
                channel_id="chat-001",
                sender_id="user-001",
                text="테스트 메시지",
            )

            await pipeline.process(msg)

            stats = await storage.get_stats()
            assert stats["total_messages"] == 1
        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_multiple_messages(self, storage, pipeline):
        """다중 메시지 저장"""
        await storage.connect()
        try:
            for i in range(5):
                msg = NormalizedMessage(
                    id=f"test-multi-{i}",
                    channel=ChannelType.KAKAO,
                    channel_id="chat-001",
                    sender_id="user-001",
                    text=f"테스트 메시지 {i}",
                )
                await pipeline.process(msg)

            stats = await storage.get_stats()
            assert stats["total_messages"] == 5
        finally:
            await storage.close()


class TestPipelineResult:
    """PipelineResult 테스트"""

    def test_to_dict(self):
        """딕셔너리 변환"""
        result = PipelineResult(
            message_id="test-001",
            priority="urgent",
            has_action=True,
            actions=["action_request:확인", "deadline:오늘까지"],
            processed_at=datetime(2026, 2, 2, 10, 0, 0),
        )

        d = result.to_dict()
        assert d["message_id"] == "test-001"
        assert d["priority"] == "urgent"
        assert d["has_action"] == True
        assert len(d["actions"]) == 2


class TestCustomHandler:
    """커스텀 핸들러 테스트"""

    @pytest.mark.asyncio
    async def test_custom_handler_called(self, storage, pipeline):
        """커스텀 핸들러 호출 확인"""
        await storage.connect()
        try:
            handler_called = []

            async def custom_handler(msg, result):
                handler_called.append(msg.id)

            pipeline.add_handler(custom_handler)

            msg = NormalizedMessage(
                id="test-handler-1",
                channel=ChannelType.KAKAO,
                channel_id="chat-001",
                sender_id="user-001",
                text="테스트",
            )

            await pipeline.process(msg)
            assert "test-handler-1" in handler_called
        finally:
            await storage.close()
