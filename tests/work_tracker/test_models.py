"""
Work Tracker 데이터 모델 테스트

models.py의 Enum, dataclass, __post_init__, to_dict() 검증.
"""

import pytest
from scripts.work_tracker.models import (
    CommitType,
    StreamStatus,
    DetectionMethod,
    DailyCommit,
    FileChange,
    WorkStream,
    DailySummary,
    WeeklySummary,
)


# ---------------------------------------------------------------------------
# Enum 값 검증
# ---------------------------------------------------------------------------

class TestCommitType:
    def test_values(self):
        assert CommitType.FEAT.value == "feat"
        assert CommitType.FIX.value == "fix"
        assert CommitType.DOCS.value == "docs"
        assert CommitType.REFACTOR.value == "refactor"
        assert CommitType.TEST.value == "test"
        assert CommitType.CHORE.value == "chore"
        assert CommitType.STYLE.value == "style"
        assert CommitType.PERF.value == "perf"
        assert CommitType.CI.value == "ci"
        assert CommitType.BUILD.value == "build"
        assert CommitType.OTHER.value == "other"

    def test_from_string(self):
        assert CommitType("feat") is CommitType.FEAT
        assert CommitType("other") is CommitType.OTHER

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            CommitType("invalid")


class TestStreamStatus:
    def test_values(self):
        assert StreamStatus.ACTIVE.value == "active"
        assert StreamStatus.IDLE.value == "idle"
        assert StreamStatus.COMPLETED.value == "completed"
        assert StreamStatus.NEW.value == "new"

    def test_from_string(self):
        assert StreamStatus("active") is StreamStatus.ACTIVE
        assert StreamStatus("new") is StreamStatus.NEW


class TestDetectionMethod:
    def test_values(self):
        assert DetectionMethod.BRANCH.value == "branch"
        assert DetectionMethod.SCOPE.value == "scope"
        assert DetectionMethod.PATH.value == "path"
        assert DetectionMethod.KEYWORD.value == "keyword"

    def test_from_string(self):
        assert DetectionMethod("branch") is DetectionMethod.BRANCH


# ---------------------------------------------------------------------------
# DailyCommit
# ---------------------------------------------------------------------------

class TestDailyCommit:
    def _make(self, **kwargs):
        defaults = dict(
            date="2026-03-17",
            repo="secretary",
            project="Secretary",
            category=None,
            commit_hash="abc1234",
            commit_type=CommitType.FEAT,
            commit_scope="models",
            message="add work tracker models",
            author="AidenKim",
            timestamp="2026-03-17T10:00:00",
        )
        defaults.update(kwargs)
        return DailyCommit(**defaults)

    def test_default_fields(self):
        dc = self._make()
        assert dc.files_changed == 0
        assert dc.insertions == 0
        assert dc.deletions == 0
        assert dc.branch is None

    def test_post_init_enum_from_string(self):
        dc = self._make(commit_type="feat")
        assert dc.commit_type is CommitType.FEAT

    def test_post_init_enum_already_enum(self):
        dc = self._make(commit_type=CommitType.DOCS)
        assert dc.commit_type is CommitType.DOCS

    def test_to_dict_keys(self):
        dc = self._make(files_changed=3, insertions=10, deletions=2, branch="feat/x")
        d = dc.to_dict()
        assert d["commit_type"] == "feat"
        assert d["files_changed"] == 3
        assert d["insertions"] == 10
        assert d["deletions"] == 2
        assert d["branch"] == "feat/x"
        assert d["category"] is None

    def test_to_dict_round_trip(self):
        dc = self._make(commit_type="chore", branch="main")
        d = dc.to_dict()
        assert d["commit_type"] == "chore"
        assert d["branch"] == "main"


# ---------------------------------------------------------------------------
# FileChange
# ---------------------------------------------------------------------------

class TestFileChange:
    def test_defaults(self):
        fc = FileChange(file_path="src/main.py", change_type="modified")
        assert fc.insertions == 0
        assert fc.deletions == 0

    def test_to_dict(self):
        fc = FileChange(file_path="src/main.py", change_type="added", insertions=5)
        d = fc.to_dict()
        assert d["file_path"] == "src/main.py"
        assert d["change_type"] == "added"
        assert d["insertions"] == 5
        assert d["deletions"] == 0

    def test_change_type_is_plain_string(self):
        for ct in ("added", "modified", "deleted"):
            fc = FileChange(file_path="x.py", change_type=ct)
            assert fc.to_dict()["change_type"] == ct


# ---------------------------------------------------------------------------
# WorkStream
# ---------------------------------------------------------------------------

class TestWorkStream:
    def test_defaults(self):
        ws = WorkStream(name="EBS UI Redesign", project="EBS")
        assert ws.repos == []
        assert ws.total_commits == 0
        assert ws.status is StreamStatus.NEW
        assert ws.detection_method is None
        assert ws.metadata is None

    def test_post_init_status_from_string(self):
        ws = WorkStream(name="X", project="EBS", status="active")
        assert ws.status is StreamStatus.ACTIVE

    def test_post_init_detection_method_from_string(self):
        ws = WorkStream(name="X", project="EBS", detection_method="branch")
        assert ws.detection_method is DetectionMethod.BRANCH

    def test_post_init_none_detection_method(self):
        ws = WorkStream(name="X", project="EBS", detection_method=None)
        assert ws.detection_method is None

    def test_to_dict_serializes_enums(self):
        ws = WorkStream(
            name="Tracker Build",
            project="Secretary",
            repos=["secretary"],
            status=StreamStatus.ACTIVE,
            detection_method=DetectionMethod.SCOPE,
            metadata={"scope": "work_tracker"},
        )
        d = ws.to_dict()
        assert d["status"] == "active"
        assert d["detection_method"] == "scope"
        assert d["metadata"] == {"scope": "work_tracker"}
        assert d["repos"] == ["secretary"]

    def test_to_dict_none_detection_method(self):
        ws = WorkStream(name="X", project="EBS")
        d = ws.to_dict()
        assert d["detection_method"] is None
        assert d["metadata"] is None

    def test_mutable_default_isolation(self):
        ws1 = WorkStream(name="A", project="EBS")
        ws2 = WorkStream(name="B", project="EBS")
        ws1.repos.append("repo1")
        assert ws2.repos == []


# ---------------------------------------------------------------------------
# DailySummary
# ---------------------------------------------------------------------------

class TestDailySummary:
    def test_defaults(self):
        ds = DailySummary(date="2026-03-17")
        assert ds.total_commits == 0
        assert ds.total_insertions == 0
        assert ds.total_deletions == 0
        assert ds.doc_change_ratio == 0.0
        assert ds.project_distribution is None
        assert ds.active_streams == 0
        assert ds.highlights == []
        assert ds.slack_message_id is None

    def test_post_init_none_highlights_normalized(self):
        ds = DailySummary(date="2026-03-17", highlights=None)
        assert ds.highlights == []

    def test_to_dict(self):
        ds = DailySummary(
            date="2026-03-17",
            total_commits=5,
            project_distribution={"EBS": 60, "WSOPTV": 40},
            highlights=["완료: models.py", "신규: test 작성"],
            slack_message_id="S12345",
        )
        d = ds.to_dict()
        assert d["date"] == "2026-03-17"
        assert d["total_commits"] == 5
        assert d["project_distribution"] == {"EBS": 60, "WSOPTV": 40}
        assert d["highlights"] == ["완료: models.py", "신규: test 작성"]
        assert d["slack_message_id"] == "S12345"

    def test_to_dict_none_distribution(self):
        ds = DailySummary(date="2026-03-17")
        d = ds.to_dict()
        assert d["project_distribution"] is None

    def test_mutable_default_isolation(self):
        ds1 = DailySummary(date="2026-03-17")
        ds2 = DailySummary(date="2026-03-17")
        ds1.highlights.append("item")
        assert ds2.highlights == []


# ---------------------------------------------------------------------------
# WeeklySummary
# ---------------------------------------------------------------------------

class TestWeeklySummary:
    def _make(self, **kwargs):
        defaults = dict(
            week_label="W12 (3/10~3/16)",
            start_date="2026-03-10",
            end_date="2026-03-16",
        )
        defaults.update(kwargs)
        return WeeklySummary(**defaults)

    def test_defaults(self):
        ws = self._make()
        assert ws.total_commits == 0
        assert ws.velocity_trend is None
        assert ws.completed_streams == []
        assert ws.new_streams == []
        assert ws.project_distribution is None
        assert ws.highlights == []
        assert ws.slack_message_id is None

    def test_post_init_none_lists_normalized(self):
        ws = self._make(completed_streams=None, new_streams=None, highlights=None)
        assert ws.completed_streams == []
        assert ws.new_streams == []
        assert ws.highlights == []

    def test_to_dict(self):
        ws = self._make(
            total_commits=20,
            velocity_trend={"W09": 12, "W10": 15, "W11": 18, "W12": 20},
            completed_streams=["EBS UI Redesign"],
            new_streams=["Work Tracker"],
            project_distribution={"EBS": 50, "Secretary": 50},
            highlights=["EBS 완료"],
            slack_message_id="W99",
        )
        d = ws.to_dict()
        assert d["week_label"] == "W12 (3/10~3/16)"
        assert d["start_date"] == "2026-03-10"
        assert d["end_date"] == "2026-03-16"
        assert d["total_commits"] == 20
        assert d["velocity_trend"] == {"W09": 12, "W10": 15, "W11": 18, "W12": 20}
        assert d["completed_streams"] == ["EBS UI Redesign"]
        assert d["new_streams"] == ["Work Tracker"]
        assert d["project_distribution"] == {"EBS": 50, "Secretary": 50}
        assert d["highlights"] == ["EBS 완료"]
        assert d["slack_message_id"] == "W99"

    def test_to_dict_none_velocity(self):
        ws = self._make()
        d = ws.to_dict()
        assert d["velocity_trend"] is None
        assert d["project_distribution"] is None

    def test_mutable_default_isolation(self):
        ws1 = self._make()
        ws2 = self._make()
        ws1.completed_streams.append("stream_a")
        ws1.new_streams.append("stream_b")
        ws1.highlights.append("highlight")
        assert ws2.completed_streams == []
        assert ws2.new_streams == []
        assert ws2.highlights == []
