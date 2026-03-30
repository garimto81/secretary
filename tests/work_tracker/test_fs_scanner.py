"""
FileSystemScanner + file_snapshots 스토리지 테스트
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.work_tracker.fs_scanner import FileSystemScanner, FileRecord
from scripts.work_tracker.storage import WorkTrackerStorage


class TestFileRecord:
    def test_to_dict(self):
        r = FileRecord(file_path="proj/src/main.py", file_size=1024, modified_at="2026-03-19T10:00:00")
        d = r.to_dict()
        assert d["file_path"] == "proj/src/main.py"
        assert d["file_size"] == 1024
        assert d["modified_at"] == "2026-03-19T10:00:00"


class TestFileSystemScanner:
    def test_scan_project_nonexistent(self, tmp_path):
        scanner = FileSystemScanner(base_dir=tmp_path)
        result = scanner.scan_project("nonexistent")
        assert result == []

    def test_scan_project_with_files(self, tmp_path):
        proj = tmp_path / "my_project"
        proj.mkdir()
        (proj / "readme.md").write_text("hello")
        (proj / "src").mkdir()
        (proj / "src" / "main.py").write_text("print('hi')")

        scanner = FileSystemScanner(base_dir=tmp_path)
        records = scanner.scan_project("my_project")
        paths = [r.file_path for r in records]
        assert "my_project/readme.md" in paths
        assert "my_project/src/main.py" in paths

    def test_skip_dirs(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "app.py").write_text("code")
        nm = proj / "node_modules"
        nm.mkdir()
        (nm / "pkg.js").write_text("module")

        scanner = FileSystemScanner(base_dir=tmp_path)
        records = scanner.scan_project("proj")
        paths = [r.file_path for r in records]
        assert "proj/app.py" in paths
        assert not any("node_modules" in p for p in paths)

    def test_skip_extensions(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "main.py").write_text("code")
        (proj / "main.pyc").write_bytes(b"\x00\x00")

        scanner = FileSystemScanner(base_dir=tmp_path)
        records = scanner.scan_project("proj")
        paths = [r.file_path for r in records]
        assert "proj/main.py" in paths
        assert "proj/main.pyc" not in paths

    def test_max_depth(self, tmp_path):
        proj = tmp_path / "proj"
        current = proj
        for i in range(6):
            current = current / f"d{i}"
        current.mkdir(parents=True)
        (current / "deep.txt").write_text("deep")

        scanner = FileSystemScanner(base_dir=tmp_path)
        records = scanner.scan_project("proj")
        # MAX_DEPTH=4 이므로 depth 5 이상은 스캔 안 됨
        deep_paths = [r for r in records if "deep.txt" in r.file_path]
        assert len(deep_paths) == 0

    def test_scan_all(self, tmp_path):
        (tmp_path / "proj_a").mkdir()
        (tmp_path / "proj_a" / "a.txt").write_text("a")
        (tmp_path / "proj_b").mkdir()
        (tmp_path / "proj_b" / "b.txt").write_text("b")
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "h.txt").write_text("h")

        scanner = FileSystemScanner(base_dir=tmp_path)
        result = scanner.scan_all()
        assert "proj_a" in result
        assert "proj_b" in result
        assert ".hidden" not in result

    def test_detect_changes_added(self):
        old = [{"file_path": "a.txt", "file_size": 10, "modified_at": "2026-03-18T10:00:00"}]
        new = [
            {"file_path": "a.txt", "file_size": 10, "modified_at": "2026-03-18T10:00:00"},
            {"file_path": "b.txt", "file_size": 20, "modified_at": "2026-03-19T10:00:00"},
        ]
        changes = FileSystemScanner.detect_changes(old, new)
        assert len(changes["added"]) == 1
        assert changes["added"][0]["file_path"] == "b.txt"
        assert len(changes["modified"]) == 0
        assert len(changes["deleted"]) == 0

    def test_detect_changes_modified(self):
        old = [{"file_path": "a.txt", "file_size": 10, "modified_at": "2026-03-18T10:00:00"}]
        new = [{"file_path": "a.txt", "file_size": 15, "modified_at": "2026-03-19T10:00:00"}]
        changes = FileSystemScanner.detect_changes(old, new)
        assert len(changes["modified"]) == 1
        assert len(changes["added"]) == 0

    def test_detect_changes_deleted(self):
        old = [
            {"file_path": "a.txt", "file_size": 10, "modified_at": "2026-03-18T10:00:00"},
            {"file_path": "b.txt", "file_size": 20, "modified_at": "2026-03-18T10:00:00"},
        ]
        new = [{"file_path": "a.txt", "file_size": 10, "modified_at": "2026-03-18T10:00:00"}]
        changes = FileSystemScanner.detect_changes(old, new)
        assert len(changes["deleted"]) == 1
        assert changes["deleted"][0]["file_path"] == "b.txt"

    def test_summarize_by_project(self):
        changes = {
            "added": [
                {"file_path": "proj_a/new.txt", "file_size": 10, "modified_at": "2026-03-19T10:00:00"},
            ],
            "modified": [
                {"file_path": "proj_a/old.txt", "file_size": 20, "modified_at": "2026-03-19T10:00:00"},
                {"file_path": "proj_b/app.py", "file_size": 30, "modified_at": "2026-03-19T10:00:00"},
            ],
            "deleted": [],
        }
        summary = FileSystemScanner.summarize_by_project(changes)
        assert summary["proj_a"]["added"] == 1
        assert summary["proj_a"]["modified"] == 1
        assert summary["proj_b"]["modified"] == 1


@pytest.mark.asyncio
class TestFileSnapshotStorage:
    async def test_save_and_get_file_snapshots(self, tmp_path):
        db_path = tmp_path / "test.db"
        async with WorkTrackerStorage(db_path) as storage:
            records = [
                {
                    "project_dir": "proj_a",
                    "file_path": "proj_a/main.py",
                    "file_size": 100,
                    "modified_at": "2026-03-19T10:00:00",
                    "snapshot_date": "2026-03-19",
                },
                {
                    "project_dir": "proj_a",
                    "file_path": "proj_a/utils.py",
                    "file_size": 200,
                    "modified_at": "2026-03-19T09:00:00",
                    "snapshot_date": "2026-03-19",
                },
            ]
            saved = await storage.save_file_snapshots(records)
            assert saved == 2

            # 조회
            result = await storage.get_latest_file_snapshot("proj_a")
            assert len(result) == 2
            paths = [r["file_path"] for r in result]
            assert "proj_a/main.py" in paths

    async def test_duplicate_insert_ignored(self, tmp_path):
        db_path = tmp_path / "test.db"
        async with WorkTrackerStorage(db_path) as storage:
            record = [{
                "project_dir": "proj",
                "file_path": "proj/a.txt",
                "file_size": 50,
                "modified_at": "2026-03-19T10:00:00",
                "snapshot_date": "2026-03-19",
            }]
            await storage.save_file_snapshots(record)
            saved2 = await storage.save_file_snapshots(record)
            # UNIQUE constraint → 중복 무시
            result = await storage.get_latest_file_snapshot("proj")
            assert len(result) == 1

    async def test_get_snapshot_dates(self, tmp_path):
        db_path = tmp_path / "test.db"
        async with WorkTrackerStorage(db_path) as storage:
            for date in ["2026-03-17", "2026-03-18", "2026-03-19"]:
                await storage.save_file_snapshots([{
                    "project_dir": "proj",
                    "file_path": f"proj/{date}.txt",
                    "file_size": 10,
                    "modified_at": f"{date}T10:00:00",
                    "snapshot_date": date,
                }])
            dates = await storage.get_file_snapshot_dates()
            assert dates == ["2026-03-19", "2026-03-18", "2026-03-17"]

    async def test_get_latest_without_project_filter(self, tmp_path):
        db_path = tmp_path / "test.db"
        async with WorkTrackerStorage(db_path) as storage:
            await storage.save_file_snapshots([
                {
                    "project_dir": "a",
                    "file_path": "a/x.txt",
                    "file_size": 10,
                    "modified_at": "2026-03-19T10:00:00",
                    "snapshot_date": "2026-03-19",
                },
                {
                    "project_dir": "b",
                    "file_path": "b/y.txt",
                    "file_size": 20,
                    "modified_at": "2026-03-19T10:00:00",
                    "snapshot_date": "2026-03-19",
                },
            ])
            result = await storage.get_latest_file_snapshot()
            assert len(result) == 2
