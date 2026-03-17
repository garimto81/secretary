"""
Work Tracker 데이터 모델

Git 커밋 기반 업무 흐름 추적을 위한 통합 데이터 모델 정의.
"""

from dataclasses import dataclass, field
from enum import Enum


class CommitType(Enum):
    """Conventional Commit 타입"""
    FEAT = "feat"
    FIX = "fix"
    DOCS = "docs"
    REFACTOR = "refactor"
    TEST = "test"
    CHORE = "chore"
    STYLE = "style"
    PERF = "perf"
    CI = "ci"
    BUILD = "build"
    OTHER = "other"


class StreamStatus(Enum):
    """Work Stream 상태"""
    ACTIVE = "active"        # 최근 7일 내 커밋
    IDLE = "idle"            # 7~30일 미활동
    COMPLETED = "completed"  # merged 또는 30일+
    NEW = "new"              # 오늘 최초 감지


class DetectionMethod(Enum):
    """Stream 감지 방법"""
    BRANCH = "branch"
    SCOPE = "scope"
    PATH = "path"
    KEYWORD = "keyword"


@dataclass
class DailyCommit:
    """일일 커밋 로그"""
    date: str                    # YYYY-MM-DD
    repo: str                    # 레포 디렉토리명
    project: str                 # EBS/WSOPTV/Secretary
    category: str | None         # 기획/역공학 등
    commit_hash: str
    commit_type: CommitType
    commit_scope: str | None
    message: str
    author: str
    timestamp: str               # ISO 8601
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    branch: str | None = None

    def __post_init__(self):
        """유효성 검사 및 타입 변환"""
        if isinstance(self.commit_type, str):
            self.commit_type = CommitType(self.commit_type)

    def to_dict(self) -> dict:
        """딕셔너리 직렬화"""
        return {
            "date": self.date,
            "repo": self.repo,
            "project": self.project,
            "category": self.category,
            "commit_hash": self.commit_hash,
            "commit_type": self.commit_type.value,
            "commit_scope": self.commit_scope,
            "message": self.message,
            "author": self.author,
            "timestamp": self.timestamp,
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "branch": self.branch,
        }


@dataclass
class FileChange:
    """파일 변경 기록"""
    file_path: str
    change_type: str             # added/modified/deleted
    insertions: int = 0
    deletions: int = 0

    def __post_init__(self):
        """유효성 검사 및 타입 변환"""
        # change_type은 자유 문자열 — Enum 변환 없음

    def to_dict(self) -> dict:
        """딕셔너리 직렬화"""
        return {
            "file_path": self.file_path,
            "change_type": self.change_type,
            "insertions": self.insertions,
            "deletions": self.deletions,
        }


@dataclass
class WorkStream:
    """Work Stream (여러 날에 걸친 연속 업무 단위)"""
    name: str
    project: str                 # EBS/WSOPTV/Secretary
    repos: list[str] = field(default_factory=list)
    first_commit: str = ""       # ISO 8601
    last_commit: str = ""        # ISO 8601
    total_commits: int = 0
    status: StreamStatus = StreamStatus.NEW
    duration_days: int = 0
    detection_method: DetectionMethod | None = None
    metadata: dict | None = None  # keywords, branches, etc.

    def __post_init__(self):
        """유효성 검사 및 타입 변환"""
        if isinstance(self.status, str):
            self.status = StreamStatus(self.status)
        if self.detection_method is not None and isinstance(self.detection_method, str):
            self.detection_method = DetectionMethod(self.detection_method)

    def to_dict(self) -> dict:
        """딕셔너리 직렬화"""
        return {
            "name": self.name,
            "project": self.project,
            "repos": list(self.repos),
            "first_commit": self.first_commit,
            "last_commit": self.last_commit,
            "total_commits": self.total_commits,
            "status": self.status.value,
            "duration_days": self.duration_days,
            "detection_method": self.detection_method.value if self.detection_method else None,
            "metadata": dict(self.metadata) if self.metadata else None,
        }


@dataclass
class DailySummary:
    """일일 요약"""
    date: str                    # YYYY-MM-DD
    total_commits: int = 0
    total_insertions: int = 0
    total_deletions: int = 0
    doc_change_ratio: float = 0.0
    project_distribution: dict | None = None  # {"EBS": 60, "WSOPTV": 30}
    active_streams: int = 0
    highlights: list[str] = field(default_factory=list)
    slack_message_id: str | None = None

    def __post_init__(self):
        """유효성 검사 및 타입 변환"""
        # highlights가 None으로 전달된 경우 빈 리스트로 정규화
        if self.highlights is None:
            self.highlights = []

    def to_dict(self) -> dict:
        """딕셔너리 직렬화"""
        return {
            "date": self.date,
            "total_commits": self.total_commits,
            "total_insertions": self.total_insertions,
            "total_deletions": self.total_deletions,
            "doc_change_ratio": self.doc_change_ratio,
            "project_distribution": dict(self.project_distribution) if self.project_distribution else None,
            "active_streams": self.active_streams,
            "highlights": list(self.highlights),
            "slack_message_id": self.slack_message_id,
        }


@dataclass
class WeeklySummary:
    """주간 요약"""
    week_label: str              # e.g., "W12 (3/10~3/16)"
    start_date: str
    end_date: str
    total_commits: int = 0
    velocity_trend: dict | None = None  # last 4 weeks
    completed_streams: list[str] = field(default_factory=list)
    new_streams: list[str] = field(default_factory=list)
    project_distribution: dict | None = None
    highlights: list[str] = field(default_factory=list)
    slack_message_id: str | None = None

    def __post_init__(self):
        """유효성 검사 및 타입 변환"""
        # None으로 전달된 list 필드를 빈 리스트로 정규화
        if self.completed_streams is None:
            self.completed_streams = []
        if self.new_streams is None:
            self.new_streams = []
        if self.highlights is None:
            self.highlights = []

    def to_dict(self) -> dict:
        """딕셔너리 직렬화"""
        return {
            "week_label": self.week_label,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "total_commits": self.total_commits,
            "velocity_trend": dict(self.velocity_trend) if self.velocity_trend else None,
            "completed_streams": list(self.completed_streams),
            "new_streams": list(self.new_streams),
            "project_distribution": dict(self.project_distribution) if self.project_distribution else None,
            "highlights": list(self.highlights),
            "slack_message_id": self.slack_message_id,
        }
