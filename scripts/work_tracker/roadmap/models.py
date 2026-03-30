"""Roadmap 도메인 모델 — Phase / Milestone / Task dataclass 정의"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PhaseStatus(Enum):
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"


class MilestoneStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"


class TaskPriority(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskEffort(Enum):
    SMALL = 1
    MEDIUM = 2
    LARGE = 4


class TaskSource(Enum):
    PRD = "prd"
    REPORT = "report"
    GIT = "git"
    MANUAL = "manual"


@dataclass
class RoadmapPhase:
    """프로젝트 Phase"""
    id: Optional[int]  # DB auto-increment
    project: str
    name: str  # "Phase 1-2: RFID POC + GFX"
    order: int  # 정렬 순서
    status: PhaseStatus
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None
    description: str = ""

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = PhaseStatus(self.status)


@dataclass
class RoadmapMilestone:
    """Phase 하위 Milestone"""
    id: Optional[int]
    phase_id: int
    project: str
    name: str  # "기획 확정", "역공학 완료"
    order: int
    status: MilestoneStatus
    target_date: Optional[str] = None
    completed_date: Optional[str] = None
    description: str = ""

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = MilestoneStatus(self.status)


@dataclass
class RoadmapTask:
    """Milestone 하위 Task"""
    id: Optional[int]
    milestone_id: int
    project: str
    title: str  # "마스터 기획서 v5.5 확정"
    status: TaskStatus
    priority: TaskPriority = TaskPriority.MEDIUM
    effort: TaskEffort = TaskEffort.MEDIUM
    source: TaskSource = TaskSource.MANUAL
    related_repo: Optional[str] = None  # 관련 레포
    linked_commits: str = "[]"  # JSON 배열
    completed_date: Optional[str] = None
    completed_week: Optional[str] = None  # "W5"
    description: str = ""
    depends_on: str = "[]"  # JSON: task_id 배열

    def __post_init__(self):
        if isinstance(self.status, str):
            self.status = TaskStatus(self.status)
        if isinstance(self.priority, str):
            self.priority = TaskPriority(self.priority)
        if isinstance(self.effort, (str, int)):
            if isinstance(self.effort, str):
                self.effort = TaskEffort[self.effort.upper()]
            else:
                self.effort = TaskEffort(self.effort)
        if isinstance(self.source, str):
            self.source = TaskSource(self.source)
