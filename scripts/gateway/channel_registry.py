"""
ChannelRegistry — config/channels.json 기반 단일 채널 레지스트리.
3중 import fallback 패턴 적용.
"""

import json
from pathlib import Path


class ChannelRegistry:
    def __init__(self):
        self._channels: list = []

    def load(self, path: Path) -> None:
        """channels.json 로드. 파일 없거나 파싱 실패 시 빈 목록 유지."""
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._channels = data.get("channels", [])
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._channels = []

    def get_by_role(self, role: str, channel_type: str = "slack") -> list[str]:
        """특정 role이 부여된 enabled 채널 ID 목록 반환."""
        return [
            ch.get("id", "")
            for ch in self._channels
            if ch.get("id")
            and ch.get("enabled", True)
            and role in ch.get("roles", [])
            and ch.get("type", "slack") == channel_type
        ]

    def get_project_id(self, channel_id: str) -> str | None:
        """채널 ID → project_id 반환."""
        for ch in self._channels:
            if ch.get("id") == channel_id and "project-bound" in ch.get("roles", []):
                return ch.get("project_id")
        return None

    def is_enabled(self, channel_id: str) -> bool:
        for ch in self._channels:
            if ch.get("id") == channel_id:
                return ch.get("enabled", True)
        return False

    def all_channel_ids(self, channel_type: str = "slack") -> list[str]:
        return [
            ch.get("id", "")
            for ch in self._channels
            if ch.get("id")
            and ch.get("enabled", True)
            and ch.get("type", "slack") == channel_type
        ]
