"""
Channel Adapter Base Interface 테스트
"""

import pytest
from datetime import datetime
from scripts.gateway.models import (
    ChannelType,
    MessageType,
    MessagePriority,
    NormalizedMessage,
    OutboundMessage,
)
from scripts.gateway.adapters import ChannelAdapter, SendResult, AdapterConfig


# NormalizedMessage 필드 매핑 (기존 구조 유지)
def create_normalized_message(**kwargs):
    """NormalizedMessage 생성 헬퍼"""
    return NormalizedMessage(
        id=kwargs.get("message_id", "test-123"),
        channel=kwargs.get("channel", ChannelType.EMAIL),
        channel_id=kwargs.get("thread_id", "channel-1"),
        sender_id=kwargs.get("sender_id", "user@example.com"),
        sender_name=kwargs.get("sender_name", "Test User"),
        text=kwargs.get("content", "Test message"),
        timestamp=kwargs.get("timestamp", datetime.now()),
    )


class MockAdapter(ChannelAdapter):
    """테스트용 목 어댑터"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.channel_type = ChannelType.EMAIL

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def listen(self):
        """단순 테스트용 메시지 생성"""
        message = create_normalized_message()
        yield message

    async def send(self, message: OutboundMessage) -> SendResult:
        # OutboundMessage의 필드: channel, to, text, confirmed 등
        if message.confirmed:
            return SendResult(
                success=True,
                message_id="sent-123",
                sent_at=datetime.now(),
            )
        else:
            return SendResult(
                success=True,
                draft_path="C:\\claude\\secretary\\output\\drafts\\draft-123.txt",
            )

    async def get_status(self) -> dict:
        return {
            "connected": self._connected,
            "channel": self.channel_type.value,
        }


@pytest.mark.asyncio
async def test_adapter_connect():
    """어댑터 연결 테스트"""
    adapter = MockAdapter({"enabled": True})
    assert not adapter.is_connected

    success = await adapter.connect()
    assert success
    assert adapter.is_connected


@pytest.mark.asyncio
async def test_adapter_disconnect():
    """어댑터 연결 해제 테스트"""
    adapter = MockAdapter({"enabled": True})
    await adapter.connect()
    assert adapter.is_connected

    await adapter.disconnect()
    assert not adapter.is_connected


@pytest.mark.asyncio
async def test_adapter_listen():
    """메시지 수신 테스트"""
    adapter = MockAdapter({"enabled": True})
    await adapter.connect()

    messages = []
    async for message in adapter.listen():
        messages.append(message)
        break  # 첫 메시지만 받고 종료

    assert len(messages) == 1
    assert messages[0].sender_id == "user@example.com"
    assert messages[0].text == "Test message"


@pytest.mark.asyncio
async def test_adapter_send_confirmed():
    """확정 메시지 전송 테스트"""
    adapter = MockAdapter({"enabled": True})
    await adapter.connect()

    message = OutboundMessage(
        channel=ChannelType.EMAIL,
        to="recipient@example.com",
        text="Hello World",
        confirmed=True,
    )

    result = await adapter.send(message)
    assert result.success
    assert result.message_id == "sent-123"
    assert result.sent_at is not None
    assert result.draft_path is None


@pytest.mark.asyncio
async def test_adapter_send_draft():
    """초안 생성 테스트"""
    adapter = MockAdapter({"enabled": True})
    await adapter.connect()

    message = OutboundMessage(
        channel=ChannelType.EMAIL,
        to="recipient@example.com",
        text="Hello World",
        confirmed=False,
    )

    result = await adapter.send(message)
    assert result.success
    assert result.message_id is None
    assert result.draft_path is not None
    assert "draft-123.txt" in result.draft_path


@pytest.mark.asyncio
async def test_adapter_get_status():
    """어댑터 상태 조회 테스트"""
    adapter = MockAdapter({"enabled": True})

    status = await adapter.get_status()
    assert status["connected"] is False

    await adapter.connect()
    status = await adapter.get_status()
    assert status["connected"] is True
    assert status["channel"] == "email"


def test_send_result_to_dict():
    """SendResult 딕셔너리 변환 테스트"""
    result = SendResult(
        success=True,
        message_id="test-123",
        sent_at=datetime(2026, 2, 2, 12, 0, 0),
    )

    data = result.to_dict()
    assert data["success"] is True
    assert data["message_id"] == "test-123"
    assert data["sent_at"] == "2026-02-02T12:00:00"


def test_adapter_config():
    """AdapterConfig 테스트"""
    config = AdapterConfig(enabled=True, name="EmailAdapter")
    assert config.enabled is True
    assert config.name == "EmailAdapter"

    config_default = AdapterConfig()
    assert config_default.enabled is True
    assert config_default.name == ""
