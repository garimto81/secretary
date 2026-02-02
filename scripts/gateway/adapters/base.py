"""
Channel Adapter Base Interface

모든 메시징 채널 어댑터가 구현해야 하는 추상 인터페이스.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional
from datetime import datetime

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.models import NormalizedMessage, OutboundMessage, ChannelType
except ImportError:
    try:
        from gateway.models import NormalizedMessage, OutboundMessage, ChannelType
    except ImportError:
        from ..models import NormalizedMessage, OutboundMessage, ChannelType


@dataclass
class SendResult:
    """
    메시지 전송 결과

    Attributes:
        success: 전송 성공 여부
        message_id: 전송된 메시지 ID (성공 시)
        error: 에러 메시지 (실패 시)
        sent_at: 전송 시각
        draft_path: 초안 저장 경로 (confirmed=False 시)
    """
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    sent_at: Optional[datetime] = None
    draft_path: Optional[str] = None

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "success": self.success,
            "message_id": self.message_id,
            "error": self.error,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "draft_path": self.draft_path,
        }


@dataclass
class AdapterConfig:
    """
    어댑터 설정

    Attributes:
        enabled: 어댑터 활성화 여부
        name: 어댑터 이름
    """
    enabled: bool = True
    name: str = ""


class ChannelAdapter(ABC):
    """
    채널 어댑터 추상 인터페이스

    모든 메시징 채널 어댑터는 이 인터페이스를 구현해야 함.

    Example:
        >>> class EmailAdapter(ChannelAdapter):
        ...     def __init__(self, config: dict):
        ...         super().__init__(config)
        ...         self.channel_type = ChannelType.EMAIL
        ...
        ...     async def connect(self) -> bool:
        ...         self._connected = True
        ...         return True
    """

    def __init__(self, config: dict):
        """
        어댑터 초기화

        Args:
            config: 어댑터 설정 딕셔너리
        """
        self.config = config
        self.channel_type: Optional[ChannelType] = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._connected

    @abstractmethod
    async def connect(self) -> bool:
        """
        채널 연결

        Returns:
            연결 성공 여부

        Example:
            >>> adapter = EmailAdapter(config)
            >>> success = await adapter.connect()
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """
        채널 연결 해제

        Example:
            >>> await adapter.disconnect()
        """
        pass

    @abstractmethod
    async def listen(self) -> AsyncIterator[NormalizedMessage]:
        """
        메시지 수신 (비동기 제너레이터)

        Yields:
            NormalizedMessage: 정규화된 메시지

        Example:
            >>> async for message in adapter.listen():
            ...     print(message.content)
        """
        pass

    @abstractmethod
    async def send(self, message: OutboundMessage) -> SendResult:
        """
        메시지 전송

        confirmed=True일 때만 실제 전송, False면 초안만 생성.

        Args:
            message: 발신 메시지

        Returns:
            SendResult: 전송 결과

        Example:
            >>> message = OutboundMessage(
            ...     channel=ChannelType.EMAIL,
            ...     recipient_id="user@example.com",
            ...     content="Hello",
            ...     confirmed=True
            ... )
            >>> result = await adapter.send(message)
        """
        pass

    @abstractmethod
    async def get_status(self) -> dict:
        """
        어댑터 상태 반환

        Returns:
            상태 딕셔너리

        Example:
            >>> status = await adapter.get_status()
            >>> print(status["connected"])
        """
        pass
