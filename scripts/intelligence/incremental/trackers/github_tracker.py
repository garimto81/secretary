"""
GitHubTracker - GitHub 증분 수집기

GitHub API를 사용하여 프로젝트 관련 이벤트를 수집합니다.
- Issues, PRs, Comments
"""

import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ...context_store import IntelligenceStorage
from ..analysis_state import AnalysisStateManager


def _get_github_token() -> str | None:
    """GitHub 토큰 로드"""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    token_file = Path(r"C:\claude\json\github_token.txt")
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()

    return None


class GitHubTracker:
    """GitHub 증분 수집기"""

    def __init__(self, storage: IntelligenceStorage, state_manager: AnalysisStateManager):
        self.storage = storage
        self.state_manager = state_manager
        self._token = _get_github_token()

    async def fetch_new(
        self,
        project_id: str,
        repos: list[str],
    ) -> int:
        """
        프로젝트 GitHub 레포에서 최신 활동 수집

        Args:
            project_id: 프로젝트 ID
            repos: 레포 목록 (owner/repo 형식)

        Returns:
            수집된 항목 수
        """
        if not self._token:
            return 0

        total = 0
        for repo in repos:
            count = await self._fetch_repo(project_id, repo)
            total += count

        return total

    async def _fetch_repo(self, project_id: str, repo: str) -> int:
        """단일 레포에서 이벤트 수집"""
        since = await self.state_manager.get_github_since(project_id)
        if not since:
            since = (datetime.now() - timedelta(days=7)).isoformat() + "Z"

        count = 0

        # Issues 수집
        issues = await self._fetch_api_paginated(f"repos/{repo}/issues", {"since": since, "state": "all"})
        for issue in issues:
            entry_id = hashlib.sha256(f"github:issue:{repo}:{issue['number']}".encode()).hexdigest()[:16]
            await self.storage.save_context_entry({
                "id": entry_id,
                "project_id": project_id,
                "source": "github",
                "source_id": str(issue["number"]),
                "entry_type": "issue" if "pull_request" not in issue else "pull_request",
                "title": issue.get("title", ""),
                "content": (issue.get("body") or "")[:4000],
                "metadata": {
                    "repo": repo,
                    "number": issue["number"],
                    "state": issue.get("state"),
                    "user": issue.get("user", {}).get("login"),
                    "labels": [l["name"] for l in issue.get("labels", [])],
                    "updated_at": issue.get("updated_at"),
                },
            })
            count += 1

        new_since = datetime.now().isoformat() + "Z"
        await self.state_manager.save_github_since(project_id, new_since, count)

        return count

    async def _fetch_api(
        self,
        endpoint: str,
        params: dict[str, Any],
        per_page: int = 100,
        page: int = 1,
    ) -> list[dict]:
        """GitHub API 호출"""
        import urllib.parse
        import urllib.request

        query_params = {**params, "per_page": per_page, "page": page}
        query = urllib.parse.urlencode(query_params)
        url = f"https://api.github.com/{endpoint}?{query}"

        headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Secretary-AI",
        }

        def _do_request():
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception:
                return []

        return await asyncio.to_thread(_do_request)

    async def _fetch_api_paginated(
        self,
        endpoint: str,
        params: dict[str, Any],
        max_pages: int = 3,
        per_page: int = 100,
    ) -> list[dict]:
        """GitHub API 호출 (페이지네이션 지원)

        Args:
            endpoint: API 엔드포인트
            params: 쿼리 파라미터
            max_pages: 최대 페이지 수 (기본 3 = 300 결과)
            per_page: 페이지당 결과 수 (기본 100)

        Returns:
            모든 페이지의 결과를 연결한 리스트
        """
        all_results = []

        for page in range(1, max_pages + 1):
            results = await self._fetch_api(endpoint, params, per_page=per_page, page=page)

            if not results:
                break

            all_results.extend(results)

            # 결과가 per_page보다 적으면 마지막 페이지
            if len(results) < per_page:
                break

        return all_results
