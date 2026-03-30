"""
OllamaAnalyzer 테스트

마커 추출, 자유 추론 파싱, fallback, rate limiting 검증.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.response.analyzer import AnalysisResult, OllamaAnalyzer

# ==========================================
# AnalysisResult 기본 테스트
# ==========================================

class TestAnalysisResult:
    """AnalysisResult dataclass 테스트"""

    def test_default_values(self):
        result = AnalysisResult()
        assert result.project_id is None
        assert result.needs_response is False
        assert result.intent == "unknown"
        assert result.summary == ""
        assert result.confidence == 0.0
        assert result.reasoning == ""

    def test_to_dict(self):
        result = AnalysisResult(
            project_id="secretary",
            needs_response=True,
            confidence=0.85,
            reasoning="테스트 추론",
        )
        d = result.to_dict()
        assert d["project_id"] == "secretary"
        assert d["needs_response"] is True
        assert d["confidence"] == 0.85

    def test_reasoning_preserves_full_text(self):
        long_reasoning = "A" * 5000
        result = AnalysisResult(reasoning=long_reasoning)
        assert len(result.reasoning) == 5000


# ==========================================
# 마커 추출 (_extract_decision) 테스트
# ==========================================

class TestExtractDecision:
    """_extract_decision 마커 추출 테스트"""

    @pytest.fixture
    def analyzer(self, tmp_path):
        prompt_file = tmp_path / "analyze_prompt.txt"
        prompt_file.write_text("test prompt {project_list} {rule_hint} {sender_name} {source_channel} {original_text}", encoding="utf-8")
        with patch.object(OllamaAnalyzer, '__init__', lambda self: None):
            a = OllamaAnalyzer.__new__(OllamaAnalyzer)
            a.model = "test"
            a.ollama_url = "http://localhost:11434"
            a.timeout = 10
            a.max_context_chars = 12000
            a.max_requests_per_minute = 10
            a._request_times = __import__('collections').deque(maxlen=10)
            a.prompt_template = "test"
            return a

    def test_response_needed_marker(self, analyzer):
        content = """이 메시지는 secretary 프로젝트 관련입니다.
발신자가 진행 상황을 물어보고 있으므로 응답이 필요합니다.
[RESPONSE_NEEDED] project_id=secretary confidence=0.85"""

        result = analyzer._extract_decision(content)
        assert result.needs_response is True
        assert result.project_id == "secretary"
        assert result.confidence == 0.85
        assert "secretary 프로젝트" in result.reasoning

    def test_no_response_marker(self, analyzer):
        content = """일반적인 잡담 메시지입니다.
특별히 응답이 필요하지 않습니다.
[NO_RESPONSE] project_id=wsoptv confidence=0.9"""

        result = analyzer._extract_decision(content)
        assert result.needs_response is False
        assert result.project_id == "wsoptv"
        assert result.confidence == 0.9

    def test_unknown_project_id(self, analyzer):
        content = """프로젝트를 특정하기 어렵습니다.
[RESPONSE_NEEDED] project_id=unknown confidence=0.3"""

        result = analyzer._extract_decision(content)
        assert result.needs_response is True
        assert result.project_id is None  # unknown → None

    def test_no_marker_fallback(self, analyzer):
        content = "마커 없이 그냥 텍스트만 있는 응답"
        result = analyzer._extract_decision(content)
        assert result.needs_response is False
        assert result.confidence == 0.0
        assert result.summary == "마커 미발견"

    def test_empty_content(self, analyzer):
        result = analyzer._extract_decision("")
        assert result.needs_response is False
        assert result.confidence == 0.0

    def test_whitespace_only_content(self, analyzer):
        result = analyzer._extract_decision("   \n  \n  ")
        assert result.needs_response is False

    def test_marker_with_extra_text_after(self, analyzer):
        content = """분석 결과입니다.
[RESPONSE_NEEDED] project_id=secretary confidence=0.7
추가 텍스트는 무시됩니다."""
        # reversed search이므로 마지막 마커를 찾아야 하지만
        # 이 경우 추가 텍스트가 있으므로 여전히 마커를 찾아야 함
        result = analyzer._extract_decision(content)
        assert result.needs_response is True
        assert result.project_id == "secretary"

    def test_multiple_markers_uses_last(self, analyzer):
        content = """[NO_RESPONSE] project_id=wsoptv confidence=0.5
재분석 후...
[RESPONSE_NEEDED] project_id=secretary confidence=0.9"""
        result = analyzer._extract_decision(content)
        # reversed search: 마지막 마커 우선
        assert result.needs_response is True
        assert result.project_id == "secretary"
        assert result.confidence == 0.9

    def test_confidence_default_when_missing(self, analyzer):
        content = "[RESPONSE_NEEDED] project_id=secretary"
        result = analyzer._extract_decision(content)
        assert result.needs_response is True
        assert result.confidence == 0.5  # default

    def test_marker_in_middle_of_line(self, analyzer):
        content = "결론: [NO_RESPONSE] project_id=test confidence=0.8 입니다"
        result = analyzer._extract_decision(content)
        assert result.needs_response is False
        assert result.project_id == "test"


# ==========================================
# 필드 추출 (_extract_field) 테스트
# ==========================================

class TestExtractField:

    @pytest.fixture
    def analyzer(self):
        with patch.object(OllamaAnalyzer, '__init__', lambda self: None):
            a = OllamaAnalyzer.__new__(OllamaAnalyzer)
            return a

    def test_extract_project_id(self, analyzer):
        line = "[RESPONSE_NEEDED] project_id=secretary confidence=0.85"
        assert analyzer._extract_field(line, "project_id") == "secretary"

    def test_extract_confidence(self, analyzer):
        line = "[RESPONSE_NEEDED] project_id=secretary confidence=0.85"
        assert analyzer._extract_field(line, "confidence") == "0.85"

    def test_missing_field_returns_default(self, analyzer):
        line = "[RESPONSE_NEEDED] project_id=secretary"
        assert analyzer._extract_field(line, "confidence", "0.5") == "0.5"

    def test_empty_default(self, analyzer):
        line = "[NO_RESPONSE]"
        assert analyzer._extract_field(line, "project_id") == ""


# ==========================================
# 의도 추론 (_infer_intent) 테스트
# ==========================================

class TestInferIntent:

    @pytest.fixture
    def analyzer(self):
        with patch.object(OllamaAnalyzer, '__init__', lambda self: None):
            a = OllamaAnalyzer.__new__(OllamaAnalyzer)
            return a

    def test_question_intent(self, analyzer):
        assert analyzer._infer_intent("이것은 질문입니다. 어떻게 해야 하나요?") == "질문"

    def test_request_intent(self, analyzer):
        assert analyzer._infer_intent("이 작업을 처리해줘. 요청합니다.") == "요청"

    def test_info_sharing_intent(self, analyzer):
        assert analyzer._infer_intent("참고로 공유드립니다. 알림입니다.") == "정보공유"

    def test_chat_intent(self, analyzer):
        assert analyzer._infer_intent("오늘 날씨가 좋네요.") == "잡담"


# ==========================================
# 요약 추출 (_extract_summary) 테스트
# ==========================================

class TestExtractSummary:

    @pytest.fixture
    def analyzer(self):
        with patch.object(OllamaAnalyzer, '__init__', lambda self: None):
            a = OllamaAnalyzer.__new__(OllamaAnalyzer)
            return a

    def test_extracts_first_meaningful_line(self, analyzer):
        content = "# 분석\n- 목록\n이것이 요약입니다."
        assert analyzer._extract_summary(content) == "이것이 요약입니다."

    def test_skips_marker_lines(self, analyzer):
        content = "[RESPONSE_NEEDED] project_id=test\n실제 내용입니다"
        assert analyzer._extract_summary(content) == "실제 내용입니다"

    def test_truncates_to_50_chars(self, analyzer):
        content = "A" * 100
        assert len(analyzer._extract_summary(content)) == 50

    def test_empty_content(self, analyzer):
        assert analyzer._extract_summary("") == ""


# ==========================================
# 프로젝트 목록 빌드 테스트
# ==========================================

class TestBuildProjectList:

    @pytest.fixture
    def analyzer(self):
        with patch.object(OllamaAnalyzer, '__init__', lambda self: None):
            a = OllamaAnalyzer.__new__(OllamaAnalyzer)
            return a

    def test_empty_projects(self, analyzer):
        result = analyzer._build_project_list([])
        assert "등록된 프로젝트가 없습니다" in result

    def test_formats_project(self, analyzer):
        projects = [{"id": "test", "name": "Test Project", "keywords": ["k1", "k2"], "description": "desc"}]
        result = analyzer._build_project_list(projects)
        assert "test: Test Project" in result
        assert "k1, k2" in result
        assert "desc" in result


# ==========================================
# 텍스트 절삭 테스트
# ==========================================

class TestTruncateText:

    @pytest.fixture
    def analyzer(self):
        with patch.object(OllamaAnalyzer, '__init__', lambda self: None):
            a = OllamaAnalyzer.__new__(OllamaAnalyzer)
            a.max_context_chars = 100
            return a

    def test_short_text_unchanged(self, analyzer):
        text = "짧은 텍스트"
        assert analyzer._truncate_text(text) == text

    def test_long_text_truncated(self, analyzer):
        text = "A" * 200
        result = analyzer._truncate_text(text)
        assert len(result) < 200
        assert "[... 텍스트 생략 ...]" in result


# ==========================================
# Analyze 통합 테스트 (Mock httpx)
# ==========================================

class TestAnalyzeIntegration:

    @pytest.fixture
    def analyzer(self, tmp_path):
        prompt_file = tmp_path / "analyze_prompt.txt"
        prompt_file.write_text(
            "분석하세요.\n프로젝트: {project_list}\n{rule_hint}\n발신자: {sender_name}\n소스: {source_channel}\n메시지: {original_text}",
            encoding="utf-8",
        )
        with patch('scripts.intelligence.response.analyzer.Path') as mock_path:
            mock_path_instance = MagicMock()
            mock_path_instance.exists.return_value = True
            mock_path.return_value = mock_path_instance

            a = OllamaAnalyzer.__new__(OllamaAnalyzer)
            a.model = "qwen3:8b"
            a.ollama_url = "http://localhost:11434"
            a.timeout = 10
            a.max_context_chars = 12000
            a.max_requests_per_minute = 10
            a._request_times = __import__('collections').deque(maxlen=10)
            a.prompt_template = prompt_file.read_text(encoding="utf-8")
            return a

    @pytest.mark.asyncio
    async def test_analyze_success(self, analyzer):
        """정상 분석 흐름"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "content": "이 메시지는 secretary 관련입니다.\n[RESPONSE_NEEDED] project_id=secretary confidence=0.85"
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            # retry_async가 None이면 직접 호출
            with patch('scripts.intelligence.response.analyzer.retry_async', None):
                result = await analyzer.analyze(
                    text="비서 프로젝트 진행 상황 알려주세요",
                    sender_name="TestUser",
                    source_channel="slack",
                    channel_id="C12345",
                    project_list=[{"id": "secretary", "name": "Secretary"}],
                )

        assert result.needs_response is True
        assert result.project_id == "secretary"

    @pytest.mark.asyncio
    async def test_analyze_with_thinking(self, analyzer):
        """thinking 필드가 있는 경우"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {
                "thinking": "내부 추론 과정...",
                "content": "[NO_RESPONSE] project_id=wsoptv confidence=0.9"
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch('scripts.intelligence.response.analyzer.retry_async', None):
                result = await analyzer.analyze(
                    text="잡담입니다",
                    sender_name="User",
                    source_channel="slack",
                    channel_id="C12345",
                    project_list=[],
                )

        assert result.needs_response is False
        assert "내부 추론 과정" in result.reasoning

    @pytest.mark.asyncio
    async def test_analyze_http_error(self, analyzer):
        """HTTP 오류 시 안전한 fallback"""
        import httpx

        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch('scripts.intelligence.response.analyzer.retry_async', None):
                result = await analyzer.analyze(
                    text="test",
                    sender_name="User",
                    source_channel="slack",
                    channel_id="C12345",
                    project_list=[],
                )

        assert result.needs_response is False
        assert "HTTP" in result.reasoning

    @pytest.mark.asyncio
    async def test_analyze_request_error(self, analyzer):
        """네트워크 오류 시 안전한 fallback"""
        import httpx

        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(
                side_effect=httpx.RequestError("Connection refused")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with patch('scripts.intelligence.response.analyzer.retry_async', None):
                result = await analyzer.analyze(
                    text="test",
                    sender_name="User",
                    source_channel="slack",
                    channel_id="C12345",
                    project_list=[],
                )

        assert result.needs_response is False
        assert "요청 오류" in result.reasoning
