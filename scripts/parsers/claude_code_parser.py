#!/usr/bin/env python3
"""
Claude Code JSONL Parser

Parses Claude Code session logs from ~/.claude/projects/{hash}/*.jsonl
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from dataclasses import dataclass


@dataclass
class LLMSession:
    """통합 LLM 세션 데이터 모델"""

    source: str  # "claude_code" | "chatgpt"
    session_id: str
    title: str | None
    start_time: datetime
    end_time: datetime
    message_count: int
    project: str | None  # Claude Code only
    topics: list[str]  # 키워드 추출
    files_mentioned: list[str]
    tools_used: dict[str, int]  # {Read: 5, Write: 3, ...}


class ClaudeCodeParser:
    """Claude Code JSONL 파서"""

    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir

    def find_session_files(self, days: int = 7) -> list[Path]:
        """최근 N일 세션 파일 찾기"""
        cutoff_time = datetime.now(timezone.utc).timestamp() - (days * 24 * 3600)
        session_files = []

        if not self.projects_dir.exists():
            return []

        for project_dir in self.projects_dir.iterdir():
            if not project_dir.is_dir():
                continue

            for jsonl_file in project_dir.glob("*.jsonl"):
                # 파일 수정 시간으로 필터링
                if jsonl_file.stat().st_mtime >= cutoff_time:
                    session_files.append(jsonl_file)

        return sorted(session_files, key=lambda f: f.stat().st_mtime, reverse=True)

    def parse_session_file(self, file_path: Path) -> LLMSession | None:
        """단일 JSONL 파일 파싱"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                return None

            # 메타데이터 추출
            session_id = None
            project_path = None
            git_branch = None
            start_time = None
            end_time = None
            message_count = 0
            files_mentioned = set()
            tools_used = {}
            topics = set()

            for line in lines:
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue

                # 세션 ID 추출
                if "sessionId" in entry and not session_id:
                    session_id = entry["sessionId"]

                # 프로젝트 경로 및 브랜치
                if "cwd" in entry and not project_path:
                    project_path = entry["cwd"]
                if "gitBranch" in entry and not git_branch:
                    git_branch = entry["gitBranch"]

                # 타임스탬프
                if "timestamp" in entry:
                    ts = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
                    if not start_time or ts < start_time:
                        start_time = ts
                    if not end_time or ts > end_time:
                        end_time = ts

                # 메시지 카운트
                if entry.get("type") in ["user", "assistant"]:
                    message_count += 1

                    # 파일 경로 추출 (C:\... 패턴)
                    content_str = json.dumps(entry.get("message", {}))
                    file_paths = re.findall(r"C:\\[^\s\"']+\.[a-z]+", content_str)
                    files_mentioned.update(file_paths)

                    # 키워드 추출 (간단한 패턴)
                    if isinstance(entry.get("message"), dict):
                        msg_content = str(entry["message"].get("content", ""))
                        keywords = self._extract_keywords(msg_content)
                        topics.update(keywords)

                # 도구 사용 추출
                if entry.get("type") == "assistant":
                    message = entry.get("message", {})
                    if isinstance(message, dict):
                        content = message.get("content", [])
                        if isinstance(content, list):
                            for item in content:
                                if isinstance(item, dict) and item.get("type") == "tool_use":
                                    tool_name = item.get("name", "Unknown")
                                    tools_used[tool_name] = tools_used.get(tool_name, 0) + 1

            if not session_id or not start_time:
                return None

            # 프로젝트 이름 추출 (경로의 마지막 부분)
            project_name = None
            if project_path:
                project_name = Path(project_path).name

            return LLMSession(
                source="claude_code",
                session_id=session_id,
                title=f"{project_name} ({git_branch})" if project_name else None,
                start_time=start_time,
                end_time=end_time or start_time,
                message_count=message_count,
                project=project_name,
                topics=sorted(topics)[:10],  # 상위 10개
                files_mentioned=sorted(files_mentioned)[:20],  # 상위 20개
                tools_used=tools_used,
            )

        except Exception as e:
            print(f"Warning: 파일 파싱 실패 ({file_path.name}): {e}")
            return None

    def _extract_keywords(self, text: str) -> set[str]:
        """간단한 키워드 추출 (파일명, 함수명, 클래스명 등)"""
        keywords = set()

        # 파일 확장자
        extensions = re.findall(r"\b\w+\.(py|ts|js|md|json|yaml)\b", text.lower())
        keywords.update(ext.split(".")[0] for ext in extensions)

        # 함수/클래스 패턴
        identifiers = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text)  # PascalCase
        identifiers += re.findall(r"\b[a-z]+_[a-z]+\b", text)  # snake_case
        keywords.update(identifiers[:10])

        # 기술 키워드
        tech_keywords = [
            "api",
            "auth",
            "test",
            "database",
            "bug",
            "fix",
            "feature",
            "refactor",
            "deploy",
            "error",
        ]
        for kw in tech_keywords:
            if kw in text.lower():
                keywords.add(kw)

        return keywords

    def parse_all_sessions(self, days: int = 7) -> Iterator[LLMSession]:
        """모든 세션 파일 파싱"""
        session_files = self.find_session_files(days)

        for file_path in session_files:
            session = self.parse_session_file(file_path)
            if session:
                yield session
