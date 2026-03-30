"""Knowledge Store 데이터 모델"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class KnowledgeDocument:
    """Knowledge Store 문서"""
    id: str                          # "{source}:{source_id}"
    project_id: str
    source: str                      # "gmail", "slack"
    source_id: str
    content: str
    sender_name: str = ""
    sender_id: str = ""
    subject: str = ""                # 이메일 제목 (Slack은 "")
    thread_id: str = ""
    content_type: str = "message"    # "message", "email", "thread_summary"
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass
class SearchResult:
    """FTS5 검색 결과"""
    document: KnowledgeDocument
    score: float                     # FTS5 rank score
    snippet: str = ""                # 매칭 하이라이트


@dataclass
class ChannelProfile:
    """Slack 채널 전문가 프로파일"""
    channel_id: str
    channel_name: str
    topic: str = ""
    purpose: str = ""
    created: datetime | None = None
    members: list = field(default_factory=list)
    pinned_messages: list = field(default_factory=list)
    collected_at: datetime | None = None
    total_messages: int = 0
    total_threads: int = 0
