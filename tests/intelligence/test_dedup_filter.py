"""
DedupFilter 테스트
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.response.dedup_filter import DedupFilter


class TestDedupFilter:
    """DedupFilter 테스트"""

    @pytest.fixture
    def mock_storage(self):
        """mock IntelligenceStorage"""
        storage = AsyncMock()
        storage.find_by_message_id = AsyncMock(return_value=None)
        return storage

    @pytest.fixture
    def dedup(self, mock_storage):
        return DedupFilter(mock_storage, max_cache=5)

    @pytest.mark.asyncio
    async def test_not_duplicate_new_message(self, dedup):
        """새 메시지는 중복 아님"""
        result = await dedup.is_duplicate("slack", "msg-001")
        assert result is False

    @pytest.mark.asyncio
    async def test_duplicate_after_mark(self, dedup):
        """마킹 후 중복 검출"""
        dedup.mark_processed("slack", "msg-001")
        result = await dedup.is_duplicate("slack", "msg-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_empty_message_id_not_duplicate(self, dedup):
        """빈 message_id는 항상 False"""
        result = await dedup.is_duplicate("slack", "")
        assert result is False

    @pytest.mark.asyncio
    async def test_db_fallback(self, mock_storage):
        """메모리 캐시 미스 시 DB fallback"""
        mock_storage.find_by_message_id = AsyncMock(return_value={"id": 1})
        dedup = DedupFilter(mock_storage, max_cache=5)

        result = await dedup.is_duplicate("slack", "msg-002")
        assert result is True
        mock_storage.find_by_message_id.assert_called_once_with("slack", "msg-002")

    @pytest.mark.asyncio
    async def test_lru_eviction(self, dedup):
        """LRU 캐시 초과 시 가장 오래된 항목 제거"""
        for i in range(7):
            dedup.mark_processed("slack", f"msg-{i:03d}")

        # max_cache=5이므로 0, 1은 제거됨
        assert dedup.cache_size() == 5
        result = await dedup.is_duplicate("slack", "msg-000")
        assert result is False  # 캐시에서 제거됨

        result = await dedup.is_duplicate("slack", "msg-006")
        assert result is True  # 최신은 남아있음

    def test_cache_size(self, dedup):
        """cache_size 반환값"""
        assert dedup.cache_size() == 0
        dedup.mark_processed("slack", "msg-1")
        assert dedup.cache_size() == 1

    def test_clear_cache(self, dedup):
        """캐시 초기화"""
        dedup.mark_processed("slack", "msg-1")
        dedup.mark_processed("slack", "msg-2")
        assert dedup.cache_size() == 2
        dedup.clear_cache()
        assert dedup.cache_size() == 0
