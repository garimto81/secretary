"""Checklist Parser - CHECKLIST_STANDARD.md 형식 파서

docs/checklists/*.md 파일을 파싱하여 프로젝트 진행률 계산
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import re


@dataclass
class ChecklistItem:
    """단일 체크리스트 항목"""

    text: str
    completed: bool
    pr_number: Optional[int] = None  # (#123) 형식에서 추출
    phase: Optional[str] = None  # 상위 Phase 헤더


@dataclass
class ChecklistProject:
    """PRD 단위 프로젝트"""

    prd_id: str  # "PRD-0001"
    title: str  # Checklist 제목
    status: str  # "In Progress" | "Completed" | "On Hold"
    items: list[ChecklistItem] = field(default_factory=list)

    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def completed_items(self) -> int:
        return len([i for i in self.items if i.completed])

    @property
    def progress(self) -> float:
        if self.total_items == 0:
            return 0.0
        return (self.completed_items / self.total_items) * 100

    @property
    def pending_items(self) -> list[ChecklistItem]:
        return [i for i in self.items if not i.completed]


@dataclass
class ChecklistResult:
    """전체 Checklist 파싱 결과"""

    projects: list[ChecklistProject]
    scan_paths: list[str]
    scanned_at: str

    @property
    def total_progress(self) -> float:
        """전체 평균 진행률"""
        if not self.projects:
            return 0.0
        return sum(p.progress for p in self.projects) / len(self.projects)


class ChecklistParser:
    """CHECKLIST_STANDARD.md 형식 파서"""

    # 기본 스캔 경로 (우선순위 순)
    DEFAULT_PATHS = [
        "docs/checklists",
        "tasks/prds",
        "docs",
    ]

    # 파싱 정규식
    CHECKBOX_PATTERN = re.compile(r"^[-*]\s+\[([ xX])\]\s+(.+)$")
    PR_LINK_PATTERN = re.compile(r"\(#(\d+)\)")
    PHASE_HEADER_PATTERN = re.compile(r"^##\s+Phase\s+\d+[:\s]+(.+)$", re.IGNORECASE)
    PRD_ID_PATTERN = re.compile(r"PRD-(\d{4})", re.IGNORECASE)
    STATUS_PATTERN = re.compile(r"\*\*Status\*\*:\s*(.+)", re.IGNORECASE)
    TITLE_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)

    def scan(self, paths: list[str] = None) -> ChecklistResult:
        """
        지정된 경로에서 모든 Checklist 파일 스캔

        Args:
            paths: 스캔할 경로 목록 (None이면 DEFAULT_PATHS 사용)

        Returns:
            ChecklistResult: 파싱된 프로젝트 목록
        """
        scan_paths = paths or self.DEFAULT_PATHS
        projects = []

        for path in scan_paths:
            full_path = self.base_path / path
            if not full_path.exists():
                continue

            # .md 파일만 스캔
            for md_file in full_path.glob("*.md"):
                project = self.parse_file(md_file)
                if project is not None:
                    projects.append(project)

        return ChecklistResult(
            projects=projects,
            scan_paths=scan_paths,
            scanned_at=datetime.now().isoformat(),
        )

    def parse_file(self, file_path: Path) -> Optional[ChecklistProject]:
        """
        단일 Checklist 파일 파싱

        Args:
            file_path: Checklist 파일 경로

        Returns:
            ChecklistProject: 파싱된 프로젝트 또는 None (파싱 실패 시)
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return None

        # 1. PRD ID 추출 (헤더 우선, 파일명 fallback)
        prd_id = self._extract_prd_id(content, file_path.stem)
        if not prd_id:
            return None  # PRD ID 없으면 스킵

        # 2. 제목 추출 (첫 번째 # 헤더)
        title = self._extract_title(content)

        # 3. Status 추출
        status = self._extract_status(content)

        # 4. 항목 파싱
        items = self._parse_items(content)

        return ChecklistProject(
            prd_id=prd_id,
            title=title,
            status=status,
            items=items,
        )

    def _extract_prd_id(self, content: str, filename: str) -> Optional[str]:
        """PRD ID 추출 (헤더 우선, 파일명 fallback)"""
        # 헤더에서 먼저 찾기
        match = self.PRD_ID_PATTERN.search(content)
        if match:
            return f"PRD-{match.group(1)}"

        # 파일명에서 찾기
        match = self.PRD_ID_PATTERN.search(filename)
        if match:
            return f"PRD-{match.group(1)}"

        return None

    def _extract_title(self, content: str) -> str:
        """제목 추출 (첫 번째 # 헤더)"""
        match = self.TITLE_PATTERN.search(content)
        if match:
            return match.group(1).strip()
        return "Untitled"

    def _extract_status(self, content: str) -> str:
        """Status 추출 (기본값: In Progress)"""
        match = self.STATUS_PATTERN.search(content)
        if match:
            return match.group(1).strip()
        return "In Progress"

    def _parse_items(self, content: str) -> list[ChecklistItem]:
        """Checkbox 항목 파싱"""
        items = []
        current_phase = None

        for line in content.split("\n"):
            # Phase 헤더 감지
            phase_match = self.PHASE_HEADER_PATTERN.match(line.strip())
            if phase_match:
                current_phase = phase_match.group(1).strip()
                continue

            # Checkbox 항목 감지
            checkbox_match = self.CHECKBOX_PATTERN.match(line.strip())
            if checkbox_match:
                completed = checkbox_match.group(1).lower() == "x"
                text = checkbox_match.group(2)

                # PR 번호 추출
                pr_match = self.PR_LINK_PATTERN.search(text)
                pr_number = int(pr_match.group(1)) if pr_match else None

                items.append(
                    ChecklistItem(
                        text=text,
                        completed=completed,
                        pr_number=pr_number,
                        phase=current_phase,
                    )
                )

        return items
