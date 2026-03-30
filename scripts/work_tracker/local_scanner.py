"""
Local Scanner — 로컬 레포 전수 검사

C:\\claude 아래 34개 레포의 구조, docs, PRD, git 히스토리를 스캔합니다.
"""

import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

REPOS_ROOT = Path(r"C:\claude")
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", "dist", ".venv", ".next", "build"}
SCAN_TIMEOUT = 30  # 레포당 타임아웃 (초)


class LocalScanner:
    """로컬 레포 전수 검사기"""

    def __init__(self, repos_root: Path | None = None):
        self.repos_root = repos_root or REPOS_ROOT

    def scan_all(self) -> dict[str, dict]:
        """전체 레포 스캔 → {repo_name: scan_result}"""
        results = {}
        repos = self._discover_repos()
        logger.info(f"로컬 레포 {len(repos)}개 발견")

        for repo_path in repos:
            name = repo_path.name
            try:
                results[name] = self.scan_repo(repo_path)
            except Exception as e:
                logger.warning(f"레포 스캔 실패 ({name}): {e}")
                results[name] = {"error": str(e)}

        return results

    def scan_repo(self, repo_path: Path) -> dict:
        """단일 레포 스캔"""
        result = {
            "path": str(repo_path),
            "dir_structure": self._scan_directory_structure(repo_path),
            "doc_inventory": self._scan_docs(repo_path),
            "prd_status": self._scan_prds(repo_path),
            "recent_commits": self._get_recent_commits(repo_path),
            "branches": self._get_branches(repo_path),
        }
        return result

    def _discover_repos(self) -> list[Path]:
        """repos_root 자체 + 직접 자식 중 .git 존재하는 디렉토리"""
        repos = []
        if not self.repos_root.exists():
            return repos
        # repos_root 자체가 git 레포이면 포함
        if (self.repos_root / ".git").exists():
            repos.append(self.repos_root)
        for item in sorted(self.repos_root.iterdir()):
            if item.is_dir() and (item / ".git").exists():
                repos.append(item)
        return repos

    def _scan_directory_structure(self, repo_path: Path, max_depth: int = 2) -> dict:
        """디렉토리 구조 스캔 (2레벨, skip 패턴 적용)"""
        structure = {"dirs": [], "key_files": []}
        try:
            for item in sorted(repo_path.iterdir()):
                if item.name.startswith(".") and item.name != ".claude":
                    continue
                if item.name in SKIP_DIRS:
                    continue
                if item.is_dir():
                    sub_info = {"name": item.name, "children": []}
                    if max_depth > 1:
                        try:
                            for child in sorted(item.iterdir()):
                                if child.name.startswith("."):
                                    continue
                                if child.name in SKIP_DIRS:
                                    continue
                                if child.is_dir():
                                    sub_info["children"].append(child.name + "/")
                                elif child.is_file():
                                    sub_info["children"].append(child.name)
                        except PermissionError:
                            pass
                    structure["dirs"].append(sub_info)
                elif item.is_file() and item.suffix in (".py", ".ts", ".js", ".json", ".md", ".toml"):
                    structure["key_files"].append(item.name)
        except PermissionError:
            pass
        return structure

    def _scan_docs(self, repo_path: Path) -> list[dict]:
        """docs/ 내 .md 파일 목록 + 최근 수정일"""
        docs_dir = repo_path / "docs"
        if not docs_dir.exists():
            return []
        inventory = []
        try:
            for md_file in sorted(docs_dir.rglob("*.md")):
                try:
                    stat = md_file.stat()
                    inventory.append({
                        "path": str(md_file.relative_to(repo_path)),
                        "title": self._extract_md_title(md_file),
                        "last_modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                    })
                except Exception:
                    continue
        except PermissionError:
            pass
        return inventory

    def _scan_prds(self, repo_path: Path) -> list[dict]:
        """docs/00-prd/ PRD 파일 파싱"""
        prd_dir = repo_path / "docs" / "00-prd"
        if not prd_dir.exists():
            return []
        prds = []
        for prd_file in sorted(prd_dir.glob("*.md")):
            try:
                prd_info = self._parse_prd(prd_file, repo_path)
                if prd_info:
                    prds.append(prd_info)
            except Exception:
                continue
        return prds

    def _parse_prd(self, prd_file: Path, repo_path: Path) -> dict | None:
        """PRD 파일 파싱 — 제목, 버전, 구현 상태"""
        try:
            content = prd_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        # 제목 추출
        title = prd_file.stem
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        # 버전 추출
        version = "unknown"
        ver_match = re.search(r"v(\d+\.\d+)", content)
        if ver_match:
            version = f"v{ver_match.group(1)}"

        # 구현 상태 테이블 파싱
        status_counts = {"완료": 0, "진행 중": 0, "예정": 0}
        in_status_section = False
        for line in content.split("\n"):
            if "구현 상태" in line and line.strip().startswith("#"):
                in_status_section = True
                continue
            if in_status_section and line.strip().startswith("#"):
                break
            if in_status_section and "|" in line:
                line_lower = line.lower()
                if "완료" in line_lower:
                    status_counts["완료"] += 1
                elif "진행" in line_lower:
                    status_counts["진행 중"] += 1
                elif "예정" in line_lower:
                    status_counts["예정"] += 1

        return {
            "path": str(prd_file.relative_to(repo_path)),
            "title": title,
            "version": version,
            "status": status_counts,
        }

    def _get_recent_commits(self, repo_path: Path, count: int = 20) -> list[dict]:
        """최근 N개 커밋 (git log --oneline)"""
        try:
            result = subprocess.run(
                ["git", "log", f"--oneline", f"-{count}", "--format=%H|%s|%ai"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=SCAN_TIMEOUT,
                encoding="utf-8",
                errors="replace",
            )
            if result.returncode != 0:
                return []
            commits = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 2)
                if len(parts) >= 3:
                    commits.append({
                        "hash": parts[0][:7],
                        "message": parts[1],
                        "date": parts[2][:10],
                    })
            return commits
        except Exception:
            return []

    def _get_branches(self, repo_path: Path) -> list[dict]:
        """활성 브랜치 목록"""
        try:
            result = subprocess.run(
                ["git", "branch", "-a", "--format=%(refname:short)|%(committerdate:short)|%(objectname:short)"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=SCAN_TIMEOUT,
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
                name = parts[0] if parts else ""
                # origin/HEAD 등 심볼릭 레퍼런스 제외
                if "HEAD" in name:
                    continue
                branches.append({
                    "name": name,
                    "last_commit_date": parts[1] if len(parts) > 1 else "",
                    "last_commit_hash": parts[2] if len(parts) > 2 else "",
                })
            return branches
        except Exception:
            return []

    @staticmethod
    def _extract_md_title(md_file: Path) -> str:
        """마크다운 파일에서 첫 번째 # 제목 추출"""
        try:
            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("# "):
                        return line[2:].strip()
            return md_file.stem
        except Exception:
            return md_file.stem
