"""
GitHub Collector — GitHub API 래핑 (issues, PRs, attention 항목)

기존 scripts/github_analyzer.py의 함수를 재사용하여
Work Tracker용 구조화된 데이터를 수집합니다.
"""

import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

TOKEN_FILE = Path(r"C:\claude\json\github_token.txt")
BASE_URL = "https://api.github.com"


class GitHubCollector:
    """GitHub 현황 수집기"""

    def __init__(self, owner: str = "garimto81", repo: str = "claude"):
        self.owner = owner
        self.repo = repo
        self._token: str | None = None

    def _get_token(self) -> str | None:
        """GitHub 토큰 로드 (graceful — 없으면 None)"""
        if self._token:
            return self._token
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            self._token = token
            return token
        if TOKEN_FILE.exists():
            self._token = TOKEN_FILE.read_text().strip()
            return self._token
        logger.warning("GitHub 토큰 없음 — GitHub 수집 건너뜀")
        return None

    def _api_get(self, endpoint: str, params: dict | None = None) -> list | dict | None:
        """GitHub API GET 요청"""
        token = self._get_token()
        if not token:
            return None
        url = f"{BASE_URL}{endpoint}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(url, headers=headers, params=params)
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 403:
                    logger.warning(f"Rate limit 또는 접근 제한: {endpoint}")
                elif resp.status_code != 404:
                    logger.warning(f"API 실패 {resp.status_code}: {endpoint}")
                return None
        except Exception as e:
            logger.warning(f"API 요청 오류: {e}")
            return None

    def collect(self) -> dict:
        """GitHub 현황 수집 → dict

        Returns:
            {"open_issues": [...], "open_prs": [...], "attention": [...]}
            실패 시 빈 dict 키들 반환.
        """
        result = {"open_issues": [], "open_prs": [], "attention": []}

        if not self._get_token():
            return result

        try:
            result["open_issues"] = self._collect_issues()
            result["open_prs"] = self._collect_prs()
            result["attention"] = self._detect_attention(
                result["open_issues"], result["open_prs"]
            )
        except Exception as e:
            logger.warning(f"GitHub 수집 실패: {e}")

        return result

    def _collect_issues(self) -> list[dict]:
        """오픈 이슈 수집 (PR 제외)"""
        raw = self._api_get(
            f"/repos/{self.owner}/{self.repo}/issues",
            params={"state": "open", "per_page": 50},
        )
        if not raw:
            return []
        issues = []
        for item in raw:
            if "pull_request" in item:
                continue
            issues.append({
                "number": item.get("number"),
                "title": item.get("title", ""),
                "state": item.get("state", ""),
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
                "labels": [l.get("name", "") for l in item.get("labels", [])],
                "url": item.get("html_url", ""),
            })
        return issues

    def _collect_prs(self) -> list[dict]:
        """오픈 PR 수집"""
        raw = self._api_get(
            f"/repos/{self.owner}/{self.repo}/pulls",
            params={"state": "open", "per_page": 30},
        )
        if not raw:
            return []
        prs = []
        for item in raw:
            prs.append({
                "number": item.get("number"),
                "title": item.get("title", ""),
                "draft": item.get("draft", False),
                "created_at": item.get("created_at", ""),
                "updated_at": item.get("updated_at", ""),
                "url": item.get("html_url", ""),
                "head_branch": item.get("head", {}).get("ref", ""),
            })
        return prs

    def _detect_attention(
        self, issues: list[dict], prs: list[dict]
    ) -> list[dict]:
        """주의 필요 항목: stale PRs (3일+), unresponded issues (4일+)"""
        attention = []
        now = datetime.now(UTC)

        for pr in prs:
            created = pr.get("created_at", "")
            if not created:
                continue
            days = self._days_since(created, now)
            if days >= 3:
                attention.append({
                    "type": "pr",
                    "number": pr["number"],
                    "title": pr["title"],
                    "days": days,
                    "reason": f"리뷰 대기 {days}일",
                    "url": pr.get("url", ""),
                })

        for issue in issues:
            updated = issue.get("updated_at", "")
            if not updated:
                continue
            days = self._days_since(updated, now)
            if days >= 4:
                attention.append({
                    "type": "issue",
                    "number": issue["number"],
                    "title": issue["title"],
                    "days": days,
                    "reason": f"응답 없음 {days}일",
                    "url": issue.get("url", ""),
                })

        return attention

    @staticmethod
    def _days_since(date_str: str, now: datetime | None = None) -> int:
        """날짜 문자열로부터 경과 일수"""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            ref = now or datetime.now(dt.tzinfo)
            return (ref - dt).days
        except Exception:
            return 0
