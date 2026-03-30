"""
Knowledge Module - 프로젝트별 지식 저장소

Phase 1: SQLite FTS5 전문검색
Phase 3 (조건부): ChromaDB Vector DB
"""

from .bootstrap import BootstrapResult, KnowledgeBootstrap
from .channel_profile import ChannelProfileStore
from .models import ChannelProfile, KnowledgeDocument, SearchResult
from .store import KnowledgeStore

__all__ = [
    "KnowledgeDocument",
    "SearchResult",
    "ChannelProfile",
    "KnowledgeStore",
    "KnowledgeBootstrap",
    "BootstrapResult",
    "ChannelProfileStore",
]
