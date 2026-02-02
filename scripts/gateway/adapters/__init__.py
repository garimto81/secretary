"""
Channel Adapters

각 메시징 채널(Email, Slack, Kakao 등)의 어댑터 구현.
"""

from .base import ChannelAdapter, SendResult, AdapterConfig
from .telegram import TelegramAdapter, MockTelegramAdapter

__all__ = [
    "ChannelAdapter",
    "SendResult",
    "AdapterConfig",
    "TelegramAdapter",
    "MockTelegramAdapter",
]
