"""Tests for ChecklistParser - TDD Red Phase"""

import pytest
from pathlib import Path
import sys

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from checklist_parser import ChecklistParser, ChecklistProject, ChecklistItem, ChecklistResult


class TestChecklistItem:
    """ChecklistItem dataclass tests"""

    def test_create_completed_item(self):
        """완료된 항목 생성"""
        item = ChecklistItem(text="요구사항 분석", completed=True, pr_number=101)
        assert item.text == "요구사항 분석"
        assert item.completed is True
        assert item.pr_number == 101

    def test_create_pending_item(self):
        """미완료 항목 생성"""
        item = ChecklistItem(text="API 설계", completed=False)
        assert item.completed is False
        assert item.pr_number is None


class TestChecklistProject:
    """ChecklistProject dataclass tests"""

    def test_progress_calculation(self):
        """진행률 계산"""
        items = [
            ChecklistItem(text="Done 1", completed=True),
            ChecklistItem(text="Done 2", completed=True),
            ChecklistItem(text="Pending 1", completed=False),
            ChecklistItem(text="Pending 2", completed=False),
        ]
        project = ChecklistProject(
            prd_id="PRD-0001",
            title="Test Project",
            status="In Progress",
            items=items
        )

        assert project.total_items == 4
        assert project.completed_items == 2
        assert project.progress == 50.0

    def test_empty_project_progress(self):
        """항목 없는 프로젝트 진행률은 0%"""
        project = ChecklistProject(
            prd_id="PRD-0002",
            title="Empty Project",
            status="In Progress",
            items=[]
        )
        assert project.progress == 0.0

    def test_pending_items_property(self):
        """미완료 항목 목록 조회"""
        items = [
            ChecklistItem(text="Done", completed=True),
            ChecklistItem(text="Pending 1", completed=False),
            ChecklistItem(text="Pending 2", completed=False),
        ]
        project = ChecklistProject(
            prd_id="PRD-0003",
            title="Test",
            status="In Progress",
            items=items
        )

        pending = project.pending_items
        assert len(pending) == 2
        assert all(not item.completed for item in pending)


class TestChecklistParser:
    """ChecklistParser tests"""

    @pytest.fixture
    def parser(self, tmp_path):
        """임시 디렉토리 기반 파서"""
        return ChecklistParser(tmp_path)

    @pytest.fixture
    def standard_checklist(self) -> str:
        """CHECKLIST_STANDARD.md 형식 샘플"""
        return """# [PRD-0001] Checklist

**PRD**: PRD-0001
**Version**: 1.0.0
**Last Updated**: 2026-02-05
**Status**: In Progress

## Phase 1: 설계

- [x] 요구사항 분석 (#101)
- [x] 아키텍처 설계 (#102)
- [ ] API 설계

## Phase 2: 구현

- [ ] 핵심 기능 구현
- [ ] 테스트 작성 (#103)
"""

    def test_parse_standard_checklist(self, parser, tmp_path, standard_checklist):
        """CHECKLIST_STANDARD.md 형식 파싱"""
        # Setup
        checklist_dir = tmp_path / "docs" / "checklists"
        checklist_dir.mkdir(parents=True)
        checklist_file = checklist_dir / "PRD-0001.md"
        checklist_file.write_text(standard_checklist, encoding="utf-8")

        # Execute
        project = parser.parse_file(checklist_file)

        # Verify
        assert project is not None
        assert project.prd_id == "PRD-0001"
        assert project.status == "In Progress"
        assert len(project.items) == 5
        assert project.completed_items == 2
        assert project.progress == 40.0

    def test_extract_pr_number(self, parser, tmp_path):
        """PR 번호 추출"""
        content = """# [PRD-0002] Test

**Status**: In Progress

- [x] 완료됨 (#123)
- [ ] 진행중
"""
        file = tmp_path / "PRD-0002.md"
        file.write_text(content, encoding="utf-8")

        project = parser.parse_file(file)

        assert project is not None
        assert len(project.items) == 2
        assert project.items[0].pr_number == 123
        assert project.items[1].pr_number is None

    def test_no_prd_id_returns_none(self, parser, tmp_path):
        """PRD ID 없는 파일은 None 반환"""
        content = "# Random Checklist\n- [ ] Item 1"
        file = tmp_path / "random.md"
        file.write_text(content, encoding="utf-8")

        assert parser.parse_file(file) is None

    def test_empty_checklist(self, parser, tmp_path):
        """Checkbox 없는 파일"""
        content = "# [PRD-0003] Checklist\n**Status**: In Progress\nNo items yet."
        file = tmp_path / "PRD-0003.md"
        file.write_text(content, encoding="utf-8")

        project = parser.parse_file(file)

        assert project is not None
        assert project.total_items == 0
        assert project.progress == 0.0

    def test_parse_phase_headers(self, parser, tmp_path):
        """Phase 헤더 파싱"""
        content = """# [PRD-0004] Test

**Status**: In Progress

## Phase 1: 설계

- [x] 설계 항목

## Phase 2: 구현

- [ ] 구현 항목
"""
        file = tmp_path / "PRD-0004.md"
        file.write_text(content, encoding="utf-8")

        project = parser.parse_file(file)

        assert project is not None
        assert project.items[0].phase == "설계"
        assert project.items[1].phase == "구현"

    def test_scan_multiple_paths(self, parser, tmp_path):
        """여러 경로 스캔"""
        # Setup: 두 개의 checklist 생성
        checklists_dir = tmp_path / "docs" / "checklists"
        checklists_dir.mkdir(parents=True)

        (checklists_dir / "PRD-0001.md").write_text(
            "# [PRD-0001] Test\n**Status**: In Progress\n- [x] Done",
            encoding="utf-8"
        )
        (checklists_dir / "PRD-0002.md").write_text(
            "# [PRD-0002] Test\n**Status**: In Progress\n- [ ] Pending",
            encoding="utf-8"
        )

        # Execute
        result = parser.scan(["docs/checklists"])

        # Verify
        assert len(result.projects) == 2
        assert result.total_progress == 50.0  # (100 + 0) / 2

    def test_scan_ignores_non_prd_files(self, parser, tmp_path):
        """PRD가 아닌 파일은 무시"""
        checklists_dir = tmp_path / "docs" / "checklists"
        checklists_dir.mkdir(parents=True)

        (checklists_dir / "PRD-0001.md").write_text(
            "# [PRD-0001] Test\n- [x] Done",
            encoding="utf-8"
        )
        (checklists_dir / "README.md").write_text(
            "# README\nNot a checklist",
            encoding="utf-8"
        )

        result = parser.scan(["docs/checklists"])

        assert len(result.projects) == 1
        assert result.projects[0].prd_id == "PRD-0001"

    def test_uppercase_x_checkbox(self, parser, tmp_path):
        """대문자 X도 완료로 인식"""
        content = "# [PRD-0005] Test\n- [X] Done with uppercase"
        file = tmp_path / "PRD-0005.md"
        file.write_text(content, encoding="utf-8")

        project = parser.parse_file(file)

        assert project.items[0].completed is True

    def test_asterisk_checkbox(self, parser, tmp_path):
        """* 로 시작하는 체크박스도 파싱"""
        content = "# [PRD-0006] Test\n* [x] Done with asterisk\n* [ ] Pending"
        file = tmp_path / "PRD-0006.md"
        file.write_text(content, encoding="utf-8")

        project = parser.parse_file(file)

        assert len(project.items) == 2
        assert project.items[0].completed is True


class TestChecklistResult:
    """ChecklistResult tests"""

    def test_total_progress_calculation(self):
        """전체 평균 진행률 계산"""
        projects = [
            ChecklistProject(
                prd_id="PRD-0001",
                title="P1",
                status="In Progress",
                items=[
                    ChecklistItem(text="Done", completed=True),
                    ChecklistItem(text="Done", completed=True),
                ]
            ),
            ChecklistProject(
                prd_id="PRD-0002",
                title="P2",
                status="In Progress",
                items=[
                    ChecklistItem(text="Pending", completed=False),
                    ChecklistItem(text="Pending", completed=False),
                ]
            ),
        ]

        result = ChecklistResult(
            projects=projects,
            scan_paths=["docs/checklists"],
            scanned_at="2026-02-05T10:00:00"
        )

        # (100% + 0%) / 2 = 50%
        assert result.total_progress == 50.0

    def test_empty_result_total_progress(self):
        """빈 결과의 진행률은 0%"""
        result = ChecklistResult(
            projects=[],
            scan_paths=[],
            scanned_at="2026-02-05T10:00:00"
        )
        assert result.total_progress == 0.0
