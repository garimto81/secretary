"""
Roadmap Generator — 프로젝트별 업무 로드맵 Mermaid gantt 생성

프로젝트 소속 레포들의 활성 브랜치/최근 커밋 기반으로
Mermaid gantt 차트를 생성하고 PNG 렌더링 + Slack 전송합니다.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECTS_CONFIG = Path(r"C:\claude\secretary\config\projects.json")
BASE_DIR = Path(r"C:\claude")


class RoadmapGenerator:
    """프로젝트별 Mermaid gantt 로드맵 생성기"""

    def __init__(
        self,
        config_path: Path | None = None,
        base_dir: Path | None = None,
    ):
        self.config_path = config_path or PROJECTS_CONFIG
        self.base_dir = base_dir or BASE_DIR
        self._repo_mapping = self._load_repo_mapping()

    def _load_repo_mapping(self) -> dict:
        """projects.json에서 local_repo_mapping 로드"""
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("local_repo_mapping", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _get_project_repos(self, project_name: str) -> list[str]:
        """프로젝트에 속한 레포명 리스트"""
        return [
            name
            for name, info in self._repo_mapping.items()
            if info.get("project", "").lower() == project_name.lower()
        ]

    def _get_all_projects(self) -> list[str]:
        """고유 프로젝트 목록"""
        projects = set()
        for info in self._repo_mapping.values():
            proj = info.get("project")
            if proj:
                projects.add(proj)
        return sorted(projects)

    def _get_branch_info(self, repo_path: Path) -> list[dict]:
        """레포의 로컬 브랜치 + 최근 커밋 날짜 수집"""
        try:
            result = subprocess.run(
                [
                    "git", "branch",
                    "--format=%(refname:short)|%(committerdate:short)|%(committerdate:iso)",
                ],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return []

            branches = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 2)
                name = parts[0].strip()
                if not name or name == "HEAD":
                    continue
                last_date = parts[1].strip() if len(parts) > 1 else ""
                branches.append({
                    "name": name,
                    "last_date": last_date,
                })
            return branches
        except Exception:
            return []

    def _get_first_commit_date(self, repo_path: Path, branch: str) -> str | None:
        """브랜치의 첫 번째 커밋 날짜 (main에서 분기한 시점)"""
        try:
            # main과의 merge-base 이후 첫 커밋
            result = subprocess.run(
                ["git", "log", "main.." + branch, "--reverse", "--format=%ai", "-1"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=15,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()[:10]
        except Exception:
            pass
        return None

    def generate_project_roadmap(self, project_name: str) -> str | None:
        """프로젝트 소속 레포들의 활성 브랜치 기반 Mermaid gantt 생성"""
        repo_names = self._get_project_repos(project_name)
        if not repo_names:
            return None

        today = datetime.now().strftime("%Y-%m-%d")
        sections = []

        for repo_name in sorted(repo_names):
            repo_path = self.base_dir / repo_name
            if not repo_path.is_dir() or not (repo_path / ".git").exists():
                continue

            branches = self._get_branch_info(repo_path)
            if not branches:
                continue

            tasks = []
            for br in branches:
                if br["name"] in ("main", "master"):
                    continue

                last_date = br["last_date"] or today
                start_date = self._get_first_commit_date(repo_path, br["name"])
                if not start_date:
                    start_date = last_date

                # 상태 판단
                if last_date == today:
                    status = "active,"
                elif last_date >= today[:8]:  # 같은 달
                    status = ""
                else:
                    status = "done,"

                # 브랜치명 정리 (Mermaid 특수문자 이스케이프)
                safe_name = br["name"].replace("/", " ").replace(":", " ")
                tasks.append(
                    f"    {safe_name} :{status} {start_date}, {last_date}"
                )

            if tasks:
                category = self._repo_mapping.get(repo_name, {}).get("category", repo_name)
                sections.append(f"    section {category}")
                sections.extend(tasks)

        if not sections:
            return None

        gantt = f"gantt\n    title {project_name} 업무 로드맵\n    dateFormat YYYY-MM-DD\n"
        gantt += "\n".join(sections)
        return gantt

    def generate_all_roadmaps(self) -> dict[str, str]:
        """전체 프로젝트 로드맵 dict {project: mermaid_code}"""
        result = {}
        for project in self._get_all_projects():
            code = self.generate_project_roadmap(project)
            if code:
                result[project] = code
        return result

    def render_and_send(self, channel: str, project: str | None = None) -> list[str]:
        """프로젝트 로드맵 PNG 렌더링 + Slack 전송

        Args:
            channel: Slack 채널 ID
            project: 특정 프로젝트만 (None이면 전체)

        Returns:
            전송된 PNG 파일 경로 리스트
        """
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
        from lib.google_docs.mermaid_renderer import render_mermaid
        from lib.slack.client import SlackClient

        if project:
            roadmaps = {}
            code = self.generate_project_roadmap(project)
            if code:
                roadmaps[project] = code
        else:
            roadmaps = self.generate_all_roadmaps()

        if not roadmaps:
            print("로드맵 생성 대상 없음")
            return []

        client = SlackClient()
        sent_files = []

        for proj_name, mermaid_code in roadmaps.items():
            png_path = render_mermaid(mermaid_code)
            if not png_path:
                print(f"  [WARN] {proj_name} 렌더링 실패 — Mermaid 코드만 출력")
                print(mermaid_code)
                continue

            client.upload_file(
                channel=channel,
                file_path=png_path,
                title=f"{proj_name} 업무 로드맵",
                initial_comment=f"*{proj_name} 업무 로드맵* — {datetime.now().strftime('%Y-%m-%d')}",
            )
            print(f"  Slack 전송 완료: {proj_name} ({Path(png_path).name})")
            sent_files.append(png_path)

        return sent_files
