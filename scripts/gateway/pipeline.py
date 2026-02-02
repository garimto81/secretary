"""
MessagePipeline - 메시지 처리 파이프라인

메시지 분석 및 액션 디스패치를 담당합니다.

Stages:
1. Priority Analysis (긴급 키워드 감지)
2. Action Detection (할일, 마감일 감지)
3. Storage (DB 저장)
4. Notification (Toast 알림)
5. Action Dispatch (TODO 생성 등)
"""

import re
import sys
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any, Awaitable

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.models import NormalizedMessage, Priority
    from scripts.gateway.storage import UnifiedStorage
except ImportError:
    try:
        from gateway.models import NormalizedMessage, Priority
        from gateway.storage import UnifiedStorage
    except ImportError:
        from .models import NormalizedMessage, Priority
        from .storage import UnifiedStorage


# 기본 설정
DEFAULT_CONFIG = {
    "urgent_keywords": ["긴급", "urgent", "ASAP", "지금", "바로", "즉시", "빨리", "급함"],
    "action_keywords": ["해주세요", "부탁", "요청", "확인", "검토", "답변", "회신", "처리"],
    "deadline_patterns": [
        r"(\d{1,2})[/.](\d{1,2})\s*까지",  # 2/10 까지, 2.10까지
        r"(\d{1,2})일\s*까지",  # 10일 까지
        r"오늘\s*(중|까지|내)",  # 오늘 중, 오늘까지
        r"내일\s*(까지|중)",  # 내일까지, 내일 중
        r"이번\s*주\s*(내|까지)",  # 이번 주 내
    ],
    "toast_enabled": True,
    "rate_limit_per_minute": 10,
}


@dataclass
class PipelineResult:
    """파이프라인 처리 결과"""
    message_id: str
    priority: Optional[str] = None
    has_action: bool = False
    actions: List[str] = field(default_factory=list)
    error: Optional[str] = None
    processed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "message_id": self.message_id,
            "priority": self.priority,
            "has_action": self.has_action,
            "actions": self.actions,
            "error": self.error,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }


# Handler 타입 정의
PipelineHandler = Callable[[NormalizedMessage, 'PipelineResult'], Awaitable[None]]


class MessagePipeline:
    """
    메시지 처리 파이프라인

    Stages:
    1. Priority Analysis (긴급 키워드 감지)
    2. Action Detection (할일, 마감일 감지)
    3. Storage (DB 저장)
    4. Notification (Toast 알림)
    5. Action Dispatch (TODO 생성 등)

    Example:
        async with UnifiedStorage() as storage:
            pipeline = MessagePipeline(storage)
            result = await pipeline.process(message)
    """

    def __init__(self, storage: UnifiedStorage, config: Optional[Dict[str, Any]] = None):
        """
        파이프라인 초기화

        Args:
            storage: 통합 스토리지 인스턴스
            config: 설정 딕셔너리 (None이면 기본값 사용)
        """
        self.storage = storage
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.handlers: List[PipelineHandler] = []
        self._rate_limit_times: List[datetime] = []

        # 정규식 컴파일
        self._deadline_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config["deadline_patterns"]
        ]

    def add_handler(self, handler: PipelineHandler) -> None:
        """
        커스텀 핸들러 추가

        Args:
            handler: 비동기 핸들러 함수 (message, result) -> None
        """
        self.handlers.append(handler)

    async def process(self, message: NormalizedMessage) -> PipelineResult:
        """
        메시지 처리

        Args:
            message: 처리할 메시지

        Returns:
            처리 결과
        """
        result = PipelineResult(message_id=message.id)

        try:
            # Stage 1: Priority Analysis
            priority = self._analyze_priority(message)
            if priority:
                result.priority = priority
                message.priority = Priority(priority)

            # Stage 2: Action Detection
            actions = self._detect_actions(message)
            if actions:
                result.has_action = True
                result.actions = actions
                message.has_action = True

            # Stage 3: Storage (DB 저장)
            await self._save_to_storage(message)

            # Stage 4: Notification (Toast 알림)
            if result.priority == "urgent" or result.priority == "high":
                await self._send_notification(message, result)

            # Stage 5: Action Dispatch (TODO 생성 등)
            if result.has_action:
                await self._dispatch_actions(message, result)

            # Stage 6: Custom Handlers
            for handler in self.handlers:
                await handler(message, result)

            result.processed_at = datetime.now()

        except Exception as e:
            result.error = str(e)

        return result

    def _analyze_priority(self, message: NormalizedMessage) -> Optional[str]:
        """
        우선순위 분석

        Args:
            message: 분석할 메시지

        Returns:
            우선순위 문자열 ('urgent', 'high', 'normal', 'low') 또는 None
        """
        text = message.text or ""
        text_lower = text.lower()

        # 긴급 키워드 체크
        urgent_keywords = self.config["urgent_keywords"]
        for keyword in urgent_keywords:
            if keyword.lower() in text_lower:
                return "urgent"

        # 멘션인 경우 높은 우선순위
        if message.is_mention:
            return "high"

        # 마감일 감지
        for pattern in self._deadline_patterns:
            if pattern.search(text):
                return "high"

        return "normal"

    def _detect_actions(self, message: NormalizedMessage) -> List[str]:
        """
        액션 감지

        Args:
            message: 분석할 메시지

        Returns:
            감지된 액션 목록
        """
        text = message.text or ""
        text_lower = text.lower()
        actions = []

        # 액션 키워드 체크
        action_keywords = self.config["action_keywords"]
        for keyword in action_keywords:
            if keyword.lower() in text_lower:
                actions.append(f"action_request:{keyword}")
                break

        # 마감일 감지
        for pattern in self._deadline_patterns:
            match = pattern.search(text)
            if match:
                actions.append(f"deadline:{match.group(0)}")
                break

        # 질문 패턴 감지
        if "?" in text or "어떻게" in text or "언제" in text or "왜" in text:
            actions.append("question")

        return actions

    async def _save_to_storage(self, message: NormalizedMessage) -> None:
        """
        스토리지에 메시지 저장

        Args:
            message: 저장할 메시지 (models.NormalizedMessage)

        Note:
            storage.py가 models.NormalizedMessage를 직접 지원하므로 변환이 필요 없음.
        """
        await self.storage.save_message(message)

    async def _send_notification(self, message: NormalizedMessage, result: PipelineResult) -> None:
        """
        Toast 알림 전송

        Args:
            message: 알림 대상 메시지
            result: 파이프라인 결과
        """
        if not self.config.get("toast_enabled", True):
            return

        # Rate limiting 체크
        if not self._check_rate_limit():
            return

        try:
            # toast_notifier를 subprocess로 실행
            sender = message.sender_name or message.sender_id
            title = f"[{message.channel.value.upper()}] {sender}"
            body = message.text[:100] if message.text else ""

            if result.priority == "urgent":
                title = f"[긴급] {title}"

            # Windows에서 toast 전송
            if sys.platform == "win32":
                try:
                    from winotify import Notification, audio

                    toast = Notification(
                        app_id="Secretary AI",
                        title=title,
                        msg=body,
                        duration="short",
                    )
                    toast.set_audio(audio.Default, loop=False)
                    toast.show()
                except ImportError:
                    # winotify 미설치 시 무시
                    pass

        except Exception:
            # 알림 실패는 무시
            pass

    async def _dispatch_actions(self, message: NormalizedMessage, result: PipelineResult) -> None:
        """
        액션 디스패치

        Args:
            message: 메시지
            result: 파이프라인 결과
        """
        # 현재는 액션 기록만 수행
        # 추후 TODO 생성, Calendar 일정 생성 등 확장 가능

        # TODO 생성이 필요한 경우 로그만 남김
        for action in result.actions:
            if action.startswith("deadline:") or action.startswith("action_request:"):
                # TODO: todo_generator 연동
                pass

    def _check_rate_limit(self) -> bool:
        """
        Rate limit 체크

        Returns:
            전송 가능 여부
        """
        now = datetime.now()
        limit = self.config.get("rate_limit_per_minute", 10)

        # 1분 이내 기록만 유지
        self._rate_limit_times = [
            t for t in self._rate_limit_times
            if (now - t).total_seconds() < 60
        ]

        if len(self._rate_limit_times) >= limit:
            return False

        self._rate_limit_times.append(now)
        return True

    def get_stats(self) -> Dict[str, Any]:
        """
        파이프라인 통계 조회

        Returns:
            통계 딕셔너리
        """
        return {
            "handlers_count": len(self.handlers),
            "rate_limit_current": len(self._rate_limit_times),
            "rate_limit_max": self.config.get("rate_limit_per_minute", 10),
            "toast_enabled": self.config.get("toast_enabled", True),
        }
