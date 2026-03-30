"""
Git 커밋 수집기

C:/claude 하위 레포들에서 git log를 수집하고
Conventional Commit 패턴으로 파싱한다.
"""

import json
import re
import subprocess
from pathlib import Path

from scripts.shared.paths import PROJECTS_CONFIG
from scripts.work_tracker.models import CommitType, DailyCommit, FileChange


class GitCollector:
    """Git log 수집 및 Conventional Commit 파싱"""

    # Conventional Commit 정규식
    _CONVENTIONAL_RE = re.compile(r"^(\w+)(?:\(([^)]+)\))?!?:\s*(.+)")

    # --stat 요약 라인 정규식
    _STAT_SUMMARY_RE = re.compile(
        r"^\s*(\d+) files? changed"
        r"(?:,\s*(\d+) insertions?\(\+\))?"
        r"(?:,\s*(\d+) deletions?\(-\))?"
    )

    # --stat 개별 파일 라인 정규식
    _STAT_FILE_RE = re.compile(r"^\s(.+?)\s+\|\s+(.+)$")

    def __init__(
        self,
        base_dir: str = r"C:\claude",
        config_path: Path | None = None,
    ):
        self.base_dir = Path(base_dir)
        self.config_path = config_path or PROJECTS_CONFIG
        self._repo_mapping = self._load_repo_mapping()

    # ------------------------------------------------------------------
    # 설정 로드
    # ------------------------------------------------------------------

    def _load_repo_mapping(self) -> dict:
        """config/projects.json에서 local_repo_mapping 로드"""
        try:
            with open(self.config_path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("local_repo_mapping", {})
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    # ------------------------------------------------------------------
    # 레포 탐색
    # ------------------------------------------------------------------

    def discover_repos(self) -> list[Path]:
        """C:\\claude\\*\\.git glob → 유효 레포 경로 리스트

        base_dir 자체가 git 레포이면 포함한다.
        base_dir 직접 자식 디렉토리 중 .git이 존재하는 것만 반환한다.
        재귀 탐색하지 않는다.
        """
        repos: list[Path] = []
        # base_dir 자체가 git 레포이면 포함
        if (self.base_dir / ".git").exists():
            repos.append(self.base_dir)
        for git_dir in self.base_dir.glob("*/.git"):
            parent = git_dir.parent
            if parent.is_dir() and parent != self.base_dir:
                repos.append(parent)
        # 매핑 기반 보충 — 매핑에 있지만 glob에서 못 찾은 레포
        found_names = {r.name for r in repos}
        for repo_name in self._repo_mapping:
            if repo_name not in found_names:
                candidate = self.base_dir / repo_name
                if candidate.is_dir() and (candidate / ".git").exists():
                    repos.append(candidate)
        return repos

    # ------------------------------------------------------------------
    # 수집 진입점
    # ------------------------------------------------------------------

    def collect_date(
        self,
        date: str,
        repos: list[Path] | None = None,
    ) -> list[DailyCommit]:
        """지정일 모든 레포에서 커밋 수집

        Args:
            date: YYYY-MM-DD
            repos: 대상 레포 리스트 (None이면 discover_repos() 사용)

        Returns:
            list[DailyCommit]
        """
        if repos is None:
            repos = self.discover_repos()

        result: list[DailyCommit] = []
        for repo_path in repos:
            try:
                commits = self._collect_repo_date(repo_path, date)
                result.extend(commits)
            except subprocess.TimeoutExpired:
                print(f"[WARNING] timeout: {repo_path.name}")
            except Exception as exc:  # noqa: BLE001
                print(f"[WARNING] skip {repo_path.name}: {exc}")
        return result

    # ------------------------------------------------------------------
    # 단일 레포 수집
    # ------------------------------------------------------------------

    def _collect_repo_date(self, repo_path: Path, date: str) -> list[DailyCommit]:
        """단일 레포에서 지정일 커밋 수집"""
        cmd = [
            "git",
            "log",
            f"--since={date}T00:00:00",
            f"--until={date}T23:59:59",
            "--format=%H|%s|%an|%ai|%D",
            "--stat",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=str(repo_path),
        )
        if result.returncode != 0 and not result.stdout.strip():
            return []
        return self._parse_git_output(result.stdout, repo_path.name, date)

    # ------------------------------------------------------------------
    # git log 출력 파싱
    # ------------------------------------------------------------------

    def _parse_git_output(
        self, output: str, repo_name: str, date: str
    ) -> list[DailyCommit]:
        """git log --format="%H|%s|%an|%ai|%D" --stat 출력 파싱

        출력 구조:
            <hash>|<subject>|<author>|<timestamp>|<refnames>
             file1.py | 10 +++++-----
             2 files changed, 5 insertions(+), 5 deletions(-)

            <next commit header>
            ...
        """
        if not output.strip():
            return []

        commits: list[DailyCommit] = []
        project, category = self._classify_repo(repo_name)

        # 커밋 블록 분리: 헤더 라인으로 시작하는 구획
        # 헤더 패턴: "<hash>|..."  (hex 문자열 + pipe)
        _HEADER_RE = re.compile(r"^([0-9a-f]+)\|")

        lines = output.splitlines()
        blocks: list[list[str]] = []
        current_block: list[str] = []

        for line in lines:
            if _HEADER_RE.match(line):
                if current_block:
                    blocks.append(current_block)
                current_block = [line]
            else:
                if current_block:
                    current_block.append(line)

        if current_block:
            blocks.append(current_block)

        for block in blocks:
            if not block:
                continue

            header = block[0]
            stat_lines = block[1:]

            # 헤더 파싱: hash|subject|author|timestamp|refnames
            parts = header.split("|", 4)
            if len(parts) < 4:
                continue

            commit_hash = parts[0].strip()
            subject = parts[1].strip()
            author = parts[2].strip()
            timestamp = parts[3].strip()
            ref_names = parts[4].strip() if len(parts) > 4 else ""

            commit_type, scope, description = self._parse_conventional_commit(subject)
            branch = self._extract_branch(ref_names)
            files_changed, insertions, deletions, _ = self._parse_file_changes(
                stat_lines
            )

            commits.append(
                DailyCommit(
                    date=date,
                    repo=repo_name,
                    project=project,
                    category=category,
                    commit_hash=commit_hash,
                    commit_type=commit_type,
                    commit_scope=scope,
                    message=description,
                    author=author,
                    timestamp=timestamp,
                    files_changed=files_changed,
                    insertions=insertions,
                    deletions=deletions,
                    branch=branch,
                )
            )

        return commits

    # ------------------------------------------------------------------
    # Conventional Commit 파싱
    # ------------------------------------------------------------------

    def _parse_conventional_commit(
        self, message: str
    ) -> tuple[CommitType, str | None, str]:
        """Conventional Commit 파싱

        Pattern: ^(\\w+)(?:\\(([^)]+)\\))?!?:\\s*(.+)

        Returns:
            (type, scope, description)
            매칭 실패 → (CommitType.OTHER, None, original_message)
        """
        m = self._CONVENTIONAL_RE.match(message.strip())
        if not m:
            return CommitType.OTHER, None, message.strip()

        type_str = m.group(1).lower()
        scope = m.group(2)  # None if not present
        description = m.group(3).strip()

        try:
            commit_type = CommitType(type_str)
        except ValueError:
            commit_type = CommitType.OTHER

        return commit_type, scope, description

    # ------------------------------------------------------------------
    # 레포 분류
    # ------------------------------------------------------------------

    def _classify_repo(self, repo_name: str) -> tuple[str, str | None]:
        """레포명 → (project, category) 분류

        repo_mapping에 있으면 해당 값 사용.
        없으면 ("기타", None).
        """
        entry = self._repo_mapping.get(repo_name)
        if entry:
            return entry.get("project", "기타"), entry.get("category")
        return "기타", None

    # ------------------------------------------------------------------
    # 브랜치 추출
    # ------------------------------------------------------------------

    def _extract_branch(self, ref_names: str) -> str | None:
        """%D (ref names) 문자열에서 브랜치명 추출

        우선순위:
        1. HEAD -> <branch>
        2. origin/<branch>
        3. 첫 번째 ref
        """
        if not ref_names.strip():
            return None

        # HEAD -> branch_name
        head_match = re.search(r"HEAD\s*->\s*([\w/.\-]+)", ref_names)
        if head_match:
            return head_match.group(1)

        # origin/branch_name
        origin_match = re.search(r"origin/([\w/.\-]+)", ref_names)
        if origin_match:
            return origin_match.group(1)

        # 첫 번째 ref (쉼표 구분)
        first = ref_names.split(",")[0].strip()
        return first if first else None

    # ------------------------------------------------------------------
    # --stat 파싱
    # ------------------------------------------------------------------

    def _parse_file_changes(
        self, stat_lines: list[str]
    ) -> tuple[int, int, int, list[FileChange]]:
        """--stat 출력에서 파일 변경 파싱

        Returns:
            (files_changed, insertions, deletions, list[FileChange])

        stat line 예시:
            " filename | 10 +++++-----"
            " filename | Bin 0 -> 100 bytes"
        summary line 예시:
            " 2 files changed, 5 insertions(+), 5 deletions(-)"
        """
        file_changes: list[FileChange] = []
        files_changed = 0
        insertions = 0
        deletions = 0

        for line in stat_lines:
            # 요약 라인 먼저 확인
            summary_m = self._STAT_SUMMARY_RE.match(line)
            if summary_m:
                files_changed = int(summary_m.group(1))
                insertions = int(summary_m.group(2) or 0)
                deletions = int(summary_m.group(3) or 0)
                continue

            # 개별 파일 라인
            file_m = self._STAT_FILE_RE.match(line)
            if not file_m:
                continue

            file_path = file_m.group(1).strip()
            change_info = file_m.group(2).strip()

            # Binary 파일
            if "Bin" in change_info:
                file_changes.append(
                    FileChange(
                        file_path=file_path,
                        change_type="modified",
                        insertions=0,
                        deletions=0,
                    )
                )
                continue

            # +/- 카운트
            ins = len(re.findall(r"\+", change_info))
            dels = len(re.findall(r"-", change_info))

            if ins > 0 and dels > 0:
                change_type = "modified"
            elif ins > 0:
                change_type = "added"
            else:
                change_type = "deleted"

            file_changes.append(
                FileChange(
                    file_path=file_path,
                    change_type=change_type,
                    insertions=ins,
                    deletions=dels,
                )
            )

        return files_changed, insertions, deletions, file_changes
