"""
Knowledge Module - 프로젝트별 지식 저장소

Phase 1: SQLite FTS5 전문검색
Phase 3 (조건부): ChromaDB Vector DB
"""

from .models import KnowledgeDocument, SearchResult, ChannelProfile
from .store import KnowledgeStore
from .bootstrap import KnowledgeBootstrap, BootstrapResult
from .channel_profile import ChannelProfileStore

__all__ = [
    "KnowledgeDocument",
    "SearchResult",
    "ChannelProfile",
    "KnowledgeStore",
    "KnowledgeBootstrap",
    "BootstrapResult",
    "ChannelProfileStore",
]
