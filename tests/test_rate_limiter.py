"""
RateLimiter 테스트
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.shared.rate_limiter import RateLimiter


class TestRateLimiter:
    """RateLimiter 테스트"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """각 테스트 전 싱글톤 리셋"""
        RateLimiter.reset()
        yield
        RateLimiter.reset()

    def test_singleton(self):
        """싱글톤 패턴"""
        a = RateLimiter.get_instance()
        b = RateLimiter.get_instance()
        assert a is b

    def test_unlimited_by_default(self):
        """미설정 bucket은 무제한"""
        limiter = RateLimiter()
        assert limiter.check("unknown") is True

    def test_within_limit(self):
        """limit 이내 허용"""
        limiter = RateLimiter()
        limiter.configure("test", max_per_minute=5)

        for _ in range(5):
            assert limiter.check("test") is True

    def test_exceeds_limit(self):
        """limit 초과 거부"""
        limiter = RateLimiter()
        limiter.configure("test", max_per_minute=3)

        for _ in range(3):
            assert limiter.check("test") is True

        assert limiter.check("test") is False

    def test_get_remaining(self):
        """남은 횟수 조회"""
        limiter = RateLimiter()
        limiter.configure("test", max_per_minute=5)

        limiter.check("test")
        limiter.check("test")
        assert limiter.get_remaining("test") == 3

    def test_get_remaining_unknown(self):
        """미설정 bucket은 -1"""
        limiter = RateLimiter()
        assert limiter.get_remaining("unknown") == -1

    def test_multiple_buckets(self):
        """독립적인 bucket 관리"""
        limiter = RateLimiter()
        limiter.configure("a", max_per_minute=2)
        limiter.configure("b", max_per_minute=3)

        limiter.check("a")
        limiter.check("a")
        assert limiter.check("a") is False
        assert limiter.check("b") is True  # b는 독립적

    def test_get_stats(self):
        """통계 조회"""
        limiter = RateLimiter()
        limiter.configure("test", max_per_minute=5)
        limiter.check("test")
        limiter.check("test")

        stats = limiter.get_stats()
        assert "test" in stats
        assert stats["test"]["limit"] == 5
        assert stats["test"]["used"] == 2
        assert stats["test"]["remaining"] == 3

    @pytest.mark.asyncio
    async def test_wait_if_needed(self):
        """대기 없이 통과"""
        limiter = RateLimiter()
        limiter.configure("test", max_per_minute=10)

        # 제한 내이므로 즉시 통과
        await limiter.wait_if_needed("test")

    def test_reset(self):
        """싱글톤 리셋"""
        a = RateLimiter.get_instance()
        a.configure("test", max_per_minute=1)
        RateLimiter.reset()
        b = RateLimiter.get_instance()
        assert a is not b
