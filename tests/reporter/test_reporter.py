"""
SecretaryReporter 테스트
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.reporter.alert import DraftNotification, UrgentAlert
from scripts.reporter.reporter import SecretaryReporter


class TestUrgentAlert:
    """UrgentAlert 테스트"""

    def test_format_slack(self):
        """Slack 포맷"""
        alert = UrgentAlert(
            message_id="msg-1",
            sender_name="John",
            source_channel="slack",
            channel_id="ch-1",
            text_preview="서버가 다운됐습니다! 즉시 확인 필요",
        )

        text = alert.format_slack()
        assert "[긴급]" in text
        assert "John" in text
        assert "slack" in text
        assert "서버가 다운됐습니다" in text


class TestDraftNotification:
    """DraftNotification 테스트"""

    def test_format_slack(self):
        """Slack 포맷"""
        notif = DraftNotification(
            draft_id=42,
            project_id="secretary",
            sender_name="Alice",
            source_channel="gmail",
            match_confidence=0.85,
            match_tier="channel",
        )

        text = notif.format_slack()
        assert "secretary" in text
        assert "Alice" in text
        assert "0.85" in text
        assert "approve 42" in text


class TestSecretaryReporter:
    """SecretaryReporter 테스트"""

    @pytest.fixture
    def reporter_config(self):
        return {
            "enabled": True,
            "digest_time": "18:00",
            "channels": {
                "slack_dm": {
                    "enabled": True,
                    "user_id": "U12345678",
                }
            },
        }

    def test_init(self, reporter_config):
        """초기화"""
        reporter = SecretaryReporter(config=reporter_config)
        assert reporter.config["enabled"] is True
        assert reporter._running is False

    @pytest.mark.asyncio
    async def test_send_urgent_no_channel(self):
        """Slack DM 미연결 시 False 반환"""
        reporter = SecretaryReporter(config={"enabled": False})
        alert = UrgentAlert(
            message_id="m1",
            sender_name="Test",
            source_channel="slack",
            channel_id="ch",
            text_preview="urgent",
        )
        result = await reporter.send_urgent_alert(alert)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_draft_no_channel(self):
        """Slack DM 미연결 시 False 반환"""
        reporter = SecretaryReporter(config={"enabled": False})
        notif = DraftNotification(
            draft_id=1,
            project_id="test",
            sender_name="Test",
            source_channel="slack",
            match_confidence=0.8,
            match_tier="channel",
        )
        result = await reporter.send_draft_notification(notif)
        assert result is False

    @pytest.mark.asyncio
    async def test_send_with_mock_channel(self, reporter_config):
        """Mock 채널로 전송"""
        reporter = SecretaryReporter(config=reporter_config)

        # Mock Slack DM channel
        mock_channel = AsyncMock()
        mock_channel.send = AsyncMock(return_value=True)
        mock_channel.is_connected = True
        reporter._slack_dm = mock_channel

        alert = UrgentAlert(
            message_id="m1",
            sender_name="Test",
            source_channel="slack",
            channel_id="ch",
            text_preview="urgent msg",
        )
        result = await reporter.send_urgent_alert(alert)
        assert result is True
        mock_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_digest_no_channel(self):
        """Slack DM 미연결 시 Digest도 False"""
        reporter = SecretaryReporter(config={"enabled": False})
        result = await reporter.send_daily_digest()
        assert result is False

    def test_is_active(self):
        """is_active 속성"""
        reporter = SecretaryReporter(config={"enabled": False})
        assert reporter.is_active is False
