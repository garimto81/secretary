"""
MessagePipeline - 메시지 처리 파이프라인

메시지 분석 및 액션 디스패치를 담당합니다.

Stages:
0.5. Project Context Resolution (프로젝트 해석)
1. Priority Analysis (긴급 키워드 감지, 프로젝트별)
2. Action Detection (할일, 마감일 감지, 프로젝트별)
3. Storage (DB 저장, project_id 포함)
4. Action Dispatch (TODO 생성 등)
"""

import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# 상대/절대 import 모두 지원
try:
    from scripts.gateway.models import EnrichedMessage, NormalizedMessage, Priority
    from scripts.gateway.project_context import ProjectContext, ProjectContextResolver
    from scripts.gateway.storage import UnifiedStorage
except ImportError:
    try:
        from gateway.models import EnrichedMessage, NormalizedMessage, Priority
        from gateway.project_context import ProjectContext, ProjectContextResolver
        from gateway.storage import UnifiedStorage
    except ImportError:
        from .models import EnrichedMessage, NormalizedMessage, Priority
        from .project_context import ProjectContext, ProjectContextResolver
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
    "rate_limit_per_minute": 10,
}


@dataclass
class PipelineResult:
    """파이프라인 처리 결과"""
    message_id: str
    project_id: str | None = None
    priority: str | None = None
    has_action: bool = False
    actions: list[str] = field(default_factory=list)
    error: str | None = None
    processed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "message_id": self.message_id,
            "project_id": self.project_id,
            "priority": self.priority,
            "has_action": self.has_action,
            "actions": self.actions,
            "error": self.error,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }


# Handler 타입 정의 (EnrichedMessage + PipelineResult)
PipelineHandler = Callable[['EnrichedMessage', 'PipelineResult'], Awaitable[None]]


class MessagePipeline:
    """
    메시지 처리 파이프라인

    Stages:
    1. Priority Analysis (긴급 키워드 감지)
    2. Action Detection (할일, 마감일 감지)
    3. Storage (DB 저장)
    4. Action Dispatch (TODO 생성 등)

    Example:
        async with UnifiedStorage() as storage:
            pipeline = MessagePipeline(storage)
            result = await pipeline.process(message)
    """

    def __init__(self, storage: UnifiedStorage, config: dict[str, Any] | None = None,
                 project_resolver: ProjectContextResolver | None = None):
        """
        파이프라인 초기화

        Args:
            storage: 통합 스토리지 인스턴스
            config: 설정 딕셔너리 (None이면 기본값 사용)
            project_resolver: 프로젝트 컨텍스트 해석기 (None이면 자동 생성)
        """
        self.storage = storage
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.handlers: list[PipelineHandler] = []
        self._project_resolver = project_resolver or ProjectContextResolver()

        # 정규식 컴파일
        self._deadline_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.config["deadline_patterns"]
        ]

        # 긴급 키워드 정규식 (단어 경계)
        self._urgent_patterns = []
        for keyword in self.config["urgent_keywords"]:
            pattern = re.compile(
                rf'(?:^|[\s,.\-!?;:()\"\'·]){re.escape(keyword)}(?:[\s,.\-!?;:()\"\'·]|$)',
                re.IGNORECASE
            )
            self._urgent_patterns.append(pattern)

        # 긴급 부정 컨텍스트 패턴 (이 패턴에 매칭되면 긴급이 아님)
        self._urgent_deny_patterns = [
            re.compile(r'지금까지|지금은|지금처럼|지금도', re.IGNORECASE),
            re.compile(r'바로가기|바로잡|바로옆|바로그', re.IGNORECASE),
        ]

        # 액션 완료형 제외 패턴
        self._action_completion_patterns = {}
        for keyword in self.config["action_keywords"]:
            self._action_completion_patterns[keyword] = re.compile(
                rf'{re.escape(keyword)}(했|됐|완료|끝|드립니다|드렸|감사)',
                re.IGNORECASE
            )

        # 질문 패턴 (URL, 코드블록 제외용 정규식)
        self._url_pattern = re.compile(r'https?://\S+')
        self._code_block_pattern = re.compile(r'`[^`]*`')
        self._question_patterns = [
            re.compile(r'\?(?!\S*[/=&])'),  # URL query string이 아닌 ?
            re.compile(r'(?:^|[\s])어떻게(?:[\s]|$)', re.MULTILINE),
            re.compile(r'(?:^|[\s])언제(?:[\s]|$)', re.MULTILINE),
            re.compile(r'(?:^|[\s])왜(?:[\s,.\-!?]|$)', re.MULTILINE),
        ]

        # Action Dispatcher 초기화
        try:
            from scripts.gateway.action_dispatcher import ActionDispatcher
        except ImportError:
            try:
                from gateway.action_dispatcher import ActionDispatcher
            except ImportError:
                from .action_dispatcher import ActionDispatcher
        self._dispatcher = ActionDispatcher()

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

        원본 NormalizedMessage를 변경하지 않고,
        EnrichedMessage에 분석 결과를 기록합니다.

        Args:
            message: 처리할 메시지 (불변)

        Returns:
            처리 결과
        """
        result = PipelineResult(message_id=message.id)
        enriched = EnrichedMessage(original=message)

        try:
            # Stage 0.5: Project Context Resolution
            project_id = message.project_id or self._project_resolver.resolve(message)
            project_ctx = self._project_resolver.get_context(project_id) if project_id else None
            result.project_id = project_id
            enriched.project_id = project_id

            # Stage 1: Priority Analysis → EnrichedMessage에 기록 (프로젝트별 키워드 확장)
            priority = self._analyze_priority(message, project_ctx)
            if priority:
                result.priority = priority
                enriched.priority = Priority(priority)

            # Stage 2: Action Detection → EnrichedMessage에 기록 (프로젝트별 키워드 확장)
            actions = self._detect_actions(message, project_ctx)
            if actions:
                result.has_action = True
                result.actions = actions
                enriched.has_action = True
                enriched.actions = actions

            # Stage 3: Storage (원본 메시지 저장, project_id 포함)
            await self._save_to_storage(message, project_id)

            # Stage 4: Action Dispatch (TODO 생성 등)
            if result.has_action:
                await self._dispatch_actions(message, result)

            # Stage 6: Custom Handlers (EnrichedMessage 전달)
            for handler in self.handlers:
                await handler(enriched, result)

            result.processed_at = datetime.now()

        except Exception as e:
            result.error = str(e)

        return result

    def _analyze_priority(self, message: NormalizedMessage,
                          project_ctx: ProjectContext | None = None) -> str | None:
        """우선순위 분석 (프로젝트별 긴급 키워드 확장)"""
        text = message.text or ""

        # 부정 컨텍스트 체크 (먼저 실행)
        has_deny = any(p.search(text) for p in self._urgent_deny_patterns)

        # 긴급 키워드 체크 (단어 경계 정규식 - 기본 키워드)
        if not has_deny:
            for pattern in self._urgent_patterns:
                if pattern.search(text):
                    return "urgent"

            # 프로젝트별 긴급 키워드 체크
            if project_ctx and project_ctx.urgent_keywords:
                text_lower = text.lower()
                for kw in project_ctx.urgent_keywords:
                    if kw.lower() in text_lower:
                        return "urgent"

        # 멘션인 경우 높은 우선순위
        if message.is_mention:
            return "high"

        # 마감일 감지
        for pattern in self._deadline_patterns:
            if pattern.search(text):
                return "high"

        return "normal"

    def _detect_actions(self, message: NormalizedMessage,
                        project_ctx: ProjectContext | None = None) -> list[str]:
        """액션 감지 (프로젝트별 액션 키워드 확장)"""
        text = message.text or ""
        text_lower = text.lower()
        actions = []

        # 액션 키워드 체크 (완료형 제외, 모든 매칭 수집)
        action_keywords = self.config["action_keywords"]
        for keyword in action_keywords:
            if keyword.lower() in text_lower:
                # 완료형인지 확인
                completion_pat = self._action_completion_patterns.get(keyword)
                if completion_pat and completion_pat.search(text):
                    continue
                actions.append(f"action_request:{keyword}")

        # 마감일 감지 (모든 매칭 수집)
        for pattern in self._deadline_patterns:
            match = pattern.search(text)
            if match:
                actions.append(f"deadline:{match.group(0)}")

        # 프로젝트별 액션 키워드 체크
        if project_ctx and project_ctx.action_keywords:
            for kw in project_ctx.action_keywords:
                if kw.lower() in text_lower:
                    actions.append(f"action_request:{kw}")

        # 질문 패턴 감지 (URL, 코드블록 제외)
        text_clean = self._url_pattern.sub('', text)
        text_clean = self._code_block_pattern.sub('', text_clean)
        if any(p.search(text_clean) for p in self._question_patterns):
            actions.append("question")

        return actions

    async def _save_to_storage(self, message: NormalizedMessage,
                               project_id: str | None = None) -> None:
        """스토리지에 메시지 저장 (project_id 포함)"""
        await self.storage.save_message(message, project_id=project_id)

    async def _dispatch_actions(self, message: NormalizedMessage, result: PipelineResult) -> None:
        """
        액션 디스패치 - ActionDispatcher를 통해 TODO/Calendar 처리

        Args:
            message: 메시지
            result: 파이프라인 결과
        """
        try:
            dispatch_results = await self._dispatcher.dispatch(message, result.actions)
            for dr in dispatch_results:
                if dr.success and dr.output_path:
                    print(f"[Pipeline] Action dispatched: {dr.action} -> {dr.output_path}")
                elif not dr.success and dr.error:
                    print(f"[Pipeline] Action failed: {dr.action} - {dr.error}")
        except Exception as e:
            # dispatch 실패는 pipeline을 중단하지 않음
            print(f"[Pipeline] Dispatch error: {e}")

    def get_stats(self) -> dict[str, Any]:
        """
        파이프라인 통계 조회

        Returns:
            통계 딕셔너리
        """
        return {
            "handlers_count": len(self.handlers),
            "rate_limit_max": self.config.get("rate_limit_per_minute", 10),
        }
