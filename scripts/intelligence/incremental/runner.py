"""
IncrementalRunner - 증분 분석 실행기

모든 소스의 Tracker를 실행하고 결과를 집계합니다.
"""

from typing import Optional, Dict, Any, List

from .analysis_state import AnalysisStateManager
from .trackers.slack_tracker import SlackTracker
from .trackers.gmail_tracker import GmailTracker
from .trackers.github_tracker import GitHubTracker
from ..context_store import IntelligenceStorage
from ..project_registry import ProjectRegistry


class IncrementalRunner:
    """증분 분석 실행기"""

    def __init__(self, storage: IntelligenceStorage, registry: ProjectRegistry):
        self.storage = storage
        self.registry = registry
        self.state_manager = AnalysisStateManager(storage)

        self.slack_tracker = SlackTracker(storage, self.state_manager)
        self.gmail_tracker = GmailTracker(storage, self.state_manager)
        self.github_tracker = GitHubTracker(storage, self.state_manager)

    async def run(
        self,
        project_id: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        증분 분석 실행

        Args:
            project_id: 특정 프로젝트만 분석 (None이면 전체)
            sources: 특정 소스만 실행 (None이면 전체)

        Returns:
            실행 결과 요약
        """
        if project_id:
            project = await self.registry.get(project_id)
            if not project:
                return {"error": f"Project '{project_id}' not found"}
            projects = [project]
        else:
            projects = await self.registry.list_all()

        results = {}

        for project in projects:
            pid = project["id"]
            project_result = {}

            run_sources = sources or ["slack", "gmail", "github"]

            if "slack" in run_sources:
                channels = project.get("slack_channels", [])
                if channels:
                    try:
                        count = await self.slack_tracker.fetch_new(pid, channels)
                        project_result["slack"] = {"collected": count}
                    except Exception as e:
                        project_result["slack"] = {"error": str(e)}

            if "gmail" in run_sources:
                queries = project.get("gmail_queries", [])
                try:
                    count = await self.gmail_tracker.fetch_new(pid, queries)
                    project_result["gmail"] = {"collected": count}
                except Exception as e:
                    project_result["gmail"] = {"error": str(e)}

            if "github" in run_sources:
                repos = project.get("github_repos", [])
                if repos:
                    try:
                        count = await self.github_tracker.fetch_new(pid, repos)
                        project_result["github"] = {"collected": count}
                    except Exception as e:
                        project_result["github"] = {"error": str(e)}

            results[pid] = project_result

        return results
