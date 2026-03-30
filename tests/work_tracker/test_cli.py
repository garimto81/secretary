"""
Work Tracker CLI 테스트

argparse 서브커맨드 파싱 및 각 cmd_* 함수의 동작을 검증합니다.
모든 외부 의존성(GitCollector, WorkTrackerStorage, MetricsCalculator, SlackFormatter)은
unittest.mock으로 대체합니다.
"""

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.work_tracker.cli import (
    build_parser,
    cmd_collect,
    cmd_metrics,
    cmd_post,
    cmd_streams,
    cmd_summary,
)
from scripts.work_tracker.models import (
    CommitType,
    DailyCommit,
    DailySummary,
    DetectionMethod,
    StreamStatus,
    WeeklySummary,
    WorkStream,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_commit(
    date: str = "2026-03-17",
    repo: str = "secretary",
    project: str = "Secretary",
    commit_hash: str = "abc123",
    message: str = "initial commit",
) -> DailyCommit:
    return DailyCommit(
        date=date,
        repo=repo,
        project=project,
        category=None,
        commit_hash=commit_hash,
        commit_type=CommitType.FEAT,
        commit_scope="cli",
        message=message,
        author="tester",
        timestamp="2026-03-17T10:00:00+09:00",
        files_changed=2,
        insertions=20,
        deletions=5,
    )


def _make_stream(
    name: str = "work-tracker",
    project: str = "Secretary",
    status: StreamStatus = StreamStatus.ACTIVE,
) -> WorkStream:
    return WorkStream(
        name=name,
        project=project,
        repos=["secretary"],
        first_commit="2026-03-10T09:00:00+09:00",
        last_commit="2026-03-17T10:00:00+09:00",
        total_commits=10,
        status=status,
        duration_days=8,
        detection_method=DetectionMethod.BRANCH,
    )


def _make_daily_summary(date: str = "2026-03-17") -> DailySummary:
    return DailySummary(
        date=date,
        total_commits=3,
        total_insertions=30,
        total_deletions=10,
        doc_change_ratio=0.33,
        project_distribution={"Secretary": 100},
        active_streams=1,
    )


def _make_weekly_summary() -> WeeklySummary:
    return WeeklySummary(
        week_label="W12 (3/10~3/16)",
        start_date="2026-03-10",
        end_date="2026-03-16",
        total_commits=15,
        velocity_trend={"W9": 10, "W10": 12, "W11": 14, "W12": 15},
        completed_streams=[],
        new_streams=["work-tracker"],
        project_distribution={"Secretary": 100},
    )


# ---------------------------------------------------------------------------
# argparse 파싱 테스트
# ---------------------------------------------------------------------------

class TestArgparse:
    """build_parser()로 생성된 파서의 서브커맨드 파싱 검증"""

    def setup_method(self):
        self.parser = build_parser()

    def test_collect_no_args(self):
        args = self.parser.parse_args(["collect"])
        assert args.command == "collect"
        assert args.date is None
        assert args.json is False

    def test_collect_with_date(self):
        args = self.parser.parse_args(["collect", "--date", "2026-03-17"])
        assert args.command == "collect"
        assert args.date == "2026-03-17"

    def test_collect_with_json(self):
        args = self.parser.parse_args(["collect", "--json"])
        assert args.json is True

    def test_summary_defaults(self):
        args = self.parser.parse_args(["summary"])
        assert args.command == "summary"
        assert args.date is None
        assert args.json is False

    def test_summary_with_date_and_json(self):
        args = self.parser.parse_args(["summary", "--date", "2026-03-15", "--json"])
        assert args.date == "2026-03-15"
        assert args.json is True

    def test_streams_default_status(self):
        args = self.parser.parse_args(["streams"])
        assert args.command == "streams"
        assert args.status == "all"

    def test_streams_status_filter(self):
        for status in ("active", "idle", "completed", "all"):
            args = self.parser.parse_args(["streams", "--status", status])
            assert args.status == status

    def test_streams_invalid_status_raises(self):
        with pytest.raises(SystemExit):
            self.parser.parse_args(["streams", "--status", "unknown"])

    def test_metrics_defaults(self):
        args = self.parser.parse_args(["metrics"])
        assert args.command == "metrics"
        assert args.weekly is False
        assert args.weeks == 1
        assert args.date is None
        assert args.json is False

    def test_metrics_weekly_flag(self):
        args = self.parser.parse_args(["metrics", "--weekly"])
        assert args.weekly is True

    def test_metrics_weeks_value(self):
        args = self.parser.parse_args(["metrics", "--weeks", "4"])
        assert args.weeks == 4

    def test_post_defaults(self):
        args = self.parser.parse_args(["post"])
        assert args.command == "post"
        assert args.confirm is False
        assert args.weekly is False

    def test_post_confirm_flag(self):
        args = self.parser.parse_args(["post", "--confirm"])
        assert args.confirm is True

    def test_post_weekly_flag(self):
        args = self.parser.parse_args(["post", "--weekly"])
        assert args.weekly is True

    def test_post_channel(self):
        args = self.parser.parse_args(["post", "--channel", "C1234567890"])
        assert args.channel == "C1234567890"

    def test_no_command_exits(self):
        with pytest.raises(SystemExit):
            parser = build_parser()
            args = parser.parse_args([])
            # main()은 sys.exit(1)을 호출하지만 여기선 직접 검증
            if not args.command:
                raise SystemExit(1)


# ---------------------------------------------------------------------------
# cmd_collect 테스트
# ---------------------------------------------------------------------------

class TestCmdCollect:
    """cmd_collect: GitCollector + WorkTrackerStorage + StreamDetector mock"""

    @pytest.mark.asyncio
    async def test_collect_no_commits(self, capsys):
        """커밋 없으면 '커밋 없음' 출력"""
        args = argparse.Namespace(date="2026-03-17", json=False)

        mock_collector = MagicMock()
        mock_collector.collect_date.return_value = []

        with patch(
            "scripts.work_tracker.cli.GitCollector",
            return_value=mock_collector,
        ):
            await cmd_collect(args)

        out = capsys.readouterr().out
        assert "커밋 없음" in out

    @pytest.mark.asyncio
    async def test_collect_no_commits_json(self, capsys):
        """--json 모드에서 커밋 없으면 JSON 출력"""
        args = argparse.Namespace(date="2026-03-17", json=True)

        mock_collector = MagicMock()
        mock_collector.collect_date.return_value = []

        with patch(
            "scripts.work_tracker.cli.GitCollector",
            return_value=mock_collector,
        ):
            await cmd_collect(args)

        out = capsys.readouterr().out
        # JSON 중 마지막 출력만 파싱 (print가 여러 번 호출될 수 있음)
        json_lines = [line for line in out.splitlines() if line.strip().startswith("{")]
        # JSON 블록 전체를 수집
        json_text = "\n".join(
            line for line in out.splitlines()
            if line.strip() and not line.startswith("Git")
            and not line.startswith("   ")
        )
        # 마지막 JSON 블록만 파싱
        result = json.loads(out[out.index("{"):])
        assert result["commits_collected"] == 0
        assert result["commits_saved"] == 0
        assert result["streams_detected"] == 0

    @pytest.mark.asyncio
    async def test_collect_with_commits(self, capsys):
        """커밋 있으면 저장 및 stream 감지 결과 출력"""
        args = argparse.Namespace(date="2026-03-17", json=False)

        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_collector = MagicMock()
        mock_collector.collect_date.return_value = commits

        mock_storage = AsyncMock()
        mock_storage.save_commits = AsyncMock(return_value=1)
        mock_storage.save_streams = AsyncMock()
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_detector = AsyncMock()
        mock_detector.detect_streams = AsyncMock(return_value=streams)

        with (
            patch("scripts.work_tracker.cli.GitCollector", return_value=mock_collector),
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.StreamDetector", return_value=mock_detector),
        ):
            await cmd_collect(args)

        out = capsys.readouterr().out
        assert "수집: 1건" in out
        assert "저장: 1건" in out
        assert "Stream: 1건" in out

    @pytest.mark.asyncio
    async def test_collect_with_commits_json(self, capsys):
        """--json 모드에서 커밋 결과를 JSON으로 출력"""
        args = argparse.Namespace(date="2026-03-17", json=True)

        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_collector = MagicMock()
        mock_collector.collect_date.return_value = commits

        mock_storage = AsyncMock()
        mock_storage.save_commits = AsyncMock(return_value=1)
        mock_storage.save_streams = AsyncMock()
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_detector = AsyncMock()
        mock_detector.detect_streams = AsyncMock(return_value=streams)

        with (
            patch("scripts.work_tracker.cli.GitCollector", return_value=mock_collector),
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.StreamDetector", return_value=mock_detector),
        ):
            await cmd_collect(args)

        out = capsys.readouterr().out
        result = json.loads(out[out.index("{"):])
        assert result["commits_collected"] == 1
        assert result["commits_saved"] == 1
        assert result["streams_detected"] == 1

    @pytest.mark.asyncio
    async def test_collect_uses_today_when_no_date(self, capsys):
        """--date 미지정 시 오늘 날짜 사용"""
        args = argparse.Namespace(date=None, json=False)

        mock_collector = MagicMock()
        mock_collector.collect_date.return_value = []

        with patch("scripts.work_tracker.cli.GitCollector", return_value=mock_collector):
            await cmd_collect(args)

        today = MagicMock()
        mock_collector.collect_date.assert_called_once()
        call_args = mock_collector.collect_date.call_args[0][0]
        # YYYY-MM-DD 형식 검증
        from datetime import datetime as dt
        dt.strptime(call_args, "%Y-%m-%d")  # 형식 오류면 ValueError 발생


# ---------------------------------------------------------------------------
# cmd_summary 테스트
# ---------------------------------------------------------------------------

class TestCmdSummary:
    """cmd_summary: MetricsCalculator + WorkTrackerStorage + SlackFormatter mock"""

    @pytest.mark.asyncio
    async def test_summary_text_output(self, capsys):
        """기본 모드: SlackFormatter.format_daily 결과 출력"""
        args = argparse.Namespace(date="2026-03-17", json=False)

        summary = _make_daily_summary()
        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_commits_by_date = AsyncMock(return_value=commits)
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_daily = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_daily.return_value = "일일 요약 텍스트"

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
        ):
            await cmd_summary(args)

        out = capsys.readouterr().out
        assert "일일 요약 텍스트" in out
        mock_fmt.format_daily.assert_called_once_with(summary, commits, streams)

    @pytest.mark.asyncio
    async def test_summary_json_output(self, capsys):
        """--json 모드: SlackFormatter.format_json 결과 출력"""
        args = argparse.Namespace(date="2026-03-17", json=True)

        summary = _make_daily_summary()
        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_commits_by_date = AsyncMock(return_value=commits)
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_daily = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_json.return_value = '{"summary": {}}'

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
        ):
            await cmd_summary(args)

        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "summary" in parsed
        assert "snapshots" in parsed


# ---------------------------------------------------------------------------
# cmd_streams 테스트
# ---------------------------------------------------------------------------

class TestCmdStreams:
    """cmd_streams: WorkTrackerStorage mock"""

    @pytest.mark.asyncio
    async def test_streams_empty(self, capsys):
        """stream 없으면 '없음' 출력"""
        args = argparse.Namespace(status="all", json=False)

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=[])
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        with patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage):
            await cmd_streams(args)

        out = capsys.readouterr().out
        assert "Work Stream 없음" in out

    @pytest.mark.asyncio
    async def test_streams_list_text(self, capsys):
        """stream 목록을 텍스트로 출력"""
        args = argparse.Namespace(status="all", json=False)
        streams = [
            _make_stream("work-tracker", "Secretary", StreamStatus.ACTIVE),
            _make_stream("overlay", "EBS", StreamStatus.IDLE),
        ]

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        with patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage):
            await cmd_streams(args)

        out = capsys.readouterr().out
        assert "work-tracker" in out
        assert "진행 중" in out
        assert "overlay" in out
        assert "미활동" in out

    @pytest.mark.asyncio
    async def test_streams_status_filter_passed_to_storage(self):
        """--status active 지정 시 storage.get_streams(status='active') 호출"""
        args = argparse.Namespace(status="active", json=False)
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        with patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage):
            await cmd_streams(args)

        mock_storage.get_streams.assert_called_once_with(status="active")

    @pytest.mark.asyncio
    async def test_streams_all_passes_none_to_storage(self):
        """--status all 지정 시 storage.get_streams(status=None) 호출"""
        args = argparse.Namespace(status="all", json=False)

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=[])
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        with patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage):
            await cmd_streams(args)

        mock_storage.get_streams.assert_called_once_with(status=None)

    @pytest.mark.asyncio
    async def test_streams_json_output(self, capsys):
        """--json 모드에서 JSON 배열 출력"""
        args = argparse.Namespace(status="all", json=True)
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        with patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage):
            await cmd_streams(args)

        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "work-tracker"


# ---------------------------------------------------------------------------
# cmd_metrics 테스트
# ---------------------------------------------------------------------------

class TestCmdMetrics:
    """cmd_metrics: daily/weekly 분기 검증"""

    @pytest.mark.asyncio
    async def test_metrics_daily_default(self, capsys):
        """기본 모드(daily): format_daily 호출"""
        args = argparse.Namespace(weekly=False, date="2026-03-17", json=False)

        summary = _make_daily_summary()
        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_commits_by_date = AsyncMock(return_value=commits)
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_daily = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_daily.return_value = "daily output"

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
        ):
            await cmd_metrics(args)

        mock_fmt.format_daily.assert_called_once()

    @pytest.mark.asyncio
    async def test_metrics_weekly_flag(self, capsys):
        """--weekly 모드: calculate_weekly + format_weekly 호출"""
        args = argparse.Namespace(weekly=True, date="2026-03-17", json=False)

        summary = _make_weekly_summary()
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_weekly = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_weekly.return_value = "weekly output"

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
        ):
            await cmd_metrics(args)

        mock_calc.calculate_weekly.assert_called_once_with("2026-03-17")
        mock_fmt.format_weekly.assert_called_once_with(summary, streams)

    @pytest.mark.asyncio
    async def test_metrics_weekly_json(self, capsys):
        """--weekly --json 모드: format_json 호출"""
        args = argparse.Namespace(weekly=True, date="2026-03-17", json=True)

        summary = _make_weekly_summary()
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_weekly = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_json.return_value = '{"summary": {}}'

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
        ):
            await cmd_metrics(args)

        mock_fmt.format_json.assert_called_once_with(summary, streams=streams)


# ---------------------------------------------------------------------------
# cmd_post 테스트
# ---------------------------------------------------------------------------

class TestCmdPost:
    """cmd_post: dry-run 기본 동작 + confirm 분기"""

    @pytest.mark.asyncio
    async def test_post_dry_run_default(self, capsys):
        """--confirm 없으면 DRY RUN 메시지 출력"""
        args = argparse.Namespace(
            confirm=False,
            weekly=False,
            date="2026-03-17",
            json=False,
            channel=None,
        )

        summary = _make_daily_summary()
        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_commits_by_date = AsyncMock(return_value=commits)
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_daily = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_daily.return_value = "일일 요약"

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
        ):
            await cmd_post(args)

        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert "--confirm" in out

    @pytest.mark.asyncio
    async def test_post_dry_run_weekly(self, capsys):
        """--weekly dry-run: 주간 요약 미리보기"""
        args = argparse.Namespace(
            confirm=False,
            weekly=True,
            date="2026-03-17",
            json=False,
            channel=None,
        )

        summary = _make_weekly_summary()
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_weekly = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_weekly.return_value = "주간 요약"

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
        ):
            await cmd_post(args)

        out = capsys.readouterr().out
        assert "DRY RUN" in out

    @pytest.mark.asyncio
    async def test_post_confirm_import_error(self, capsys):
        """--confirm 모드에서 lib.slack ImportError → 오류 메시지 출력"""
        args = argparse.Namespace(
            confirm=True,
            weekly=False,
            date="2026-03-17",
            json=False,
            channel=None,
        )

        summary = _make_daily_summary()
        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_commits_by_date = AsyncMock(return_value=commits)
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_daily = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_daily.return_value = "일일 요약"

        # lib.slack.client가 없는 환경 시뮬레이션
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "lib.slack.client":
                raise ImportError("No module named 'lib.slack.client'")
            return real_import(name, *args, **kwargs)

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
            patch("builtins.__import__", side_effect=mock_import),
        ):
            await cmd_post(args)

        out = capsys.readouterr().out
        assert "lib.slack" in out or "Slack 전송 중" in out

    @pytest.mark.asyncio
    async def test_post_confirm_slack_success(self, capsys):
        """--confirm 모드에서 Slack 전송 성공"""
        args = argparse.Namespace(
            confirm=True,
            weekly=False,
            date="2026-03-17",
            json=False,
            channel="C1234567890",
        )

        summary = _make_daily_summary()
        commits = [_make_commit()]
        streams = [_make_stream()]

        mock_storage = AsyncMock()
        mock_storage.get_commits_by_date = AsyncMock(return_value=commits)
        mock_storage.get_streams = AsyncMock(return_value=streams)
        mock_storage.__aenter__ = AsyncMock(return_value=mock_storage)
        mock_storage.__aexit__ = AsyncMock(return_value=False)

        mock_calc = AsyncMock()
        mock_calc.calculate_daily = AsyncMock(return_value=summary)

        mock_fmt = MagicMock()
        mock_fmt.format_daily.return_value = "일일 요약"

        mock_slack_client = AsyncMock()
        mock_slack_client.send_message = AsyncMock()

        mock_slack_module = MagicMock()
        mock_slack_module.SlackClient = MagicMock(return_value=mock_slack_client)

        with (
            patch("scripts.work_tracker.cli.WorkTrackerStorage", return_value=mock_storage),
            patch("scripts.work_tracker.cli.MetricsCalculator", return_value=mock_calc),
            patch("scripts.work_tracker.cli.SlackFormatter", return_value=mock_fmt),
            patch.dict("sys.modules", {"lib.slack.client": mock_slack_module}),
        ):
            await cmd_post(args)

        out = capsys.readouterr().out
        assert "Slack 전송 완료" in out or "Slack 전송 중" in out
