"""
Deep Analyzer — 프로젝트 로드맵 심층 분석

최초 1회 PRD + 주간 보고서 + projects.json 기반으로
Phase-Milestone-Task 계층 구조를 생성하고 DB에 적재합니다.
"""

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

# 3-way import
try:
    from scripts.work_tracker.roadmap.models import (
        RoadmapPhase, RoadmapMilestone, RoadmapTask,
        PhaseStatus, MilestoneStatus, TaskStatus, TaskPriority, TaskEffort, TaskSource,
    )
    from scripts.work_tracker.roadmap.storage import RoadmapStorage
except ImportError:
    try:
        from work_tracker.roadmap.models import (
            RoadmapPhase, RoadmapMilestone, RoadmapTask,
            PhaseStatus, MilestoneStatus, TaskStatus, TaskPriority, TaskEffort, TaskSource,
        )
        from work_tracker.roadmap.storage import RoadmapStorage
    except ImportError:
        from .models import (
            RoadmapPhase, RoadmapMilestone, RoadmapTask,
            PhaseStatus, MilestoneStatus, TaskStatus, TaskPriority, TaskEffort, TaskSource,
        )
        from .storage import RoadmapStorage


class DeepAnalyzer:
    """프로젝트 로드맵 심층 분석 — 최초 1회 PRD + 보고서 기반 구조화"""

    PROJECTS_CONFIG = Path(r"C:\claude\secretary\config\projects.json")
    BASE_DIR = Path(r"C:\claude")

    # PRD 구현 상태 테이블에서 상태값 매핑
    _STATUS_MAP = {
        "완료": "done",
        "진행 중": "in_progress",
        "진행중": "in_progress",
        "예정": "pending",
        "계획": "pending",
        "blocked": "blocked",
        "차단": "blocked",
    }

    def __init__(self):
        self._repo_mapping = self._load_repo_mapping()

    def _load_repo_mapping(self) -> dict:
        """projects.json에서 local_repo_mapping 로드"""
        try:
            with open(self.PROJECTS_CONFIG, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("local_repo_mapping", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _get_project_repos(self, project: str) -> list[str]:
        """프로젝트에 속한 레포명 리스트"""
        return [
            repo_name
            for repo_name, info in self._repo_mapping.items()
            if info.get("project", "").lower() == project.lower()
        ]

    def _scan_prds(self, project: str) -> list[dict]:
        """프로젝트 레포들의 PRD 파일 스캔 + 구현 상태 테이블 파싱"""
        repos = self._get_project_repos(project)
        prds = []
        for repo in repos:
            prd_dir = self.BASE_DIR / repo / "docs" / "00-prd"
            if not prd_dir.exists():
                continue
            for prd_file in prd_dir.glob("*.prd.md"):
                try:
                    content = prd_file.read_text(encoding="utf-8", errors="replace")
                    impl_items = self._parse_impl_table(content)
                    prds.append({
                        "repo": repo,
                        "file": prd_file.name,
                        "title": self._extract_title(content),
                        "content_preview": content[:3000],
                        "impl_items": impl_items,
                    })
                except OSError:
                    continue
        return prds

    def _extract_title(self, content: str) -> str:
        """마크다운 첫 번째 H1 추출"""
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
        return "제목 없음"

    # 구현 상태 테이블 헤더에서 "상태" 컬럼을 식별하는 키워드
    _STATUS_HEADER_KEYWORDS = {"상태", "Status", "status", "진행", "완료여부"}
    # 구현 상태 테이블 헤더에서 "항목" 컬럼을 식별하는 키워드
    _ITEM_HEADER_KEYWORDS = {"항목", "Item", "기능", "구현", "서브시스템", "모듈", "컴포넌트", "화면", "Feature"}
    # 유효한 상태값 (이 값이 있는 행만 Task로 인정)
    _VALID_STATUS_VALUES = set(_STATUS_MAP.keys()) | {"done", "in_progress", "pending", "blocked", "완료됨", "미구현"}

    def _parse_impl_table(self, content: str) -> list[dict]:
        """PRD 구현 상태 테이블만 선택적으로 파싱

        "상태" 컬럼이 있는 테이블만 파싱하고,
        실제 상태값(완료/진행 중/예정 등)이 있는 행만 Task로 인정.
        스키마/설정/요구사항 ID 테이블은 무시.
        """
        items = []
        in_table = False
        header_passed = False
        status_col_idx = -1  # "상태" 컬럼 위치
        item_col_idx = 0     # "항목" 컬럼 위치
        note_col_idx = -1    # "비고" 컬럼 위치

        for line in content.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                if in_table:
                    in_table = False
                    header_passed = False
                    status_col_idx = -1
                continue

            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 2:
                continue

            # 구분선 행 건너뜀
            if all(re.match(r"^[-:]+$", c) for c in cells if c):
                if in_table:
                    header_passed = True
                continue

            if not header_passed:
                # 헤더 행 분석 — "상태" 컬럼이 있는 테이블만 파싱 대상
                has_status_col = False
                for idx, cell in enumerate(cells):
                    if any(k in cell for k in self._STATUS_HEADER_KEYWORDS):
                        status_col_idx = idx
                        has_status_col = True
                    if any(k in cell for k in self._ITEM_HEADER_KEYWORDS):
                        item_col_idx = idx
                    if cell in ("비고", "Note", "설명", "Description"):
                        note_col_idx = idx

                if has_status_col:
                    in_table = True
                continue

            if in_table and header_passed and len(cells) > status_col_idx >= 0:
                title = cells[item_col_idx].strip() if item_col_idx < len(cells) else ""
                status_raw = cells[status_col_idx].strip() if status_col_idx < len(cells) else ""
                note = cells[note_col_idx].strip() if 0 <= note_col_idx < len(cells) else ""

                # 유효한 상태값이 있는 행만 Task로 인정
                if not title or title.startswith("-"):
                    continue
                if status_raw.lower() not in {v.lower() for v in self._VALID_STATUS_VALUES}:
                    continue

                mapped_status = self._STATUS_MAP.get(status_raw, "pending")
                items.append({
                    "title": title,
                    "status": mapped_status,
                    "note": note,
                })
        return items

    def _scan_reports(self) -> str:
        """주간 보고서 파싱 — task_manager 레포의 보고서 로드"""
        report_path = self.BASE_DIR / "task_manager" / "docs" / "04-report"
        if not report_path.exists():
            return ""
        reports = []
        for f in sorted(report_path.glob("*.report.md")):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                reports.append(f"# {f.name}\n{content}")
            except OSError:
                continue
        return "\n---\n".join(reports[-4:])  # 최근 4주만 (토큰 절약)

    def _get_recent_git_activity(self, project: str, days: int = 30) -> list[dict]:
        """최근 N일 git log 수집"""
        repos = self._get_project_repos(project)
        activities = []
        for repo in repos:
            repo_path = self.BASE_DIR / repo
            if not (repo_path / ".git").exists():
                continue
            try:
                result = subprocess.run(
                    [
                        "git", "log",
                        f"--since={days} days ago",
                        "--pretty=format:%H|%s|%ai",
                        "--no-merges",
                    ],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                for line in result.stdout.strip().split("\n"):
                    if "|" in line:
                        parts = line.split("|", 2)
                        if len(parts) >= 3:
                            activities.append({
                                "repo": repo,
                                "hash": parts[0][:8],
                                "message": parts[1].strip(),
                                "date": parts[2][:10],
                            })
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass
        return activities

    def _build_from_collected_data(
        self,
        project: str,
        prds: list[dict],
        git_activities: list[dict],
        report_text: str,
    ) -> dict:
        """수집된 PRD/보고서/git 데이터 기반으로 로드맵 구조 자동 매핑

        Claude CLI 없이 규칙 기반으로 Phase/Milestone/Task 생성:
        - PRD 파일 1개 = Milestone 1개
        - PRD 내 구현 상태 항목 = Task
        - 완료된 커밋이 많은 레포는 ACTIVE Phase
        """
        today = datetime.now().strftime("%Y-%m-%d")

        # Phase: 레포별 카테고리를 그룹핑
        category_map: dict[str, list[dict]] = {}
        for prd in prds:
            repo_info = self._repo_mapping.get(prd["repo"], {})
            category = repo_info.get("category", "기타")
            category_map.setdefault(category, []).append(prd)

        # git 활동 레포 집합 (최근 30일)
        active_repos = {a["repo"] for a in git_activities}

        phases = []
        for p_idx, (category, cat_prds) in enumerate(category_map.items()):
            # Phase 상태: 해당 카테고리 레포에 최근 활동이 있으면 active
            phase_repos = {p["repo"] for p in cat_prds}
            phase_status = "active" if phase_repos & active_repos else "planned"

            milestones = []
            for m_idx, prd in enumerate(cat_prds):
                tasks = []
                for item in prd.get("impl_items", []):
                    tasks.append({
                        "title": item["title"],
                        "status": item["status"],
                        "priority": "medium",
                        "effort": 2,
                        "source": "prd",
                        "related_repo": prd["repo"],
                        "description": item.get("note", ""),
                    })

                # impl_items가 없으면 git 활동에서 task 생성
                if not tasks:
                    repo_commits = [
                        a for a in git_activities if a["repo"] == prd["repo"]
                    ]
                    for commit in repo_commits[:10]:
                        tasks.append({
                            "title": commit["message"][:80],
                            "status": "done",
                            "priority": "medium",
                            "effort": 1,
                            "source": "git",
                            "related_repo": prd["repo"],
                            "completed_date": commit["date"],
                        })

                ms_status = "completed"
                if any(t["status"] == "in_progress" for t in tasks):
                    ms_status = "active"
                elif any(t["status"] == "pending" for t in tasks):
                    ms_status = "pending"

                milestones.append({
                    "name": prd["title"],
                    "status": ms_status,
                    "tasks": tasks,
                })

            phases.append({
                "name": f"{category} Phase",
                "status": phase_status,
                "start_date": None,
                "end_date": None,
                "description": f"{project} 프로젝트 {category} 영역",
                "milestones": milestones,
            })

        if not phases:
            # 데이터가 전혀 없는 경우 기본 Phase 생성
            phases.append({
                "name": "Phase 1: 초기화",
                "status": "planned",
                "start_date": today,
                "end_date": None,
                "description": "로드맵 초기화 단계",
                "milestones": [
                    {
                        "name": "PRD 작성",
                        "status": "pending",
                        "tasks": [
                            {
                                "title": "요구사항 정의",
                                "status": "pending",
                                "priority": "high",
                                "effort": 2,
                                "source": "manual",
                            }
                        ],
                    }
                ],
            })

        return {"phases": phases}

    async def _save_to_db(self, project: str, roadmap_data: dict) -> dict:
        """구조화된 로드맵 데이터를 DB에 저장

        roadmap_data 형식:
        {
            "phases": [
                {
                    "name": "...",
                    "status": "active",
                    "start_date": "YYYY-MM-DD" | None,
                    "end_date": "YYYY-MM-DD" | None,
                    "description": "...",
                    "milestones": [
                        {
                            "name": "...",
                            "status": "pending",
                            "tasks": [
                                {
                                    "title": "...",
                                    "status": "done",
                                    "source": "prd",
                                    "related_repo": "ebs",
                                    "completed_week": "W5",
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        """
        async with RoadmapStorage() as storage:
            await storage.clear_project(project)
            stats = {"phases": 0, "milestones": 0, "tasks": 0}

            for p_idx, p_data in enumerate(roadmap_data.get("phases", [])):
                phase = RoadmapPhase(
                    id=None,
                    project=project,
                    name=p_data["name"],
                    order=p_idx,
                    status=p_data.get("status", "planned"),
                    start_date=p_data.get("start_date"),
                    end_date=p_data.get("end_date"),
                    description=p_data.get("description", ""),
                )
                phase_id = await storage.save_phase(phase)
                stats["phases"] += 1

                for m_idx, m_data in enumerate(p_data.get("milestones", [])):
                    milestone = RoadmapMilestone(
                        id=None,
                        phase_id=phase_id,
                        project=project,
                        name=m_data["name"],
                        order=m_idx,
                        status=m_data.get("status", "pending"),
                        target_date=m_data.get("target_date"),
                        completed_date=m_data.get("completed_date"),
                        description=m_data.get("description", ""),
                    )
                    ms_id = await storage.save_milestone(milestone)
                    stats["milestones"] += 1

                    for t_data in m_data.get("tasks", []):
                        effort_raw = t_data.get("effort", 2)
                        try:
                            effort = TaskEffort(int(effort_raw))
                        except (ValueError, TypeError):
                            effort = TaskEffort.MEDIUM

                        task = RoadmapTask(
                            id=None,
                            milestone_id=ms_id,
                            project=project,
                            title=t_data["title"],
                            status=t_data.get("status", "pending"),
                            priority=t_data.get("priority", "medium"),
                            effort=effort,
                            source=t_data.get("source", "manual"),
                            related_repo=t_data.get("related_repo"),
                            completed_date=t_data.get("completed_date"),
                            completed_week=t_data.get("completed_week"),
                            description=t_data.get("description", ""),
                        )
                        await storage.save_task(task)
                        stats["tasks"] += 1

        return stats

    async def init_roadmap(self, project: str) -> dict:
        """심층 분석 → DB 적재 (메인 엔트리포인트)

        1. PRD 스캔 + 보고서 파싱 + git 활동 수집
        2. 수집 데이터 출력 (사용자 확인용)
        3. 규칙 기반 자동 매핑으로 Phase/Milestone/Task 구조화
        4. RoadmapStorage에 저장
        5. 결과 요약 반환
        """
        print(f"\n[DeepAnalyzer] 프로젝트 '{project}' 심층 분석 시작")
        print("-" * 60)

        # Step 1: 데이터 수집
        print("1. PRD 스캔 중...")
        prds = self._scan_prds(project)
        print(f"   발견된 PRD: {len(prds)}개")
        for prd in prds:
            impl_count = len(prd.get("impl_items", []))
            print(f"   - [{prd['repo']}] {prd['file']} (구현 항목 {impl_count}개)")

        print("2. 주간 보고서 로드 중...")
        report_text = self._scan_reports()
        report_lines = len(report_text.splitlines()) if report_text else 0
        print(f"   보고서 {report_lines}줄 로드됨")

        print("3. git 활동 수집 중 (최근 30일)...")
        git_activities = self._get_recent_git_activity(project, days=30)
        print(f"   커밋 {len(git_activities)}건 수집됨")

        # Step 2: 수집 데이터 요약 출력
        print("\n[수집 데이터 요약]")
        if git_activities:
            by_repo: dict[str, int] = {}
            for a in git_activities:
                by_repo[a["repo"]] = by_repo.get(a["repo"], 0) + 1
            for repo, cnt in sorted(by_repo.items(), key=lambda x: -x[1]):
                print(f"   {repo}: {cnt}건")

        # Step 3: 규칙 기반 자동 매핑
        print("\n4. 로드맵 구조화 중...")
        roadmap_data = self._build_from_collected_data(
            project, prds, git_activities, report_text
        )
        phase_count = len(roadmap_data.get("phases", []))
        print(f"   Phase {phase_count}개 구성됨")

        # Step 4: DB 저장
        print("5. DB 적재 중...")
        stats = await self._save_to_db(project, roadmap_data)

        print(f"\n[완료] {project} 로드맵 초기화 완료")
        print(f"   Phase {stats['phases']}개 | Milestone {stats['milestones']}개 | Task {stats['tasks']}개")

        return {
            "project": project,
            "stats": stats,
            "roadmap": roadmap_data,
        }

    async def analyze_project(self, project: str) -> dict:
        """프로젝트 심층 분석 → Phase/Milestone/Task 구조 반환 (저장 없음)

        1. PRD 파일 탐색 (docs/00-prd/*.prd.md)
        2. 주간 보고서 파싱 (docs/04-report/)
        3. git log 최근 활동 수집
        4. 구조화된 로드맵 dict 반환
        """
        prds = self._scan_prds(project)
        report_text = self._scan_reports()
        git_activities = self._get_recent_git_activity(project, days=30)
        return self._build_from_collected_data(project, prds, git_activities, report_text)
