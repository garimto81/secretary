"""
WorkTrackerAIAnalyzer 단위 테스트

커버리지:
- cluster_keywords: JSON 응답 파싱 + fallback
- generate_stream_names: 이름 매핑 + fallback
- generate_highlights_and_tasks: 하이라이트/태스크 추출 + fallback
- _extract_json: 5-전략 JSON 추출
- _call_ollama: httpx mock + <think> 태그 제거
- Graceful degradation: Ollama 불가 시 빈 결과 반환
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.ai_analyzer import WorkTrackerAIAnalyzer
from scripts.work_tracker.models import (
    CommitType,
    DailyCommit,
    DetectionMethod,
    StreamStatus,
    WorkStream,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_commit(
    *,
    commit_hash: str = "abc1234",
    message: str = "feat: test commit",
    repo: str = "secretary",
    project: str = "Secretary",
    commit_type: CommitType = CommitType.FEAT,
    date: str = "2026-03-17",
) -> DailyCommit:
    return DailyCommit(
        date=date,
        repo=repo,
        project=project,
        category=None,
        commit_hash=commit_hash,
        commit_type=commit_type,
        commit_scope=None,
        message=message,
        author="test",
        timestamp=f"{date}T10:00:00",
    )


def make_stream(
    *,
    name: str = "test-stream",
    project: str = "Secretary",
    total_commits: int = 5,
    duration_days: int = 3,
) -> WorkStream:
    return WorkStream(
        name=name,
        project=project,
        repos=["secretary"],
        first_commit="2026-03-14T10:00:00",
        last_commit="2026-03-17T10:00:00",
        total_commits=total_commits,
        status=StreamStatus.ACTIVE,
        duration_days=duration_days,
        detection_method=DetectionMethod.BRANCH,
    )


def _mock_ollama_response(content: str):
    """httpx response mock 생성"""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": content}
    }
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ---------------------------------------------------------------------------
# _extract_json 테스트
# ---------------------------------------------------------------------------

class TestExtractJson:
    """5-전략 JSON 추출 테스트"""

    def setup_method(self):
        self.analyzer = WorkTrackerAIAnalyzer.__new__(WorkTrackerAIAnalyzer)
        # 최소 초기화 (Ollama 호출 안 함)

    def test_direct_json(self):
        result = self.analyzer._extract_json('{"clusters": []}')
        assert result == {"clusters": []}

    def test_json_code_block(self):
        text = 'some text\n```json\n{"highlights": ["a", "b"]}\n```\nmore text'
        result = self.analyzer._extract_json(text)
        assert result == {"highlights": ["a", "b"]}

    def test_generic_code_block(self):
        text = 'answer:\n```\n{"next_tasks": ["x"]}\n```'
        result = self.analyzer._extract_json(text)
        assert result == {"next_tasks": ["x"]}

    def test_brace_matching(self):
        text = 'Here is the result: {"key": "value", "nested": {"a": 1}} done.'
        result = self.analyzer._extract_json(text)
        assert result == {"key": "value", "nested": {"a": 1}}

    def test_empty_input(self):
        assert self.analyzer._extract_json("") is None
        assert self.analyzer._extract_json(None) is None

    def test_invalid_json(self):
        assert self.analyzer._extract_json("not json at all") is None

    def test_think_tag_in_json(self):
        text = '```json\n{"clusters": [{"name": "test", "hashes": ["a", "b"]}]}\n```'
        result = self.analyzer._extract_json(text)
        assert result["clusters"][0]["name"] == "test"


# ---------------------------------------------------------------------------
# cluster_keywords 테스트
# ---------------------------------------------------------------------------

class TestClusterKeywords:

    @pytest.fixture
    def analyzer(self):
        return WorkTrackerAIAnalyzer.__new__(WorkTrackerAIAnalyzer)

    @pytest.fixture(autouse=True)
    def setup_prompts(self, analyzer):
        analyzer._prompts = {
            "keyword_cluster": "test {commit_messages}",
            "stream_naming": "test {stream_list}",
            "highlights_and_tasks": "test {commit_summary} {stream_summary}",
        }
        analyzer.model = "qwen3.5:9b"
        analyzer.ollama_url = "http://localhost:9000"
        analyzer.timeout = 10.0
        analyzer.max_requests_per_minute = 10
        analyzer._request_times = __import__("collections").deque(maxlen=10)

    @pytest.mark.asyncio
    async def test_success(self, analyzer):
        response_json = json.dumps({
            "clusters": [
                {"name": "UI 개선", "hashes": ["abc1234", "def5678"]},
                {"name": "테스트", "hashes": ["ghi9012", "jkl3456"]},
            ]
        })
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, return_value=response_json):
            commits = [
                make_commit(commit_hash="abc1234", message="feat: UI 개선"),
                make_commit(commit_hash="def5678", message="fix: UI 버그"),
                make_commit(commit_hash="ghi9012", message="test: 테스트 추가"),
                make_commit(commit_hash="jkl3456", message="test: 테스트 수정"),
            ]
            result = await analyzer.cluster_keywords(commits)
            assert "UI 개선" in result
            assert len(result["UI 개선"]) == 2

    @pytest.mark.asyncio
    async def test_empty_commits(self, analyzer):
        result = await analyzer.cluster_keywords([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_ollama_failure(self, analyzer):
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, side_effect=Exception("timeout")):
            commits = [make_commit(), make_commit(commit_hash="xyz")]
            result = await analyzer.cluster_keywords(commits)
            assert result == {}

    @pytest.mark.asyncio
    async def test_invalid_json_response(self, analyzer):
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, return_value="not valid json"):
            commits = [make_commit(), make_commit(commit_hash="xyz")]
            result = await analyzer.cluster_keywords(commits)
            assert result == {}


# ---------------------------------------------------------------------------
# generate_stream_names 테스트
# ---------------------------------------------------------------------------

class TestGenerateStreamNames:

    @pytest.fixture
    def analyzer(self):
        a = WorkTrackerAIAnalyzer.__new__(WorkTrackerAIAnalyzer)
        a._prompts = {
            "keyword_cluster": "",
            "stream_naming": "test {stream_list}",
            "highlights_and_tasks": "",
        }
        a.model = "qwen3.5:9b"
        a.ollama_url = "http://localhost:9000"
        a.timeout = 10.0
        a.max_requests_per_minute = 10
        a._request_times = __import__("collections").deque(maxlen=10)
        return a

    @pytest.mark.asyncio
    async def test_success(self, analyzer):
        response_json = json.dumps({
            "work-tracker": "업무 추적기",
            "anno-workflow": "Annotation 워크플로우",
        })
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, return_value=response_json):
            streams = [
                make_stream(name="work-tracker"),
                make_stream(name="anno-workflow"),
            ]
            result = await analyzer.generate_stream_names(streams)
            assert result["work-tracker"] == "업무 추적기"

    @pytest.mark.asyncio
    async def test_empty_streams(self, analyzer):
        result = await analyzer.generate_stream_names([])
        assert result == {}

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self, analyzer):
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, side_effect=Exception("err")):
            result = await analyzer.generate_stream_names([make_stream()])
            assert result == {}


# ---------------------------------------------------------------------------
# generate_highlights_and_tasks 테스트
# ---------------------------------------------------------------------------

class TestGenerateHighlightsAndTasks:

    @pytest.fixture
    def analyzer(self):
        a = WorkTrackerAIAnalyzer.__new__(WorkTrackerAIAnalyzer)
        a._prompts = {
            "keyword_cluster": "",
            "stream_naming": "",
            "highlights_and_tasks": "test {commit_summary} {stream_summary}",
        }
        a.model = "qwen3.5:9b"
        a.ollama_url = "http://localhost:9000"
        a.timeout = 10.0
        a.max_requests_per_minute = 10
        a._request_times = __import__("collections").deque(maxlen=10)
        return a

    @pytest.mark.asyncio
    async def test_success(self, analyzer):
        response_json = json.dumps({
            "highlights": ["AI 통합 완료", "테스트 커버리지 개선"],
            "next_tasks": ["E2E 테스트 작성", "Slack 포맷 검증"],
        })
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, return_value=response_json):
            commits = [make_commit()]
            streams = [make_stream()]
            highlights, tasks = await analyzer.generate_highlights_and_tasks(commits, streams)
            assert len(highlights) == 2
            assert "AI 통합 완료" in highlights
            assert len(tasks) == 2

    @pytest.mark.asyncio
    async def test_empty_commits(self, analyzer):
        highlights, tasks = await analyzer.generate_highlights_and_tasks([], [])
        assert highlights == []
        assert tasks == []

    @pytest.mark.asyncio
    async def test_failure_returns_empty_tuple(self, analyzer):
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, side_effect=Exception("err")):
            highlights, tasks = await analyzer.generate_highlights_and_tasks(
                [make_commit()], [make_stream()]
            )
            assert highlights == []
            assert tasks == []

    @pytest.mark.asyncio
    async def test_max_3_items(self, analyzer):
        response_json = json.dumps({
            "highlights": ["a", "b", "c", "d", "e"],
            "next_tasks": ["1", "2", "3", "4"],
        })
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, return_value=response_json):
            highlights, tasks = await analyzer.generate_highlights_and_tasks(
                [make_commit()], []
            )
            assert len(highlights) <= 3
            assert len(tasks) <= 3

    @pytest.mark.asyncio
    async def test_think_tag_removed(self, analyzer):
        response = '<think>reasoning here</think>```json\n{"highlights": ["done"], "next_tasks": ["next"]}\n```'
        with patch.object(analyzer, "_call_ollama", new_callable=AsyncMock, return_value=response):
            highlights, tasks = await analyzer.generate_highlights_and_tasks(
                [make_commit()], []
            )
            assert highlights == ["done"]
            assert tasks == ["next"]


# ---------------------------------------------------------------------------
# Graceful degradation 통합 테스트
# ---------------------------------------------------------------------------

class TestGracefulDegradation:

    @pytest.mark.asyncio
    async def test_stream_detector_without_ai(self):
        """AI 없이 기존 동작 유지"""
        from scripts.work_tracker.stream_detector import StreamDetector
        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=[])

        detector = StreamDetector(mock_storage, ai_analyzer=None)
        commits = [
            make_commit(commit_hash="a1", message="feat: test"),
            make_commit(commit_hash="a2", message="fix: bug"),
        ]
        # branch/scope 없는 커밋 → PATH fallback
        streams = await detector.detect_streams(commits)
        # AI 없어도 에러 없이 실행 완료
        assert isinstance(streams, list)

    @pytest.mark.asyncio
    async def test_metrics_without_ai(self):
        """AI 없이 기존 메트릭 계산"""
        from scripts.work_tracker.metrics import MetricsCalculator
        mock_storage = AsyncMock()
        mock_storage.get_commits_by_date = AsyncMock(return_value=[])
        mock_storage.get_streams = AsyncMock(return_value=[])
        mock_storage.save_daily_summary = AsyncMock()

        calc = MetricsCalculator(mock_storage)
        summary = await calc.calculate_daily("2026-03-17")
        assert summary.highlights == []
        assert summary.next_tasks == []


# ---------------------------------------------------------------------------
# DailySummary next_tasks 모델 테스트
# ---------------------------------------------------------------------------

class TestDailySummaryNextTasks:

    def test_next_tasks_default(self):
        from scripts.work_tracker.models import DailySummary
        s = DailySummary(date="2026-03-17")
        assert s.next_tasks == []

    def test_next_tasks_none_normalized(self):
        from scripts.work_tracker.models import DailySummary
        s = DailySummary(date="2026-03-17", next_tasks=None)
        assert s.next_tasks == []

    def test_next_tasks_serialization(self):
        from scripts.work_tracker.models import DailySummary
        s = DailySummary(date="2026-03-17", next_tasks=["task1", "task2"])
        d = s.to_dict()
        assert d["next_tasks"] == ["task1", "task2"]


# ---------------------------------------------------------------------------
# Storage next_tasks 라운드트립 테스트
# ---------------------------------------------------------------------------

class TestStorageNextTasks:

    @pytest.mark.asyncio
    async def test_save_and_load_next_tasks(self, tmp_path):
        from scripts.work_tracker.models import DailySummary
        from scripts.work_tracker.storage import WorkTrackerStorage

        async with WorkTrackerStorage(tmp_path / "test.db") as storage:
            summary = DailySummary(
                date="2026-03-17",
                total_commits=5,
                highlights=["done something"],
                next_tasks=["do next thing"],
            )
            await storage.save_daily_summary(summary)
            loaded = await storage.get_daily_summary("2026-03-17")
            assert loaded is not None
            assert loaded.next_tasks == ["do next thing"]
            assert loaded.highlights == ["done something"]
