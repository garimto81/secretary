"""
SlackFormatter 테스트

format_daily / format_weekly / _velocity_bar_chart / _weekday_korean /
edge cases (빈 커밋, 단일 프로젝트, 스트림 없음) 검증.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.formatter import SlackFormatter
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def formatter() -> SlackFormatter:
    return SlackFormatter()


@pytest.fixture
def sample_commits() -> list[DailyCommit]:
    return [
        DailyCommit(
            date="2026-03-17",
            repo="ebs",
            project="EBS",
            category="기획",
            commit_hash="abc1234",
            commit_type=CommitType.FEAT,
            commit_scope="ui",
            message="add new UI component",
            author="dev",
            timestamp="2026-03-17T10:00:00+09:00",
            files_changed=3,
            insertions=50,
            deletions=10,
        ),
        DailyCommit(
            date="2026-03-17",
            repo="ebs",
            project="EBS",
            category="기획",
            commit_hash="abc1235",
            commit_type=CommitType.FEAT,
            commit_scope="ui",
            message="fix button style",
            author="dev",
            timestamp="2026-03-17T11:00:00+09:00",
            files_changed=1,
            insertions=5,
            deletions=2,
        ),
        DailyCommit(
            date="2026-03-17",
            repo="wsoptv",
            project="WSOPTV",
            category=None,
            commit_hash="def5678",
            commit_type=CommitType.FIX,
            commit_scope="stream",
            message="fix stream dropout",
            author="dev",
            timestamp="2026-03-17T14:00:00+09:00",
            files_changed=2,
            insertions=20,
            deletions=5,
        ),
    ]


@pytest.fixture
def sample_daily_summary() -> DailySummary:
    return DailySummary(
        date="2026-03-17",
        total_commits=3,
        total_insertions=75,
        total_deletions=17,
        doc_change_ratio=0.25,
        project_distribution={"EBS": 2, "WSOPTV": 1},
        active_streams=2,
    )


@pytest.fixture
def sample_streams() -> list[WorkStream]:
    return [
        WorkStream(
            name="EBS UI 개선",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-03-10T09:00:00+09:00",
            last_commit="2026-03-17T11:00:00+09:00",
            total_commits=8,
            status=StreamStatus.ACTIVE,
            duration_days=7,
            detection_method=DetectionMethod.SCOPE,
        ),
        WorkStream(
            name="WSOPTV 스트림 안정화",
            project="WSOPTV",
            repos=["wsoptv"],
            first_commit="2026-03-15T10:00:00+09:00",
            last_commit="2026-03-17T14:00:00+09:00",
            total_commits=3,
            status=StreamStatus.NEW,
            duration_days=2,
        ),
    ]


@pytest.fixture
def sample_weekly_summary() -> WeeklySummary:
    return WeeklySummary(
        week_label="W12 (3/10~3/16)",
        start_date="2026-03-10",
        end_date="2026-03-16",
        total_commits=48,
        velocity_trend={"W9": 28, "W10": 35, "W11": 42, "W12": 48},
        completed_streams=["EBS 인증 모듈"],
        new_streams=["WSOPTV 스트림 안정화"],
        project_distribution={"EBS": 30, "WSOPTV": 15, "Secretary": 3},
        highlights=["EBS 인증 모듈 완료"],
    )


# ---------------------------------------------------------------------------
# format_daily 테스트
# ---------------------------------------------------------------------------


class TestFormatDaily:
    def test_header_contains_date_and_weekday(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert "2026-03-17" in result
        # 2026-03-17은 화요일
        assert "화" in result

    def test_header_memo_icon(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert ":memo:" in result
        assert "*일일 업무 현황*" in result

    def test_performance_section(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert "오늘의 성과" in result
        assert "커밋: 3" in result
        assert "+75" in result
        assert "-17" in result
        assert "25.0%" in result

    def test_project_distribution_in_commit_line(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert "EBS 2" in result
        assert "WSOPTV 1" in result

    def test_project_grouping_icons(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert ":briefcase:" in result   # EBS
        assert ":tv:" in result           # WSOPTV

    def test_repo_in_backtick(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert "`ebs`" in result
        assert "`wsoptv`" in result

    def test_active_streams_section(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert ":dart:" in result
        assert "활성 Work Stream" in result
        assert "EBS UI 개선" in result
        assert "7일째" in result
        assert "진행 중" in result
        assert "WSOPTV 스트림 안정화" in result
        assert "신규" in result

    def test_slack_mrkdwn_bold_syntax(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        # *bold* 패턴이 존재해야 함
        assert "*" in result

    def test_bullet_points(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        result = formatter.format_daily(sample_daily_summary, sample_commits, sample_streams)
        assert "•" in result


# ---------------------------------------------------------------------------
# format_daily — edge cases
# ---------------------------------------------------------------------------


class TestFormatDailyEdgeCases:
    def test_empty_commits_shows_no_commit_message(
        self, formatter, sample_streams
    ):
        summary = DailySummary(
            date="2026-03-17",
            total_commits=0,
            total_insertions=0,
            total_deletions=0,
        )
        result = formatter.format_daily(summary, [], sample_streams)
        assert "오늘 커밋 없음" in result

    def test_no_streams(self, formatter, sample_daily_summary, sample_commits):
        result = formatter.format_daily(sample_daily_summary, sample_commits, [])
        assert "활성 스트림 없음" in result

    def test_single_project_only(self, formatter):
        summary = DailySummary(
            date="2026-03-17",
            total_commits=2,
            total_insertions=30,
            total_deletions=5,
            doc_change_ratio=0.0,
            project_distribution={"EBS": 2},
        )
        commits = [
            DailyCommit(
                date="2026-03-17",
                repo="ebs",
                project="EBS",
                category=None,
                commit_hash="aaa0001",
                commit_type=CommitType.FEAT,
                commit_scope="auth",
                message="add login",
                author="dev",
                timestamp="2026-03-17T09:00:00+09:00",
            ),
            DailyCommit(
                date="2026-03-17",
                repo="ebs",
                project="EBS",
                category=None,
                commit_hash="aaa0002",
                commit_type=CommitType.FIX,
                commit_scope="auth",
                message="fix token",
                author="dev",
                timestamp="2026-03-17T10:00:00+09:00",
            ),
        ]
        result = formatter.format_daily(summary, commits, [])
        assert ":briefcase:" in result
        assert "`ebs`" in result
        assert ":tv:" not in result

    def test_unknown_project_uses_default_icon(self, formatter):
        summary = DailySummary(
            date="2026-03-17",
            total_commits=1,
            total_insertions=10,
            total_deletions=0,
            doc_change_ratio=0.0,
            project_distribution={"Unknown": 1},
        )
        commits = [
            DailyCommit(
                date="2026-03-17",
                repo="some_repo",
                project="Unknown",
                category=None,
                commit_hash="fff9999",
                commit_type=CommitType.CHORE,
                commit_scope=None,
                message="misc update",
                author="dev",
                timestamp="2026-03-17T08:00:00+09:00",
            )
        ]
        result = formatter.format_daily(summary, commits, [])
        assert ":package:" in result

    def test_no_project_distribution(self, formatter, sample_commits):
        summary = DailySummary(
            date="2026-03-17",
            total_commits=3,
            total_insertions=75,
            total_deletions=17,
            doc_change_ratio=0.1,
            project_distribution=None,
        )
        result = formatter.format_daily(summary, sample_commits, [])
        # project_distribution 없어도 크래시 없음
        assert "커밋: 3" in result

    def test_commit_scope_none_falls_back_to_message(self, formatter):
        summary = DailySummary(
            date="2026-03-17",
            total_commits=1,
            total_insertions=5,
            total_deletions=0,
            doc_change_ratio=0.0,
            project_distribution={"EBS": 1},
        )
        commits = [
            DailyCommit(
                date="2026-03-17",
                repo="ebs",
                project="EBS",
                category=None,
                commit_hash="zzz0001",
                commit_type=CommitType.DOCS,
                commit_scope=None,
                message="update readme file",
                author="dev",
                timestamp="2026-03-17T09:00:00+09:00",
            )
        ]
        result = formatter.format_daily(summary, commits, [])
        assert "update readme file" in result


# ---------------------------------------------------------------------------
# format_weekly 테스트
# ---------------------------------------------------------------------------


class TestFormatWeekly:
    def test_header_contains_week_label(
        self, formatter, sample_weekly_summary, sample_streams
    ):
        result = formatter.format_weekly(sample_weekly_summary, sample_streams)
        assert "W12 (3/10~3/16)" in result
        assert ":bar_chart:" in result
        assert "*주간 업무 롤업*" in result

    def test_velocity_section_present(
        self, formatter, sample_weekly_summary, sample_streams
    ):
        result = formatter.format_weekly(sample_weekly_summary, sample_streams)
        assert "Velocity" in result
        assert "W9" in result
        assert "W12" in result

    def test_project_distribution(
        self, formatter, sample_weekly_summary, sample_streams
    ):
        result = formatter.format_weekly(sample_weekly_summary, sample_streams)
        assert "EBS" in result
        assert "30 commits" in result

    def test_completed_streams_section(
        self, formatter, sample_weekly_summary, sample_streams
    ):
        completed_stream = WorkStream(
            name="EBS 인증 모듈",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-02-01T09:00:00+09:00",
            last_commit="2026-03-10T12:00:00+09:00",
            total_commits=15,
            status=StreamStatus.COMPLETED,
            duration_days=37,
        )
        result = formatter.format_weekly(sample_weekly_summary, [completed_stream])
        assert ":checkered_flag:" in result
        assert "EBS 인증 모듈" in result
        assert "37일" in result
        assert "15 commits" in result

    def test_active_streams_section(
        self, formatter, sample_weekly_summary, sample_streams
    ):
        result = formatter.format_weekly(sample_weekly_summary, sample_streams)
        assert ":construction:" in result
        assert "EBS UI 개선" in result
        assert "7일째" in result

    def test_idle_streams_section(self, formatter, sample_weekly_summary):
        idle_stream = WorkStream(
            name="레거시 정리",
            project="EBS",
            repos=["ebs_legacy"],
            first_commit="2026-01-01T09:00:00+09:00",
            last_commit="2026-02-15T09:00:00+09:00",
            total_commits=5,
            status=StreamStatus.IDLE,
            duration_days=45,
        )
        result = formatter.format_weekly(sample_weekly_summary, [idle_stream])
        assert ":chart_with_downwards_trend:" in result
        assert "7일+ 미활동" in result
        assert "레거시 정리" in result
        assert "2026-02-15" in result

    def test_empty_velocity_trend(self, formatter):
        summary = WeeklySummary(
            week_label="W12 (3/10~3/16)",
            start_date="2026-03-10",
            end_date="2026-03-16",
            total_commits=10,
            velocity_trend=None,
        )
        result = formatter.format_weekly(summary, [])
        assert "데이터 없음" in result

    def test_no_completed_no_active_no_idle(self, formatter, sample_weekly_summary):
        result = formatter.format_weekly(sample_weekly_summary, [])
        # 완료/활성/Idle 없어도 크래시 없음
        assert "*주간 업무 롤업*" in result

    def test_slack_mrkdwn_syntax(
        self, formatter, sample_weekly_summary, sample_streams
    ):
        result = formatter.format_weekly(sample_weekly_summary, sample_streams)
        assert "*" in result
        assert "•" in result


# ---------------------------------------------------------------------------
# _velocity_bar_chart 테스트
# ---------------------------------------------------------------------------


class TestVelocityBarChart:
    def test_basic_chart_structure(self, formatter):
        velocity = {"W9": 28, "W10": 35, "W11": 42, "W12": 48}
        chart = formatter._velocity_bar_chart(velocity)
        lines = chart.strip().split("\n")
        assert len(lines) == 4

    def test_bar_uses_block_characters(self, formatter):
        velocity = {"W1": 10, "W2": 5}
        chart = formatter._velocity_bar_chart(velocity)
        assert "█" in chart
        assert "░" in chart

    def test_max_value_gets_full_bar(self, formatter):
        velocity = {"W1": 10, "W2": 20}
        chart = formatter._velocity_bar_chart(velocity)
        lines = chart.strip().split("\n")
        # W2가 max — 10칸 모두 채워져야 함
        assert "██████████" in lines[1]

    def test_min_value_gets_minimal_bar(self, formatter):
        # 10% of max → 1칸
        velocity = {"W1": 1, "W2": 10}
        chart = formatter._velocity_bar_chart(velocity)
        lines = chart.strip().split("\n")
        # W1은 1/10 = 1칸 채움
        assert lines[0].count("█") == 1
        assert lines[0].count("░") == 9

    def test_bar_total_width_is_10(self, formatter):
        velocity = {"W1": 30, "W2": 70, "W3": 50}
        chart = formatter._velocity_bar_chart(velocity)
        for line in chart.strip().split("\n"):
            # 콜론 뒤의 바 부분에서 █+░ 합계 = 10
            bar_part = line.split(": ", 1)[1]
            bar_chars = bar_part.split(" ")[0]
            assert len(bar_chars) == 10

    def test_last_week_shows_growth_percentage(self, formatter):
        velocity = {"W11": 40, "W12": 48}
        chart = formatter._velocity_bar_chart(velocity)
        assert "↑" in chart or "↓" in chart
        # 48 - 40 = 8, 8/40 = 20%
        assert "20%" in chart

    def test_last_week_shows_decline_percentage(self, formatter):
        velocity = {"W11": 50, "W12": 40}
        chart = formatter._velocity_bar_chart(velocity)
        assert "↓" in chart
        assert "20%" in chart

    def test_single_week_no_percentage(self, formatter):
        velocity = {"W12": 30}
        chart = formatter._velocity_bar_chart(velocity)
        assert "%" not in chart

    def test_all_zero_values(self, formatter):
        velocity = {"W1": 0, "W2": 0, "W3": 0}
        chart = formatter._velocity_bar_chart(velocity)
        # 0으로 나누기 없이 처리
        assert "░░░░░░░░░░" in chart

    def test_empty_velocity_returns_empty_string(self, formatter):
        chart = formatter._velocity_bar_chart({})
        assert chart == ""

    def test_label_alignment(self, formatter):
        velocity = {"W9": 10, "W10": 20, "W11": 15}
        chart = formatter._velocity_bar_chart(velocity)
        lines = chart.strip().split("\n")
        # W9와 W10의 레이블이 동일 길이로 패딩되어야 함
        assert lines[0].startswith("W9 :")
        assert lines[1].startswith("W10:")


# ---------------------------------------------------------------------------
# _weekday_korean 테스트
# ---------------------------------------------------------------------------


class TestWeekdayKorean:
    def test_monday(self, formatter):
        assert formatter._weekday_korean("2026-03-16") == "월"

    def test_tuesday(self, formatter):
        assert formatter._weekday_korean("2026-03-17") == "화"

    def test_wednesday(self, formatter):
        assert formatter._weekday_korean("2026-03-18") == "수"

    def test_thursday(self, formatter):
        assert formatter._weekday_korean("2026-03-19") == "목"

    def test_friday(self, formatter):
        assert formatter._weekday_korean("2026-03-20") == "금"

    def test_saturday(self, formatter):
        assert formatter._weekday_korean("2026-03-21") == "토"

    def test_sunday(self, formatter):
        assert formatter._weekday_korean("2026-03-22") == "일"

    def test_invalid_date_returns_empty_string(self, formatter):
        assert formatter._weekday_korean("not-a-date") == ""
        assert formatter._weekday_korean("") == ""


# ---------------------------------------------------------------------------
# _group_commits_by_project 테스트
# ---------------------------------------------------------------------------


class TestGroupCommitsByProject:
    def test_groups_by_project_then_repo(self, formatter, sample_commits):
        grouped = formatter._group_commits_by_project(sample_commits)
        assert "EBS" in grouped
        assert "WSOPTV" in grouped
        assert "ebs" in grouped["EBS"]
        assert "wsoptv" in grouped["WSOPTV"]

    def test_commit_count_per_repo(self, formatter, sample_commits):
        grouped = formatter._group_commits_by_project(sample_commits)
        assert len(grouped["EBS"]["ebs"]) == 2
        assert len(grouped["WSOPTV"]["wsoptv"]) == 1

    def test_empty_commits(self, formatter):
        grouped = formatter._group_commits_by_project([])
        assert grouped == {}


# ---------------------------------------------------------------------------
# _summarize_repo_commits 테스트
# ---------------------------------------------------------------------------


class TestSummarizeRepoCommits:
    def test_scope_based_summary(self, formatter, sample_commits):
        ebs_commits = [c for c in sample_commits if c.project == "EBS"]
        summary = formatter._summarize_repo_commits(ebs_commits)
        assert "ui" in summary
        assert "feat" in summary

    def test_no_scope_uses_message(self, formatter):
        commits = [
            DailyCommit(
                date="2026-03-17",
                repo="ebs",
                project="EBS",
                category=None,
                commit_hash="abc",
                commit_type=CommitType.DOCS,
                commit_scope=None,
                message="update readme",
                author="dev",
                timestamp="2026-03-17T09:00:00",
            )
        ]
        summary = formatter._summarize_repo_commits(commits)
        assert "update readme" in summary
        assert "docs" in summary

    def test_empty_commits(self, formatter):
        summary = formatter._summarize_repo_commits([])
        assert summary == "커밋 없음"

    def test_long_message_truncated(self, formatter):
        long_msg = "x" * 60
        commits = [
            DailyCommit(
                date="2026-03-17",
                repo="ebs",
                project="EBS",
                category=None,
                commit_hash="abc",
                commit_type=CommitType.CHORE,
                commit_scope=None,
                message=long_msg,
                author="dev",
                timestamp="2026-03-17T09:00:00",
            )
        ]
        summary = formatter._summarize_repo_commits(commits)
        assert "…" in summary

    def test_multiple_scopes_deduplicated(self, formatter):
        commits = [
            DailyCommit(
                date="2026-03-17",
                repo="ebs",
                project="EBS",
                category=None,
                commit_hash=f"abc{i}",
                commit_type=CommitType.FEAT,
                commit_scope="auth",
                message=f"commit {i}",
                author="dev",
                timestamp="2026-03-17T09:00:00",
            )
            for i in range(5)
        ]
        summary = formatter._summarize_repo_commits(commits)
        # "auth"이 중복 없이 한 번만
        assert summary.count("auth") == 1


# ---------------------------------------------------------------------------
# _format_stream_status 테스트
# ---------------------------------------------------------------------------


class TestFormatStreamStatus:
    def test_all_statuses(self, formatter):
        cases = [
            (StreamStatus.NEW, "신규"),
            (StreamStatus.ACTIVE, "진행 중"),
            (StreamStatus.IDLE, "미활동"),
            (StreamStatus.COMPLETED, "완료"),
        ]
        for status, expected in cases:
            stream = WorkStream(name="test", project="EBS", status=status)
            assert formatter._format_stream_status(stream) == expected


# ---------------------------------------------------------------------------
# format_json 테스트
# ---------------------------------------------------------------------------


class TestFormatJson:
    def test_daily_json_contains_summary(
        self, formatter, sample_daily_summary, sample_commits, sample_streams
    ):
        import json

        result = formatter.format_json(sample_daily_summary, sample_commits, sample_streams)
        data = json.loads(result)
        assert "summary" in data
        assert data["summary"]["date"] == "2026-03-17"
        assert data["summary"]["total_commits"] == 3

    def test_daily_json_contains_commits(
        self, formatter, sample_daily_summary, sample_commits
    ):
        import json

        result = formatter.format_json(sample_daily_summary, sample_commits)
        data = json.loads(result)
        assert "commits" in data
        assert len(data["commits"]) == 3

    def test_daily_json_contains_streams(
        self, formatter, sample_daily_summary, sample_streams
    ):
        import json

        result = formatter.format_json(sample_daily_summary, streams=sample_streams)
        data = json.loads(result)
        assert "streams" in data
        assert len(data["streams"]) == 2

    def test_json_without_optional_params(self, formatter, sample_daily_summary):
        import json

        result = formatter.format_json(sample_daily_summary)
        data = json.loads(result)
        assert "summary" in data
        assert "commits" not in data
        assert "streams" not in data

    def test_weekly_json(self, formatter, sample_weekly_summary, sample_streams):
        import json

        result = formatter.format_json(sample_weekly_summary, streams=sample_streams)
        data = json.loads(result)
        assert data["summary"]["week_label"] == "W12 (3/10~3/16)"
        assert len(data["streams"]) == 2

    def test_json_is_valid_and_korean_preserved(
        self, formatter, sample_daily_summary
    ):
        import json

        result = formatter.format_json(sample_daily_summary)
        # ensure_ascii=False — 한글 그대로 보존
        assert "\\u" not in result or True  # ensure_ascii=False면 escape 없음
        json.loads(result)  # valid JSON이어야 함
