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

import asyncio
import json
import logging
from typing import Any

try:
    from scripts.shared.paths import CHANNEL_CONTEXTS_DIR as _CHANNEL_CONTEXTS_DIR
except ImportError:
    try:
        from shared.paths import CHANNEL_CONTEXTS_DIR as _CHANNEL_CONTEXTS_DIR
    except ImportError:
        _CHANNEL_CONTEXTS_DIR = None

from ..context_store import IntelligenceStorage
from ..project_registry import ProjectRegistry
from .analyzer import AnalysisResult, OllamaAnalyzer
from .context_matcher import ContextMatcher
from .dedup_filter import DedupFilter
from .draft_store import DraftStore
from .draft_writer import ClaudeCodeDraftWriter

logger = logging.getLogger(__name__)


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
        ollama_config: dict[str, Any] | None = None,
        claude_config: dict[str, Any] | None = None,
        knowledge_store=None,  # Optional[KnowledgeStore]
        chatbot_channels: list | None = None,
        mastery_analyzer=None,  # Optional[ChannelMasteryAnalyzer]
    ):
        self.storage = storage
        self.registry = registry
        self._knowledge_store = knowledge_store
        self._mastery_analyzer = mastery_analyzer
        self.matcher = ContextMatcher(registry, storage)
        self.draft_store = DraftStore(storage)
        self.dedup = DedupFilter(storage)
        self._chatbot_channels: list = chatbot_channels or []
        self._slack_client = None  # lazy init for chatbot reply

        # Tier 1: Ollama Analyzer (모든 메시지 분석)
        self._analyzer: OllamaAnalyzer | None = None
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
        self._draft_writer: ClaudeCodeDraftWriter | None = None
        if claude_config and claude_config.get("enabled", False):
            try:
                self._draft_writer = ClaudeCodeDraftWriter(
                    model=claude_config.get("model", "opus"),
                    timeout=claude_config.get("timeout", 60),
                )
            except Exception as e:
                print(f"[Intelligence] ClaudeCodeDraftWriter 초기화 실패: {e}")

        # Priority Queue (낮은 숫자 = 높은 우선순위)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._worker_task: asyncio.Task | None = None
        self._counter = 0  # 같은 우선순위 시 FIFO 보장

        # Reporter (Phase 5에서 주입)
        self._reporter = None

        # 채널 문서 캐시 (mtime 기반)
        self._channel_doc_cache: dict = {}

    async def handle(self, enriched_or_message, result) -> None:
        """
        Pipeline handler 진입점

        큐 워커가 활성화되어 있으면 큐에 삽입, 아니면 직접 처리.
        """
        if self._worker_task is not None:
            # 우선순위 결정: urgent=0, high=1, normal=2, low=3
            priority_val = self._get_priority_value(enriched_or_message, result)
            self._counter += 1
            await self._queue.put((priority_val, self._counter, enriched_or_message, result))
            return

        await self._process_message(enriched_or_message, result)

    def _get_priority_value(self, enriched_or_message, result) -> int:
        """PriorityQueue용 우선순위 값 (낮을수록 먼저 처리)"""
        priority_str = getattr(result, 'priority', None) or 'normal'
        mapping = {'urgent': 0, 'high': 1, 'normal': 2, 'low': 3}
        return mapping.get(priority_str, 2)

    async def _process_message(self, enriched_or_message, result) -> None:
        """실제 메시지 처리 로직"""
        # EnrichedMessage면 원본 추출, 아니면 직접 사용 (하위호환)
        if hasattr(enriched_or_message, 'original'):
            message = enriched_or_message.original
        else:
            message = enriched_or_message

        source_channel = message.channel.value if hasattr(message.channel, "value") else str(message.channel)
        priority_str = getattr(result, 'priority', None) or 'normal'

        # Step 1: 중복 체크
        if await self.dedup.is_duplicate(source_channel, message.id):
            return

        # Step 1.5: Chatbot channel 체크
        if self._is_chatbot_channel(message.channel_id):
            await self._handle_chatbot_message(message, source_channel)
            self.dedup.mark_processed(source_channel, message.id)
            return

        # Step 2: 규칙 기반 매칭 (빠른 힌트 생성)
        rule_match = await self.matcher.match(
            channel_id=message.channel_id,
            text=message.text,
            sender_id=message.sender_id,
            source_channel=source_channel,
        )

        rule_hint = self._build_rule_hint(rule_match)

        # Step 2.5: RAG 컨텍스트 검색 (Knowledge Store)
        rag_context = ""
        original_text = message.text or ""
        if self._knowledge_store and original_text:
            try:
                # 규칙 기반 매칭의 project_id를 힌트로 활용
                hint_project_id = rule_match.project_id if rule_match.matched else None
                results = await self._knowledge_store.search(
                    query=original_text[:500],
                    project_id=hint_project_id,
                    limit=5,
                )
                if results:
                    rag_parts = []
                    for r in results:
                        doc = r.document
                        date_str = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""
                        source_label = "이메일" if doc.source == "gmail" else "Slack"
                        rag_parts.append(f"[{source_label} {date_str}] {doc.sender_name}: {doc.content[:300]}")
                    rag_context = "\n".join(rag_parts)
            except Exception as e:
                logger.warning(f"Knowledge Store RAG 검색 실패: {e}")

        # Step 3: Ollama 분석
        # urgent + 규칙 매칭 시 Ollama 건너뛰기 (fast-track)
        if priority_str == 'urgent' and rule_match.matched:
            logger.info("Fast-track: urgent + rule match → skip Ollama")
            analysis = AnalysisResult(
                project_id=rule_match.project_id,
                needs_response=True,
                confidence=rule_match.confidence,
                reasoning="fast-track: urgent + rule match",
                intent="요청",
                summary="긴급 메시지 (fast-track)",
            )
        else:
            analysis = await self._analyze_message(message, source_channel, rule_hint, rag_context=rag_context)

        # Step 4: project_id 해석 (Ollama 우선, 규칙 기반 fallback)
        project_id = self._resolve_project(analysis, rule_match)

        # Step 5: project_id 없으면 pending_match로 저장 후 종료
        if not project_id:
            await self._save_pending_match(message, source_channel, analysis)
            self.dedup.mark_processed(source_channel, message.id)
            return

        # Step 6: needs_response=false면 종료 (분석만 완료)
        if not analysis.needs_response:
            self.dedup.mark_processed(source_channel, message.id)
            return

        # Step 7: Claude Opus로 초안 작성 (needs_response=true일 때만)
        await self._generate_draft(message, source_channel, project_id, analysis, rule_match)

        # Step 8: 처리 완료 마킹
        self.dedup.mark_processed(source_channel, message.id)

        # Step 9: PRD 문서 갱신 판단 (Slack 채널 메시지만, fire-and-forget)
        if source_channel == "slack" and message.channel_id:
            asyncio.create_task(self._check_prd_update(message, source_channel))

    async def _analyze_message(
        self,
        message,
        source_channel: str,
        rule_hint: str,
        rag_context: str = "",
    ) -> AnalysisResult:
        """
        Ollama로 메시지 분석 (Tier 1)

        Ollama 불가 시 기본값 반환 (needs_response=False로 설정하여 비용 폭주 방지)
        """
        if not self._analyzer:
            # Ollama 비활성화 → Claude Sonnet으로 분석 (Tier 1 fallback)
            if self._draft_writer:
                return await self._analyze_with_claude(message, source_channel, rule_hint, rag_context)
            print("[Intelligence] WARNING: 분석기 없음 - 건너뜀")
            return AnalysisResult(
                needs_response=False,
                project_id=None,
                confidence=0.0,
                reasoning="분석기 없음",
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
                rag_context=rag_context,
            )
        except Exception as e:
            print(f"[Intelligence] WARNING: Ollama 분석 실패 - 분석 건너뜀: {e}")
            return AnalysisResult(
                needs_response=False,
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
            original_text = message.text or ""

            # RAG: Knowledge Store 검색으로 과거 커뮤니케이션 이력 구성
            rag_context = ""
            if self._knowledge_store and original_text:
                try:
                    results = await self._knowledge_store.search(
                        query=original_text[:500],
                        project_id=project_id,
                        limit=5,
                    )
                    if results:
                        rag_parts = []
                        for r in results:
                            doc = r.document
                            date_str = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""
                            source_label = "이메일" if doc.source == "gmail" else "Slack"
                            rag_parts.append(f"[{source_label} {date_str}] {doc.sender_name}: {doc.content[:300]}")
                        rag_context = "\n".join(rag_parts)
                except Exception as e:
                    logger.warning(f"Knowledge Store RAG 검색 실패: {e}")

            context, channel_ctx_section = await self._build_context(
                project_id,
                query_text=original_text,
                channel_id=message.channel_id or "",
            )
            project = await self.registry.get(project_id)
            project_name = project.get("name", project_id) if project else project_id

            # Claude Opus로 초안 생성
            draft_text = await self._draft_writer.write_draft(
                project_name=project_name,
                project_context=context,
                original_text=original_text,
                sender_name=message.sender_name or message.sender_id or "",
                source_channel=source_channel,
                ollama_reasoning=analysis.reasoning,
                analysis_summary=analysis.summary,
                rag_context=rag_context,
                channel_context=channel_ctx_section,
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

    def _is_chatbot_channel(self, channel_id: str | None) -> bool:
        """channel_id가 chatbot_channels 목록에 포함되는지 확인"""
        if not channel_id or not self._chatbot_channels:
            return False
        return channel_id in self._chatbot_channels

    def _load_channel_doc(self, channel_id: str) -> str:
        """config/channel_docs/{channel_id}.md 로드 (mtime 기반 캐싱)."""
        if not channel_id:
            return ""
        try:
            if _CHANNEL_CONTEXTS_DIR is not None:
                from pathlib import Path as _P
                doc_path = _P(str(_CHANNEL_CONTEXTS_DIR).replace("channel_contexts", "channel_docs")) / f"{channel_id}.md"
            else:
                from pathlib import Path as _P
                doc_path = _P(r"C:\claude\secretary\config\channel_docs") / f"{channel_id}.md"

            if not doc_path.exists():
                return ""

            mtime = doc_path.stat().st_mtime
            cached = self._channel_doc_cache.get(channel_id)
            if cached and cached[0] == mtime:
                return cached[1]

            content = doc_path.read_text(encoding="utf-8")
            self._channel_doc_cache[channel_id] = (mtime, content)
            logger.info(f"[Handler] Channel doc loaded: {channel_id} ({len(content)} chars)")
            return content
        except Exception as e:
            logger.warning(f"채널 문서 로드 실패 {channel_id}: {e}")
            return ""

    def _load_channel_context(self, channel_id: str) -> dict:
        """config/channel_contexts/{channel_id}.json 로드 및 필드 추출 (7개 필드)"""
        if _CHANNEL_CONTEXTS_DIR is not None:
            ctx_path = _CHANNEL_CONTEXTS_DIR / f"{channel_id}.json"
        else:
            from pathlib import Path as _P
            ctx_path = _P(r"C:\claude\secretary\config\channel_contexts") / f"{channel_id}.json"
        if not ctx_path.exists():
            return {}
        try:
            data = json.loads(ctx_path.read_text(encoding="utf-8"))
            result = {
                "channel_summary": data.get("channel_summary", ""),
                "key_topics": data.get("key_topics", [])[:8],
                "response_guidelines": data.get("response_guidelines", []),
                "key_decisions": data.get("key_decisions", [])[:5],
                "member_profiles": data.get("member_profiles", {}),
                "escalation_hints": data.get("escalation_hints", [])[:5],
                "issue_patterns": data.get("issue_patterns", []),
            }
            logger.info(f"[Handler] Channel context loaded: {channel_id}")
            return result
        except Exception as e:
            logger.warning(f"채널 컨텍스트 로드 실패 {channel_id}: {e}")
            return {}

    def _channel_context_to_str(self, ch_ctx: dict) -> str:
        """채널 컨텍스트 dict → chatbot용 요약 문자열 변환"""
        parts = []
        if ch_ctx.get("channel_summary"):
            parts.append(f"채널 개요: {ch_ctx['channel_summary']}")
        if ch_ctx.get("key_topics"):
            parts.append(f"주요 토픽: {', '.join(ch_ctx['key_topics'])}")
        if ch_ctx.get("response_guidelines"):
            guidelines = ch_ctx["response_guidelines"]
            if isinstance(guidelines, list):
                parts.append(f"응답 지침: {', '.join(guidelines)}")
            else:
                parts.append(f"응답 지침: {guidelines}")
        return "\n".join(parts)

    async def _handle_chatbot_message(self, message, source_channel: str) -> None:
        """
        Chatbot 채널 메시지 처리.

        봇 자기 메시지 방지 → 채널 컨텍스트 로드 → Qwen 분석 → 에스컬레이션 판단
        → Sonnet 에스컬레이션 또는 Qwen 응답 → Slack thread reply 전송.
        """
        import time as _time
        start_ms = _time.monotonic() * 1000

        # 봇 자기 메시지 방지: raw_json에서 subtype 확인
        raw_json_str = getattr(message, 'raw_json', None) or '{}'
        try:
            raw_data = json.loads(raw_json_str) if isinstance(raw_json_str, str) else raw_json_str
        except (json.JSONDecodeError, TypeError):
            raw_data = {}

        subtype = raw_data.get('subtype', '')
        if subtype in ('bot_message', 'message_changed', 'message_deleted'):
            logger.debug(f"Chatbot: 봇 메시지 건너뜀 (subtype={subtype})")
            return

        text = message.text or ""
        sender_name = message.sender_name or message.sender_id or "사용자"
        channel_id = message.channel_id

        # 1. 채널 컨텍스트 로드
        ch_ctx_dict = self._load_channel_context(channel_id or "")
        channel_context = self._channel_context_to_str(ch_ctx_dict)

        # MD 채널 지식 문서 우선 주입
        channel_doc = self._load_channel_doc(channel_id or "")
        if channel_doc:
            channel_context = f"## 채널 지식베이스\n{channel_doc[:6000]}\n\n{channel_context}"

        # 실시간 컨텍스트 조회 (날씨 등)
        context = await self._get_realtime_context(text)

        # 2. Qwen 응답 생성 + 에스컬레이션 판단용 분석
        response_text = None
        qwen_confidence = 1.0
        qwen_intent = "unknown"

        if self._analyzer:
            try:
                # analyze()로 에스컬레이션 판단에 필요한 메타데이터 수집
                analysis = await self._analyzer.analyze(
                    text=text,
                    sender_name=sender_name,
                    source_channel=source_channel or "slack",
                    channel_id=channel_id or "",
                    project_list=[],
                )
                qwen_confidence = analysis.confidence
                qwen_intent = analysis.intent

                response_text = await self._analyzer.chatbot_respond(
                    text=text,
                    sender_name=sender_name,
                    context=context,
                    channel_context=channel_context,
                )
            except Exception as e:
                logger.warning(f"Chatbot Ollama 응답 생성 실패: {e}")

        # 3. 에스컬레이션 판단
        should_escalate = False
        if self._draft_writer:
            try:
                from scripts.intelligence.response.escalation_router import EscalationRouter
            except ImportError:
                try:
                    from intelligence.response.escalation_router import EscalationRouter
                except ImportError:
                    from .escalation_router import EscalationRouter

            router = EscalationRouter()
            decision = router.decide(qwen_confidence, qwen_intent, text)
            should_escalate = decision.should_escalate

            if should_escalate:
                logger.info(f"[Chatbot] Escalating to Sonnet: reason={decision.reason}")

        # 4. Sonnet 에스컬레이션 (또는 Qwen 없거나 실패 시 Claude fallback)
        if (not response_text or should_escalate) and self._draft_writer:
            try:
                sonnet_response = await self._draft_writer.chatbot_respond(
                    text=text,
                    sender_name=sender_name,
                    context=context,
                    channel_context=channel_context,
                )
                if sonnet_response:
                    response_text = sonnet_response
            except Exception as e:
                logger.warning(f"Chatbot Claude 응답 생성 실패: {e}")
                # sonnet 실패 시 기존 qwen_response 유지 (fallback)

        if not response_text:
            response_text = "현재 AI 응답 서비스를 이용할 수 없습니다. 잠시 후 다시 시도해 주세요."

        elapsed_ms = _time.monotonic() * 1000 - start_ms
        mode = "sonnet" if should_escalate else "qwen"
        logger.info(f"[Chatbot] Processed in {elapsed_ms:.0f}ms ({mode})")

        # thread_ts 추출: raw_json.ts 우선, reply_to_id fallback
        thread_ts = raw_data.get('ts') or getattr(message, 'reply_to_id', None)

        await self._send_chatbot_reply(channel_id, response_text, thread_ts)

    # 웹 검색 트리거 키워드 (poc_slack_chatbot.py에서 포팅)
    _SEARCH_TRIGGER_KEYWORDS = [
        "날씨", "기온", "비", "눈", "weather",
        "뉴스", "소식", "news", "헤드라인",
        "환율", "달러", "엔화", "유로", "원화",
        "주가", "주식", "코스피", "나스닥", "stock",
        "검색", "찾아줘", "찾아봐", "알아봐",
        "누구", "어디", "언제", "얼마",
        "최근", "최신", "현재", "지금", "올해", "이번",
        "결과", "점수", "순위", "경기",
        "맛집", "추천", "리뷰",
        "사건", "사고", "이슈",
    ]
    _SKIP_PATTERNS = [
        r"^(안녕|ㅎㅇ|ㅋㅋ|ㅎㅎ|네|응|ㅇㅇ|감사|고마워|수고|bye|hi|hello)",
        r"^.{1,3}$",
    ]
    _NEWS_KEYWORDS = ["뉴스", "소식", "news", "헤드라인", "사건", "사고", "이슈"]

    def _needs_web_search(self, message: str) -> bool:
        """메시지가 웹 검색이 필요한지 판단"""
        import re as _re
        msg_lower = message.lower().strip()
        for pattern in self._SKIP_PATTERNS:
            if _re.match(pattern, msg_lower):
                return False
        for keyword in self._SEARCH_TRIGGER_KEYWORDS:
            if keyword in msg_lower:
                return True
        if "?" in message or "\uff1f" in message:
            return True
        return False

    @staticmethod
    def _build_search_query(message: str) -> str:
        """사용자 메시지에서 검색 쿼리 생성"""
        query = message.strip().rstrip("?\uff1f")
        for suffix in [
            "알려주세요", "알려줘", "찾아주세요", "찾아줘", "찾아봐줘", "찾아봐",
            "검색해줘", "검색해주세요", "검색", "해주세요", "해줘", "부탁해",
            "어때", "어떤가요", "어떻게 돼", "어떻게 되나요", "얼마야",
            "뭐야", "뭔가요", "인가요", "인지", "좀",
        ]:
            query = query.replace(suffix, "")
        query = query.strip()
        return query if len(query) >= 2 else message.strip()

    async def _web_search(self, query: str, max_results: int = 3) -> str:
        """DuckDuckGo로 웹 검색 (뉴스 키워드면 뉴스 검색)"""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("duckduckgo-search 미설치, 웹 검색 스킵")
            return ""
        try:
            is_news = any(kw in query.lower() for kw in self._NEWS_KEYWORDS)
            def _search():
                with DDGS() as ddgs:
                    if is_news:
                        return list(ddgs.news(query, region="kr-kr", max_results=max_results))
                    return list(ddgs.text(query, region="kr-kr", max_results=max_results))
            results = await asyncio.to_thread(_search)
            if not results:
                return ""
            lines = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                body = r.get("body", "")
                href = r.get("href", r.get("url", ""))
                lines.append(f"{i}. {title}\n   {body}\n   출처: {href}")
            return "\n\n".join(lines)
        except Exception as e:
            logger.warning(f"웹 검색 오류: {e}")
            return ""

    async def _get_realtime_context(self, text: str) -> str:
        """POC 기반 웹 검색 컨텍스트 조회"""
        if not self._needs_web_search(text):
            return ""
        query = self._build_search_query(text)
        logger.info(f"Chatbot 웹 검색: \"{query}\"")
        return await self._web_search(query)

    async def _send_chatbot_reply(
        self,
        channel_id: str,
        text: str,
        thread_ts: str | None,
    ) -> None:
        """
        Slack thread reply 전송. 실패 시 로그만 출력 (fire-and-forget).
        """
        # SlackClient lazy 초기화
        if self._slack_client is None:
            try:
                import sys
                claude_root = r"C:\claude"
                if claude_root not in sys.path:
                    sys.path.insert(0, claude_root)
                from lib.slack import SlackClient
                self._slack_client = SlackClient()
            except Exception as e:
                logger.error(f"Chatbot: SlackClient 초기화 실패 - 응답 전송 불가: {e}")
                return

        try:
            kwargs: dict[str, Any] = {
                "channel": channel_id,
                "text": text,
            }
            if thread_ts:
                kwargs["thread_ts"] = thread_ts

            await asyncio.to_thread(self._slack_client.send_message, **kwargs)
            logger.info(f"Chatbot reply 전송 완료: channel={channel_id}, thread_ts={thread_ts}")
        except Exception as e:
            logger.error(f"Chatbot reply 전송 실패: {e}")

    async def _analyze_with_claude(
        self,
        message,
        source_channel: str,
        rule_hint: str,
        rag_context: str = "",
    ) -> AnalysisResult:
        """
        Claude Sonnet으로 메시지 분석 (Ollama 비활성화 시 Tier 1 대체)

        draft_writer.write_draft() 대신 분석 전용 subprocess 호출.
        """
        import json as _json
        import re
        import subprocess
        import sys

        try:
            project_list = await self.registry.list_all()
            project_names = ", ".join([f"{p['id']}({p['name']})" for p in project_list]) if project_list else "없음"

            prompt = f"""다음 메시지를 분석하여 JSON으로 응답하세요.

메시지: {message.text or ""}
발신자: {message.sender_name or message.sender_id or "unknown"}
채널: {source_channel}
{f"규칙 힌트: {rule_hint}" if rule_hint else ""}
{f"관련 컨텍스트:{chr(10)}{rag_context}" if rag_context else ""}

등록된 프로젝트: {project_names}

분석 결과를 다음 JSON 형식으로만 응답하세요 (다른 텍스트 없이):
{{
  "project_id": "프로젝트ID 또는 null",
  "needs_response": true/false,
  "confidence": 0.0~1.0,
  "intent": "요청/질문/정보공유/잡담/긴급",
  "summary": "메시지 한줄 요약",
  "reasoning": "판단 근거 한줄"
}}"""

            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, "-m", "claude_code", "-p", prompt, "--output-format", "text"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                cwd=r"C:\claude",
            )

            # subprocess 실패 시 claude CLI 직접 시도
            if result.returncode != 0 or not result.stdout.strip():
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["claude", "-p", prompt, "--output-format", "text"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                    cwd=r"C:\claude",
                )

            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout.strip()
                json_match = re.search(r'\{[^{}]*"project_id"[^{}]*\}', output, re.DOTALL)
                if json_match:
                    data = _json.loads(json_match.group())
                    return AnalysisResult(
                        project_id=data.get("project_id"),
                        needs_response=data.get("needs_response", False),
                        confidence=float(data.get("confidence", 0.5)),
                        intent=data.get("intent", ""),
                        summary=data.get("summary", ""),
                        reasoning=data.get("reasoning", "Claude Sonnet 분석"),
                    )

        except Exception as e:
            logger.warning(f"Claude 분석 실패: {e}")

        # 분석 실패 시 기본값 (규칙 기반에 위임)
        return AnalysisResult(
            needs_response=False,
            project_id=None,
            confidence=0.0,
            reasoning="Claude 분석 실패 - 규칙 기반 fallback",
        )

    def _build_rule_hint(self, rule_match) -> str:
        """규칙 기반 매칭 결과를 힌트 문자열로 변환"""
        if not rule_match.matched:
            return ""

        return (
            f"규칙 기반 매칭: project_id={rule_match.project_id}, "
            f"confidence={rule_match.confidence:.2f}, tier={rule_match.tier}"
        )

    def _resolve_project(self, analysis: AnalysisResult, rule_match) -> str | None:
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

        # 규칙 기반 매칭 성공 (confidence >= 0.6 이상만)
        if rule_match.matched and rule_match.confidence >= 0.6:
            return rule_match.project_id

        # Ollama가 낮은 신뢰도로라도 project_id 제시
        if analysis.project_id and analysis.confidence >= 0.3:
            return analysis.project_id

        return None

    async def _build_context(self, project_id: str, query_text: str = "", channel_id: str = "") -> tuple[str, str]:
        """프로젝트 컨텍스트 + RAG 검색 결합 + 채널 컨텍스트 주입

        Returns:
            (full_context, channel_ctx_section) tuple
        """
        parts = []
        channel_ctx_section = ""

        # 채널 컨텍스트 섹션 생성 (channel_id가 있을 때)
        if channel_id:
            ch_ctx = self._load_channel_context(channel_id)
            if ch_ctx:
                lines = ["## 채널 전문가 컨텍스트"]
                if ch_ctx.get("channel_summary"):
                    lines.append(f"**채널 요약**: {ch_ctx['channel_summary']}")
                if ch_ctx.get("key_topics"):
                    lines.append(f"**주요 토픽**: {', '.join(ch_ctx['key_topics'])}")
                if ch_ctx.get("issue_patterns"):
                    lines.append("**반복 이슈 패턴**:")
                    for p in ch_ctx["issue_patterns"]:
                        lines.append(f"  - {p}")
                if ch_ctx.get("response_guidelines"):
                    lines.append("**응답 가이드라인**:")
                    guidelines = ch_ctx["response_guidelines"]
                    if isinstance(guidelines, list):
                        for g in guidelines:
                            lines.append(f"  - {g}")
                    else:
                        lines.append(f"  - {guidelines}")
                if ch_ctx.get("escalation_hints"):
                    lines.append("**에스컬레이션 힌트**:")
                    for h in ch_ctx["escalation_hints"]:
                        lines.append(f"  - {h}")
                channel_ctx_section = "\n".join(lines)

        # 1. 프로젝트 기본 정보
        project = await self.registry.get(project_id)
        if project:
            parts.append(f"프로젝트: {project.get('name', project_id)}")
            desc = project.get('description', '')
            if desc:
                parts.append(f"설명: {desc}")

        # 2. Knowledge Store 검색 (RAG)
        if self._knowledge_store and query_text:
            try:
                results = await self._knowledge_store.search(
                    query=query_text,
                    project_id=project_id,
                    limit=5,
                )
                if results:
                    parts.append("\n## 관련 과거 커뮤니케이션")
                    for r in results:
                        doc = r.document
                        date_str = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""
                        source_label = "이메일" if doc.source == "gmail" else "Slack"
                        parts.append(
                            f"[{source_label} {date_str}] {doc.sender_name}: "
                            f"{doc.content[:300]}"
                        )
            except Exception as e:
                logger.warning(f"Knowledge Store 검색 실패: {e}")

        # 3. context_entries (하위호환)
        entries = await self.storage.get_context_entries(project_id, limit=5)
        if entries:
            parts.append("\n## 등록된 컨텍스트")
            for entry in entries[:10]:
                source = entry.get("source", "")
                title = entry.get("title", "")
                content = entry.get("content", "")[:500]
                parts.append(f"[{source}] {title}: {content}")

        # 4. 채널 전문가 컨텍스트 (CM-K05)
        if self._mastery_analyzer:
            try:
                mastery = await self._mastery_analyzer.build_mastery_context(
                    project_id=project_id,
                    channel_id="",  # profile_store에서 프로젝트의 채널 조회
                )
                if mastery and any(mastery.values()):
                    parts.append("\n## 채널 전문가 컨텍스트")
                    if mastery.get("channel_summary"):
                        parts.append(f"채널 요약: {mastery['channel_summary']}")
                    if mastery.get("top_keywords"):
                        parts.append(f"주요 키워드: {', '.join(mastery['top_keywords'][:10])}")
                    if mastery.get("key_decisions"):
                        decisions_str = "\n".join(f"  - {d}" for d in mastery["key_decisions"][:5])
                        parts.append(f"주요 의사결정:\n{decisions_str}")
                    if mastery.get("member_roles"):
                        roles_str = ", ".join(f"{k}: {v}" for k, v in mastery["member_roles"].items())
                        parts.append(f"멤버 역할: {roles_str}")
                    if mastery.get("active_topics"):
                        parts.append(f"활성 토픽: {', '.join(mastery['active_topics'][:5])}")
            except Exception as e:
                logger.warning(f"채널 전문가 컨텍스트 주입 실패: {e}")

        existing_context = "\n".join(parts)
        if channel_ctx_section:
            full_context = channel_ctx_section + "\n\n" + existing_context
        else:
            full_context = existing_context
        return full_context, channel_ctx_section

    async def start_worker(self) -> None:
        """우선순위 큐 워커 시작"""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._process_loop())
            logger.info("Intelligence handler worker started")

    async def stop_worker(self) -> None:
        """우선순위 큐 워커 중지"""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("Intelligence handler worker stopped")

    def set_reporter(self, reporter) -> None:
        """Reporter 주입"""
        self._reporter = reporter

    async def _check_prd_update(self, message, source_channel: str) -> None:
        """PRD 문서 갱신 판단 및 자동 업데이트 (fire-and-forget)"""
        try:
            try:
                from scripts.knowledge.channel_prd_writer import ChannelPRDWriter
                from scripts.knowledge.channel_update_judge import ChannelUpdateJudge
            except ImportError:
                try:
                    from knowledge.channel_prd_writer import ChannelPRDWriter
                    from knowledge.channel_update_judge import ChannelUpdateJudge
                except ImportError:
                    return

            channel_id = message.channel_id
            judge = ChannelUpdateJudge()
            prd_writer = ChannelPRDWriter()

            # PRD 현재 내용 로드
            prd_path = await prd_writer.get_prd_path(channel_id)
            prd_content = prd_path.read_text(encoding="utf-8") if prd_path.exists() else ""

            if not prd_content:
                # PRD 없으면 판단 스킵 (채널 최초 등록 시 ChannelWatcher가 처리)
                return

            decision = await judge.judge(
                message_text=message.text or "",
                channel_id=channel_id,
                prd_content=prd_content,
            )

            if decision.needs_update and decision.section and decision.new_content:
                success = await prd_writer.update_section(
                    channel_id=channel_id,
                    section=decision.section,
                    new_content=decision.new_content,
                )
                if success:
                    logger.info(
                        f"PRD 갱신 완료: channel={channel_id}, "
                        f"section={decision.section}, judged_by={decision.judged_by}"
                    )
            else:
                logger.debug(
                    f"PRD 갱신 불필요: channel={channel_id}, "
                    f"judged_by={decision.judged_by}, confidence={decision.confidence:.2f}"
                )

        except Exception as e:
            logger.warning(f"PRD 갱신 판단 실패 (무시): {e}")

    async def _process_loop(self) -> None:
        """큐에서 메시지를 꺼내 처리하는 워커 루프"""
        while True:
            try:
                priority_val, counter, enriched_or_message, result = await self._queue.get()
                await self._process_message(enriched_or_message, result)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
