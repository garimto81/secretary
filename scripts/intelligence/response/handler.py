"""
Pipeline Handler - Project Intelligence 메시지 핸들러 (2-Tier LLM)

MessagePipeline에 등록되어 수신 메시지를 처리합니다.

2-Tier 아키텍처:
- Tier 1 (Ollama): 모든 메시지 분석 (needs_response, project_id, intent, summary)
- Tier 2 (Claude Opus): needs_response=true일 때만 초안 작성
- DedupFilter: 중복 메시지 처리 방지
- ContextMatcher: 규칙 기반 힌트 제공

처리 흐름:
1. DedupFilter로 중복 체크
2. ContextMatcher로 규칙 기반 힌트 생성
3. OllamaAnalyzer로 메시지 분석 (ALL)
4. 분석 결과 DB 저장 + 중복 마킹
5. project_id 해석 (Ollama 우선, 규칙 기반 fallback)
6. project_id 없으면 pending_match로 저장 후 종료
7. needs_response=false면 종료 (분석만 완료)
8. needs_response=true면 ClaudeCodeDraftWriter로 초안 작성
"""

from typing import Optional, Dict, Any

from .context_matcher import ContextMatcher
from .draft_store import DraftStore
from .analyzer import OllamaAnalyzer, AnalysisResult
from .draft_writer import ClaudeCodeDraftWriter
from ..context_store import IntelligenceStorage
from ..project_registry import ProjectRegistry


class DedupFilter:
    """중복 메시지 처리 방지"""

    def __init__(self, storage: IntelligenceStorage):
        self.storage = storage
        self._recent_ids: set = set()
        self._max_cache = 1000

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
            self._recent_ids.add(key)
            return True

        return False

    def mark_processed(self, source_channel: str, source_message_id: str):
        """처리 완료 마킹 (메모리 캐시에만)"""
        key = f"{source_channel}:{source_message_id}"
        self._recent_ids.add(key)

        # 캐시 크기 제한 (최근 500개만 유지)
        if len(self._recent_ids) > self._max_cache:
            self._recent_ids = set(list(self._recent_ids)[-500:])


class ProjectIntelligenceHandler:
    """
    Gateway Pipeline에 등록되는 Project Intelligence 핸들러

    pipeline.add_handler(handler.handle) 형태로 사용.

    2-Tier LLM 아키텍처:
    - Tier 1 (Ollama): 모든 메시지 분석 (가벼운 로컬 모델)
    - Tier 2 (Claude Opus): needs_response=true일 때만 초안 작성 (고품질 모델)
    """

    def __init__(
        self,
        storage: IntelligenceStorage,
        registry: ProjectRegistry,
        ollama_config: Optional[Dict[str, Any]] = None,
        claude_config: Optional[Dict[str, Any]] = None,
    ):
        self.storage = storage
        self.registry = registry
        self.matcher = ContextMatcher(registry, storage)
        self.draft_store = DraftStore(storage)
        self.dedup = DedupFilter(storage)

        # Tier 1: Ollama Analyzer (모든 메시지 분석)
        self._analyzer: Optional[OllamaAnalyzer] = None
        if ollama_config and ollama_config.get("enabled", False):
            try:
                self._analyzer = OllamaAnalyzer(
                    model=ollama_config.get("model", "qwen3:8b"),
                    ollama_url=ollama_config.get("endpoint", "http://localhost:11434"),
                    timeout=ollama_config.get("timeout", 90),
                    max_context_chars=ollama_config.get("max_context_chars", 12000),
                )
            except Exception as e:
                print(f"[Intelligence] OllamaAnalyzer 초기화 실패: {e}")

        # Tier 2: Claude Opus Draft Writer (needs_response=true일 때만)
        self._draft_writer: Optional[ClaudeCodeDraftWriter] = None
        if claude_config and claude_config.get("enabled", False):
            try:
                self._draft_writer = ClaudeCodeDraftWriter(
                    model=claude_config.get("model", "opus"),
                    timeout=claude_config.get("timeout", 60),
                )
            except Exception as e:
                print(f"[Intelligence] ClaudeCodeDraftWriter 초기화 실패: {e}")

    async def handle(self, message, result) -> None:
        """
        Pipeline handler 진입점

        Args:
            message: NormalizedMessage
            result: PipelineResult
        """
        source_channel = message.channel.value if hasattr(message.channel, "value") else str(message.channel)

        # Step 1: 중복 체크
        if await self.dedup.is_duplicate(source_channel, message.id):
            return

        # Step 2: 규칙 기반 매칭 (빠른 힌트 생성)
        rule_match = await self.matcher.match(
            channel_id=message.channel_id,
            text=message.text,
            sender_id=message.sender_id,
            source_channel=source_channel,
        )

        rule_hint = self._build_rule_hint(rule_match)

        # Step 3: Ollama 분석 (모든 메시지)
        analysis = await self._analyze_message(message, source_channel, rule_hint)

        # Step 4: 분석 결과 DB 저장 + 중복 마킹
        self.dedup.mark_processed(source_channel, message.id)

        # Step 5: project_id 해석 (Ollama 우선, 규칙 기반 fallback)
        project_id = self._resolve_project(analysis, rule_match)

        # Step 6: project_id 없으면 pending_match로 저장 후 종료
        if not project_id:
            await self._save_pending_match(message, source_channel, analysis)
            return

        # Step 7: needs_response=false면 종료 (분석만 완료)
        if not analysis.needs_response:
            return

        # Step 8: Claude Opus로 초안 작성 (needs_response=true일 때만)
        await self._generate_draft(message, source_channel, project_id, analysis, rule_match)

    async def _analyze_message(
        self,
        message,
        source_channel: str,
        rule_hint: str,
    ) -> AnalysisResult:
        """
        Ollama로 메시지 분석 (Tier 1)

        Ollama 불가 시 기본값 반환 (needs_response=True로 설정하여 항상 초안 생성 시도)
        """
        if not self._analyzer:
            return AnalysisResult(
                needs_response=True,
                project_id=None,
                confidence=0.0,
                reasoning="Ollama 비활성화됨",
            )

        try:
            project_list = await self.registry.list_all()
            return await self._analyzer.analyze(
                text=message.text or "",
                sender_name=message.sender_name or message.sender_id or "",
                source_channel=source_channel,
                channel_id=message.channel_id or "",
                project_list=project_list,
                rule_hint=rule_hint,
            )
        except Exception as e:
            print(f"[Intelligence] Ollama 분석 실패: {e}")
            return AnalysisResult(
                needs_response=True,
                project_id=None,
                confidence=0.0,
                reasoning=f"분석 실패: {str(e)}",
            )

    async def _generate_draft(
        self,
        message,
        source_channel: str,
        project_id: str,
        analysis: AnalysisResult,
        rule_match,
    ):
        """
        Claude Opus로 초안 작성 (Tier 2)

        Claude 불가 시 awaiting_draft로 fallback
        """
        confidence = max(
            analysis.confidence,
            rule_match.confidence if rule_match.matched else 0.0,
        )
        match_tier = rule_match.tier if rule_match.matched else "ollama"

        if not self._draft_writer:
            await self._save_awaiting_draft(
                message, source_channel, project_id, confidence, match_tier,
            )
            return

        try:
            context = await self._build_context(project_id)
            project = await self.registry.get(project_id)
            project_name = project.get("name", project_id) if project else project_id

            # Claude Opus로 초안 생성
            draft_text = await self._draft_writer.write_draft(
                project_name=project_name,
                project_context=context,
                original_text=message.text or "",
                sender_name=message.sender_name or message.sender_id or "",
                source_channel=source_channel,
                analysis_summary=analysis.summary,
            )

            # DraftStore에 저장
            await self.draft_store.save(
                project_id=project_id,
                source_channel=source_channel,
                source_message_id=message.id,
                sender_id=message.sender_id,
                sender_name=message.sender_name,
                original_text=message.text[:4000] if message.text else "",
                draft_text=draft_text,
                match_confidence=confidence,
                match_tier=match_tier,
            )

        except Exception as e:
            print(f"[Intelligence] Claude 초안 생성 실패, awaiting_draft로 전환: {e}")
            await self._save_awaiting_draft(
                message, source_channel, project_id, confidence, match_tier,
            )

    async def _save_pending_match(
        self,
        message,
        source_channel: str,
        analysis: AnalysisResult,
    ):
        """프로젝트 미매칭 메시지 저장"""
        try:
            await self.storage.save_draft({
                "project_id": None,
                "source_channel": source_channel,
                "source_message_id": message.id,
                "sender_id": message.sender_id,
                "sender_name": message.sender_name,
                "original_text": message.text[:4000] if message.text else "",
                "draft_text": None,
                "draft_file": None,
                "match_confidence": analysis.confidence,
                "match_tier": "ollama" if analysis.project_id else None,
                "match_status": "pending_match",
                "status": "pending",
            })
        except Exception as e:
            print(f"[Intelligence] pending_match 저장 실패: {e}")

    async def _save_awaiting_draft(
        self,
        message,
        source_channel: str,
        project_id: str,
        confidence: float,
        match_tier: str,
    ):
        """awaiting_draft로 저장 (Claude 비활성화 시 fallback)"""
        try:
            await self.storage.save_draft({
                "project_id": project_id,
                "source_channel": source_channel,
                "source_message_id": message.id,
                "sender_id": message.sender_id,
                "sender_name": message.sender_name,
                "original_text": message.text[:4000] if message.text else "",
                "draft_text": None,
                "draft_file": None,
                "match_confidence": confidence,
                "match_tier": match_tier,
                "match_status": "matched",
                "status": "awaiting_draft",
            })
        except Exception as e:
            print(f"[Intelligence] awaiting_draft 저장 실패: {e}")

    def _build_rule_hint(self, rule_match) -> str:
        """규칙 기반 매칭 결과를 힌트 문자열로 변환"""
        if not rule_match.matched:
            return ""

        return (
            f"규칙 기반 매칭: project_id={rule_match.project_id}, "
            f"confidence={rule_match.confidence:.2f}, tier={rule_match.tier}"
        )

    def _resolve_project(self, analysis: AnalysisResult, rule_match) -> Optional[str]:
        """
        Ollama 분석과 규칙 기반 매칭을 결합하여 최종 project_id 결정

        우선순위:
        1. Ollama가 confidence >= 0.7로 project_id 제시한 경우
        2. 규칙 기반 매칭이 성공한 경우
        3. Ollama가 낮은 confidence로라도 project_id 제시한 경우
        4. 둘 다 실패: None
        """
        # Ollama가 높은 신뢰도로 project_id 제시
        if analysis.project_id and analysis.confidence >= 0.7:
            return analysis.project_id

        # 규칙 기반 매칭 성공
        if rule_match.matched:
            return rule_match.project_id

        # Ollama가 낮은 신뢰도로라도 project_id 제시
        if analysis.project_id and analysis.confidence >= 0.3:
            return analysis.project_id

        return None

    async def _build_context(self, project_id: str) -> str:
        """프로젝트 컨텍스트 조합 (Claude 초안 작성용)"""
        entries = await self.storage.get_context_entries(project_id, limit=20)

        if not entries:
            project = await self.registry.get(project_id)
            if project:
                return f"프로젝트: {project.get('name', project_id)}\n설명: {project.get('description', '')}"
            return ""

        context_parts = []
        for entry in entries[:10]:
            source = entry.get("source", "")
            title = entry.get("title", "")
            content = entry.get("content", "")[:500]
            context_parts.append(f"[{source}] {title}: {content}")

        return "\n".join(context_parts)
