"""
Work Tracker 성과 지표 계산기

Git 커밋 데이터 기반으로 일일/주간 성과 지표를 계산합니다.
"""

import sys
from datetime import date, timedelta
from pathlib import Path

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# 3-way import
try:
    from scripts.work_tracker.models import (
        CommitType,
        DailyCommit,
        DailySummary,
        StreamStatus,
        WeeklySummary,
    )
    from scripts.work_tracker.storage import WorkTrackerStorage
except ImportError:
    try:
        from work_tracker.models import (
            CommitType,
            DailyCommit,
            DailySummary,
            StreamStatus,
            WeeklySummary,
        )
        from work_tracker.storage import WorkTrackerStorage
    except ImportError:
        from .models import (
            CommitType,
            DailyCommit,
            DailySummary,
            StreamStatus,
            WeeklySummary,
        )
        from .storage import WorkTrackerStorage


class MetricsCalculator:
    """
    성과 지표 계산기

    WorkTrackerStorage에서 커밋 데이터를 읽어 일일/주간 요약을 계산하고 저장합니다.

    Example:
        async with WorkTrackerStorage() as storage:
            calc = MetricsCalculator(storage)
            summary = await calc.calculate_daily("2026-03-17")
    """

    def __init__(self, storage: WorkTrackerStorage):
        self.storage = storage

    async def calculate_daily(self, date: str) -> DailySummary:
        """일일 지표 계산

        Args:
            date: YYYY-MM-DD

        Returns:
            DailySummary (저장 완료 후 반환)
        """
        commits = await self.storage.get_commits_by_date(date)

        total_commits = len(commits)
        total_insertions = sum(c.insertions for c in commits)
        total_deletions = sum(c.deletions for c in commits)
        doc_change_ratio = self._calculate_doc_ratio(commits)
        project_distribution = self._calculate_project_distribution(commits)

        active_streams = await self.storage.get_streams(status=StreamStatus.ACTIVE.value)
        active_stream_count = len(active_streams)

        summary = DailySummary(
            date=date,
            total_commits=total_commits,
            total_insertions=total_insertions,
            total_deletions=total_deletions,
            doc_change_ratio=doc_change_ratio,
            project_distribution=project_distribution,
            active_streams=active_stream_count,
        )

        await self.storage.save_daily_summary(summary)
        return summary

    async def calculate_weekly(self, end_date: str, weeks: int = 1) -> WeeklySummary:
        """주간 지표 계산

        Args:
            end_date: 주간 종료일 (YYYY-MM-DD, 보통 일요일)
            weeks: 계산할 주 수 (기본 1, 현재 미사용 — 단일 주 계산)

        Returns:
            WeeklySummary (저장 완료 후 반환)
        """
        start_date, _end_date = self._get_week_range(end_date)
        week_label = self._get_week_label(start_date, _end_date)

        commits = await self.storage.get_commits_by_range(start_date, _end_date)

        total_commits = len(commits)
        project_distribution = self._calculate_project_distribution(commits)
        velocity_trend = await self.velocity_trend(_end_date, num_weeks=4)

        all_streams = await self.storage.get_streams()
        completed_streams = [
            s.name for s in all_streams if s.status == StreamStatus.COMPLETED
        ]
        new_streams = [
            s.name for s in all_streams if s.status == StreamStatus.NEW
        ]

        summary = WeeklySummary(
            week_label=week_label,
            start_date=start_date,
            end_date=_end_date,
            total_commits=total_commits,
            velocity_trend=velocity_trend,
            completed_streams=completed_streams,
            new_streams=new_streams,
            project_distribution=project_distribution,
        )

        await self.storage.save_weekly_summary(summary)
        return summary

    async def velocity_trend(
        self, end_date: str, num_weeks: int = 4
    ) -> dict[str, int]:
        """최근 N주 velocity 트렌드

        Args:
            end_date: 기준 종료일 (YYYY-MM-DD)
            num_weeks: 계산할 주 수 (기본 4)

        Returns:
            {"W9": 28, "W10": 35, "W11": 42, "W12": 48}
            가장 오래된 주부터 최신 주 순서
        """
        end_dt = date.fromisoformat(end_date)
        result: dict[str, int] = {}

        for i in range(num_weeks - 1, -1, -1):
            # end_date 기준으로 역방향으로 i주 앞의 주를 계산
            week_end_dt = end_dt - timedelta(weeks=i)
            week_start_str, week_end_str = self._get_week_range(
                week_end_dt.isoformat()
            )

            commits = await self.storage.get_commits_by_range(
                week_start_str, week_end_str
            )

            start_dt = date.fromisoformat(week_start_str)
            iso_week = start_dt.isocalendar()[1]
            label = f"W{iso_week}"
            result[label] = len(commits)

        return result

    def _get_week_range(self, date_str: str) -> tuple[str, str]:
        """날짜가 속한 주의 월~일 범위 반환

        ISO 8601 기준: 월요일(weekday=0) ~ 일요일(weekday=6)

        Returns:
            (start_date, end_date) as YYYY-MM-DD strings
        """
        dt = date.fromisoformat(date_str)
        # 월요일: weekday() == 0
        days_since_monday = dt.weekday()
        monday = dt - timedelta(days=days_since_monday)
        sunday = monday + timedelta(days=6)
        return monday.isoformat(), sunday.isoformat()

    def _get_week_label(self, start_date: str, end_date: str) -> str:
        """주간 레이블 생성

        Returns:
            "W{iso_week} ({M}/{D}~{M}/{D})"
            예: "W12 (3/10~3/16)"
        """
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date)
        iso_week = start_dt.isocalendar()[1]
        start_label = f"{start_dt.month}/{start_dt.day}"
        end_label = f"{end_dt.month}/{end_dt.day}"
        return f"W{iso_week} ({start_label}~{end_label})"

    def _calculate_project_distribution(
        self, commits: list[DailyCommit]
    ) -> dict[str, int]:
        """프로젝트별 커밋 수를 백분율로 변환

        Args:
            commits: 커밋 목록

        Returns:
            {"EBS": 60, "WSOPTV": 30, "Secretary": 10}
            반올림 후 합계가 100이 되도록 가장 큰 프로젝트에서 차이 조정.
            커밋이 없으면 빈 딕셔너리 반환.
        """
        if not commits:
            return {}

        # 프로젝트별 커밋 수 집계
        counts: dict[str, int] = {}
        for commit in commits:
            project = commit.project
            counts[project] = counts.get(project, 0) + 1

        total = len(commits)

        # 정확한 백분율 계산 (소수점 포함)
        exact: dict[str, float] = {
            project: count / total * 100
            for project, count in counts.items()
        }

        # 각 값을 floor 반올림 (int 변환)
        floored: dict[str, int] = {
            project: int(pct)
            for project, pct in exact.items()
        }

        # 반올림 오차 보정: 합계 100이 될 때까지 소수점 내림 오차가 가장 큰 항목에 1씩 추가
        remainder = 100 - sum(floored.values())
        if remainder > 0:
            # 소수점 부분 내림차순으로 정렬하여 오차가 큰 항목에 우선 배분
            fractional_parts = sorted(
                exact.keys(),
                key=lambda p: exact[p] - floored[p],
                reverse=True,
            )
            for i in range(remainder):
                project = fractional_parts[i % len(fractional_parts)]
                floored[project] += 1

        return floored

    def _calculate_doc_ratio(self, commits: list[DailyCommit]) -> float:
        """문서 변경 비율 계산

        Args:
            commits: 커밋 목록

        Returns:
            commit_type == CommitType.DOCS인 커밋 수 / 전체 커밋 수.
            전체 커밋이 0이면 0.0 반환.
        """
        if not commits:
            return 0.0

        doc_count = sum(
            1 for c in commits if c.commit_type == CommitType.DOCS
        )
        return doc_count / len(commits)
