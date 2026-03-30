"""
Snapshot Builder — Phase A 오케스트레이터

GitHubCollector + LocalScanner의 데이터를 조합하여
프로젝트별 ProjectSnapshot을 생성하고 DB에 저장합니다.
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 3-way import
try:
    from scripts.work_tracker.models import ProjectSnapshot
    from scripts.work_tracker.storage import WorkTrackerStorage
    from scripts.work_tracker.github_collector import GitHubCollector
    from scripts.work_tracker.local_scanner import LocalScanner
except ImportError:
    try:
        from work_tracker.models import ProjectSnapshot
        from work_tracker.storage import WorkTrackerStorage
        from work_tracker.github_collector import GitHubCollector
        from work_tracker.local_scanner import LocalScanner
    except ImportError:
        from .models import ProjectSnapshot
        from .storage import WorkTrackerStorage
        from .github_collector import GitHubCollector
        from .local_scanner import LocalScanner

# 프로젝트 → 레포 매핑 로드
try:
    try:
        from scripts.shared.paths import PROJECTS_CONFIG
    except ImportError:
        try:
            from shared.paths import PROJECTS_CONFIG
        except ImportError:
            from ..shared.paths import PROJECTS_CONFIG
except Exception:
    PROJECTS_CONFIG = Path(r"C:\claude\secretary\config\projects.json")


def _load_repo_mapping() -> dict[str, dict]:
    """projects.json에서 local_repo_mapping 로드"""
    try:
        with open(PROJECTS_CONFIG, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("local_repo_mapping", {})
    except Exception as e:
        logger.warning(f"projects.json 로드 실패: {e}")
        return {}


def _group_repos_by_project(repo_mapping: dict) -> dict[str, list[str]]:
    """레포 매핑 → 프로젝트별 레포 목록"""
    project_repos: dict[str, list[str]] = {}
    for repo_name, info in repo_mapping.items():
        project = info.get("project", "Other")
        if project not in project_repos:
            project_repos[project] = []
        project_repos[project].append(repo_name)
    return project_repos


class SnapshotBuilder:
    """프로젝트 스냅샷 생성기"""

    def __init__(
        self,
        storage: WorkTrackerStorage,
    ):
        self.storage = storage
        self.github = GitHubCollector()
        self.scanner = LocalScanner()
        self._repo_mapping = _load_repo_mapping()
        self._project_repos = _group_repos_by_project(self._repo_mapping)

    async def build_all(self) -> list[ProjectSnapshot]:
        """전체 프로젝트 스냅샷 생성"""
        today = datetime.now().strftime("%Y-%m-%d")

        # 1. GitHub 데이터 수집
        print("GitHub 현황 수집 중...")
        github_data = self.github.collect()
        print(f"   이슈: {len(github_data.get('open_issues', []))}건, "
              f"PR: {len(github_data.get('open_prs', []))}건")

        # 2. 로컬 스캔
        print("로컬 레포 스캔 중...")
        local_data = self.scanner.scan_all()
        print(f"   스캔 완료: {len(local_data)}개 레포")

        # 3. 프로젝트별 스냅샷 생성
        snapshots = []
        for project, repos in self._project_repos.items():
            snapshot = self._build_project_snapshot(
                project, repos, today, github_data, local_data
            )
            snapshots.append(snapshot)

        # 4. DB 저장
        for snapshot in snapshots:
            await self.storage.save_snapshot(snapshot)
            print(f"   저장: {snapshot.project} (진행률 {snapshot.estimated_progress}%)")

        return snapshots

    async def build_project(self, project: str) -> ProjectSnapshot | None:
        """단일 프로젝트 스냅샷"""
        repos = self._project_repos.get(project)
        if not repos:
            logger.warning(f"프로젝트 '{project}'에 매핑된 레포 없음")
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        github_data = self.github.collect()
        local_data = self.scanner.scan_all()

        snapshot = self._build_project_snapshot(
            project, repos, today, github_data, local_data
        )

        await self.storage.save_snapshot(snapshot)
        return snapshot

    def _build_project_snapshot(
        self,
        project: str,
        repos: list[str],
        snapshot_date: str,
        github_data: dict,
        local_data: dict[str, dict],
    ) -> ProjectSnapshot:
        """개별 프로젝트 스냅샷 구성"""
        # 디렉토리 구조 + docs + PRD
        dir_structure = {}
        all_prds = []
        all_docs = []
        recent_activity = {}
        active_branches = []

        for repo_name in repos:
            scan = local_data.get(repo_name, {})
            if "error" in scan:
                continue

            dir_structure[repo_name] = scan.get("dir_structure", {})

            for doc in scan.get("doc_inventory", []):
                doc_with_repo = {**doc, "repo": repo_name}
                all_docs.append(doc_with_repo)

            for prd in scan.get("prd_status", []):
                prd_with_repo = {**prd, "repo": repo_name}
                all_prds.append(prd_with_repo)

            commits = scan.get("recent_commits", [])
            recent_activity[repo_name] = {
                "last_commit": commits[0]["date"] if commits else "",
                "commits_count": len(commits),
                "recent_messages": [c["message"] for c in commits[:5]],
            }

            for branch in scan.get("branches", []):
                if branch["name"].startswith("origin/"):
                    continue
                active_branches.append({
                    "repo": repo_name,
                    "branch": branch["name"],
                    "last_commit_date": branch.get("last_commit_date", ""),
                })

        # PRD 기반 진행률 추정 (AI 없이도 기본값)
        estimated_progress = self._estimate_progress_from_prds(all_prds)

        return ProjectSnapshot(
            project=project,
            snapshot_date=snapshot_date,
            repos=repos,
            github_open_issues=github_data.get("open_issues", []),
            github_open_prs=github_data.get("open_prs", []),
            github_attention=github_data.get("attention", []),
            dir_structure=dir_structure,
            prd_status=all_prds,
            doc_inventory=all_docs,
            recent_activity=recent_activity,
            active_branches=active_branches,
            estimated_progress=estimated_progress,
        )

    def _estimate_progress_from_prds(self, prds: list[dict]) -> int:
        """PRD 구현 상태 테이블 기반 진행률 추정"""
        if not prds:
            return 0
        total_items = 0
        done_items = 0
        for prd in prds:
            status = prd.get("status", {})
            done = status.get("완료", 0)
            in_progress = status.get("진행 중", 0)
            planned = status.get("예정", 0)
            prd_total = done + in_progress + planned
            if prd_total > 0:
                total_items += prd_total
                done_items += done + (in_progress * 0.5)
        if total_items == 0:
            return 0
        return min(100, int(done_items / total_items * 100))

