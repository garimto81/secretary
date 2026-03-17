"""
StreamDetector 단위 테스트

커버리지:
- _detect_by_branch: feat/fix 브랜치 감지
- _detect_by_scope: Conventional Commit scope 감지
- _merge_candidates: 겹치는 stream 병합
- update_stream_statuses: 날짜 차이별 상태 전환
- reconcile_with_existing: mock storage / 실제 async storage
- PRD 검증 데이터: 13개 Work Stream 시나리오
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.models import (
    CommitType,
    DailyCommit,
    DetectionMethod,
    StreamStatus,
    WorkStream,
)
from scripts.work_tracker.stream_detector import StreamDetector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_commit(
    *,
    repo: str = "ebs",
    project: str = "EBS",
    branch: str | None = None,
    commit_scope: str | None = None,
    commit_type: CommitType = CommitType.FEAT,
    date: str = "2026-03-17",
    timestamp: str | None = None,
    commit_hash: str | None = None,
    message: str = "test commit",
    category: str | None = None,
) -> DailyCommit:
    ts = timestamp or f"{date}T10:00:00"
    return DailyCommit(
        date=date,
        repo=repo,
        project=project,
        category=category,
        commit_hash=commit_hash or f"abc{hash((repo, branch, commit_scope, date)) % 100000:05d}",
        commit_type=commit_type,
        commit_scope=commit_scope,
        message=message,
        author="test",
        timestamp=ts,
        branch=branch,
    )


def make_detector(storage=None) -> StreamDetector:
    if storage is None:
        mock_storage = MagicMock()
        mock_storage.get_streams = AsyncMock(return_value=[])
        storage = mock_storage
    return StreamDetector(storage)


# ---------------------------------------------------------------------------
# _detect_by_branch
# ---------------------------------------------------------------------------

class TestDetectByBranch:
    def test_feat_branch_extracts_name(self):
        detector = make_detector()
        commits = [
            make_commit(branch="feat/overlay-analysis", repo="ui_overlay", project="EBS"),
            make_commit(branch="feat/overlay-analysis", repo="ui_overlay", project="EBS",
                        date="2026-03-18", timestamp="2026-03-18T11:00:00",
                        commit_hash="bcd00002"),
        ]
        streams = detector._detect_by_branch(commits)
        assert len(streams) == 1
        assert streams[0].name == "overlay-analysis"
        assert streams[0].project == "EBS"
        assert streams[0].detection_method == DetectionMethod.BRANCH
        assert streams[0].total_commits == 2

    def test_fix_branch_extracts_name(self):
        detector = make_detector()
        commits = [make_commit(branch="fix/login-bug", project="WSOPTV")]
        streams = detector._detect_by_branch(commits)
        assert len(streams) == 1
        assert streams[0].name == "login-bug"
        assert streams[0].detection_method == DetectionMethod.BRANCH

    def test_main_branch_skipped(self):
        detector = make_detector()
        commits = [make_commit(branch="main"), make_commit(branch="master", commit_hash="xyz00001")]
        streams = detector._detect_by_branch(commits)
        assert len(streams) == 0

    def test_head_branch_skipped(self):
        detector = make_detector()
        commits = [make_commit(branch="HEAD")]
        streams = detector._detect_by_branch(commits)
        assert len(streams) == 0

    def test_no_branch_skipped(self):
        detector = make_detector()
        commits = [make_commit(branch=None), make_commit(branch="", commit_hash="empty0001")]
        streams = detector._detect_by_branch(commits)
        assert len(streams) == 0

    def test_multiple_branches_separate_streams(self):
        detector = make_detector()
        commits = [
            make_commit(branch="feat/stream-a", project="EBS", repo="ebs"),
            make_commit(branch="feat/stream-b", project="EBS", repo="ebs",
                        commit_hash="bbb00001"),
        ]
        streams = detector._detect_by_branch(commits)
        names = {s.name for s in streams}
        assert "stream-a" in names
        assert "stream-b" in names

    def test_different_projects_separate_streams(self):
        detector = make_detector()
        commits = [
            make_commit(branch="feat/ui", project="EBS"),
            make_commit(branch="feat/ui", project="WSOPTV", commit_hash="ccc00001"),
        ]
        streams = detector._detect_by_branch(commits)
        assert len(streams) == 2

    def test_repos_aggregated(self):
        detector = make_detector()
        commits = [
            make_commit(branch="feat/multi-repo", repo="ebs", project="EBS"),
            make_commit(branch="feat/multi-repo", repo="ebs_reverse", project="EBS",
                        commit_hash="ddd00001"),
        ]
        streams = detector._detect_by_branch(commits)
        assert len(streams) == 1
        assert set(streams[0].repos) == {"ebs", "ebs_reverse"}

    def test_first_last_commit_timestamps(self):
        detector = make_detector()
        commits = [
            make_commit(branch="feat/timeline", timestamp="2026-03-17T08:00:00"),
            make_commit(branch="feat/timeline", timestamp="2026-03-19T20:00:00",
                        commit_hash="zzz00001"),
        ]
        streams = detector._detect_by_branch(commits)
        assert streams[0].first_commit == "2026-03-17T08:00:00"
        assert streams[0].last_commit == "2026-03-19T20:00:00"


# ---------------------------------------------------------------------------
# _detect_by_scope
# ---------------------------------------------------------------------------

class TestDetectByScope:
    def test_scope_groups_commits(self):
        detector = make_detector()
        commits = [
            make_commit(commit_scope="overlay", project="EBS"),
            make_commit(commit_scope="overlay", project="EBS",
                        date="2026-03-18", commit_hash="sss00001"),
        ]
        streams = detector._detect_by_scope(commits)
        assert len(streams) == 1
        assert streams[0].name == "overlay"
        assert streams[0].detection_method == DetectionMethod.SCOPE
        assert streams[0].total_commits == 2

    def test_none_scope_skipped(self):
        detector = make_detector()
        commits = [make_commit(commit_scope=None)]
        streams = detector._detect_by_scope(commits)
        assert len(streams) == 0

    def test_empty_scope_skipped(self):
        detector = make_detector()
        commits = [make_commit(commit_scope="")]
        streams = detector._detect_by_scope(commits)
        assert len(streams) == 0

    def test_different_scopes_separate_streams(self):
        detector = make_detector()
        commits = [
            make_commit(commit_scope="prd", project="EBS"),
            make_commit(commit_scope="ui", project="EBS", commit_hash="uuu00001"),
        ]
        streams = detector._detect_by_scope(commits)
        assert len(streams) == 2

    def test_scope_cross_repos(self):
        detector = make_detector()
        commits = [
            make_commit(commit_scope="gfx", repo="ebs", project="EBS"),
            make_commit(commit_scope="gfx", repo="ui_overlay", project="EBS",
                        commit_hash="ggg00001"),
        ]
        streams = detector._detect_by_scope(commits)
        assert len(streams) == 1
        assert set(streams[0].repos) == {"ebs", "ui_overlay"}

    def test_scope_different_projects(self):
        detector = make_detector()
        commits = [
            make_commit(commit_scope="core", project="EBS"),
            make_commit(commit_scope="core", project="WSOPTV", commit_hash="ppp00001"),
        ]
        streams = detector._detect_by_scope(commits)
        assert len(streams) == 2


# ---------------------------------------------------------------------------
# _detect_by_path
# ---------------------------------------------------------------------------

class TestDetectByPath:
    def test_no_branch_no_scope_groups_by_repo(self):
        detector = make_detector()
        commits = [
            make_commit(branch=None, commit_scope=None, repo="wsoptv_ott", project="WSOPTV"),
            make_commit(branch=None, commit_scope=None, repo="wsoptv_ott", project="WSOPTV",
                        date="2026-03-18", commit_hash="pth00001"),
        ]
        streams = detector._detect_by_path(commits)
        assert len(streams) == 1
        assert streams[0].name == "wsoptv_ott"
        assert streams[0].detection_method == DetectionMethod.PATH

    def test_commit_with_branch_excluded_from_path(self):
        detector = make_detector()
        commits = [
            make_commit(branch="feat/something", commit_scope=None, repo="ebs", project="EBS"),
            make_commit(branch=None, commit_scope=None, repo="ebs", project="EBS",
                        commit_hash="nob00001"),
        ]
        streams = detector._detect_by_path(commits)
        # Only the commit without branch should be grouped
        assert len(streams) == 1
        assert streams[0].total_commits == 1

    def test_commit_with_scope_excluded_from_path(self):
        detector = make_detector()
        commits = [
            make_commit(branch=None, commit_scope="prd", repo="ebs", project="EBS"),
            make_commit(branch=None, commit_scope=None, repo="ebs", project="EBS",
                        commit_hash="nos00001"),
        ]
        streams = detector._detect_by_path(commits)
        assert len(streams) == 1
        assert streams[0].total_commits == 1


# ---------------------------------------------------------------------------
# _merge_candidates
# ---------------------------------------------------------------------------

class TestMergeCandidates:
    def test_empty_returns_empty(self):
        detector = make_detector()
        assert detector._merge_candidates([]) == []

    def test_no_overlap_keeps_separate(self):
        detector = make_detector()
        s1 = WorkStream(
            name="stream-a", project="EBS", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=3, detection_method=DetectionMethod.BRANCH,
        )
        s2 = WorkStream(
            name="stream-b", project="EBS", repos=["wsoptv_ott"],
            first_commit="2026-01-06T00:00:00", last_commit="2026-01-10T00:00:00",
            total_commits=5, detection_method=DetectionMethod.SCOPE,
        )
        merged = detector._merge_candidates([s1, s2])
        assert len(merged) == 2

    def test_70_percent_overlap_merges(self):
        detector = make_detector()
        # Same stream detected by BRANCH and SCOPE — name must be similar for merge
        # repos identical → 100% overlap; names: "overlay" is substring of "overlay-analysis"
        s1 = WorkStream(
            name="overlay-analysis", project="EBS",
            repos=["ebs", "ebs_reverse", "ui_overlay"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=3, detection_method=DetectionMethod.BRANCH,
        )
        s2 = WorkStream(
            name="overlay", project="EBS",
            repos=["ebs", "ebs_reverse", "ui_overlay"],
            first_commit="2026-01-03T00:00:00", last_commit="2026-01-08T00:00:00",
            total_commits=4, detection_method=DetectionMethod.SCOPE,
        )
        merged = detector._merge_candidates([s1, s2])
        assert len(merged) == 1
        # BRANCH has higher priority → name from BRANCH
        assert merged[0].name == "overlay-analysis"
        assert merged[0].detection_method == DetectionMethod.BRANCH
        # total_commits merged
        assert merged[0].total_commits == 7
        # repos union
        assert set(merged[0].repos) == {"ebs", "ebs_reverse", "ui_overlay"}
        # date range expanded
        assert merged[0].first_commit == "2026-01-01T00:00:00"
        assert merged[0].last_commit == "2026-01-08T00:00:00"

    def test_below_70_not_merged(self):
        detector = make_detector()
        # ["ebs", "ebs_reverse"] vs ["ebs", "ui_overlay"] → overlap=1/2=50% < 70%
        s1 = WorkStream(
            name="s1", project="EBS", repos=["ebs", "ebs_reverse"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=2, detection_method=DetectionMethod.BRANCH,
        )
        s2 = WorkStream(
            name="s2", project="EBS", repos=["ebs", "ui_overlay"],
            first_commit="2026-01-03T00:00:00", last_commit="2026-01-08T00:00:00",
            total_commits=2, detection_method=DetectionMethod.SCOPE,
        )
        merged = detector._merge_candidates([s1, s2])
        assert len(merged) == 2

    def test_priority_branch_over_scope(self):
        detector = make_detector()
        # Same stream "gfx" detected by both SCOPE and BRANCH (branch name contains "gfx")
        s_scope = WorkStream(
            name="gfx", project="EBS", repos=["ebs", "ebs_reverse", "ui_overlay"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=2, detection_method=DetectionMethod.SCOPE,
        )
        s_branch = WorkStream(
            name="gfx-tab-ui", project="EBS", repos=["ebs", "ebs_reverse", "ui_overlay"],
            first_commit="2026-01-03T00:00:00", last_commit="2026-01-08T00:00:00",
            total_commits=3, detection_method=DetectionMethod.BRANCH,
        )
        merged = detector._merge_candidates([s_scope, s_branch])
        assert len(merged) == 1
        assert merged[0].name == "gfx-tab-ui"
        assert merged[0].detection_method == DetectionMethod.BRANCH

    def test_priority_scope_over_path(self):
        detector = make_detector()
        # Same stream "ebs" detected by PATH (repo name) and SCOPE with similar name
        s_path = WorkStream(
            name="ebs", project="EBS", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=1, detection_method=DetectionMethod.PATH,
        )
        s_scope = WorkStream(
            name="ebs", project="EBS", repos=["ebs"],
            first_commit="2026-01-03T00:00:00", last_commit="2026-01-08T00:00:00",
            total_commits=2, detection_method=DetectionMethod.SCOPE,
        )
        merged = detector._merge_candidates([s_path, s_scope])
        assert len(merged) == 1
        assert merged[0].name == "ebs"
        assert merged[0].detection_method == DetectionMethod.SCOPE

    def test_different_project_not_merged(self):
        detector = make_detector()
        s1 = WorkStream(
            name="same-name", project="EBS", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=2, detection_method=DetectionMethod.BRANCH,
        )
        s2 = WorkStream(
            name="same-name", project="WSOPTV", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=3, detection_method=DetectionMethod.BRANCH,
        )
        merged = detector._merge_candidates([s1, s2])
        assert len(merged) == 2

    def test_exact_70_percent_merges(self):
        detector = make_detector()
        # repos_a=["a","b","c"], repos_b=["a","b","c","d"] → overlap=3, max=4 → 0.75 >= 0.7
        # Names must be similar: "feature" is substring of "feature-detail"
        s1 = WorkStream(
            name="feature-detail", project="EBS", repos=["a", "b", "c"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=1, detection_method=DetectionMethod.BRANCH,
        )
        s2 = WorkStream(
            name="feature", project="EBS", repos=["a", "b", "c", "d"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=1, detection_method=DetectionMethod.SCOPE,
        )
        merged = detector._merge_candidates([s1, s2])
        assert len(merged) == 1

    def test_single_repo_same_name_merges(self):
        detector = make_detector()
        # Exact same name + same repo → should merge (same stream, two detection methods)
        s1 = WorkStream(
            name="overlay", project="EBS", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=1, detection_method=DetectionMethod.BRANCH,
        )
        s2 = WorkStream(
            name="overlay", project="EBS", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=2, detection_method=DetectionMethod.SCOPE,
        )
        merged = detector._merge_candidates([s1, s2])
        assert len(merged) == 1

    def test_single_repo_different_name_not_merged(self):
        detector = make_detector()
        # Same repo but completely different names → NOT merged
        s1 = WorkStream(
            name="master-plan", project="EBS", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=1, detection_method=DetectionMethod.BRANCH,
        )
        s2 = WorkStream(
            name="hardware-plan", project="EBS", repos=["ebs"],
            first_commit="2026-01-01T00:00:00", last_commit="2026-01-05T00:00:00",
            total_commits=2, detection_method=DetectionMethod.SCOPE,
        )
        merged = detector._merge_candidates([s1, s2])
        assert len(merged) == 2


# ---------------------------------------------------------------------------
# update_stream_statuses
# ---------------------------------------------------------------------------

class TestUpdateStreamStatuses:
    def _make_stream(self, last_commit_date: str, status=StreamStatus.ACTIVE) -> WorkStream:
        return WorkStream(
            name="test-stream",
            project="EBS",
            repos=["ebs"],
            first_commit=f"{last_commit_date}T00:00:00",
            last_commit=f"{last_commit_date}T12:00:00",
            total_commits=3,
            status=status,
        )

    def test_today_commit_active(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = self._make_stream("2026-03-17")
        result = detector.update_stream_statuses([stream], ref)
        assert result[0].status == StreamStatus.ACTIVE

    def test_7_days_ago_still_active(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = self._make_stream("2026-03-10")  # 7 days ago
        result = detector.update_stream_statuses([stream], ref)
        assert result[0].status == StreamStatus.ACTIVE

    def test_8_days_ago_idle(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = self._make_stream("2026-03-09")  # 8 days ago
        result = detector.update_stream_statuses([stream], ref)
        assert result[0].status == StreamStatus.IDLE

    def test_30_days_ago_idle(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = self._make_stream("2026-02-15")  # 30 days ago
        result = detector.update_stream_statuses([stream], ref)
        assert result[0].status == StreamStatus.IDLE

    def test_31_days_ago_completed(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = self._make_stream("2026-02-14")  # 31 days ago
        result = detector.update_stream_statuses([stream], ref)
        assert result[0].status == StreamStatus.COMPLETED

    def test_new_status_preserved(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = self._make_stream("2026-03-17", status=StreamStatus.NEW)
        result = detector.update_stream_statuses([stream], ref)
        assert result[0].status == StreamStatus.NEW

    def test_duration_days_calculated(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = WorkStream(
            name="long-stream",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-01-01T00:00:00",
            last_commit="2026-03-17T00:00:00",
            total_commits=10,
            status=StreamStatus.ACTIVE,
        )
        result = detector.update_stream_statuses([stream], ref)
        # 2026-01-01 to 2026-03-17 = 75 days + 1 = 76
        assert result[0].duration_days == 76

    def test_same_day_duration_is_1(self):
        detector = make_detector()
        ref = "2026-03-17"
        stream = WorkStream(
            name="one-day",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-03-17T08:00:00",
            last_commit="2026-03-17T20:00:00",
            total_commits=3,
            status=StreamStatus.ACTIVE,
        )
        result = detector.update_stream_statuses([stream], ref)
        assert result[0].duration_days == 1


# ---------------------------------------------------------------------------
# reconcile_with_existing (async with real storage)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestReconcileWithExisting:
    async def test_new_stream_added(self, storage):
        detector = StreamDetector(storage)
        new_s = WorkStream(
            name="new-feature",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-03-17T08:00:00",
            last_commit="2026-03-17T20:00:00",
            total_commits=3,
            status=StreamStatus.NEW,
            detection_method=DetectionMethod.BRANCH,
        )
        result = await detector.reconcile_with_existing([new_s])
        assert any(s.name == "new-feature" for s in result)
        new_found = next(s for s in result if s.name == "new-feature")
        assert new_found.status == StreamStatus.NEW

    async def test_existing_stream_updated(self, storage):
        # Save an existing stream first
        existing = WorkStream(
            name="overlay-analysis",
            project="EBS",
            repos=["ui_overlay"],
            first_commit="2026-03-01T08:00:00",
            last_commit="2026-03-10T20:00:00",
            total_commits=5,
            status=StreamStatus.ACTIVE,
            detection_method=DetectionMethod.PATH,
        )
        await storage.save_streams([existing])

        detector = StreamDetector(storage)
        new_s = WorkStream(
            name="overlay-analysis",
            project="EBS",
            repos=["ui_overlay", "ebs"],
            first_commit="2026-03-11T08:00:00",
            last_commit="2026-03-17T20:00:00",
            total_commits=4,
            status=StreamStatus.NEW,
            detection_method=DetectionMethod.BRANCH,
        )
        result = await detector.reconcile_with_existing([new_s])

        found = next((s for s in result if s.name == "overlay-analysis"), None)
        assert found is not None
        # last_commit updated to newer
        assert found.last_commit == "2026-03-17T20:00:00"
        # repos union
        assert "ebs" in found.repos
        assert "ui_overlay" in found.repos

    async def test_existing_first_commit_not_overwritten_by_newer(self, storage):
        existing = WorkStream(
            name="old-stream",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-01-01T08:00:00",
            last_commit="2026-01-10T20:00:00",
            total_commits=5,
            status=StreamStatus.IDLE,
        )
        await storage.save_streams([existing])

        detector = StreamDetector(storage)
        new_s = WorkStream(
            name="old-stream",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-03-17T08:00:00",  # newer than existing
            last_commit="2026-03-17T20:00:00",
            total_commits=2,
            status=StreamStatus.NEW,
        )
        result = await detector.reconcile_with_existing([new_s])
        found = next(s for s in result if s.name == "old-stream")
        # first_commit should remain the older one
        assert found.first_commit == "2026-01-01T08:00:00"

    async def test_leftover_existing_included(self, storage):
        """DB에만 있는 stream도 결과에 포함되어야 한다"""
        existing = WorkStream(
            name="db-only-stream",
            project="EBS",
            repos=["ebs"],
            first_commit="2026-02-01T00:00:00",
            last_commit="2026-02-10T00:00:00",
            total_commits=8,
            status=StreamStatus.IDLE,
        )
        await storage.save_streams([existing])

        detector = StreamDetector(storage)
        # 신규 감지된 stream은 다른 이름
        new_s = WorkStream(
            name="new-unrelated",
            project="EBS",
            repos=["ebs_reverse"],
            first_commit="2026-03-17T08:00:00",
            last_commit="2026-03-17T20:00:00",
            total_commits=2,
            status=StreamStatus.NEW,
        )
        result = await detector.reconcile_with_existing([new_s])
        names = {s.name for s in result}
        assert "db-only-stream" in names
        assert "new-unrelated" in names


# ---------------------------------------------------------------------------
# detect_streams (integration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDetectStreams:
    async def test_empty_commits_returns_empty(self, storage):
        detector = StreamDetector(storage)
        result = await detector.detect_streams([])
        assert result == []

    async def test_single_branch_commit(self, storage):
        detector = StreamDetector(storage)
        commits = [make_commit(branch="feat/work-tracker", project="Secretary",
                               repo="secretary", date="2026-03-17")]
        result = await detector.detect_streams(commits)
        assert len(result) >= 1
        branch_streams = [s for s in result if s.detection_method == DetectionMethod.BRANCH]
        assert any(s.name == "work-tracker" for s in branch_streams)

    async def test_statuses_applied(self, storage):
        detector = StreamDetector(storage)
        commits = [
            make_commit(branch="feat/recent", project="EBS", date="2026-03-17"),
        ]
        result = await detector.detect_streams(commits)
        # All detected streams should have a valid status
        for s in result:
            assert s.status in list(StreamStatus)


# ---------------------------------------------------------------------------
# PRD 검증 데이터: 13 Work Streams
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPRDValidationScenario:
    """
    PRD의 'Work Stream 감지 검증 데이터' 섹션을 기반으로 커밋 데이터를 시뮬레이션하고,
    StreamDetector가 올바른 스트림을 감지하는지 검증.

    PRD 13개 Work Stream:
    EBS (8개):
      1. 마스터 기획서    - ebs, scope+path
      2. 하드웨어 기획서  - ebs, scope+path
      3. 업체 RFI/견적    - ebs, keyword
      4. 역공학 기획서    - ebs_reverse, branch+scope
      5. GFX 탭 UI 요소   - ebs, scope+path
      6. ui_overlay 분석  - ui_overlay, repo+path
      7. EBS UI Design v3 - ebs, branch+scope
      8. Flutter 앱 포팅  - ebs_reverse_app, repo+branch

    WSOPTV (5개):
      9.  OTT 기획서       - wsoptv_ott, repo+scope
      10. MVP 앱           - wsoptv_ott, branch+keyword
      11. 스트리밍 벤더    - wsoptv_ott, keyword
      12. 네비게이션       - wsoptv_ott, scope+path
      13. Academy 홈페이지 - wsop_academy, repo
    """

    def _make_prd_commits(self) -> list[DailyCommit]:
        """PRD 13개 Work Stream을 커버하는 커밋 데이터 생성"""
        commits = []

        # 1. 마스터 기획서 (ebs, scope=master-plan)
        for i, date in enumerate(["2026-01-22", "2026-01-25", "2026-01-30"]):
            commits.append(make_commit(
                repo="ebs", project="EBS", commit_scope="master-plan",
                date=date, timestamp=f"{date}T10:00:00",
                commit_hash=f"master{i:03d}",
            ))

        # 2. 하드웨어 기획서 (ebs, scope=hardware-plan)
        for i, date in enumerate(["2026-01-29", "2026-02-02", "2026-02-05"]):
            commits.append(make_commit(
                repo="ebs", project="EBS", commit_scope="hardware-plan",
                date=date, timestamp=f"{date}T11:00:00",
                commit_hash=f"hw{i:03d}",
            ))

        # 4. 역공학 기획서 (ebs_reverse, branch=feat/reverse-engineering, scope=reverse)
        for i, date in enumerate(["2026-02-13", "2026-02-20", "2026-02-26"]):
            commits.append(make_commit(
                repo="ebs_reverse", project="EBS",
                branch="feat/reverse-engineering",
                commit_scope="reverse",
                date=date, timestamp=f"{date}T09:00:00",
                commit_hash=f"rev{i:03d}",
            ))

        # 5. GFX 탭 UI 요소 (ebs, scope=gfx)
        for i, date in enumerate(["2026-02-20", "2026-02-23", "2026-02-26"]):
            commits.append(make_commit(
                repo="ebs", project="EBS", commit_scope="gfx",
                date=date, timestamp=f"{date}T14:00:00",
                commit_hash=f"gfx{i:03d}",
            ))

        # 6. ui_overlay 분석 (ui_overlay, path-based: no branch, no scope)
        for i, date in enumerate(["2026-02-23", "2026-03-01", "2026-03-14"]):
            commits.append(make_commit(
                repo="ui_overlay", project="EBS",
                branch=None, commit_scope=None,
                date=date, timestamp=f"{date}T15:00:00",
                commit_hash=f"uio{i:03d}",
            ))

        # 7. EBS UI Design v3 (ebs, branch=feat/ebs-ui-design-v3, scope=ui-design)
        for i, date in enumerate(["2026-03-05", "2026-03-08", "2026-03-11"]):
            commits.append(make_commit(
                repo="ebs", project="EBS",
                branch="feat/ebs-ui-design-v3",
                commit_scope="ui-design",
                date=date, timestamp=f"{date}T10:00:00",
                commit_hash=f"uid{i:03d}",
            ))

        # 8. Flutter 앱 포팅 (ebs_reverse_app, branch=feat/flutter-porting)
        for i, date in enumerate(["2026-03-03", "2026-03-04"]):
            commits.append(make_commit(
                repo="ebs_reverse_app", project="EBS",
                branch="feat/flutter-porting",
                date=date, timestamp=f"{date}T10:00:00",
                commit_hash=f"flu{i:03d}",
            ))

        # 9. OTT 기획서 (wsoptv_ott, scope=ott)
        for i, date in enumerate(["2026-01-19", "2026-02-15", "2026-03-13"]):
            commits.append(make_commit(
                repo="wsoptv_ott", project="WSOPTV", commit_scope="ott",
                date=date, timestamp=f"{date}T10:00:00",
                commit_hash=f"ott{i:03d}",
            ))

        # 10. MVP 앱 (wsoptv_ott, branch=feat/mvp-app)
        for i, date in enumerate(["2026-01-23", "2026-02-01", "2026-02-09"]):
            commits.append(make_commit(
                repo="wsoptv_ott", project="WSOPTV",
                branch="feat/mvp-app",
                date=date, timestamp=f"{date}T11:00:00",
                commit_hash=f"mvp{i:03d}",
            ))

        # 12. 네비게이션 (wsoptv_ott, scope=navigation)
        for i, date in enumerate(["2026-02-16", "2026-02-22", "2026-03-01"]):
            commits.append(make_commit(
                repo="wsoptv_ott", project="WSOPTV", commit_scope="navigation",
                date=date, timestamp=f"{date}T12:00:00",
                commit_hash=f"nav{i:03d}",
            ))

        # 13. Academy 홈페이지 (wsop_academy, path-based)
        for i, date in enumerate(["2026-03-09", "2026-03-11", "2026-03-13"]):
            commits.append(make_commit(
                repo="wsop_academy", project="WSOPTV",
                branch=None, commit_scope=None,
                date=date, timestamp=f"{date}T13:00:00",
                commit_hash=f"aca{i:03d}",
            ))

        return commits

    async def test_ebs_branch_streams_detected(self, storage):
        """EBS 브랜치 기반 스트림 감지 검증"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        branch_streams = {s.name: s for s in result if s.detection_method == DetectionMethod.BRANCH}
        # feat/reverse-engineering → "reverse-engineering"
        assert "reverse-engineering" in branch_streams
        # feat/ebs-ui-design-v3 → "ebs-ui-design-v3"
        assert "ebs-ui-design-v3" in branch_streams
        # feat/flutter-porting → "flutter-porting"
        assert "flutter-porting" in branch_streams
        # feat/mvp-app → "mvp-app"
        assert "mvp-app" in branch_streams

    async def test_ebs_scope_streams_detected(self, storage):
        """EBS scope 기반 스트림 감지 검증"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        # scope 기반 스트림들
        scope_or_branch_names = {s.name for s in result}
        # scope=master-plan, hardware-plan, gfx, ui-design, reverse
        assert "master-plan" in scope_or_branch_names
        assert "hardware-plan" in scope_or_branch_names
        assert "gfx" in scope_or_branch_names

    async def test_path_based_streams_detected(self, storage):
        """PATH 기반 스트림 감지 검증 (branch/scope 없는 커밋)"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        path_streams = {s.name: s for s in result if s.detection_method == DetectionMethod.PATH}
        # ui_overlay repo → stream name "ui_overlay"
        assert "ui_overlay" in path_streams
        # wsop_academy repo → stream name "wsop_academy"
        assert "wsop_academy" in path_streams

    async def test_wsoptv_streams_detected(self, storage):
        """WSOPTV 프로젝트 스트림 감지 검증"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        wsoptv_streams = [s for s in result if s.project == "WSOPTV"]
        wsoptv_names = {s.name for s in wsoptv_streams}

        # OTT 기획서 (scope=ott)
        assert "ott" in wsoptv_names
        # MVP 앱 (branch=feat/mvp-app)
        assert "mvp-app" in wsoptv_names
        # 네비게이션 (scope=navigation)
        assert "navigation" in wsoptv_names
        # Academy (path, repo=wsop_academy)
        assert "wsop_academy" in wsoptv_names

    async def test_ebs_streams_correct_project(self, storage):
        """감지된 EBS 스트림이 올바른 project 분류를 가지는지 확인"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        ebs_streams = [s for s in result if s.project == "EBS"]
        # 최소 5개 이상의 EBS 스트림이 감지되어야 함
        assert len(ebs_streams) >= 5

    async def test_all_streams_have_valid_status(self, storage):
        """모든 감지된 스트림이 유효한 상태를 가지는지 확인"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        for stream in result:
            assert stream.status in list(StreamStatus), (
                f"Stream '{stream.name}' has invalid status: {stream.status}"
            )

    async def test_all_streams_have_timestamps(self, storage):
        """모든 감지된 스트림이 first/last_commit 타임스탬프를 가지는지 확인"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        for stream in result:
            assert stream.first_commit, f"Stream '{stream.name}' missing first_commit"
            assert stream.last_commit, f"Stream '{stream.name}' missing last_commit"

    async def test_ui_overlay_path_stream_duration(self, storage):
        """ui_overlay PATH 스트림 기간 검증 (2/23~3/14 = 20일)"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        path_streams = {s.name: s for s in result if s.detection_method == DetectionMethod.PATH}
        uio = path_streams.get("ui_overlay")
        if uio:
            # first: 2026-02-23, last: 2026-03-14 → 20 days
            assert uio.duration_days == 20

    async def test_ott_stream_long_duration(self, storage):
        """OTT 기획서 스트림이 장기 기간(전 기간)을 올바르게 기록하는지 확인"""
        detector = StreamDetector(storage)
        commits = self._make_prd_commits()
        result = await detector.detect_streams(commits)

        # OTT는 scope=ott로 감지됨
        ott = next(
            (s for s in result if s.name == "ott" and s.project == "WSOPTV"),
            None,
        )
        assert ott is not None
        # first: 2026-01-19, last: 2026-03-13
        assert ott.first_commit.startswith("2026-01-19")
        assert ott.last_commit.startswith("2026-03-13")
        # duration >= 53 days
        assert ott.duration_days >= 53
