"""
Gateway 모듈

통합 메시징 게이트웨이 (Phase 4)
- 메시지 정규화
- 통합 스토리지
- 액션 디스패처
- 채널 어댑터
- 메시지 파이프라인
- Gateway 서버
"""

from .storage import UnifiedStorage
from .models import (
    ChannelType,
    MessageType,
    Priority,
    MessagePriority,
    NormalizedMessage,
    OutboundMessage,
)
from .adapters import ChannelAdapter, SendResult, AdapterConfig
from .pipeline import MessagePipeline, PipelineResult
from .server import SecretaryGateway, load_config

__all__ = [
    # Storage
    "UnifiedStorage",
    # Models
    "ChannelType",
    "MessageType",
    "Priority",
    "MessagePriority",
    "NormalizedMessage",
    "OutboundMessage",
    # Adapters
    "ChannelAdapter",
    "SendResult",
    "AdapterConfig",
    # Pipeline
    "MessagePipeline",
    "PipelineResult",
    # Server
    "SecretaryGateway",
    "load_config",
]
