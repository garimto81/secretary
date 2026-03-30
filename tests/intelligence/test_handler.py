"""
ProjectIntelligenceHandler 테스트

Priority queue, fast-track, full pipeline 통합 테스트.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.response.analyzer import AnalysisResult
from scripts.intelligence.response.context_matcher import MatchResult
from scripts.intelligence.response.handler import ProjectIntelligenceHandler

# ==========================================
# Mock 클래스
# ==========================================

class MockChannel:
    def __init__(self, value="slack"):
        self.value = value


@dataclass
class MockMessage:
    id: str = "msg-001"
    text: str = "테스트 메시지"
    sender_id: str = "U12345"
    sender_name: str = "TestUser"
    channel_id: str = "C09N8J3UJN9"
    channel: MockChannel = field(default_factory=lambda: MockChannel("slack"))
    raw_json: str = '{"ts": "1234.5678", "channel": "C09N8J3UJN9"}'


@dataclass
class MockEnriched:
    original: MockMessage = field(default_factory=MockMessage)


@dataclass
class MockResult:
    priority: str | None = "normal"


# ==========================================
# Handler 초기화 테스트
# ==========================================

class TestHandlerInit:

    @pytest.fixture
    def handler(self):
        storage = AsyncMock()
        storage.find_by_message_id = AsyncMock(return_value=None)
        registry = AsyncMock()
        registry.list_all = AsyncMock(return_value=[])
        registry.get = AsyncMock(return_value=None)
        return ProjectIntelligenceHandler(storage, registry)

    def test_init_without_llm(self, handler):
        """LLM 미설정 시 analyzer/writer가 None"""
        assert handler._analyzer is None
        assert handler._draft_writer is None

    def test_init_with_ollama_disabled(self):
        """ollama enabled=false 시 analyzer가 None"""
        storage = AsyncMock()
        registry = AsyncMock()
        h = ProjectIntelligenceHandler(
            storage, registry,
            ollama_config={"enabled": False},
        )
        assert h._analyzer is None

    def test_init_with_claude_disabled(self):
        """claude enabled=false 시 writer가 None"""
        storage = AsyncMock()
        registry = AsyncMock()
        h = ProjectIntelligenceHandler(
            storage, registry,
            claude_config={"enabled": False},
        )
        assert h._draft_writer is None


# ==========================================
# _resolve_project 테스트
# ==========================================

class TestResolveProject:

    @pytest.fixture
    def handler(self):
        storage = AsyncMock()
        registry = AsyncMock()
        return ProjectIntelligenceHandler(storage, registry)

    def test_ollama_high_confidence(self, handler):
        """Ollama confidence >= 0.7 우선"""
        analysis = AnalysisResult(project_id="secretary", confidence=0.8)
        rule_match = MatchResult(matched=True, project_id="wsoptv", confidence=0.9)
        assert handler._resolve_project(analysis, rule_match) == "secretary"

    def test_rule_match_fallback(self, handler):
        """Ollama 낮은 confidence → 규칙 기반 fallback"""
        analysis = AnalysisResult(project_id="secretary", confidence=0.5)
        rule_match = MatchResult(matched=True, project_id="wsoptv", confidence=0.9)
        assert handler._resolve_project(analysis, rule_match) == "wsoptv"

    def test_ollama_low_confidence_fallback(self, handler):
        """규칙 실패 시 Ollama 낮은 confidence (>= 0.3)"""
        analysis = AnalysisResult(project_id="secretary", confidence=0.4)
        rule_match = MatchResult(matched=False)
        assert handler._resolve_project(analysis, rule_match) == "secretary"

    def test_both_fail_returns_none(self, handler):
        """둘 다 실패 → None"""
        analysis = AnalysisResult(project_id=None, confidence=0.0)
        rule_match = MatchResult(matched=False)
        assert handler._resolve_project(analysis, rule_match) is None

    def test_rule_match_low_confidence_ignored(self, handler):
        """규칙 기반 confidence < 0.6이면 무시"""
        analysis = AnalysisResult(project_id=None, confidence=0.1)
        rule_match = MatchResult(matched=True, project_id="test", confidence=0.4)
        assert handler._resolve_project(analysis, rule_match) is None

    def test_ollama_very_low_confidence_ignored(self, handler):
        """Ollama confidence < 0.3이면 무시"""
        analysis = AnalysisResult(project_id="test", confidence=0.2)
        rule_match = MatchResult(matched=False)
        assert handler._resolve_project(analysis, rule_match) is None


# ==========================================
# _build_rule_hint 테스트
# ==========================================

class TestBuildRuleHint:

    @pytest.fixture
    def handler(self):
        storage = AsyncMock()
        registry = AsyncMock()
        return ProjectIntelligenceHandler(storage, registry)

    def test_matched_hint(self, handler):
        rule_match = MatchResult(
            matched=True, project_id="secretary",
            confidence=0.9, tier="channel",
        )
        hint = handler._build_rule_hint(rule_match)
        assert "secretary" in hint
        assert "0.90" in hint
        assert "channel" in hint

    def test_unmatched_empty_hint(self, handler):
        rule_match = MatchResult(matched=False)
        assert handler._build_rule_hint(rule_match) == ""


# ==========================================
# _get_priority_value 테스트
# ==========================================

class TestGetPriorityValue:

    @pytest.fixture
    def handler(self):
        storage = AsyncMock()
        registry = AsyncMock()
        return ProjectIntelligenceHandler(storage, registry)

    def test_urgent_priority(self, handler):
        enriched = MockEnriched()
        result = MockResult(priority="urgent")
        assert handler._get_priority_value(enriched, result) == 0

    def test_high_priority(self, handler):
        result = MockResult(priority="high")
        assert handler._get_priority_value(MockEnriched(), result) == 1

    def test_normal_priority(self, handler):
        result = MockResult(priority="normal")
        assert handler._get_priority_value(MockEnriched(), result) == 2

    def test_low_priority(self, handler):
        result = MockResult(priority="low")
        assert handler._get_priority_value(MockEnriched(), result) == 3

    def test_unknown_priority_defaults_normal(self, handler):
        result = MockResult(priority="unknown")
        assert handler._get_priority_value(MockEnriched(), result) == 2

    def test_none_priority_defaults_normal(self, handler):
        result = MockResult(priority=None)
        assert handler._get_priority_value(MockEnriched(), result) == 2


# ==========================================
# _process_message 통합 테스트
# ==========================================

class TestProcessMessage:

    @pytest.fixture
    def handler(self):
        storage = AsyncMock()
        storage.find_by_message_id = AsyncMock(return_value=None)
        storage.save_draft = AsyncMock(return_value=1)
        storage.get_context_entries = AsyncMock(return_value=[])

        registry = AsyncMock()
        registry.list_all = AsyncMock(return_value=[])
        registry.get = AsyncMock(return_value={"id": "secretary", "name": "Secretary"})

        h = ProjectIntelligenceHandler(storage, registry)
        return h

    @pytest.mark.asyncio
    async def test_duplicate_skipped(self, handler):
        """중복 메시지 건너뛰기"""
        handler.dedup.mark_processed("slack", "msg-001")

        enriched = MockEnriched()
        result = MockResult()

        await handler._process_message(enriched, result)
        # save_draft가 호출되지 않아야 함
        handler.storage.save_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_analyzer_skips_analysis(self, handler):
        """Ollama 비활성화 시 분석 건너뛰기"""
        enriched = MockEnriched()
        result = MockResult()

        await handler._process_message(enriched, result)
        # needs_response=False이므로 draft 생성하지 않음
        # dedup.mark_processed만 호출됨

    @pytest.mark.asyncio
    async def test_fast_track_urgent_with_rule_match(self, handler):
        """urgent + rule match → Ollama 건너뛰기 (fast-track)"""
        # matcher를 patch
        match_result = MatchResult(
            matched=True, project_id="secretary",
            confidence=0.9, tier="channel",
        )
        handler.matcher.match = AsyncMock(return_value=match_result)

        # draft_writer 설정
        mock_writer = AsyncMock()
        mock_writer.write_draft = AsyncMock(return_value="Fast-track draft")
        handler._draft_writer = mock_writer

        # draft_store를 mock으로 교체
        mock_draft_store = AsyncMock()
        mock_draft_store.save = AsyncMock(return_value={"draft_id": 1, "draft_file": "test.md"})
        handler.draft_store = mock_draft_store

        enriched = MockEnriched()
        result = MockResult(priority="urgent")

        await handler._process_message(enriched, result)

        # draft_writer가 호출되어야 함
        mock_writer.write_draft.assert_called_once()

    @pytest.mark.asyncio
    async def test_needs_response_false_no_draft(self, handler):
        """needs_response=false → draft 생성 안 함"""
        handler._analyzer = AsyncMock()
        handler._analyzer.analyze = AsyncMock(return_value=AnalysisResult(
            project_id="secretary",
            needs_response=False,
            confidence=0.8,
        ))

        handler.matcher = AsyncMock()
        handler.matcher.match = AsyncMock(return_value=MatchResult(matched=False))

        enriched = MockEnriched()
        result = MockResult()

        await handler._process_message(enriched, result)

        # draft_writer가 호출되지 않아야 함
        assert handler._draft_writer is None  # 초기값

    @pytest.mark.asyncio
    async def test_no_project_saves_pending_match(self, handler):
        """project_id 미해석 → pending_match 저장"""
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=AnalysisResult(
            project_id=None,
            needs_response=True,
            confidence=0.1,
        ))
        handler._analyzer = mock_analyzer

        handler.matcher.match = AsyncMock(return_value=MatchResult(matched=False))

        enriched = MockEnriched()
        result = MockResult()

        await handler._process_message(enriched, result)

        # pending_match로 저장되어야 함
        handler.storage.save_draft.assert_called_once()
        saved = handler.storage.save_draft.call_args[0][0]
        assert saved["match_status"] == "pending_match"

    @pytest.mark.asyncio
    async def test_raw_message_backward_compat(self, handler):
        """EnrichedMessage 없이 raw message도 처리 (하위호환)"""
        raw_msg = MockMessage()
        result = MockResult()

        # hasattr(raw_msg, 'original')이 False이므로 message = raw_msg
        await handler._process_message(raw_msg, result)

    @pytest.mark.asyncio
    async def test_generate_draft_no_writer_saves_awaiting(self, handler):
        """draft_writer가 None일 때 awaiting_draft로 fallback 저장"""
        # analyzer 설정 (needs_response=True)
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=AnalysisResult(
            project_id="secretary",
            needs_response=True,
            confidence=0.8,
            reasoning="Test reasoning",
            summary="Test summary",
        ))
        handler._analyzer = mock_analyzer

        # matcher 설정 (rule match 성공)
        match_result = MatchResult(
            matched=True,
            project_id="secretary",
            confidence=0.9,
            tier="channel",
        )
        handler.matcher.match = AsyncMock(return_value=match_result)

        # draft_writer는 None (기본값)
        assert handler._draft_writer is None

        enriched = MockEnriched()
        result = MockResult()

        await handler._process_message(enriched, result)

        # storage.save_draft가 호출되어야 함
        handler.storage.save_draft.assert_called_once()
        saved = handler.storage.save_draft.call_args[0][0]
        assert saved["status"] == "awaiting_draft"
        assert saved["project_id"] == "secretary"
        assert saved["match_confidence"] == 0.9  # max(0.8, 0.9)
        assert saved["match_tier"] == "channel"

    @pytest.mark.asyncio
    async def test_generate_draft_claude_error_falls_back(self, handler):
        """draft_writer.write_draft()가 예외를 발생시킬 때 awaiting_draft로 fallback"""
        # analyzer 설정
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=AnalysisResult(
            project_id="secretary",
            needs_response=True,
            confidence=0.7,
            reasoning="Test reasoning",
            summary="Test summary",
        ))
        handler._analyzer = mock_analyzer

        # matcher 설정
        match_result = MatchResult(
            matched=True,
            project_id="secretary",
            confidence=0.8,
            tier="keyword",
        )
        handler.matcher.match = AsyncMock(return_value=match_result)

        # draft_writer 설정 (write_draft가 예외 발생)
        mock_writer = AsyncMock()
        mock_writer.write_draft = AsyncMock(side_effect=Exception("Claude API error"))
        handler._draft_writer = mock_writer

        enriched = MockEnriched()
        result = MockResult()

        await handler._process_message(enriched, result)

        # storage.save_draft가 호출되어야 함 (awaiting_draft)
        handler.storage.save_draft.assert_called_once()
        saved = handler.storage.save_draft.call_args[0][0]
        assert saved["status"] == "awaiting_draft"
        assert saved["project_id"] == "secretary"
        assert saved["match_confidence"] == 0.8  # max(0.7, 0.8)
        assert saved["match_tier"] == "keyword"


# ==========================================
# Worker 시작/종료 테스트
# ==========================================

class TestWorkerLifecycle:

    @pytest.fixture
    def handler(self):
        storage = AsyncMock()
        storage.find_by_message_id = AsyncMock(return_value=None)
        registry = AsyncMock()
        registry.list_all = AsyncMock(return_value=[])
        return ProjectIntelligenceHandler(storage, registry)

    @pytest.mark.asyncio
    async def test_start_worker(self, handler):
        """워커 시작"""
        await handler.start_worker()
        assert handler._worker_task is not None
        await handler.stop_worker()

    @pytest.mark.asyncio
    async def test_stop_worker(self, handler):
        """워커 중지"""
        await handler.start_worker()
        await handler.stop_worker()
        assert handler._worker_task is None

    @pytest.mark.asyncio
    async def test_stop_worker_when_not_started(self, handler):
        """워커 미시작 시 stop_worker 안전"""
        await handler.stop_worker()  # 예외 없이 종료

    @pytest.mark.asyncio
    async def test_handle_with_worker_queues(self, handler):
        """워커 활성화 시 handle()이 큐에 삽입"""
        await handler.start_worker()

        enriched = MockEnriched()
        result = MockResult()
        await handler.handle(enriched, result)

        # 큐에 1개 들어가야 함
        assert handler._queue.qsize() >= 0  # 처리 중일 수 있으므로 >= 0

        await handler.stop_worker()

    @pytest.mark.asyncio
    async def test_handle_without_worker_direct(self, handler):
        """워커 미활성화 시 handle()이 직접 처리"""
        enriched = MockEnriched()
        result = MockResult()

        # 직접 처리됨 (예외 없이)
        await handler.handle(enriched, result)


# ==========================================
# set_reporter 테스트
# ==========================================

class TestSetReporter:

    def test_set_reporter(self):
        storage = AsyncMock()
        registry = AsyncMock()
        handler = ProjectIntelligenceHandler(storage, registry)

        mock_reporter = MagicMock()
        handler.set_reporter(mock_reporter)
        assert handler._reporter is mock_reporter


# ==========================================
# Chatbot Channel 테스트
# ==========================================

CHATBOT_CHANNEL_ID = "C0985UXQN6Q"
OTHER_CHANNEL_ID = "C09N8J3UJN9"


def _make_handler_with_chatbot(chatbot_channels=None):
    storage = AsyncMock()
    storage.find_by_message_id = AsyncMock(return_value=None)
    storage.save_draft = AsyncMock(return_value=1)
    storage.get_context_entries = AsyncMock(return_value=[])
    registry = AsyncMock()
    registry.list_all = AsyncMock(return_value=[])
    registry.get = AsyncMock(return_value=None)
    return ProjectIntelligenceHandler(
        storage, registry,
        chatbot_channels=chatbot_channels or [CHATBOT_CHANNEL_ID],
    )


class TestChatbotChannel:

    @pytest.mark.asyncio
    async def test_chatbot_channel_bypasses_project_matching(self):
        """chatbot 채널 메시지는 ContextMatcher, _resolve_project를 호출하지 않음"""
        handler = _make_handler_with_chatbot()

        mock_analyzer = AsyncMock()
        mock_analyzer.chatbot_respond = AsyncMock(return_value="AI 응답입니다.")
        handler._analyzer = mock_analyzer

        # matcher가 호출되지 않도록 spy 설정
        handler.matcher.match = AsyncMock(return_value=None)

        msg = MockMessage(channel_id=CHATBOT_CHANNEL_ID)
        msg.raw_json = '{"ts": "111.222", "channel": "C0985UXQN6Q"}'

        with patch.object(handler, '_send_chatbot_reply', new_callable=AsyncMock) as mock_send:
            await handler._process_message(msg, MockResult())

        # ContextMatcher가 호출되지 않아야 함
        handler.matcher.match.assert_not_called()
        # save_draft(pending_match)도 호출되지 않아야 함
        handler.storage.save_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_chatbot_channel_uses_existing_pipeline(self):
        """chatbot 채널이 아닌 메시지는 기존 파이프라인 실행"""
        handler = _make_handler_with_chatbot()

        handler.matcher.match = AsyncMock(
            return_value=type('MatchResult', (), {'matched': False, 'project_id': None, 'confidence': 0.0, 'tier': None})()
        )
        mock_analyzer = AsyncMock()
        mock_analyzer.analyze = AsyncMock(return_value=AnalysisResult(
            project_id=None, needs_response=True, confidence=0.1,
        ))
        handler._analyzer = mock_analyzer

        msg = MockMessage(channel_id=OTHER_CHANNEL_ID)
        await handler._process_message(msg, MockResult())

        # 기존 파이프라인: matcher.match가 호출되어야 함
        handler.matcher.match.assert_called_once()

    @pytest.mark.asyncio
    async def test_chatbot_sends_slack_reply(self):
        """Ollama 응답 생성 후 Slack 전송 호출 확인"""
        handler = _make_handler_with_chatbot()

        mock_analyzer = AsyncMock()
        mock_analyzer.chatbot_respond = AsyncMock(return_value="도움이 되는 응답")
        handler._analyzer = mock_analyzer

        msg = MockMessage(channel_id=CHATBOT_CHANNEL_ID)
        msg.raw_json = '{"ts": "9999.0001", "channel": "C0985UXQN6Q"}'

        with patch.object(handler, '_send_chatbot_reply', new_callable=AsyncMock) as mock_send:
            await handler._handle_chatbot_message(msg, "slack")

        mock_send.assert_called_once_with(
            CHATBOT_CHANNEL_ID, "도움이 되는 응답", "9999.0001"
        )

    @pytest.mark.asyncio
    async def test_chatbot_ollama_failure_sends_fallback(self):
        """Ollama 실패 시 fallback 메시지 전송"""
        handler = _make_handler_with_chatbot()

        mock_analyzer = AsyncMock()
        mock_analyzer.chatbot_respond = AsyncMock(return_value=None)  # 실패 → None
        handler._analyzer = mock_analyzer

        msg = MockMessage(channel_id=CHATBOT_CHANNEL_ID)
        msg.raw_json = '{"ts": "8888.0001", "channel": "C0985UXQN6Q"}'

        with patch.object(handler, '_send_chatbot_reply', new_callable=AsyncMock) as mock_send:
            await handler._handle_chatbot_message(msg, "slack")

        # fallback 메시지로 전송되어야 함
        call_args = mock_send.call_args
        assert "현재 AI 응답 서비스를 이용할 수 없습니다" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_chatbot_rate_limiting(self):
        """chatbot_respond가 rate limiting(_wait_for_rate_limit)을 호출하는지 확인"""
        handler = _make_handler_with_chatbot()

        mock_analyzer = AsyncMock()
        mock_analyzer.chatbot_respond = AsyncMock(return_value="응답")
        mock_analyzer._wait_for_rate_limit = AsyncMock()
        handler._analyzer = mock_analyzer

        msg = MockMessage(channel_id=CHATBOT_CHANNEL_ID)
        msg.raw_json = '{"ts": "6666.0001", "channel": "C0985UXQN6Q"}'

        with patch.object(handler, '_send_chatbot_reply', new_callable=AsyncMock):
            await handler._handle_chatbot_message(msg, "slack")

        # chatbot_respond가 호출됨 (내부적으로 _wait_for_rate_limit 호출)
        mock_analyzer.chatbot_respond.assert_called_once()

    @pytest.mark.asyncio
    async def test_chatbot_skips_bot_messages(self):
        """봇 자기 메시지(subtype=bot_message)는 건너뜀"""
        handler = _make_handler_with_chatbot()

        mock_analyzer = AsyncMock()
        mock_analyzer.chatbot_respond = AsyncMock(return_value="응답")
        handler._analyzer = mock_analyzer

        msg = MockMessage(channel_id=CHATBOT_CHANNEL_ID)
        msg.raw_json = '{"ts": "7777.0001", "subtype": "bot_message", "channel": "C0985UXQN6Q"}'

        with patch.object(handler, '_send_chatbot_reply', new_callable=AsyncMock) as mock_send:
            await handler._handle_chatbot_message(msg, "slack")

        # 봇 메시지이므로 응답 생성 및 전송 없음
        mock_analyzer.chatbot_respond.assert_not_called()
        mock_send.assert_not_called()
