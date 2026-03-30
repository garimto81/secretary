"""
파일시스템 기반 프로젝트 변경 감지 스캐너

git 없는 디렉토리도 파일 크기/수정시간 변화로 활동을 감지합니다.
Snapshot + Delta 패턴: 최초 1회 baseline → 이후 증분 비교.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class FileRecord:
    """스캔된 파일 1건의 메타데이터"""
    file_path: str       # base_dir 기준 상대 경로
    file_size: int       # 바이트
    modified_at: str     # ISO 8601 (파일 mtime)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_size": self.file_size,
            "modified_at": self.modified_at,
        }


class FileSystemScanner:
    """C:\\claude 하위 디렉토리를 재귀 스캔하여 파일 메타데이터를 수집"""

    SKIP_DIRS = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        ".next", "dist", "build", ".ruff_cache", ".pytest_cache",
        ".astro", ".turbo", ".mypy_cache", ".tox", "egg-info",
    }
    SKIP_EXTENSIONS = {".pyc", ".pyo", ".o", ".so", ".dll", ".exe"}
    MAX_DEPTH = 4

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or Path(r"C:\claude")

    def scan_all(self) -> dict[str, list[FileRecord]]:
        """모든 1단계 디렉토리 스캔 → {dir_name: [FileRecord, ...]}"""
        result: dict[str, list[FileRecord]] = {}
        for item in sorted(self.base_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                records = self._scan_directory(item, depth=0)
                if records:
                    result[item.name] = records
        return result

    def scan_project(self, project_dir: str) -> list[FileRecord]:
        """특정 프로젝트만 스캔"""
        path = self.base_dir / project_dir
        if not path.is_dir():
            return []
        return self._scan_directory(path, depth=0)

    def _scan_directory(self, path: Path, depth: int) -> list[FileRecord]:
        """재귀 스캔 (MAX_DEPTH 제한, SKIP 적용)"""
        records: list[FileRecord] = []
        if depth > self.MAX_DEPTH:
            return records
        try:
            for item in path.iterdir():
                if item.name in self.SKIP_DIRS:
                    continue
                try:
                    if item.is_dir():
                        records.extend(self._scan_directory(item, depth + 1))
                    elif item.is_file() and item.suffix not in self.SKIP_EXTENSIONS:
                        stat = item.stat()
                        records.append(FileRecord(
                            file_path=str(item.relative_to(self.base_dir)).replace("\\", "/"),
                            file_size=stat.st_size,
                            modified_at=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        ))
                except (OSError, ValueError):
                    continue
        except (PermissionError, OSError):
            pass
        return records

    @staticmethod
    def detect_changes(
        old_snapshot: list[dict], new_snapshot: list[dict]
    ) -> dict[str, list[dict]]:
        """두 스냅샷 비교 → {added, modified, deleted}"""
        old_map = {r["file_path"]: r for r in old_snapshot}
        new_map = {r["file_path"]: r for r in new_snapshot}

        added = [new_map[p] for p in new_map if p not in old_map]
        deleted = [old_map[p] for p in old_map if p not in new_map]
        modified = [
            new_map[p] for p in new_map
            if p in old_map and (
                new_map[p]["file_size"] != old_map[p]["file_size"]
                or new_map[p]["modified_at"] != old_map[p]["modified_at"]
            )
        ]
        return {"added": added, "modified": modified, "deleted": deleted}

    @staticmethod
    def summarize_by_project(
        changes: dict[str, list[dict]]
    ) -> dict[str, dict[str, int]]:
        """변경 파일을 1단계 디렉토리(프로젝트)별로 집계"""
        projects: dict[str, dict[str, int]] = {}

        for change_type in ("added", "modified", "deleted"):
            for record in changes.get(change_type, []):
                # file_path: "ebs_ui/src/main.py" → project = "ebs_ui"
                parts = record["file_path"].split("/")
                proj = parts[0] if parts else "unknown"
                if proj not in projects:
                    projects[proj] = {"added": 0, "modified": 0, "deleted": 0}
                projects[proj][change_type] += 1

        return projects
