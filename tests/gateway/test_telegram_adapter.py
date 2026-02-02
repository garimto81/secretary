"""
Telegram Adapter 테스트
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from scripts.gateway.models import (
    ChannelType,
    MessageType,
    NormalizedMessage,
    OutboundMessage,
)
from scripts.gateway.adapters.telegram import TelegramAdapter, MockTelegramAdapter


class TestMockTelegramAdapter:
    """MockTelegramAdapter 테스트"""

    @pytest.fixture
    def adapter(self):
        """기본 Mock 어댑터"""
        config = {
            "bot_token": "test_token_123",
            "allowed_users": [12345, 67890],
        }
        return MockTelegramAdapter(config)

    @pytest.fixture
    def adapter_no_restriction(self):
        """사용자 제한 없는 Mock 어댑터"""
        config = {
            "bot_token": "test_token_123",
            "allowed_users": [],
        }
        return MockTelegramAdapter(config)

    @pytest.mark.asyncio
    async def test_connect_success(self, adapter):
        """연결 성공 테스트"""
        assert not adapter.is_connected

        success = await adapter.connect()

        assert success
        assert adapter.is_connected

    @pytest.mark.asyncio
    async def test_connect_no_token(self):
        """토큰 없이 연결 실패"""
        adapter = MockTelegramAdapter({"bot_token": ""})

        success = await adapter.connect()

        assert not success
        assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_disconnect(self, adapter):
        """연결 해제 테스트"""
        await adapter.connect()
        assert adapter.is_connected

        await adapter.disconnect()

        assert not adapter.is_connected
        assert not adapter._running

    @pytest.mark.asyncio
    async def test_channel_type(self, adapter):
        """채널 타입 확인"""
        assert adapter.channel_type == ChannelType.TELEGRAM

    @pytest.mark.asyncio
    async def test_listen_mock_messages(self, adapter):
        """Mock 메시지 수신 테스트"""
        # Mock 메시지 추가
        mock_msg = NormalizedMessage(
            id="msg_1",
            channel=ChannelType.TELEGRAM,
            channel_id="chat_123",
            sender_id="12345",
            sender_name="Test User",
            text="Hello from Telegram",
            timestamp=datetime.now(),
        )
        adapter.add_mock_message(mock_msg)

        await adapter.connect()

        # 메시지 수신
        messages = []
        count = 0
        async for message in adapter.listen():
            messages.append(message)
            count += 1
            if count >= 1:
                adapter._running = False  # 루프 종료

        assert len(messages) == 1
        assert messages[0].text == "Hello from Telegram"
        assert messages[0].sender_id == "12345"

    @pytest.mark.asyncio
    async def test_listen_injected_message(self, adapter):
        """실행 중 메시지 주입 테스트"""
        await adapter.connect()

        # 비동기로 메시지 주입
        async def inject():
            await asyncio.sleep(0.05)
            msg = NormalizedMessage(
                id="injected_1",
                channel=ChannelType.TELEGRAM,
                channel_id="chat_456",
                sender_id="67890",
                sender_name="Injected User",
                text="Injected message",
                timestamp=datetime.now(),
            )
            await adapter.inject_message(msg)
            await asyncio.sleep(0.05)
            adapter._running = False

        inject_task = asyncio.create_task(inject())

        messages = []
        async for message in adapter.listen():
            messages.append(message)

        await inject_task

        assert len(messages) == 1
        assert messages[0].text == "Injected message"

    @pytest.mark.asyncio
    async def test_send_confirmed(self, adapter):
        """확정 메시지 전송 테스트"""
        await adapter.connect()

        message = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            to="chat_123",
            text="Hello World",
            confirmed=True,
        )

        result = await adapter.send(message)

        assert result.success
        assert result.message_id is not None
        assert result.sent_at is not None
        assert len(adapter._sent_messages) == 1

    @pytest.mark.asyncio
    async def test_send_draft(self, adapter, tmp_path):
        """초안 저장 테스트"""
        adapter._draft_dir = tmp_path / "drafts"

        await adapter.connect()

        message = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            to="chat_123",
            text="Draft message",
            confirmed=False,
        )

        result = await adapter.send(message)

        assert result.success
        assert result.draft_path is not None
        assert "draft_chat_123" in result.draft_path

    @pytest.mark.asyncio
    async def test_send_not_connected(self, adapter):
        """연결 없이 전송 실패"""
        message = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            to="chat_123",
            text="Hello",
            confirmed=True,
        )

        result = await adapter.send(message)

        assert not result.success
        assert "Not connected" in result.error

    @pytest.mark.asyncio
    async def test_get_status_disconnected(self, adapter):
        """연결 해제 상태 조회"""
        status = await adapter.get_status()

        assert status["connected"] is False
        assert status["channel"] == "telegram"
        assert status["allowed_users_count"] == 2

    @pytest.mark.asyncio
    async def test_get_status_connected(self, adapter):
        """연결 상태 조회"""
        await adapter.connect()

        status = await adapter.get_status()

        assert status["connected"] is True
        assert status["channel"] == "telegram"
        assert status["bot_username"] == "@mock_bot"


class TestTelegramAdapterUserRestriction:
    """사용자 제한 기능 테스트"""

    def test_is_user_allowed_with_list(self):
        """허용 목록이 있는 경우"""
        config = {
            "bot_token": "test",
            "allowed_users": [12345, 67890],
        }
        adapter = MockTelegramAdapter(config)

        assert adapter._is_user_allowed(12345)
        assert adapter._is_user_allowed(67890)
        assert not adapter._is_user_allowed(99999)

    def test_is_user_allowed_empty_list(self):
        """허용 목록이 비어있는 경우 (모든 사용자 허용)"""
        config = {
            "bot_token": "test",
            "allowed_users": [],
        }
        adapter = MockTelegramAdapter(config)

        assert adapter._is_user_allowed(12345)
        assert adapter._is_user_allowed(99999)
        assert adapter._is_user_allowed(0)


class TestTelegramAdapterMessageConversion:
    """메시지 변환 테스트 (NormalizedMessage 생성)"""

    def test_normalized_message_creation(self):
        """NormalizedMessage 기본 생성"""
        msg = NormalizedMessage(
            id="12345",
            channel=ChannelType.TELEGRAM,
            channel_id="chat_100",
            sender_id="user_1",
            sender_name="John Doe",
            text="Test message",
            message_type=MessageType.TEXT,
            timestamp=datetime(2026, 2, 2, 12, 0, 0),
            is_group=False,
            is_mention=False,
        )

        assert msg.id == "12345"
        assert msg.channel == ChannelType.TELEGRAM
        assert msg.text == "Test message"
        assert msg.is_group is False

    def test_normalized_message_group(self):
        """그룹 메시지"""
        msg = NormalizedMessage(
            id="12346",
            channel=ChannelType.TELEGRAM,
            channel_id="group_200",
            sender_id="user_2",
            text="Group message",
            is_group=True,
        )

        assert msg.is_group is True

    def test_normalized_message_with_media(self):
        """미디어 포함 메시지"""
        msg = NormalizedMessage(
            id="12347",
            channel=ChannelType.TELEGRAM,
            channel_id="chat_100",
            sender_id="user_3",
            text="Photo caption",
            message_type=MessageType.IMAGE,
            media_urls=["file_id_abc123"],
        )

        assert msg.message_type == MessageType.IMAGE
        assert len(msg.media_urls) == 1

    def test_normalized_message_reply(self):
        """답장 메시지"""
        msg = NormalizedMessage(
            id="12348",
            channel=ChannelType.TELEGRAM,
            channel_id="chat_100",
            sender_id="user_4",
            text="Reply to previous",
            reply_to_id="12345",
        )

        assert msg.reply_to_id == "12345"

    def test_normalized_message_to_dict(self):
        """딕셔너리 변환"""
        msg = NormalizedMessage(
            id="12349",
            channel=ChannelType.TELEGRAM,
            channel_id="chat_100",
            sender_id="user_5",
            sender_name="Jane Doe",
            text="Dict test",
            timestamp=datetime(2026, 2, 2, 15, 30, 0),
        )

        data = msg.to_dict()

        assert data["id"] == "12349"
        assert data["channel"] == "telegram"
        assert data["sender_name"] == "Jane Doe"
        assert data["timestamp"] == "2026-02-02T15:30:00"


class TestOutboundMessage:
    """발신 메시지 테스트"""

    def test_outbound_message_creation(self):
        """OutboundMessage 기본 생성"""
        msg = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            to="chat_123",
            text="Hello World",
            confirmed=True,
        )

        assert msg.channel == ChannelType.TELEGRAM
        assert msg.to == "chat_123"
        assert msg.text == "Hello World"
        assert msg.confirmed is True

    def test_outbound_message_draft(self):
        """초안 메시지"""
        msg = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            to="chat_456",
            text="Draft content",
            confirmed=False,
        )

        assert msg.confirmed is False
        assert msg.sent_at is None

    def test_outbound_message_with_reply(self):
        """답장 메시지"""
        msg = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            to="chat_789",
            text="Reply text",
            reply_to="12345",
            confirmed=True,
        )

        assert msg.reply_to == "12345"

    def test_outbound_message_to_dict(self):
        """딕셔너리 변환"""
        msg = OutboundMessage(
            channel=ChannelType.TELEGRAM,
            to="chat_100",
            text="Dict test",
            confirmed=False,
        )

        data = msg.to_dict()

        assert data["channel"] == "telegram"
        assert data["to"] == "chat_100"
        assert data["text"] == "Dict test"
        assert data["confirmed"] is False


class TestSendResult:
    """전송 결과 테스트"""

    def test_send_result_success(self):
        """성공 결과"""
        from scripts.gateway.adapters.base import SendResult

        result = SendResult(
            success=True,
            message_id="msg_123",
            sent_at=datetime(2026, 2, 2, 16, 0, 0),
        )

        assert result.success
        assert result.message_id == "msg_123"
        assert result.error is None

    def test_send_result_failure(self):
        """실패 결과"""
        from scripts.gateway.adapters.base import SendResult

        result = SendResult(
            success=False,
            error="Connection timeout",
        )

        assert not result.success
        assert result.error == "Connection timeout"
        assert result.message_id is None

    def test_send_result_draft(self):
        """초안 저장 결과"""
        from scripts.gateway.adapters.base import SendResult

        result = SendResult(
            success=True,
            draft_path=r"C:\claude\secretary\output\drafts\telegram\draft_001.json",
        )

        assert result.success
        assert result.draft_path is not None
        assert result.message_id is None

    def test_send_result_to_dict(self):
        """딕셔너리 변환"""
        from scripts.gateway.adapters.base import SendResult

        result = SendResult(
            success=True,
            message_id="msg_456",
            sent_at=datetime(2026, 2, 2, 17, 0, 0),
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["message_id"] == "msg_456"
        assert data["sent_at"] == "2026-02-02T17:00:00"


class TestTelegramAdapterWithRealBot:
    """
    실제 Bot과의 통합 테스트 (수동 실행용)

    실행 방법:
    1. 환경변수 설정: TELEGRAM_BOT_TOKEN=your_token
    2. pytest tests/gateway/test_telegram_adapter.py -k "real" -v --run-integration
    """

    @pytest.fixture
    def real_config(self):
        """실제 설정 (환경변수에서 로드)"""
        import os
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            pytest.skip("TELEGRAM_BOT_TOKEN not set")
        return {
            "bot_token": token,
            "allowed_users": [],
        }

    @pytest.mark.skip(reason="수동 통합 테스트")
    @pytest.mark.asyncio
    async def test_real_connect(self, real_config):
        """실제 Bot 연결 테스트"""
        adapter = TelegramAdapter(real_config)

        success = await adapter.connect()

        assert success
        status = await adapter.get_status()
        print(f"Bot connected: {status}")

        await adapter.disconnect()
