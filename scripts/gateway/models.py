"""
Gateway 데이터 모델 - Phase 4

멀티 채널 메시징을 위한 통합 데이터 모델 정의.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class ChannelType(Enum):
    """메시징 채널 종류"""
    EMAIL = "email"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    DISCORD = "discord"
    SLACK = "slack"
    KAKAO = "kakao"
    SMS = "sms"
    UNKNOWN = "unknown"


class MessageType(Enum):
    """메시지 종류"""
    TEXT = "text"
    HTML = "html"
    MARKDOWN = "markdown"
    IMAGE = "image"
    FILE = "file"
    VOICE = "voice"
    LOCATION = "location"
    RICH = "rich"


class Priority(Enum):
    """메시지 우선순위"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


# Alias for backward compatibility
MessagePriority = Priority


@dataclass
class NormalizedMessage:
    """
    통합 메시지 모델 - 모든 채널의 메시지를 정규화

    Attributes:
        id: 플랫폼별 고유 메시지 ID
        channel: 메시징 채널 종류
        channel_id: 플랫폼별 채팅방 ID
        sender_id: 발신자 고유 ID
        sender_name: 발신자 이름 (선택)
        text: 메시지 텍스트 내용
        message_type: 메시지 종류 (텍스트/이미지/파일/음성/위치)
        timestamp: 메시지 수신 시각
        is_group: 그룹 채팅 여부
        is_mention: 멘션 포함 여부
        reply_to_id: 답장 대상 메시지 ID
        media_urls: 첨부 미디어 URL 목록
        raw_json: 원본 JSON 데이터 (디버깅용)
        priority: 우선순위 (분석 결과)
        has_action: 액션 필요 여부 (분석 결과)
    """
    id: str
    channel: ChannelType
    channel_id: str
    sender_id: str
    sender_name: Optional[str] = None
    text: str = ""
    message_type: MessageType = MessageType.TEXT
    timestamp: datetime = field(default_factory=datetime.now)
    is_group: bool = False
    is_mention: bool = False
    reply_to_id: Optional[str] = None
    media_urls: List[str] = field(default_factory=list)
    raw_json: Optional[str] = None
    priority: Optional[Priority] = None
    has_action: bool = False

    def __post_init__(self):
        """유효성 검사 및 타입 변환"""
        # Enum 변환 (문자열로 전달된 경우)
        if isinstance(self.channel, str):
            self.channel = ChannelType(self.channel)
        if isinstance(self.message_type, str):
            self.message_type = MessageType(self.message_type)
        if self.priority is not None and isinstance(self.priority, str):
            self.priority = Priority(self.priority)

        # 타임스탬프 변환 (문자열로 전달된 경우)
        if isinstance(self.timestamp, str):
            self.timestamp = datetime.fromisoformat(self.timestamp)

    def to_dict(self) -> dict:
        """딕셔너리 직렬화"""
        return {
            "id": self.id,
            "channel": self.channel.value,
            "channel_id": self.channel_id,
            "sender_id": self.sender_id,
            "sender_name": self.sender_name,
            "text": self.text,
            "message_type": self.message_type.value,
            "timestamp": self.timestamp.isoformat(),
            "is_group": self.is_group,
            "is_mention": self.is_mention,
            "reply_to_id": self.reply_to_id,
            "media_urls": self.media_urls,
            "raw_json": self.raw_json,
            "priority": self.priority.value if self.priority else None,
            "has_action": self.has_action,
        }


@dataclass
class OutboundMessage:
    """
    전송용 메시지 - 응답 초안

    Attributes:
        channel: 전송 채널
        to: 수신자 ID 또는 채팅방 ID
        text: 메시지 텍스트 내용
        draft_file: 초안 저장 파일 경로 (선택)
        confirmed: 전송 확인 여부
        sent_at: 실제 전송 시각
        reply_to: 답장 대상 메시지 ID
    """
    channel: ChannelType
    to: str
    text: str
    draft_file: Optional[str] = None
    confirmed: bool = False
    sent_at: Optional[datetime] = None
    reply_to: Optional[str] = None

    def __post_init__(self):
        """유효성 검사 및 타입 변환"""
        # Enum 변환 (문자열로 전달된 경우)
        if isinstance(self.channel, str):
            self.channel = ChannelType(self.channel)

        # 타임스탬프 변환 (문자열로 전달된 경우)
        if self.sent_at is not None and isinstance(self.sent_at, str):
            self.sent_at = datetime.fromisoformat(self.sent_at)

    def to_dict(self) -> dict:
        """딕셔너리 직렬화"""
        return {
            "channel": self.channel.value,
            "to": self.to,
            "text": self.text,
            "draft_file": self.draft_file,
            "confirmed": self.confirmed,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "reply_to": self.reply_to,
        }

    def mark_sent(self):
        """전송 완료 표시"""
        self.confirmed = True
        self.sent_at = datetime.now()
