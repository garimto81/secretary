"""
ChannelRegistry 단위 테스트
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.gateway.channel_registry import ChannelRegistry


@pytest.fixture
def channels_json(tmp_path):
    """테스트용 channels.json 생성"""
    config = {
        "channels": [
            {
                "id": "C0985UXQN6Q",
                "name": "general",
                "type": "slack",
                "roles": ["monitor", "chatbot", "project-bound"],
                "project_id": "secretary",
                "enabled": True,
            },
            {
                "id": "C_DISABLED",
                "name": "disabled",
                "type": "slack",
                "roles": ["monitor"],
                "project_id": None,
                "enabled": False,
            },
            {
                "id": "C_MONITOR_ONLY",
                "name": "monitor-only",
                "type": "slack",
                "roles": ["monitor"],
                "project_id": None,
                "enabled": True,
            },
        ]
    }
    path = tmp_path / "channels.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture
def registry(channels_json):
    r = ChannelRegistry()
    r.load(channels_json)
    return r


class TestChannelRegistry:
    def test_load_channels_json(self, registry):
        """파일 로드 후 채널 목록 확인"""
        # 3개 정의, 2개 enabled
        assert len(registry.all_channel_ids()) == 2

    def test_get_by_role_monitor(self, registry):
        """monitor 역할 채널 반환 — enabled만"""
        monitor_ids = registry.get_by_role("monitor", "slack")
        assert "C0985UXQN6Q" in monitor_ids
        assert "C_MONITOR_ONLY" in monitor_ids
        # disabled 채널은 제외
        assert "C_DISABLED" not in monitor_ids

    def test_get_by_role_chatbot(self, registry):
        """chatbot 역할 채널 반환"""
        chatbot_ids = registry.get_by_role("chatbot", "slack")
        assert "C0985UXQN6Q" in chatbot_ids
        # monitor-only 채널은 chatbot 역할 없음
        assert "C_MONITOR_ONLY" not in chatbot_ids

    def test_get_project_id(self, registry):
        """project_id 반환 — project-bound 역할 필수"""
        assert registry.get_project_id("C0985UXQN6Q") == "secretary"
        # monitor-only는 project-bound 역할 없으므로 None
        assert registry.get_project_id("C_MONITOR_ONLY") is None

    def test_is_enabled(self, registry):
        """enabled 상태 확인"""
        assert registry.is_enabled("C0985UXQN6Q") is True
        assert registry.is_enabled("C_DISABLED") is False
        # 레지스트리에 없는 채널은 False
        assert registry.is_enabled("C_NONEXISTENT") is False

    def test_fallback_when_no_registry(self):
        """레지스트리 미로드 시 빈 목록 반환"""
        r = ChannelRegistry()
        assert r.get_by_role("monitor") == []
        assert r.get_project_id("C0985UXQN6Q") is None
        assert r.all_channel_ids() == []
