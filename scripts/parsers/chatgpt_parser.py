#!/usr/bin/env python3
"""
ChatGPT Export JSON Parser

Parses ChatGPT conversation exports (conversations.json format)
"""

import json
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


class ChatGPTParser:
    """ChatGPT Export JSON 파서"""

    def __init__(self, export_file: Path):
        self.export_file = export_file

    def parse_export(self, days: int = 7) -> Iterator[LLMSession]:
        """ChatGPT Export 파일 파싱"""
        if not self.export_file.exists():
            print(f"Warning: ChatGPT export 파일이 없습니다: {self.export_file}")
            return

        try:
            with open(self.export_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error: ChatGPT export 파일 읽기 실패: {e}")
            return

        # conversations.json은 보통 대화 리스트를 포함
        conversations = data if isinstance(data, list) else [data]

        cutoff_time = datetime.now(timezone.utc).timestamp() - (days * 24 * 3600)

        for conv in conversations:
            session = self._parse_conversation(conv)
            if session and session.start_time.timestamp() >= cutoff_time:
                yield session

    def _parse_conversation(self, conv: dict) -> LLMSession | None:
        """단일 대화 파싱"""
        try:
            title = conv.get("title", "Untitled")
            create_time = conv.get("create_time")
            update_time = conv.get("update_time")

            if not create_time:
                return None

            start_time = datetime.fromtimestamp(create_time, tz=timezone.utc)
            end_time = (
                datetime.fromtimestamp(update_time, tz=timezone.utc)
                if update_time
                else start_time
            )

            # 메시지 추출
            mapping = conv.get("mapping", {})
            messages = []
            files_mentioned = set()
            topics = set()

            for node_id, node in mapping.items():
                message = node.get("message")
                if not message:
                    continue

                author = message.get("author", {}).get("role")
                content = message.get("content", {})

                if author in ["user", "assistant"]:
                    messages.append(message)

                    # 텍스트 추출
                    parts = content.get("parts", [])
                    text = " ".join(str(part) for part in parts if part)

                    # 파일 경로 추출 (간단한 패턴)
                    import re

                    file_paths = re.findall(r"[\w/\\]+\.\w+", text)
                    files_mentioned.update(file_paths)

                    # 키워드 추출
                    keywords = self._extract_keywords(text)
                    topics.update(keywords)

            if not messages:
                return None

            # ChatGPT는 세션 ID가 없으므로 title + create_time 조합 사용
            session_id = f"chatgpt_{create_time}_{hash(title) % 10000:04d}"

            return LLMSession(
                source="chatgpt",
                session_id=session_id,
                title=title,
                start_time=start_time,
                end_time=end_time,
                message_count=len(messages),
                project=None,  # ChatGPT는 프로젝트 정보 없음
                topics=sorted(topics)[:10],
                files_mentioned=sorted(files_mentioned)[:20],
                tools_used={},  # ChatGPT는 도구 사용 정보 없음
            )

        except Exception as e:
            print(f"Warning: 대화 파싱 실패: {e}")
            return None

    def _extract_keywords(self, text: str) -> set[str]:
        """간단한 키워드 추출"""
        import re

        keywords = set()

        # 코드 키워드
        tech_keywords = [
            "python",
            "javascript",
            "typescript",
            "react",
            "api",
            "database",
            "error",
            "fix",
            "bug",
            "feature",
            "test",
            "deploy",
            "auth",
            "code",
            "function",
            "class",
        ]

        for kw in tech_keywords:
            if kw.lower() in text.lower():
                keywords.add(kw)

        # PascalCase, snake_case 추출
        identifiers = re.findall(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b", text)
        identifiers += re.findall(r"\b[a-z]+_[a-z]+\b", text)
        keywords.update(identifiers[:10])

        return keywords
