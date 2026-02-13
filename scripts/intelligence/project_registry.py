"""
ProjectRegistry - 프로젝트 등록 및 관리

config/projects.json에서 프로젝트 정의를 로드하고,
IntelligenceStorage와 연동하여 CRUD 제공.
"""

import json
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from .context_store import IntelligenceStorage


DEFAULT_CONFIG_PATH = Path(r"C:\claude\secretary\config\projects.json")


def _word_boundary_match(term: str, text: str) -> bool:
    """단어 경계 매칭 (한국어/영어 혼합 지원)"""
    pattern = re.compile(
        rf'(?:^|[\s,.\-!?;:()\"\'·]){re.escape(term.lower())}(?:[\s,.\-!?;:()\"\'·]|$)',
        re.IGNORECASE
    )
    return bool(pattern.search(text))


class ProjectRegistry:
    """프로젝트 레지스트리"""

    def __init__(self, storage: IntelligenceStorage, config_path: Optional[Path] = None):
        self.storage = storage
        self.config_path = config_path or DEFAULT_CONFIG_PATH

    async def load_from_config(self) -> int:
        """
        config/projects.json에서 프로젝트 로드 후 DB에 저장

        Returns:
            로드된 프로젝트 수
        """
        if not self.config_path.exists():
            return 0

        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        projects = config.get("projects", [])
        for project in projects:
            await self.storage.save_project(project)

        return len(projects)

    async def register(self, project: Dict[str, Any]) -> str:
        """프로젝트 등록"""
        return await self.storage.save_project(project)

    async def get(self, project_id: str) -> Optional[Dict[str, Any]]:
        """프로젝트 조회"""
        return await self.storage.get_project(project_id)

    async def list_all(self) -> List[Dict[str, Any]]:
        """전체 프로젝트 목록"""
        return await self.storage.list_projects()

    async def delete(self, project_id: str) -> bool:
        """프로젝트 삭제"""
        return await self.storage.delete_project(project_id)

    async def find_by_channel(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Slack 채널 ID로 프로젝트 검색"""
        projects = await self.list_all()
        for project in projects:
            channels = project.get("slack_channels", [])
            if channel_id in channels:
                return project
        return None

    async def find_by_keyword(self, text: str) -> List[Dict[str, Any]]:
        """키워드로 프로젝트 검색 (매칭 점수 순 정렬)"""
        text_lower = text.lower()
        projects = await self.list_all()
        scored = []

        for project in projects:
            score = 0
            keywords = project.get("keywords", [])
            name = project.get("name", "").lower()
            project_id = project.get("id", "").lower()

            if _word_boundary_match(project_id, text_lower):
                score += 1
            if _word_boundary_match(name, text_lower):
                score += 1

            for keyword in keywords:
                if _word_boundary_match(keyword, text_lower):
                    score += 1

            if score > 0:
                project_copy = dict(project)
                project_copy["_match_score"] = score
                scored.append(project_copy)

        scored.sort(key=lambda p: p["_match_score"], reverse=True)
        return scored

    async def find_by_contact(self, sender_id: str) -> Optional[Dict[str, Any]]:
        """발신자 ID로 프로젝트 검색"""
        projects = await self.list_all()
        for project in projects:
            contacts = project.get("contacts", [])
            if sender_id in contacts:
                return project
        return None
