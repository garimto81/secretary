"""
ProjectContextResolver - Stage 0.5 프로젝트 컨텍스트 해석기

메시지가 어느 프로젝트에 속하는지 확인하고,
프로젝트별 파이프라인 설정을 반환합니다.
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

try:
    from scripts.gateway.channel_registry import ChannelRegistry
    from scripts.gateway.models import ChannelType, NormalizedMessage
except ImportError:
    try:
        from gateway.channel_registry import ChannelRegistry
        from gateway.models import ChannelType, NormalizedMessage
    except ImportError:
        from .channel_registry import ChannelRegistry
        from .models import ChannelType, NormalizedMessage

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "projects.json"
)


@dataclass
class ProjectContext:
    """프로젝트별 파이프라인 설정"""
    project_id: str
    urgent_keywords: list[str] = field(default_factory=list)
    action_keywords: list[str] = field(default_factory=list)
    notification_rules: dict[str, Any] = field(default_factory=dict)
    rate_limit_overrides: dict[str, int] = field(default_factory=dict)


class ProjectContextResolver:
    """Stage 0.5: 메시지 → 프로젝트 매핑 및 컨텍스트 반환"""

    def __init__(
        self, projects_config_path: Path | None = None, registry: ChannelRegistry | None = None
    ):
        config_path = projects_config_path or _DEFAULT_CONFIG_PATH
        self._projects: list[dict[str, Any]] = []
        self._contexts: dict[str, ProjectContext] = {}
        self._registry = registry
        self._load(config_path)

    def _load(self, path: Path) -> None:
        """projects.json 로드 및 내부 인덱스 구성"""
        if not path.exists():
            logger.warning("projects.json not found: %s", path)
            return

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._projects = data.get("projects", [])
            for p in self._projects:
                pid = p.get("id", "")
                if not pid:
                    continue
                pipeline_cfg = p.get("pipeline_config", {})
                self._contexts[pid] = ProjectContext(
                    project_id=pid,
                    urgent_keywords=pipeline_cfg.get("urgent_keywords", []),
                    action_keywords=pipeline_cfg.get("action_keywords", []),
                    notification_rules=pipeline_cfg.get("notification_rules", {}),
                    rate_limit_overrides=pipeline_cfg.get("rate_limit_overrides", {}),
                )
            logger.debug("Loaded %d projects from %s", len(self._projects), path)
        except Exception as e:
            logger.error("Failed to load projects config: %s", e)

    def resolve(self, message: NormalizedMessage) -> str | None:
        """메시지에서 project_id 결정. 순서: Registry → Slack 채널 → Email 패턴 → 키워드"""
        # 0. ChannelRegistry 우선 시도 (Slack)
        if message.channel == ChannelType.SLACK and self._registry is not None:
            registry_pid = self._registry.get_project_id(message.channel_id)
            if registry_pid:
                logger.debug("Resolved project '%s' via ChannelRegistry", registry_pid)
                return registry_pid

        for project in self._projects:
            pid = project.get("id", "")
            if not pid:
                continue

            # 1. Slack 채널 매칭
            if message.channel == ChannelType.SLACK:
                slack_channels = project.get("slack_channels", [])
                if message.channel_id in slack_channels:
                    logger.debug("Resolved project '%s' via Slack channel", pid)
                    return pid

            # 2. Email sender/subject/text 패턴 매칭
            if message.channel == ChannelType.EMAIL:
                gmail_queries = project.get("gmail_queries", [])
                if gmail_queries and self._match_email(message, gmail_queries):
                    logger.debug("Resolved project '%s' via email pattern", pid)
                    return pid

            # 3. 키워드 매칭 (텍스트)
            keywords = project.get("keywords", [])
            if keywords and self._match_keywords(message.text or "", keywords):
                logger.debug("Resolved project '%s' via keyword match", pid)
                return pid

        logger.debug("No project resolved for message %s", message.id)
        return None

    def get_context(self, project_id: str) -> ProjectContext | None:
        """project_id에 해당하는 ProjectContext 반환. 없으면 None."""
        return self._contexts.get(project_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _match_email(
        self, message: NormalizedMessage, queries: list[str]
    ) -> bool:
        """Gmail query 스타일 패턴을 텍스트/발신자에서 간단히 매칭"""
        text = (message.text or "").lower()
        sender = (message.sender_id or "").lower()
        combined = f"{sender} {text}"

        for query in queries:
            # subject:(...) 구문에서 괄호 안 키워드 추출
            subject_match = re.search(r"subject:\(([^)]+)\)", query, re.IGNORECASE)
            if subject_match:
                terms = re.split(r"\s+OR\s+", subject_match.group(1), flags=re.IGNORECASE)
                if any(term.strip().lower() in combined for term in terms):
                    return True
            else:
                # 쿼리 자체를 텍스트에서 검색
                if query.lower() in combined:
                    return True
        return False

    def _match_keywords(self, text: str, keywords: list[str]) -> bool:
        """키워드 목록 중 하나라도 텍스트에 포함되면 True (case-insensitive)"""
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)
