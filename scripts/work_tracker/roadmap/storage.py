"""Roadmap 스토리지 — aiosqlite 기반 Phase/Milestone/Task CRUD"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

try:
    try:
        from scripts.work_tracker.roadmap.models import (
            RoadmapPhase, RoadmapMilestone, RoadmapTask,
            PhaseStatus, MilestoneStatus, TaskStatus, TaskPriority, TaskEffort, TaskSource,
        )
    except ImportError:
        try:
            from work_tracker.roadmap.models import (
                RoadmapPhase, RoadmapMilestone, RoadmapTask,
                PhaseStatus, MilestoneStatus, TaskStatus, TaskPriority, TaskEffort, TaskSource,
            )
        except ImportError:
            from .models import (
                RoadmapPhase, RoadmapMilestone, RoadmapTask,
                PhaseStatus, MilestoneStatus, TaskStatus, TaskPriority, TaskEffort, TaskSource,
            )
except Exception as e:
    raise ImportError(f"roadmap.models import 실패: {e}") from e

# DB 경로 — 기존 work_tracker.db 재사용
try:
    try:
        from scripts.shared.paths import WORK_TRACKER_DB as _DEFAULT_DB_PATH
    except ImportError:
        try:
            from shared.paths import WORK_TRACKER_DB as _DEFAULT_DB_PATH
        except ImportError:
            from ...shared.paths import WORK_TRACKER_DB as _DEFAULT_DB_PATH
except Exception:
    _DEFAULT_DB_PATH = Path(r"C:\claude\secretary\data\work_tracker.db")


ROADMAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS roadmap_phases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    name TEXT NOT NULL,
    "order" INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'planned',
    start_date TEXT,
    end_date TEXT,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(project, name)
);

CREATE TABLE IF NOT EXISTS roadmap_milestones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase_id INTEGER NOT NULL REFERENCES roadmap_phases(id),
    project TEXT NOT NULL,
    name TEXT NOT NULL,
    "order" INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    target_date TEXT,
    completed_date TEXT,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(phase_id, name)
);

CREATE TABLE IF NOT EXISTS roadmap_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    milestone_id INTEGER NOT NULL REFERENCES roadmap_milestones(id),
    project TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'medium',
    effort INTEGER NOT NULL DEFAULT 2,
    source TEXT NOT NULL DEFAULT 'manual',
    related_repo TEXT,
    linked_commits TEXT DEFAULT '[]',
    completed_date TEXT,
    completed_week TEXT,
    description TEXT DEFAULT '',
    depends_on TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_roadmap_phases_project ON roadmap_phases(project);
CREATE INDEX IF NOT EXISTS idx_roadmap_milestones_phase ON roadmap_milestones(phase_id);
CREATE INDEX IF NOT EXISTS idx_roadmap_tasks_milestone ON roadmap_tasks(milestone_id);
CREATE INDEX IF NOT EXISTS idx_roadmap_tasks_status ON roadmap_tasks(status);
CREATE INDEX IF NOT EXISTS idx_roadmap_tasks_project ON roadmap_tasks(project);
"""


class RoadmapStorage:
    """Phase / Milestone / Task 비동기 CRUD 스토리지"""

    def __init__(self, db_path=None):
        self.db_path = db_path or _DEFAULT_DB_PATH
        self.db: Optional[aiosqlite.Connection] = None

    async def __aenter__(self) -> "RoadmapStorage":
        self.db = await aiosqlite.connect(str(self.db_path))
        self.db.row_factory = aiosqlite.Row
        await self._init_tables()
        return self

    async def __aexit__(self, *args) -> None:
        if self.db:
            await self.db.close()

    async def _init_tables(self) -> None:
        for stmt in ROADMAP_SCHEMA.split(";"):
            stmt = stmt.strip()
            if stmt:
                await self.db.execute(stmt)
        await self.db.commit()

    # -------------------------------------------------------------------------
    # Phase CRUD
    # -------------------------------------------------------------------------

    async def save_phase(self, phase: RoadmapPhase) -> int:
        """Phase 저장 (upsert). 반환값: rowid"""
        now = datetime.now().isoformat()
        cursor = await self.db.execute(
            """INSERT INTO roadmap_phases (project, name, "order", status, start_date, end_date, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(project, name) DO UPDATE SET
                 "order"=excluded."order",
                 status=excluded.status,
                 start_date=excluded.start_date,
                 end_date=excluded.end_date,
                 description=excluded.description,
                 updated_at=excluded.updated_at""",
            (
                phase.project, phase.name, phase.order, phase.status.value,
                phase.start_date, phase.end_date, phase.description, now, now,
            ),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def get_phases(self, project: str) -> list:
        cursor = await self.db.execute(
            'SELECT * FROM roadmap_phases WHERE project=? ORDER BY "order"',
            (project,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_phase(r) for r in rows]

    def _row_to_phase(self, row) -> RoadmapPhase:
        return RoadmapPhase(
            id=row["id"],
            project=row["project"],
            name=row["name"],
            order=row["order"],
            status=row["status"],
            start_date=row["start_date"],
            end_date=row["end_date"],
            description=row["description"] or "",
        )

    # -------------------------------------------------------------------------
    # Milestone CRUD
    # -------------------------------------------------------------------------

    async def save_milestone(self, ms: RoadmapMilestone) -> int:
        """Milestone 저장 (upsert). 반환값: rowid"""
        now = datetime.now().isoformat()
        cursor = await self.db.execute(
            """INSERT INTO roadmap_milestones (phase_id, project, name, "order", status, target_date, completed_date, description, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(phase_id, name) DO UPDATE SET
                 "order"=excluded."order",
                 status=excluded.status,
                 target_date=excluded.target_date,
                 completed_date=excluded.completed_date,
                 description=excluded.description,
                 updated_at=excluded.updated_at""",
            (
                ms.phase_id, ms.project, ms.name, ms.order, ms.status.value,
                ms.target_date, ms.completed_date, ms.description, now, now,
            ),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def get_milestones(self, phase_id: int) -> list:
        cursor = await self.db.execute(
            'SELECT * FROM roadmap_milestones WHERE phase_id=? ORDER BY "order"',
            (phase_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_milestone(r) for r in rows]

    async def get_milestones_by_project(self, project: str) -> list:
        cursor = await self.db.execute(
            'SELECT * FROM roadmap_milestones WHERE project=? ORDER BY "order"',
            (project,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_milestone(r) for r in rows]

    def _row_to_milestone(self, row) -> RoadmapMilestone:
        return RoadmapMilestone(
            id=row["id"],
            phase_id=row["phase_id"],
            project=row["project"],
            name=row["name"],
            order=row["order"],
            status=row["status"],
            target_date=row["target_date"],
            completed_date=row["completed_date"],
            description=row["description"] or "",
        )

    # -------------------------------------------------------------------------
    # Task CRUD
    # -------------------------------------------------------------------------

    async def save_task(self, task: RoadmapTask) -> int:
        """Task 저장 (insert). 반환값: rowid"""
        now = datetime.now().isoformat()
        cursor = await self.db.execute(
            """INSERT INTO roadmap_tasks
               (milestone_id, project, title, status, priority, effort, source,
                related_repo, linked_commits, completed_date, completed_week,
                description, depends_on, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.milestone_id, task.project, task.title,
                task.status.value, task.priority.value, task.effort.value,
                task.source.value, task.related_repo, task.linked_commits,
                task.completed_date, task.completed_week,
                task.description, task.depends_on, now, now,
            ),
        )
        await self.db.commit()
        return cursor.lastrowid

    async def update_task_status(
        self,
        task_id: int,
        status: TaskStatus,
        completed_date: Optional[str] = None,
    ) -> None:
        now = datetime.now().isoformat()
        await self.db.execute(
            "UPDATE roadmap_tasks SET status=?, completed_date=?, updated_at=? WHERE id=?",
            (status.value, completed_date, now, task_id),
        )
        await self.db.commit()

    async def get_tasks(self, milestone_id: int) -> list:
        cursor = await self.db.execute(
            "SELECT * FROM roadmap_tasks WHERE milestone_id=? ORDER BY priority, id",
            (milestone_id,),
        )
        rows = await cursor.fetchall()
        return [self._row_to_task(r) for r in rows]

    async def get_tasks_by_project(
        self, project: str, status: Optional[str] = None
    ) -> list:
        if status:
            cursor = await self.db.execute(
                "SELECT * FROM roadmap_tasks WHERE project=? AND status=? ORDER BY priority, id",
                (project, status),
            )
        else:
            cursor = await self.db.execute(
                "SELECT * FROM roadmap_tasks WHERE project=? ORDER BY priority, id",
                (project,),
            )
        rows = await cursor.fetchall()
        return [self._row_to_task(r) for r in rows]

    def _row_to_task(self, row) -> RoadmapTask:
        return RoadmapTask(
            id=row["id"],
            milestone_id=row["milestone_id"],
            project=row["project"],
            title=row["title"],
            status=row["status"],
            priority=row["priority"],
            effort=row["effort"],
            source=row["source"],
            related_repo=row["related_repo"],
            linked_commits=row["linked_commits"] or "[]",
            completed_date=row["completed_date"],
            completed_week=row["completed_week"],
            description=row["description"] or "",
            depends_on=row["depends_on"] or "[]",
        )

    # -------------------------------------------------------------------------
    # 집계
    # -------------------------------------------------------------------------

    async def get_project_summary(self, project: str) -> dict:
        """프로젝트 전체 Phase/Milestone/Task 요약 통계"""
        phases = await self.get_phases(project)
        result = {
            "project": project,
            "phases": len(phases),
            "milestones": 0,
            "tasks": {"total": 0, "done": 0, "in_progress": 0, "pending": 0, "blocked": 0},
            "phase_details": [],
        }
        for phase in phases:
            milestones = await self.get_milestones(phase.id)
            phase_info = {
                "name": phase.name,
                "status": phase.status.value,
                "milestones": len(milestones),
                "tasks_done": 0,
                "tasks_total": 0,
            }
            result["milestones"] += len(milestones)
            for ms in milestones:
                tasks = await self.get_tasks(ms.id)
                phase_info["tasks_total"] += len(tasks)
                for t in tasks:
                    result["tasks"]["total"] += 1
                    key = t.status.value
                    if key in result["tasks"]:
                        result["tasks"][key] += 1
                    if t.status == TaskStatus.DONE:
                        phase_info["tasks_done"] += 1
            result["phase_details"].append(phase_info)
        return result

    async def clear_project(self, project: str) -> None:
        """프로젝트 로드맵 전체 삭제 (재초기화용). FK 제약 순서 준수."""
        await self.db.execute("DELETE FROM roadmap_tasks WHERE project=?", (project,))
        await self.db.execute("DELETE FROM roadmap_milestones WHERE project=?", (project,))
        await self.db.execute("DELETE FROM roadmap_phases WHERE project=?", (project,))
        await self.db.commit()
