"""
MetricsCalculator 단위 + 통합 테스트

커버리지:
- calculate_daily: 일일 지표 계산 + 저장
- calculate_weekly: 주간 지표 계산 + 저장
- velocity_trend: 최근 N주 velocity
- _get_week_range: 엣지 케이스 (월요일/일요일/주중)
- _calculate_project_distribution: 단일/다중/빈 프로젝트
- _calculate_doc_ratio: DOCS 타입 비율
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.metrics import MetricsCalculator
from scripts.work_tracker.models import (
    CommitType,
    DailyCommit,
    StreamStatus,
    WorkStream,
)
from scripts.work_tracker.storage import WorkTrackerStorage


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_commit(
    date_str: str = "2026-03-17",
    project: str = "EBS",
    commit_type: CommitType = CommitType.FEAT,
    hash_suffix: str = "0001",
    insertions: int = 10,
    deletions: int = 5,
) -> DailyCommit:
    return DailyCommit(
        date=date_str,
        repo="test_repo",
        project=project,
        category=None,
        commit_hash=f"abc{hash_suffix}",
        commit_type=commit_type,
        commit_scope=None,
        message="test commit",
        author="tester",
        timestamp=f"{date_str}T10:00:00",
        insertions=insertions,
        deletions=deletions,
    )


# ---------------------------------------------------------------------------
# _calculate_doc_ratio
# ---------------------------------------------------------------------------

class TestCalculateDocRatio:
    def setup_method(self):
        # MetricsCalculator는 storage가 필요하지만 순수 메서드 테스트엔 None 가능
        # (단위 테스트는 storage를 호출하지 않음)
        self.calc = MetricsCalculator.__new__(MetricsCalculator)

    def test_empty_commits_returns_zero(self):
        assert self.calc._calculate_doc_ratio([]) == 0.0

    def test_no_docs_commits_returns_zero(self):
        commits = [
            make_commit(commit_type=CommitType.FEAT, hash_suffix="1"),
            make_commit(commit_type=CommitType.FIX, hash_suffix="2"),
        ]
        assert self.calc._calculate_doc_ratio(commits) == 0.0

    def test_all_docs_commits_returns_one(self):
        commits = [
            make_commit(commit_type=CommitType.DOCS, hash_suffix="1"),
            make_commit(commit_type=CommitType.DOCS, hash_suffix="2"),
        ]
        assert self.calc._calculate_doc_ratio(commits) == 1.0

    def test_mixed_commits_correct_ratio(self):
        commits = [
            make_commit(commit_type=CommitType.DOCS, hash_suffix="1"),
            make_commit(commit_type=CommitType.FEAT, hash_suffix="2"),
            make_commit(commit_type=CommitType.DOCS, hash_suffix="3"),
            make_commit(commit_type=CommitType.FIX, hash_suffix="4"),
        ]
        # 2/4 = 0.5
        assert self.calc._calculate_doc_ratio(commits) == pytest.approx(0.5)

    def test_single_doc_commit(self):
        commits = [make_commit(commit_type=CommitType.DOCS, hash_suffix="1")]
        assert self.calc._calculate_doc_ratio(commits) == 1.0

    def test_single_non_doc_commit(self):
        commits = [make_commit(commit_type=CommitType.FEAT, hash_suffix="1")]
        assert self.calc._calculate_doc_ratio(commits) == 0.0


# ---------------------------------------------------------------------------
# _calculate_project_distribution
# ---------------------------------------------------------------------------

class TestCalculateProjectDistribution:
    def setup_method(self):
        self.calc = MetricsCalculator.__new__(MetricsCalculator)

    def test_empty_commits_returns_empty_dict(self):
        assert self.calc._calculate_project_distribution([]) == {}

    def test_single_project_returns_100(self):
        commits = [make_commit(project="EBS", hash_suffix=str(i)) for i in range(5)]
        result = self.calc._calculate_project_distribution(commits)
        assert result == {"EBS": 100}

    def test_two_equal_projects(self):
        commits = [
            make_commit(project="EBS", hash_suffix=str(i)) for i in range(3)
        ] + [
            make_commit(project="WSOPTV", hash_suffix=str(i + 10)) for i in range(3)
        ]
        result = self.calc._calculate_project_distribution(commits)
        assert result == {"EBS": 50, "WSOPTV": 50}
        assert sum(result.values()) == 100

    def test_three_projects_sum_100(self):
        # EBS: 6, WSOPTV: 3, Secretary: 1 → 60%, 30%, 10%
        commits = (
            [make_commit(project="EBS", hash_suffix=str(i)) for i in range(6)]
            + [make_commit(project="WSOPTV", hash_suffix=str(i + 10)) for i in range(3)]
            + [make_commit(project="Secretary", hash_suffix="99")]
        )
        result = self.calc._calculate_project_distribution(commits)
        assert sum(result.values()) == 100
        assert result["EBS"] == 60
        assert result["WSOPTV"] == 30
        assert result["Secretary"] == 10

    def test_uneven_split_sums_to_100(self):
        # 3 projects: 1/3 each → 33.33... each → must round to 100 total
        commits = [
            make_commit(project="EBS", hash_suffix="1"),
            make_commit(project="WSOPTV", hash_suffix="2"),
            make_commit(project="Secretary", hash_suffix="3"),
        ]
        result = self.calc._calculate_project_distribution(commits)
        assert sum(result.values()) == 100
        # Each should be 33 or 34
        for v in result.values():
            assert v in (33, 34)

    def test_single_commit(self):
        commits = [make_commit(project="EBS", hash_suffix="1")]
        result = self.calc._calculate_project_distribution(commits)
        assert result == {"EBS": 100}
        assert sum(result.values()) == 100


# ---------------------------------------------------------------------------
# _get_week_range
# ---------------------------------------------------------------------------

class TestGetWeekRange:
    def setup_method(self):
        self.calc = MetricsCalculator.__new__(MetricsCalculator)

    def test_monday_is_start_of_week(self):
        # 2026-03-16 is Monday
        start, end = self.calc._get_week_range("2026-03-16")
        assert start == "2026-03-16"
        assert end == "2026-03-22"

    def test_sunday_is_end_of_week(self):
        # 2026-03-22 is Sunday
        start, end = self.calc._get_week_range("2026-03-22")
        assert start == "2026-03-16"
        assert end == "2026-03-22"

    def test_mid_week_wednesday(self):
        # 2026-03-18 is Wednesday
        start, end = self.calc._get_week_range("2026-03-18")
        assert start == "2026-03-16"
        assert end == "2026-03-22"

    def test_week_spans_month_boundary(self):
        # 2026-03-31 is Tuesday — week spans March/April
        start, end = self.calc._get_week_range("2026-03-31")
        assert start == "2026-03-30"   # Monday
        assert end == "2026-04-05"     # Sunday

    def test_week_spans_year_boundary(self):
        # 2026-01-01 is Thursday — week includes Dec 2025
        start, end = self.calc._get_week_range("2026-01-01")
        assert start == "2025-12-29"   # Monday
        assert end == "2026-01-04"     # Sunday

    def test_start_and_end_differ_by_6_days(self):
        for day_offset in range(7):
            dt = date(2026, 3, 16) + timedelta(days=day_offset)
            start, end = self.calc._get_week_range(dt.isoformat())
            start_dt = date.fromisoformat(start)
            end_dt = date.fromisoformat(end)
            assert (end_dt - start_dt).days == 6
            # start must be Monday
            assert start_dt.weekday() == 0
            # end must be Sunday
            assert end_dt.weekday() == 6


# ---------------------------------------------------------------------------
# _get_week_label
# ---------------------------------------------------------------------------

class TestGetWeekLabel:
    def setup_method(self):
        self.calc = MetricsCalculator.__new__(MetricsCalculator)

    def test_standard_label_format(self):
        # W12: 2026-03-16 ~ 2026-03-22
        label = self.calc._get_week_label("2026-03-16", "2026-03-22")
        assert label == "W12 (3/16~3/22)"

    def test_single_digit_month(self):
        # Jan week
        label = self.calc._get_week_label("2026-01-05", "2026-01-11")
        assert label == "W2 (1/5~1/11)"

    def test_month_boundary_week(self):
        label = self.calc._get_week_label("2026-03-30", "2026-04-05")
        assert label == "W14 (3/30~4/5)"


# ---------------------------------------------------------------------------
# calculate_daily — integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_daily_empty(storage):
    calc = MetricsCalculator(storage)
    summary = await calc.calculate_daily("2026-03-17")

    assert summary.date == "2026-03-17"
    assert summary.total_commits == 0
    assert summary.total_insertions == 0
    assert summary.total_deletions == 0
    assert summary.doc_change_ratio == 0.0
    assert summary.project_distribution == {}
    assert summary.active_streams == 0


@pytest.mark.asyncio
async def test_calculate_daily_with_commits(storage):
    commits = [
        make_commit(
            date_str="2026-03-17",
            project="EBS",
            commit_type=CommitType.FEAT,
            hash_suffix="A1",
            insertions=100,
            deletions=20,
        ),
        make_commit(
            date_str="2026-03-17",
            project="EBS",
            commit_type=CommitType.DOCS,
            hash_suffix="A2",
            insertions=50,
            deletions=10,
        ),
        make_commit(
            date_str="2026-03-17",
            project="WSOPTV",
            commit_type=CommitType.FIX,
            hash_suffix="A3",
            insertions=30,
            deletions=5,
        ),
    ]
    await storage.save_commits(commits)

    calc = MetricsCalculator(storage)
    summary = await calc.calculate_daily("2026-03-17")

    assert summary.total_commits == 3
    assert summary.total_insertions == 180
    assert summary.total_deletions == 35
    assert summary.doc_change_ratio == pytest.approx(1 / 3)
    assert sum(summary.project_distribution.values()) == 100
    assert "EBS" in summary.project_distribution
    assert "WSOPTV" in summary.project_distribution


@pytest.mark.asyncio
async def test_calculate_daily_counts_active_streams(storage):
    stream = WorkStream(
        name="EBS UI",
        project="EBS",
        repos=["ebs"],
        first_commit="2026-03-10T00:00:00",
        last_commit="2026-03-17T00:00:00",
        total_commits=5,
        status=StreamStatus.ACTIVE,
    )
    await storage.save_streams([stream])

    calc = MetricsCalculator(storage)
    summary = await calc.calculate_daily("2026-03-17")

    assert summary.active_streams == 1


@pytest.mark.asyncio
async def test_calculate_daily_persists_summary(storage):
    commits = [
        make_commit(date_str="2026-03-17", hash_suffix="P1"),
    ]
    await storage.save_commits(commits)

    calc = MetricsCalculator(storage)
    await calc.calculate_daily("2026-03-17")

    persisted = await storage.get_daily_summary("2026-03-17")
    assert persisted is not None
    assert persisted.total_commits == 1


# ---------------------------------------------------------------------------
# calculate_weekly — integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_calculate_weekly_empty(storage):
    calc = MetricsCalculator(storage)
    summary = await calc.calculate_weekly("2026-03-22")

    # W12: 2026-03-16 ~ 2026-03-22
    assert summary.start_date == "2026-03-16"
    assert summary.end_date == "2026-03-22"
    assert "W12" in summary.week_label
    assert summary.total_commits == 0
    assert summary.completed_streams == []
    assert summary.new_streams == []


@pytest.mark.asyncio
async def test_calculate_weekly_with_commits(storage):
    # 5 commits across the week
    commits = [
        make_commit(date_str="2026-03-16", project="EBS", hash_suffix="W1"),
        make_commit(date_str="2026-03-17", project="EBS", hash_suffix="W2"),
        make_commit(date_str="2026-03-18", project="WSOPTV", hash_suffix="W3"),
        make_commit(date_str="2026-03-19", project="EBS", hash_suffix="W4"),
        make_commit(date_str="2026-03-22", project="Secretary", hash_suffix="W5"),
    ]
    await storage.save_commits(commits)

    calc = MetricsCalculator(storage)
    summary = await calc.calculate_weekly("2026-03-22")

    assert summary.total_commits == 5
    assert sum(summary.project_distribution.values()) == 100
    assert "EBS" in summary.project_distribution


@pytest.mark.asyncio
async def test_calculate_weekly_excludes_out_of_range(storage):
    # Commits outside the week range should not be counted
    in_week = make_commit(date_str="2026-03-17", project="EBS", hash_suffix="IN1")
    out_of_week = make_commit(date_str="2026-03-09", project="EBS", hash_suffix="OUT1")
    await storage.save_commits([in_week, out_of_week])

    calc = MetricsCalculator(storage)
    summary = await calc.calculate_weekly("2026-03-22")

    assert summary.total_commits == 1


@pytest.mark.asyncio
async def test_calculate_weekly_streams_classification(storage):
    completed = WorkStream(
        name="Old Feature",
        project="EBS",
        repos=["ebs"],
        first_commit="2026-01-01T00:00:00",
        last_commit="2026-02-01T00:00:00",
        total_commits=10,
        status=StreamStatus.COMPLETED,
    )
    new_stream = WorkStream(
        name="New Feature",
        project="WSOPTV",
        repos=["wsoptv"],
        first_commit="2026-03-17T00:00:00",
        last_commit="2026-03-17T00:00:00",
        total_commits=1,
        status=StreamStatus.NEW,
    )
    await storage.save_streams([completed, new_stream])

    calc = MetricsCalculator(storage)
    summary = await calc.calculate_weekly("2026-03-22")

    assert "Old Feature" in summary.completed_streams
    assert "New Feature" in summary.new_streams


@pytest.mark.asyncio
async def test_calculate_weekly_persists_summary(storage):
    calc = MetricsCalculator(storage)
    summary = await calc.calculate_weekly("2026-03-22")

    persisted = await storage.get_weekly_summary(summary.week_label)
    assert persisted is not None
    assert persisted.start_date == "2026-03-16"


# ---------------------------------------------------------------------------
# velocity_trend — integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_velocity_trend_empty_storage(storage):
    calc = MetricsCalculator(storage)
    trend = await calc.velocity_trend("2026-03-22", num_weeks=4)

    assert len(trend) == 4
    assert all(v == 0 for v in trend.values())


@pytest.mark.asyncio
async def test_velocity_trend_counts_per_week(storage):
    # W12 (2026-03-16~22): 3 commits
    # W11 (2026-03-09~15): 2 commits
    commits_w12 = [
        make_commit(date_str="2026-03-16", hash_suffix="V1"),
        make_commit(date_str="2026-03-17", hash_suffix="V2"),
        make_commit(date_str="2026-03-18", hash_suffix="V3"),
    ]
    commits_w11 = [
        make_commit(date_str="2026-03-09", hash_suffix="V4"),
        make_commit(date_str="2026-03-10", hash_suffix="V5"),
    ]
    await storage.save_commits(commits_w12 + commits_w11)

    calc = MetricsCalculator(storage)
    trend = await calc.velocity_trend("2026-03-22", num_weeks=4)

    assert len(trend) == 4
    assert trend.get("W12") == 3
    assert trend.get("W11") == 2


@pytest.mark.asyncio
async def test_velocity_trend_label_order(storage):
    """결과 키 순서: 오래된 주 → 최신 주"""
    calc = MetricsCalculator(storage)
    trend = await calc.velocity_trend("2026-03-22", num_weeks=4)

    keys = list(trend.keys())
    assert len(keys) == 4
    # 주 번호 오름차순 정렬이어야 함
    week_nums = [int(k[1:]) for k in keys]
    assert week_nums == sorted(week_nums)


@pytest.mark.asyncio
async def test_velocity_trend_num_weeks_parameter(storage):
    calc = MetricsCalculator(storage)

    trend_2 = await calc.velocity_trend("2026-03-22", num_weeks=2)
    assert len(trend_2) == 2

    trend_6 = await calc.velocity_trend("2026-03-22", num_weeks=6)
    assert len(trend_6) == 6
