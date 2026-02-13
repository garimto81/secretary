"""
ContextCollector - 멀티소스 컨텍스트 수집 인터페이스

IncrementalRunner를 래핑하여 간단한 인터페이스 제공.
"""

from typing import Optional, Dict, Any, List

from .context_store import IntelligenceStorage
from .project_registry import ProjectRegistry
from .incremental.runner import IncrementalRunner


class ContextCollector:
    """컨텍스트 수집 통합 인터페이스"""

    def __init__(self, storage: IntelligenceStorage, registry: ProjectRegistry):
        self.storage = storage
        self.registry = registry
        self.runner = IncrementalRunner(storage, registry)

    async def collect(
        self,
        project_id: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        컨텍스트 수집 실행

        Args:
            project_id: 특정 프로젝트만 (None이면 전체)
            sources: 특정 소스만 (None이면 전체)

        Returns:
            수집 결과 요약
        """
        return await self.runner.run(project_id, sources)

    async def collect_all(self) -> Dict[str, Any]:
        """전체 프로젝트, 전체 소스 수집"""
        return await self.runner.run()

    async def get_project_context(self, project_id: str, limit: int = 20) -> str:
        """
        프로젝트 컨텍스트 텍스트 생성

        Args:
            project_id: 프로젝트 ID
            limit: 최대 항목 수

        Returns:
            컨텍스트 텍스트
        """
        project = await self.registry.get(project_id)
        entries = await self.storage.get_context_entries(project_id, limit=limit)

        parts = []
        if project:
            parts.append(f"프로젝트: {project.get('name', project_id)}")
            parts.append(f"설명: {project.get('description', '')}")
            parts.append("")

        for entry in entries:
            source = entry.get("source", "")
            title = entry.get("title", "")
            content = entry.get("content", "")[:300]
            parts.append(f"[{source}] {title}: {content}")

        return "\n".join(parts)
