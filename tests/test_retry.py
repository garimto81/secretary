"""
retry_async 유틸리티 테스트
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.shared.retry import retry_async


class TestRetryAsync:
    """retry_async 테스트"""

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """첫 시도에 성공"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_async(func, max_retries=2, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        """실패 후 재시도 성공"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("not yet")
            return "ok"

        result = await retry_async(func, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_max_retries_exceeded(self):
        """최대 재시도 초과 시 예외 발생"""
        async def func():
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError, match="always fails"):
            await retry_async(func, max_retries=2, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_non_retryable_exception(self):
        """retryable이 아닌 예외는 즉시 발생"""
        call_count = 0

        async def func():
            nonlocal call_count
            call_count += 1
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            await retry_async(
                func,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
            )
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        """재시도 콜백 호출"""
        retries = []

        async def func():
            if len(retries) < 2:
                raise ValueError("retry me")
            return "done"

        def on_retry(exc, attempt):
            retries.append(attempt)

        result = await retry_async(
            func, max_retries=3, base_delay=0.01, on_retry=on_retry
        )
        assert result == "done"
        assert retries == [1, 2]

    @pytest.mark.asyncio
    async def test_zero_retries(self):
        """max_retries=0이면 재시도 없음"""
        async def func():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            await retry_async(func, max_retries=0, base_delay=0.01)

    @pytest.mark.asyncio
    async def test_args_kwargs_passed(self):
        """인자가 올바르게 전달됨"""
        async def func(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = await retry_async(func, "x", "y", c="z", max_retries=0)
        assert result == "x-y-z"
