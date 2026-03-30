"""
Channel Adapters

각 메시징 채널(Slack, Gmail 등)의 어댑터 구현.
"""

from .base import AdapterConfig, ChannelAdapter, SendResult
from .gmail import GmailAdapter
from .slack import SlackAdapter

__all__ = [
    "ChannelAdapter",
    "SendResult",
    "AdapterConfig",
    "SlackAdapter",
    "GmailAdapter",
]
