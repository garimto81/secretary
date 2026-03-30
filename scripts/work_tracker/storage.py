"""
Work Tracker SQLite 스토리지

Git 커밋, Work Stream, 일일/주간 요약 데이터를 aiosqlite 기반으로 저장/조회합니다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# 3-way import (scripts.work_tracker.models → work_tracker.models → .models)
try:
    from scripts.work_tracker.models import (
        DailyCommit,
        FileChange,
        WorkStream,
        DailySummary,
        WeeklySummary,
        CommitType,
        StreamStatus,
        DetectionMethod,
        ProjectSnapshot,
    )
except ImportError:
    try:
        from work_tracker.models import (
            DailyCommit,
            FileChange,
            WorkStream,
            DailySummary,
            WeeklySummary,
            CommitType,
            StreamStatus,
            DetectionMethod,
            ProjectSnapshot,
        )
    except ImportError:
        from .models import (
            DailyCommit,
            FileChange,
            WorkStream,
            DailySummary,
            WeeklySummary,
            CommitType,
            StreamStatus,
            DetectionMethod,
            ProjectSnapshot,
        )

# 기본 DB 경로 (scripts.shared.paths 우선, fallback)
try:
    try:
        from scripts.shared.paths import WORK_TRACKER_DB as _DEFAULT_DB_PATH
    except ImportError:
        try:
            from shared.paths import WORK_TRACKER_DB as _DEFAULT_DB_PATH
        except ImportError:
            from ..shared.paths import WORK_TRACKER_DB as _DEFAULT_DB_PATH
except Exception:
    _DEFAULT_DB_PATH = Path(r"C:\claude\secretary\data\work_tracker.db")

DEFAULT_DB_PATH: Path = _DEFAULT_DB_PATH

# SQL Schema
SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS daily_commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    repo TEXT NOT NULL,
    project TEXT NOT NULL,
    category TEXT,
    commit_hash TEXT NOT NULL,
    commit_type TEXT,
    commit_scope TEXT,
    message TEXT NOT NULL,
    author TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    files_changed INTEGER DEFAULT 0,
    insertions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    branch TEXT,
    UNIQUE(commit_hash)
);

CREATE TABLE IF NOT EXISTS doc_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_id INTEGER REFERENCES daily_commits(id),
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,
    insertions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work_streams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project TEXT NOT NULL,
    repos TEXT NOT NULL,
    first_commit TEXT NOT NULL,
    last_commit TEXT NOT NULL,
    total_commits INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    duration_days INTEGER DEFAULT 0,
    detection_method TEXT,
    metadata TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    total_commits INTEGER DEFAULT 0,
    total_insertions INTEGER DEFAULT 0,
    total_deletions INTEGER DEFAULT 0,
    doc_change_ratio REAL DEFAULT 0,
    project_distribution TEXT,
    active_streams INTEGER DEFAULT 0,
    highlights TEXT,
    next_tasks TEXT,
    slack_message_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weekly_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_label TEXT NOT NULL UNIQUE,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_commits INTEGER DEFAULT 0,
    velocity_trend TEXT,
    completed_streams TEXT,
    new_streams TEXT,
    project_distribution TEXT,
    highlights TEXT,
    slack_message_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS project_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    repos TEXT NOT NULL,
    github_data TEXT,
    local_structure TEXT,
    git_history TEXT,
    analysis TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(project, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_commits_date ON daily_commits(date);
CREATE INDEX IF NOT EXISTS idx_commits_repo ON daily_commits(repo);
CREATE INDEX IF NOT EXISTS idx_commits_project ON daily_commits(project);
CREATE INDEX IF NOT EXISTS idx_streams_status ON work_streams(status);
CREATE INDEX IF NOT EXISTS idx_streams_project ON work_streams(project);
CREATE INDEX IF NOT EXISTS idx_snapshot_project ON project_snapshots(project);

CREATE TABLE IF NOT EXISTS file_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_dir TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    modified_at TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(file_path, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_filesnapshot_dir ON file_snapshots(project_dir);
CREATE INDEX IF NOT EXISTS idx_filesnapshot_date ON file_snapshots(snapshot_date);
"""


def _commit_to_db_dict(commit: DailyCommit) -> dict[str, Any]:
    """DailyCommit → DB 저장용 딕셔너리"""
    commit_type_val = None
    if commit.commit_type is not None:
        commit_type_val = (
            commit.commit_type.value
            if isinstance(commit.commit_type, CommitType)
            else commit.commit_type
        )
    return {
        "date": commit.date,
        "repo": commit.repo,
        "project": commit.project,
        "category": commit.category,
        "commit_hash": commit.commit_hash,
        "commit_type": commit_type_val,
        "commit_scope": commit.commit_scope,
        "message": commit.message,
        "author": commit.author,
        "timestamp": commit.timestamp,
        "files_changed": commit.files_changed,
        "insertions": commit.insertions,
        "deletions": commit.deletions,
        "branch": commit.branch,
    }


def _db_row_to_commit(row: dict[str, Any]) -> DailyCommit:
    """DB 행 → DailyCommit"""
    commit_type_raw = row.get("commit_type")
    commit_type = None
    if commit_type_raw:
        try:
            commit_type = CommitType(commit_type_raw)
        except ValueError:
            commit_type = CommitType.OTHER
    return DailyCommit(
        date=row["date"],
        repo=row["repo"],
        project=row["project"],
        category=row.get("category"),
        commit_hash=row["commit_hash"],
        commit_type=commit_type,
        commit_scope=row.get("commit_scope"),
        message=row["message"],
        author=row["author"],
        timestamp=row["timestamp"],
        files_changed=int(row.get("files_changed") or 0),
        insertions=int(row.get("insertions") or 0),
        deletions=int(row.get("deletions") or 0),
        branch=row.get("branch"),
    )


def _stream_to_db_dict(stream: WorkStream, now: str | None = None) -> dict[str, Any]:
    """WorkStream → DB 저장용 딕셔너리"""
    status_val = (
        stream.status.value if isinstance(stream.status, StreamStatus) else stream.status
    )
    detection_val = None
    if stream.detection_method is not None:
        detection_val = (
            stream.detection_method.value
            if isinstance(stream.detection_method, DetectionMethod)
            else stream.detection_method
        )
    return {
        "name": stream.name,
        "project": stream.project,
        "repos": json.dumps(stream.repos if stream.repos is not None else []),
        "first_commit": stream.first_commit,
        "last_commit": stream.last_commit,
        "total_commits": stream.total_commits,
        "status": status_val,
        "duration_days": stream.duration_days,
        "detection_method": detection_val,
        "metadata": json.dumps(stream.metadata if stream.metadata is not None else {}),
        "updated_at": now or datetime.now().isoformat(),
    }


def _db_row_to_stream(row: dict[str, Any]) -> WorkStream:
    """DB 행 → WorkStream"""
    try:
        status = StreamStatus(row.get("status", "active"))
    except ValueError:
        status = StreamStatus.ACTIVE

    detection_raw = row.get("detection_method")
    detection = None
    if detection_raw:
        try:
            detection = DetectionMethod(detection_raw)
        except ValueError:
            detection = None

    repos_raw = row.get("repos", "[]")
    try:
        repos = json.loads(repos_raw) if repos_raw else []
    except (json.JSONDecodeError, TypeError):
        repos = []

    metadata_raw = row.get("metadata")
    try:
        metadata = json.loads(metadata_raw) if metadata_raw else None
    except (json.JSONDecodeError, TypeError):
        metadata = None

    return WorkStream(
        name=row["name"],
        project=row["project"],
        repos=repos,
        first_commit=row["first_commit"],
        last_commit=row["last_commit"],
        total_commits=int(row.get("total_commits") or 0),
        status=status,
        duration_days=int(row.get("duration_days") or 0),
        detection_method=detection,
        metadata=metadata,
    )


def _daily_summary_to_db_dict(summary: DailySummary, now: str | None = None) -> dict[str, Any]:
    """DailySummary → DB 저장용 딕셔너리"""
    return {
        "date": summary.date,
        "total_commits": summary.total_commits,
        "total_insertions": summary.total_insertions,
        "total_deletions": summary.total_deletions,
        "doc_change_ratio": summary.doc_change_ratio,
        "project_distribution": json.dumps(
            summary.project_distribution if summary.project_distribution is not None else {}
        ),
        "active_streams": summary.active_streams,
        "highlights": json.dumps(summary.highlights if summary.highlights is not None else []),
        "next_tasks": json.dumps(summary.next_tasks if summary.next_tasks is not None else []),
        "slack_message_id": summary.slack_message_id,
        "github_summary": json.dumps(summary.github_summary) if summary.github_summary else None,
        "progress_by_project": json.dumps(summary.progress_by_project) if summary.progress_by_project else None,
        "predictions": json.dumps(summary.predictions if summary.predictions else []),
        "created_at": now or datetime.now().isoformat(),
    }


def _db_row_to_daily_summary(row: dict[str, Any]) -> DailySummary:
    """DB 행 → DailySummary"""
    dist_raw = row.get("project_distribution")
    try:
        project_distribution = json.loads(dist_raw) if dist_raw else {}
    except (json.JSONDecodeError, TypeError):
        project_distribution = {}

    highlights_raw = row.get("highlights")
    try:
        highlights = json.loads(highlights_raw) if highlights_raw else []
    except (json.JSONDecodeError, TypeError):
        highlights = []

    next_tasks_raw = row.get("next_tasks")
    try:
        next_tasks = json.loads(next_tasks_raw) if next_tasks_raw else []
    except (json.JSONDecodeError, TypeError):
        next_tasks = []

    github_summary_raw = row.get("github_summary")
    try:
        github_summary = json.loads(github_summary_raw) if github_summary_raw else None
    except (json.JSONDecodeError, TypeError):
        github_summary = None

    progress_raw = row.get("progress_by_project")
    try:
        progress_by_project = json.loads(progress_raw) if progress_raw else None
    except (json.JSONDecodeError, TypeError):
        progress_by_project = None

    predictions_raw = row.get("predictions")
    try:
        predictions = json.loads(predictions_raw) if predictions_raw else []
    except (json.JSONDecodeError, TypeError):
        predictions = []

    return DailySummary(
        date=row["date"],
        total_commits=int(row.get("total_commits") or 0),
        total_insertions=int(row.get("total_insertions") or 0),
        total_deletions=int(row.get("total_deletions") or 0),
        doc_change_ratio=float(row.get("doc_change_ratio") or 0.0),
        project_distribution=project_distribution,
        active_streams=int(row.get("active_streams") or 0),
        highlights=highlights,
        next_tasks=next_tasks,
        slack_message_id=row.get("slack_message_id"),
        github_summary=github_summary,
        progress_by_project=progress_by_project,
        predictions=predictions,
    )


def _weekly_summary_to_db_dict(summary: WeeklySummary, now: str | None = None) -> dict[str, Any]:
    """WeeklySummary → DB 저장용 딕셔너리"""
    return {
        "week_label": summary.week_label,
        "start_date": summary.start_date,
        "end_date": summary.end_date,
        "total_commits": summary.total_commits,
        "velocity_trend": json.dumps(
            summary.velocity_trend if summary.velocity_trend is not None else []
        ),
        "completed_streams": json.dumps(
            summary.completed_streams if summary.completed_streams is not None else []
        ),
        "new_streams": json.dumps(
            summary.new_streams if summary.new_streams is not None else []
        ),
        "project_distribution": json.dumps(
            summary.project_distribution if summary.project_distribution is not None else {}
        ),
        "highlights": json.dumps(
            summary.highlights if summary.highlights is not None else []
        ),
        "slack_message_id": summary.slack_message_id,
        "created_at": now or datetime.now().isoformat(),
    }


def _db_row_to_weekly_summary(row: dict[str, Any]) -> WeeklySummary:
    """DB 행 → WeeklySummary"""
    def _load_list(val: Any) -> list:
        try:
            return json.loads(val) if val else []
        except (json.JSONDecodeError, TypeError):
            return []

    def _load_dict(val: Any) -> dict:
        try:
            return json.loads(val) if val else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    return WeeklySummary(
        week_label=row["week_label"],
        start_date=row["start_date"],
        end_date=row["end_date"],
        total_commits=int(row.get("total_commits") or 0),
        velocity_trend=_load_list(row.get("velocity_trend")),
        completed_streams=_load_list(row.get("completed_streams")),
        new_streams=_load_list(row.get("new_streams")),
        project_distribution=_load_dict(row.get("project_distribution")),
        highlights=_load_list(row.get("highlights")),
        slack_message_id=row.get("slack_message_id"),
    )


class WorkTrackerStorage:
    """
    Work Tracker SQLite 스토리지

    Features:
    - Git 커밋 배치 저장 (UNIQUE constraint로 중복 무시)
    - Work Stream upsert
    - 일일/주간 요약 저장/조회
    - WAL 모드 비동기 SQLite

    Example:
        async with WorkTrackerStorage() as storage:
            saved = await storage.save_commits(commits)
            commits = await storage.get_commits_by_date("2026-03-17")
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: aiosqlite.Connection | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self) -> None:
        """DB 연결 및 스키마 초기화 (WAL 모드 포함)"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()
        await self._migrate_daily_summaries()

    async def _migrate_daily_summaries(self) -> None:
        """daily_summaries 테이블에 멀티소스 확장 컬럼 추가 (하위 호환)"""
        for col, col_type in [
            ("github_summary", "TEXT"),
            ("progress_by_project", "TEXT"),
            ("predictions", "TEXT"),
        ]:
            try:
                await self._connection.execute(
                    f"ALTER TABLE daily_summaries ADD COLUMN {col} {col_type}"
                )
            except Exception:
                pass  # 이미 존재하면 무시
        await self._connection.commit()

    async def close(self) -> None:
        """DB 연결 종료"""
        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None

    def _check_connected(self) -> None:
        if not self._connection:
            raise RuntimeError(
                "Storage not connected. Use 'async with' or call connect() first."
            )

    # ------------------------------------------------------------------
    # Commits
    # ------------------------------------------------------------------

    async def save_commits(self, commits: list[DailyCommit]) -> int:
        """커밋 배치 저장. INSERT OR IGNORE (UNIQUE constraint). Returns saved count."""
        self._check_connected()
        saved = 0
        for commit in commits:
            data = _commit_to_db_dict(commit)
            columns = ", ".join(data.keys())
            placeholders = ", ".join(["?" for _ in data])
            query = f"INSERT OR IGNORE INTO daily_commits ({columns}) VALUES ({placeholders})"
            cursor = await self._connection.execute(query, list(data.values()))
            saved += cursor.rowcount
        await self._connection.commit()
        return saved

    async def save_file_changes(self, commit_hash: str, changes: list[FileChange]) -> None:
        """파일 변경 저장. commit_hash → commit_id 조회 후 삽입."""
        self._check_connected()
        async with self._connection.execute(
            "SELECT id FROM daily_commits WHERE commit_hash = ?", (commit_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return
            commit_id = row["id"]

        for change in changes:
            await self._connection.execute(
                """
                INSERT INTO doc_changes (commit_id, file_path, change_type, insertions, deletions)
                VALUES (?, ?, ?, ?, ?)
                """,
                (commit_id, change.file_path, change.change_type, change.insertions, change.deletions),
            )
        await self._connection.commit()

    async def get_commits_by_date(
        self, date: str, project: str | None = None
    ) -> list[DailyCommit]:
        """날짜별 커밋 조회. project 필터 선택."""
        self._check_connected()
        query = "SELECT * FROM daily_commits WHERE date = ?"
        params: list[Any] = [date]
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY timestamp ASC"
        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_db_row_to_commit(dict(row)) for row in rows]

    async def get_commits_by_range(
        self, start_date: str, end_date: str, project: str | None = None
    ) -> list[DailyCommit]:
        """기간별 커밋 조회."""
        self._check_connected()
        query = "SELECT * FROM daily_commits WHERE date >= ? AND date <= ?"
        params: list[Any] = [start_date, end_date]
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY timestamp ASC"
        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_db_row_to_commit(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # Work Streams
    # ------------------------------------------------------------------

    async def save_streams(self, streams: list[WorkStream]) -> None:
        """Work Stream 저장. name+project로 upsert."""
        self._check_connected()
        now = datetime.now().isoformat()
        for stream in streams:
            data = _stream_to_db_dict(stream, now)
            # Check if exists by name + project
            async with self._connection.execute(
                "SELECT id FROM work_streams WHERE name = ? AND project = ?",
                (stream.name, stream.project),
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                # Update
                set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
                values = list(data.values()) + [existing["id"]]
                await self._connection.execute(
                    f"UPDATE work_streams SET {set_clause} WHERE id = ?", values
                )
            else:
                # Insert
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?" for _ in data])
                await self._connection.execute(
                    f"INSERT INTO work_streams ({columns}) VALUES ({placeholders})",
                    list(data.values()),
                )
        await self._connection.commit()

    async def get_streams(
        self, status: str | None = None, project: str | None = None
    ) -> list[WorkStream]:
        """Work Stream 조회. status/project 필터."""
        self._check_connected()
        query = "SELECT * FROM work_streams WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY updated_at DESC"
        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_db_row_to_stream(dict(row)) for row in rows]

    # ------------------------------------------------------------------
    # Daily Summaries
    # ------------------------------------------------------------------

    async def save_daily_summary(self, summary: DailySummary) -> None:
        """일일 요약 저장 (INSERT OR REPLACE)."""
        self._check_connected()
        data = _daily_summary_to_db_dict(summary)
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        await self._connection.execute(
            f"INSERT OR REPLACE INTO daily_summaries ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        await self._connection.commit()

    async def get_daily_summary(self, date: str) -> DailySummary | None:
        """일일 요약 조회."""
        self._check_connected()
        async with self._connection.execute(
            "SELECT * FROM daily_summaries WHERE date = ?", (date,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _db_row_to_daily_summary(dict(row))
            return None

    # ------------------------------------------------------------------
    # Weekly Summaries
    # ------------------------------------------------------------------

    async def save_weekly_summary(self, summary: WeeklySummary) -> None:
        """주간 요약 저장 (INSERT OR REPLACE)."""
        self._check_connected()
        data = _weekly_summary_to_db_dict(summary)
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        await self._connection.execute(
            f"INSERT OR REPLACE INTO weekly_summaries ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        await self._connection.commit()

    async def get_weekly_summary(self, week_label: str) -> WeeklySummary | None:
        """주간 요약 조회."""
        self._check_connected()
        async with self._connection.execute(
            "SELECT * FROM weekly_summaries WHERE week_label = ?", (week_label,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _db_row_to_weekly_summary(dict(row))
            return None

    # ------------------------------------------------------------------
    # Project Snapshots
    # ------------------------------------------------------------------

    async def save_snapshot(self, snapshot: ProjectSnapshot) -> None:
        """프로젝트 스냅샷 저장 (INSERT OR REPLACE)."""
        self._check_connected()
        data = {
            "project": snapshot.project,
            "snapshot_date": snapshot.snapshot_date,
            "repos": json.dumps(snapshot.repos),
            "github_data": json.dumps({
                "open_issues": snapshot.github_open_issues,
                "open_prs": snapshot.github_open_prs,
                "attention": snapshot.github_attention,
            }),
            "local_structure": json.dumps({
                "dir_structure": snapshot.dir_structure,
                "prd_status": snapshot.prd_status,
                "doc_inventory": snapshot.doc_inventory,
            }),
            "git_history": json.dumps({
                "recent_activity": snapshot.recent_activity,
                "active_branches": snapshot.active_branches,
            }),
            "analysis": json.dumps({
                "project_summary": snapshot.project_summary,
                "estimated_progress": snapshot.estimated_progress,
                "milestones": snapshot.milestones,
                "risks": snapshot.risks,
            }),
            "created_at": datetime.now().isoformat(),
        }
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        await self._connection.execute(
            f"INSERT OR REPLACE INTO project_snapshots ({columns}) VALUES ({placeholders})",
            list(data.values()),
        )
        await self._connection.commit()

    async def get_latest_snapshots(self) -> list[ProjectSnapshot]:
        """프로젝트별 최신 스냅샷 1건씩 조회."""
        self._check_connected()
        query = """
            SELECT * FROM project_snapshots
            WHERE id IN (
                SELECT MAX(id) FROM project_snapshots GROUP BY project
            )
            ORDER BY project
        """
        async with self._connection.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [self._db_row_to_snapshot(dict(row)) for row in rows]

    async def get_snapshot(self, project: str, date: str) -> ProjectSnapshot | None:
        """특정 프로젝트 + 날짜 스냅샷 조회."""
        self._check_connected()
        async with self._connection.execute(
            "SELECT * FROM project_snapshots WHERE project = ? AND snapshot_date = ?",
            (project, date),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._db_row_to_snapshot(dict(row))
            return None

    async def update_snapshot_analysis(
        self,
        project: str,
        progress: int = 0,
        summary: str = "",
        milestones: list[dict] | None = None,
        risks: list[str] | None = None,
    ) -> bool:
        """스냅샷의 분석 결과만 업데이트 (Claude Code → DB).

        최신 스냅샷의 analysis JSON 필드만 갱신합니다.

        Args:
            project: 프로젝트명
            progress: 진행률 (0-100)
            summary: 프로젝트 요약
            milestones: 마일스톤 목록 [{"name": "...", "status": "..."}]
            risks: 위험 요소 목록 ["...", "..."]

        Returns:
            True if updated, False if no snapshot found
        """
        self._check_connected()
        # 최신 스냅샷 ID 조회
        async with self._connection.execute(
            "SELECT id, analysis FROM project_snapshots WHERE project = ? ORDER BY id DESC LIMIT 1",
            (project,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False

        snapshot_id = row["id"]
        existing_analysis = json.loads(row["analysis"]) if row["analysis"] else {}

        # 분석 결과 병합
        existing_analysis["project_summary"] = summary or existing_analysis.get("project_summary", "")
        existing_analysis["estimated_progress"] = progress
        if milestones is not None:
            existing_analysis["milestones"] = milestones
        if risks is not None:
            existing_analysis["risks"] = risks

        await self._connection.execute(
            "UPDATE project_snapshots SET analysis = ? WHERE id = ?",
            (json.dumps(existing_analysis), snapshot_id),
        )
        await self._connection.commit()
        return True

    # ------------------------------------------------------------------
    # File Snapshots (파일시스템 변경 감지)
    # ------------------------------------------------------------------

    async def save_file_snapshots(self, records: list[dict]) -> int:
        """파일 스냅샷 bulk insert. Returns saved count."""
        self._check_connected()
        saved = 0
        for r in records:
            try:
                await self._connection.execute(
                    """INSERT OR IGNORE INTO file_snapshots
                       (project_dir, file_path, file_size, modified_at, snapshot_date, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        r["project_dir"],
                        r["file_path"],
                        r["file_size"],
                        r["modified_at"],
                        r["snapshot_date"],
                        r.get("created_at", datetime.now().isoformat()),
                    ),
                )
                saved += 1
            except Exception:
                pass  # UNIQUE constraint 등 무시
        await self._connection.commit()
        return saved

    async def get_latest_file_snapshot(self, project_dir: str | None = None) -> list[dict]:
        """최신 스냅샷 날짜의 파일 목록 조회. project_dir 필터 선택."""
        self._check_connected()
        # 최신 snapshot_date 조회
        if project_dir:
            async with self._connection.execute(
                "SELECT MAX(snapshot_date) as latest FROM file_snapshots WHERE project_dir = ?",
                (project_dir,),
            ) as cursor:
                row = await cursor.fetchone()
        else:
            async with self._connection.execute(
                "SELECT MAX(snapshot_date) as latest FROM file_snapshots",
            ) as cursor:
                row = await cursor.fetchone()

        if not row or not row["latest"]:
            return []

        latest_date = row["latest"]
        query = "SELECT project_dir, file_path, file_size, modified_at, snapshot_date FROM file_snapshots WHERE snapshot_date = ?"
        params: list[Any] = [latest_date]
        if project_dir:
            query += " AND project_dir = ?"
            params.append(project_dir)

        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_file_snapshot_dates(self) -> list[str]:
        """저장된 스냅샷 날짜 목록 (최신순)."""
        self._check_connected()
        async with self._connection.execute(
            "SELECT DISTINCT snapshot_date FROM file_snapshots ORDER BY snapshot_date DESC",
        ) as cursor:
            rows = await cursor.fetchall()
            return [r["snapshot_date"] for r in rows]

    @staticmethod
    def _db_row_to_snapshot(row: dict[str, Any]) -> ProjectSnapshot:
        """DB 행 → ProjectSnapshot"""
        def _load_json(val, default=None):
            if default is None:
                default = {}
            try:
                return json.loads(val) if val else default
            except (json.JSONDecodeError, TypeError):
                return default

        repos = _load_json(row.get("repos"), [])
        github_data = _load_json(row.get("github_data"))
        local_structure = _load_json(row.get("local_structure"))
        git_history = _load_json(row.get("git_history"))
        analysis = _load_json(row.get("analysis"))

        return ProjectSnapshot(
            project=row["project"],
            snapshot_date=row["snapshot_date"],
            repos=repos,
            github_open_issues=github_data.get("open_issues", []),
            github_open_prs=github_data.get("open_prs", []),
            github_attention=github_data.get("attention", []),
            dir_structure=local_structure.get("dir_structure", {}),
            prd_status=local_structure.get("prd_status", []),
            doc_inventory=local_structure.get("doc_inventory", []),
            recent_activity=git_history.get("recent_activity", {}),
            active_branches=git_history.get("active_branches", []),
            project_summary=analysis.get("project_summary", ""),
            estimated_progress=analysis.get("estimated_progress", 0),
            milestones=analysis.get("milestones", []),
            risks=analysis.get("risks", []),
        )
