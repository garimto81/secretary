"""
Retry 유틸리티 - Exponential Backoff

LLM 호출 등 외부 서비스 호출에 사용하는 재시도 래퍼.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_async(
    func: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = 2,
    base_delay: float = 2.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
    **kwargs,
) -> T:
    """
    비동기 함수 재시도 래퍼 (exponential backoff)

    Args:
        func: 재시도할 비동기 함수
        *args: 함수 인자
        max_retries: 최대 재시도 횟수 (0이면 재시도 없음)
        base_delay: 첫 재시도 대기 시간 (초)
        backoff_factor: 대기 시간 배수
        retryable_exceptions: 재시도할 예외 타입
        on_retry: 재시도 시 호출할 콜백 (exception, attempt)
        **kwargs: 함수 키워드 인자

    Returns:
        함수 반환값

    Raises:
        마지막 시도에서 발생한 예외
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e

            if attempt >= max_retries:
                logger.error(
                    f"retry_async: 최종 실패 (attempt {attempt + 1}/{max_retries + 1}): {e}"
                )
                raise

            delay = base_delay * (backoff_factor ** attempt)
            logger.warning(
                f"retry_async: attempt {attempt + 1} 실패, "
                f"{delay:.1f}초 후 재시도: {e}"
            )

            if on_retry:
                on_retry(e, attempt + 1)

            await asyncio.sleep(delay)

    raise last_exception  # type: ignore
