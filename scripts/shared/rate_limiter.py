"""
Rate Limiter - 이름 기반 bucket 전역 rate limit

Pipeline, Ollama, Claude 등 각 서비스별 rate limit 관리.
"""

import asyncio
import time
from collections import deque
from typing import Optional


class RateLimiter:
    """이름 기반 bucket rate limiter"""

    _instance: Optional["RateLimiter"] = None

    def __init__(self):
        self._buckets: dict[str, deque] = {}
        self._limits: dict[str, int] = {}

    @classmethod
    def get_instance(cls) -> "RateLimiter":
        """싱글톤 인스턴스"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """싱글톤 초기화 (테스트용)"""
        cls._instance = None

    def configure(self, name: str, max_per_minute: int) -> None:
        """bucket 설정"""
        self._limits[name] = max_per_minute
        if name not in self._buckets:
            self._buckets[name] = deque(maxlen=max_per_minute)

    def check(self, name: str) -> bool:
        """
        rate limit 체크 (비차단)

        Returns:
            True이면 허용, False이면 제한
        """
        if name not in self._limits:
            return True

        now = time.time()
        bucket = self._buckets.get(name, deque())
        limit = self._limits[name]

        # 1분 이내 기록만 유지
        while bucket and (now - bucket[0]) > 60:
            bucket.popleft()

        if len(bucket) >= limit:
            return False

        bucket.append(now)
        self._buckets[name] = bucket
        return True

    async def wait_if_needed(self, name: str) -> None:
        """
        rate limit 초과 시 대기 (차단)

        가장 오래된 요청이 1분 경과할 때까지 대기합니다.
        """
        if name not in self._limits:
            return

        now = time.time()
        bucket = self._buckets.get(name, deque())
        limit = self._limits[name]

        # 1분 이내 기록만 유지
        while bucket and (now - bucket[0]) > 60:
            bucket.popleft()

        if len(bucket) >= limit:
            oldest = bucket[0]
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            # 대기 후 다시 정리
            now = time.time()
            while bucket and (now - bucket[0]) > 60:
                bucket.popleft()

        bucket.append(now)
        self._buckets[name] = bucket

    def get_remaining(self, name: str) -> int:
        """남은 허용 횟수"""
        if name not in self._limits:
            return -1  # 무제한

        now = time.time()
        bucket = self._buckets.get(name, deque())

        # 1분 이내 기록만 카운트
        recent = sum(1 for t in bucket if (now - t) <= 60)
        return max(0, self._limits[name] - recent)

    def get_stats(self) -> dict[str, dict]:
        """전체 bucket 통계"""
        now = time.time()
        stats = {}
        for name, bucket in self._buckets.items():
            recent = sum(1 for t in bucket if (now - t) <= 60)
            stats[name] = {
                "limit": self._limits.get(name, -1),
                "used": recent,
                "remaining": max(0, self._limits.get(name, 0) - recent),
            }
        return stats
