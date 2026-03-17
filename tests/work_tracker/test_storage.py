"""
WorkTrackerStorage 테스트

save/get round-trip, UNIQUE constraint, JSON 필드 직렬화/역직렬화 검증.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.models import (
    CommitType,
    DailyCommit,
    DailySummary,
    DetectionMethod,
    FileChange,
    StreamStatus,
    WeeklySummary,
    WorkStream,
)
from scripts.work_tracker.storage import WorkTrackerStorage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_commit(
    commit_hash: str = "abc123",
    date: str = "2026-03-17",
    project: str = "secretary",
    repo: str = "secretary",
) -> DailyCommit:
    return DailyCommit(
        date=date,
        repo=repo,
        project=project,
        category="automation",
        commit_hash=commit_hash,
        commit_type=CommitType.FEAT,
        commit_scope="storage",
        message="feat(storage): add work tracker storage",
        author="Aiden Kim",
        timestamp="2026-03-17T10:00:00",
        files_changed=3,
        insertions=120,
        deletions=5,
        branch="feat/work-tracker",
    )


def _make_stream(name: str = "storage-impl", project: str = "secretary") -> WorkStream:
    return WorkStream(
        name=name,
        project=project,
        repos=["secretary", "claude"],
        first_commit="2026-03-10T09:00:00",
        last_commit="2026-03-17T10:00:00",
        total_commits=7,
        status=StreamStatus.ACTIVE,
        duration_days=7,
        detection_method=DetectionMethod.BRANCH,
        metadata={"branches": ["feat/work-tracker"], "keywords": ["storage"]},
    )


def _make_daily_summary(date: str = "2026-03-17") -> DailySummary:
    return DailySummary(
        date=date,
        total_commits=12,
        total_insertions=350,
        total_deletions=40,
        doc_change_ratio=0.15,
        project_distribution={"secretary": 60, "ebs": 40},
        active_streams=3,
        highlights=["Work Tracker 스토리지 구현 완료", "EBS PRD 업데이트"],
        slack_message_id="slack-msg-001",
    )


def _make_weekly_summary(week_label: str = "W12 (3/10~3/16)") -> WeeklySummary:
    return WeeklySummary(
        week_label=week_label,
        start_date="2026-03-10",
        end_date="2026-03-16",
        total_commits=47,
        velocity_trend=[10, 12, 15, 10],
        completed_streams=["ebs-prd-v3"],
        new_streams=["work-tracker"],
        project_distribution={"secretary": 50, "ebs": 30, "wsoptv": 20},
        highlights=["EBS PRD v3 완료", "Work Tracker 착수"],
        slack_message_id="slack-weekly-001",
    )


# ---------------------------------------------------------------------------
# Tests: save_commits / get_commits_by_date
# ---------------------------------------------------------------------------

class TestCommitsRoundTrip:
    """커밋 저장 및 날짜별 조회 round-trip"""

    async def test_save_and_get_by_date(self, storage):
        commit = _make_commit()
        saved = await storage.save_commits([commit])
        assert saved == 1

        results = await storage.get_commits_by_date("2026-03-17")
        assert len(results) == 1
        r = results[0]
        assert r.commit_hash == "abc123"
        assert r.project == "secretary"
        assert r.repo == "secretary"
        assert r.category == "automation"
        assert r.commit_type == CommitType.FEAT
        assert r.commit_scope == "storage"
        assert r.files_changed == 3
        assert r.insertions == 120
        assert r.deletions == 5
        assert r.branch == "feat/work-tracker"

    async def test_get_by_date_with_project_filter(self, storage):
        commit_a = _make_commit(commit_hash="aaa111", project="secretary")
        commit_b = _make_commit(commit_hash="bbb222", project="ebs")
        await storage.save_commits([commit_a, commit_b])

        results = await storage.get_commits_by_date("2026-03-17", project="secretary")
        assert len(results) == 1
        assert results[0].project == "secretary"

    async def test_get_by_date_no_results(self, storage):
        results = await storage.get_commits_by_date("2000-01-01")
        assert results == []

    async def test_get_commits_by_range(self, storage):
        commits = [
            _make_commit(commit_hash=f"h{i}", date=f"2026-03-{10+i:02d}")
            for i in range(5)
        ]
        await storage.save_commits(commits)

        results = await storage.get_commits_by_range("2026-03-11", "2026-03-13")
        assert len(results) == 3
        dates = [r.date for r in results]
        assert "2026-03-11" in dates
        assert "2026-03-13" in dates
        assert "2026-03-10" not in dates
        assert "2026-03-14" not in dates

    async def test_get_commits_by_range_with_project_filter(self, storage):
        commits = [
            _make_commit(commit_hash="ra1", date="2026-03-11", project="secretary"),
            _make_commit(commit_hash="rb1", date="2026-03-11", project="ebs"),
        ]
        await storage.save_commits(commits)

        results = await storage.get_commits_by_range(
            "2026-03-10", "2026-03-12", project="ebs"
        )
        assert len(results) == 1
        assert results[0].project == "ebs"

    async def test_batch_save_returns_count(self, storage):
        commits = [_make_commit(commit_hash=f"batch{i}") for i in range(5)]
        saved = await storage.save_commits(commits)
        assert saved == 5


# ---------------------------------------------------------------------------
# Tests: UNIQUE constraint (duplicate commit_hash ignored)
# ---------------------------------------------------------------------------

class TestUniqueConstraint:
    """중복 commit_hash는 INSERT OR IGNORE로 무시"""

    async def test_duplicate_commit_ignored(self, storage):
        commit = _make_commit(commit_hash="dup001")
        saved_first = await storage.save_commits([commit])
        saved_second = await storage.save_commits([commit])

        assert saved_first == 1
        assert saved_second == 0

        results = await storage.get_commits_by_date("2026-03-17")
        assert len(results) == 1

    async def test_mixed_new_and_duplicate(self, storage):
        commit_a = _make_commit(commit_hash="orig001")
        await storage.save_commits([commit_a])

        commit_dup = _make_commit(commit_hash="orig001")
        commit_new = _make_commit(commit_hash="new001")
        saved = await storage.save_commits([commit_dup, commit_new])

        assert saved == 1
        results = await storage.get_commits_by_date("2026-03-17")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Tests: save_file_changes
# ---------------------------------------------------------------------------

class TestFileChanges:
    """파일 변경 저장"""

    async def test_save_file_changes(self, storage):
        commit = _make_commit(commit_hash="fc001")
        await storage.save_commits([commit])

        changes = [
            FileChange(file_path="scripts/storage.py", change_type="modified", insertions=50, deletions=10),
            FileChange(file_path="tests/test_storage.py", change_type="added", insertions=120, deletions=0),
        ]
        # Should not raise
        await storage.save_file_changes("fc001", changes)

    async def test_save_file_changes_unknown_hash(self, storage):
        """존재하지 않는 commit_hash → 조용히 무시"""
        changes = [FileChange(file_path="x.py", change_type="added")]
        # Should not raise
        await storage.save_file_changes("nonexistent_hash", changes)


# ---------------------------------------------------------------------------
# Tests: WorkStream round-trip
# ---------------------------------------------------------------------------

class TestStreamsRoundTrip:
    """Work Stream 저장 및 조회 round-trip"""

    async def test_save_and_get_streams(self, storage):
        stream = _make_stream()
        await storage.save_streams([stream])

        results = await storage.get_streams()
        assert len(results) == 1
        r = results[0]
        assert r.name == "storage-impl"
        assert r.project == "secretary"
        assert r.repos == ["secretary", "claude"]
        assert r.total_commits == 7
        assert r.status == StreamStatus.ACTIVE
        assert r.duration_days == 7
        assert r.detection_method == DetectionMethod.BRANCH
        assert r.metadata == {"branches": ["feat/work-tracker"], "keywords": ["storage"]}

    async def test_get_streams_status_filter(self, storage):
        active = _make_stream(name="active-stream")
        idle = WorkStream(
            name="idle-stream",
            project="secretary",
            repos=["secretary"],
            first_commit="2026-02-01T00:00:00",
            last_commit="2026-02-28T00:00:00",
            status=StreamStatus.IDLE,
        )
        await storage.save_streams([active, idle])

        active_results = await storage.get_streams(status="active")
        assert all(r.status == StreamStatus.ACTIVE for r in active_results)
        assert len(active_results) == 1

        idle_results = await storage.get_streams(status="idle")
        assert len(idle_results) == 1

    async def test_get_streams_project_filter(self, storage):
        sec_stream = _make_stream(name="sec-stream", project="secretary")
        ebs_stream = _make_stream(name="ebs-stream", project="ebs")
        await storage.save_streams([sec_stream, ebs_stream])

        results = await storage.get_streams(project="ebs")
        assert len(results) == 1
        assert results[0].project == "ebs"

    async def test_upsert_stream(self, storage):
        """동일 name+project는 UPDATE (upsert)"""
        stream = _make_stream()
        await storage.save_streams([stream])

        updated_stream = WorkStream(
            name="storage-impl",
            project="secretary",
            repos=["secretary"],
            first_commit=stream.first_commit,
            last_commit="2026-03-18T12:00:00",
            total_commits=10,
            status=StreamStatus.ACTIVE,
        )
        await storage.save_streams([updated_stream])

        results = await storage.get_streams()
        assert len(results) == 1
        assert results[0].total_commits == 10
        assert results[0].last_commit == "2026-03-18T12:00:00"

    async def test_stream_metadata_none(self, storage):
        """metadata=None은 빈 dict로 복원 (JSON {} 직렬화)"""
        stream = WorkStream(
            name="no-meta",
            project="secretary",
            repos=[],
            first_commit="2026-03-17T00:00:00",
            last_commit="2026-03-17T00:00:00",
            metadata=None,
        )
        await storage.save_streams([stream])
        results = await storage.get_streams()
        # None은 json.dumps({}) → json.loads("{}") = {} 로 복원됨
        assert results[0].metadata == {}


# ---------------------------------------------------------------------------
# Tests: DailySummary round-trip
# ---------------------------------------------------------------------------

class TestDailySummaryRoundTrip:
    """일일 요약 저장/조회 round-trip"""

    async def test_save_and_get_daily_summary(self, storage):
        summary = _make_daily_summary()
        await storage.save_daily_summary(summary)

        result = await storage.get_daily_summary("2026-03-17")
        assert result is not None
        assert result.date == "2026-03-17"
        assert result.total_commits == 12
        assert result.total_insertions == 350
        assert result.total_deletions == 40
        assert abs(result.doc_change_ratio - 0.15) < 1e-9
        assert result.project_distribution == {"secretary": 60, "ebs": 40}
        assert result.active_streams == 3
        assert result.highlights == ["Work Tracker 스토리지 구현 완료", "EBS PRD 업데이트"]
        assert result.slack_message_id == "slack-msg-001"

    async def test_get_daily_summary_not_found(self, storage):
        result = await storage.get_daily_summary("2000-01-01")
        assert result is None

    async def test_daily_summary_replace(self, storage):
        """동일 date는 INSERT OR REPLACE로 덮어씀"""
        summary_v1 = _make_daily_summary()
        await storage.save_daily_summary(summary_v1)

        summary_v2 = DailySummary(
            date="2026-03-17",
            total_commits=20,
            highlights=["업데이트됨"],
        )
        await storage.save_daily_summary(summary_v2)

        result = await storage.get_daily_summary("2026-03-17")
        assert result is not None
        assert result.total_commits == 20
        assert result.highlights == ["업데이트됨"]

    async def test_daily_summary_empty_highlights(self, storage):
        summary = DailySummary(date="2026-03-18", highlights=[])
        await storage.save_daily_summary(summary)
        result = await storage.get_daily_summary("2026-03-18")
        assert result is not None
        assert result.highlights == []


# ---------------------------------------------------------------------------
# Tests: WeeklySummary round-trip
# ---------------------------------------------------------------------------

class TestWeeklySummaryRoundTrip:
    """주간 요약 저장/조회 round-trip"""

    async def test_save_and_get_weekly_summary(self, storage):
        summary = _make_weekly_summary()
        await storage.save_weekly_summary(summary)

        result = await storage.get_weekly_summary("W12 (3/10~3/16)")
        assert result is not None
        assert result.week_label == "W12 (3/10~3/16)"
        assert result.start_date == "2026-03-10"
        assert result.end_date == "2026-03-16"
        assert result.total_commits == 47
        assert result.velocity_trend == [10, 12, 15, 10]
        assert result.completed_streams == ["ebs-prd-v3"]
        assert result.new_streams == ["work-tracker"]
        assert result.project_distribution == {"secretary": 50, "ebs": 30, "wsoptv": 20}
        assert result.highlights == ["EBS PRD v3 완료", "Work Tracker 착수"]
        assert result.slack_message_id == "slack-weekly-001"

    async def test_get_weekly_summary_not_found(self, storage):
        result = await storage.get_weekly_summary("W99 (nonexistent)")
        assert result is None

    async def test_weekly_summary_replace(self, storage):
        """동일 week_label은 INSERT OR REPLACE로 덮어씀"""
        summary_v1 = _make_weekly_summary()
        await storage.save_weekly_summary(summary_v1)

        summary_v2 = WeeklySummary(
            week_label="W12 (3/10~3/16)",
            start_date="2026-03-10",
            end_date="2026-03-16",
            total_commits=99,
            highlights=["새 하이라이트"],
        )
        await storage.save_weekly_summary(summary_v2)

        result = await storage.get_weekly_summary("W12 (3/10~3/16)")
        assert result is not None
        assert result.total_commits == 99
        assert result.highlights == ["새 하이라이트"]

    async def test_weekly_summary_empty_lists(self, storage):
        """빈 리스트 필드 정상 저장/복원"""
        summary = WeeklySummary(
            week_label="W01 (empty)",
            start_date="2026-01-01",
            end_date="2026-01-07",
            velocity_trend=[],
            completed_streams=[],
            new_streams=[],
            highlights=[],
        )
        await storage.save_weekly_summary(summary)
        result = await storage.get_weekly_summary("W01 (empty)")
        assert result is not None
        assert result.velocity_trend == []
        assert result.completed_streams == []
        assert result.new_streams == []
        assert result.highlights == []
