"""
Server 테스트
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.gateway.server import SecretaryGateway, load_config


class TestLoadConfig:
    """설정 로드 테스트"""

    def test_default_config(self):
        """기본 설정 반환"""
        config = load_config(Path("nonexistent.json"))

        assert config["enabled"] == True
        assert config["port"] == 8800
        assert "channels" in config
        assert "pipeline" in config
        assert "safety" in config

    def test_load_custom_config(self, tmp_path):
        """커스텀 설정 로드"""
        config_file = tmp_path / "test_config.json"
        custom_config = {
            "enabled": True,
            "port": 9000,
            "channels": {"telegram": {"enabled": True}},
        }
        config_file.write_text(json.dumps(custom_config), encoding="utf-8")

        config = load_config(config_file)

        assert config["port"] == 9000
        assert config["channels"]["telegram"]["enabled"] == True


class TestSecretaryGateway:
    """Gateway 클래스 테스트"""

    def test_init_default_config(self):
        """기본 설정으로 초기화"""
        gateway = SecretaryGateway()

        assert gateway.config["enabled"] == True
        assert gateway.config["port"] == 8800
        assert gateway._running == False
        assert len(gateway.adapters) == 0

    def test_init_custom_config(self, tmp_path):
        """커스텀 설정으로 초기화"""
        config_file = tmp_path / "test_config.json"
        custom_config = {"enabled": True, "port": 9000}
        config_file.write_text(json.dumps(custom_config), encoding="utf-8")

        gateway = SecretaryGateway(config_file)

        assert gateway.config["port"] == 9000

    def test_get_status_not_running(self):
        """중지 상태 확인"""
        gateway = SecretaryGateway()
        status = gateway.get_status()

        assert status["running"] == False
        assert status["start_time"] == None
        assert status["adapters_count"] == 0

    def test_get_running_pid_no_file(self, tmp_path, monkeypatch):
        """PID 파일 없을 때"""
        # PID 파일 경로 변경
        monkeypatch.setattr(
            "scripts.gateway.server.PID_FILE", tmp_path / "nonexistent.pid"
        )

        pid = SecretaryGateway.get_running_pid()
        assert pid is None


class TestSafetyConfig:
    """안전 설정 테스트"""

    def test_auto_send_disabled(self):
        """자동 전송 비활성화 확인"""
        config = load_config(Path("nonexistent.json"))

        assert config["safety"]["auto_send_disabled"] == True

    def test_require_confirmation(self):
        """확인 필요 설정 확인"""
        config = load_config(Path("nonexistent.json"))

        assert config["safety"]["require_confirmation"] == True

    def test_rate_limit(self):
        """Rate limit 설정 확인"""
        config = load_config(Path("nonexistent.json"))

        assert config["safety"]["rate_limit_per_minute"] == 10
