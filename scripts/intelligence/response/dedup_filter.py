"""
DedupFilter - 중복 메시지 처리 방지

메모리 캐시(LRU) + DB fallback으로 중복 체크.
handler.py에서 추출된 독립 모듈.
"""

from collections import OrderedDict

# handler.py와 같은 import 패턴
try:
    from scripts.intelligence.context_store import IntelligenceStorage
except ImportError:
    try:
        from intelligence.context_store import IntelligenceStorage
    except ImportError:
        from ..context_store import IntelligenceStorage


class DedupFilter:
    """중복 메시지 처리 방지"""

    def __init__(self, storage: IntelligenceStorage, max_cache: int = 1000):
        self.storage = storage
        self._recent_ids: OrderedDict = OrderedDict()
        self._max_cache = max_cache

    async def is_duplicate(self, source_channel: str, source_message_id: str) -> bool:
        """
        중복 메시지인지 확인

        1차: 메모리 캐시 체크 (빠름)
        2차: DB 체크 (느림)
        """
        if not source_message_id:
            return False

        key = f"{source_channel}:{source_message_id}"

        # 메모리 캐시 체크
        if key in self._recent_ids:
            return True

        # DB 체크
        existing = await self.storage.find_by_message_id(source_channel, source_message_id)
        if existing:
            self._recent_ids[key] = True
            return True

        return False

    def mark_processed(self, source_channel: str, source_message_id: str):
        """처리 완료 마킹 (메모리 캐시에만)"""
        key = f"{source_channel}:{source_message_id}"
        self._recent_ids[key] = True

        # 캐시 크기 제한 (LRU: 가장 오래된 항목부터 제거)
        while len(self._recent_ids) > self._max_cache:
            self._recent_ids.popitem(last=False)

    def cache_size(self) -> int:
        """현재 캐시 크기"""
        return len(self._recent_ids)

    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._recent_ids.clear()
