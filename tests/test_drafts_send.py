"""
drafts send 워크플로우 테스트

테스트 커버리지:
- _resolve_channel_type: 채널 타입 변환
- _create_adapter: 어댑터 생성
- SendLogger: 전송 이력 로그
- cmd_drafts_send: 전송 워크플로우
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# 경로 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestResolveChannelType:
    """_resolve_channel_type 함수 테스트"""

    def test_slack_channel(self):
        """Slack 채널 타입 변환"""
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _resolve_channel_type

        result = _resolve_channel_type("slack")
        assert result == ChannelType.SLACK

    def test_email_channel(self):
        """Email 채널 타입 변환"""
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _resolve_channel_type

        result = _resolve_channel_type("email")
        assert result == ChannelType.EMAIL

    def test_gmail_channel_maps_to_email(self):
        """Gmail은 EMAIL로 매핑"""
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _resolve_channel_type

        result = _resolve_channel_type("gmail")
        assert result == ChannelType.EMAIL

    def test_telegram_channel(self):
        """Telegram 채널 타입 변환"""
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _resolve_channel_type

        result = _resolve_channel_type("telegram")
        assert result == ChannelType.TELEGRAM

    def test_unknown_channel_returns_unknown(self):
        """알 수 없는 채널은 UNKNOWN 반환"""
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _resolve_channel_type

        result = _resolve_channel_type("unknown_service")
        assert result == ChannelType.UNKNOWN

    def test_case_insensitive_matching(self):
        """대소문자 구분 안 함"""
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _resolve_channel_type

        assert _resolve_channel_type("SLACK") == ChannelType.SLACK
        assert _resolve_channel_type("Email") == ChannelType.EMAIL
        assert _resolve_channel_type("GmAiL") == ChannelType.EMAIL


class TestSendLogger:
    """SendLogger 클래스 테스트"""

    def test_log_send_creates_file(self, tmp_path):
        """첫 log_send 호출 시 파일 생성"""
        from scripts.intelligence.send_log import SendLogger

        log_path = tmp_path / "test_send_log.jsonl"
        logger = SendLogger(log_path=log_path)

        logger.log_send(
            draft_id=1,
            channel="slack",
            recipient="U123",
            status="sent",
            message_id="ts123",
        )

        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

        record = json.loads(lines[0])
        assert record["draft_id"] == 1
        assert record["channel"] == "slack"
        assert record["recipient"] == "U123"
        assert record["status"] == "sent"
        assert record["message_id"] == "ts123"
        assert "timestamp" in record

    def test_log_send_appends_to_existing_file(self, tmp_path):
        """기존 파일에 append"""
        from scripts.intelligence.send_log import SendLogger

        log_path = tmp_path / "test_send_log.jsonl"
        logger = SendLogger(log_path=log_path)

        logger.log_send(draft_id=1, channel="slack", recipient="U1", status="sent")
        logger.log_send(
            draft_id=2,
            channel="email",
            recipient="a@b.com",
            status="failed",
            error="timeout",
        )

        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        record2 = json.loads(lines[1])
        assert record2["draft_id"] == 2
        assert record2["status"] == "failed"
        assert record2["error"] == "timeout"

    def test_get_recent_returns_reverse_order(self, tmp_path):
        """get_recent은 최신 순 반환"""
        from scripts.intelligence.send_log import SendLogger

        log_path = tmp_path / "test_send_log.jsonl"
        logger = SendLogger(log_path=log_path)

        logger.log_send(draft_id=1, channel="slack", recipient="U1", status="sent")
        logger.log_send(draft_id=2, channel="email", recipient="a@b.com", status="sent")
        logger.log_send(draft_id=3, channel="slack", recipient="U2", status="failed")

        records = logger.get_recent(limit=10)
        assert len(records) == 3
        # 최신이 먼저
        assert records[0]["draft_id"] == 3
        assert records[1]["draft_id"] == 2
        assert records[2]["draft_id"] == 1

    def test_get_recent_respects_limit(self, tmp_path):
        """limit 파라미터 준수"""
        from scripts.intelligence.send_log import SendLogger

        log_path = tmp_path / "test_send_log.jsonl"
        logger = SendLogger(log_path=log_path)

        for i in range(10):
            logger.log_send(draft_id=i, channel="slack", recipient="U", status="sent")

        records = logger.get_recent(limit=3)
        assert len(records) == 3

    def test_get_recent_empty_file(self, tmp_path):
        """파일이 없으면 빈 리스트 반환"""
        from scripts.intelligence.send_log import SendLogger

        log_path = tmp_path / "nonexistent.jsonl"
        logger = SendLogger(log_path=log_path)
        assert logger.get_recent() == []

    def test_log_send_with_error(self, tmp_path):
        """에러 정보 포함 기록"""
        from scripts.intelligence.send_log import SendLogger

        log_path = tmp_path / "test_send_log.jsonl"
        logger = SendLogger(log_path=log_path)

        logger.log_send(
            draft_id=99,
            channel="email",
            recipient="fail@test.com",
            status="failed",
            error="Connection timeout",
        )

        records = logger.get_recent(limit=1)
        assert records[0]["error"] == "Connection timeout"


class TestDraftsSend:
    """cmd_drafts_send 워크플로우 통합 테스트"""

    @pytest.mark.asyncio
    async def test_send_pending_draft_rejected(self):
        """pending 상태 draft는 전송 불가"""
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = {
            "id": 1,
            "status": "pending",  # approved 아님
            "source_channel": "slack",
            "sender_id": "U123",
            "draft_text": "Hello",
        }

        args = MagicMock(id="1", dry_run=False, force=True)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            with pytest.raises(SystemExit) as exc_info:
                await cmd_drafts_send(args)
            assert exc_info.value.code == 1

        # 전송 관련 메서드 호출 안 됨
        mock_storage.update_draft_sent.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_dry_run_no_actual_send(self):
        """--dry-run 옵션 시 전송 안 함"""
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = {
            "id": 1,
            "status": "approved",
            "source_channel": "slack",
            "sender_id": "U123",
            "sender_name": "Test User",
            "draft_text": "Hello World",
        }

        args = MagicMock(id="1", dry_run=True, force=False)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            # 출력 확인을 위해 stdout capture
            await cmd_drafts_send(args)

        # DB 업데이트 없음
        mock_storage.update_draft_sent.assert_not_called()
        mock_storage.update_draft_send_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_nonexistent_draft(self):
        """존재하지 않는 draft ID"""
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = None

        args = MagicMock(id="999", dry_run=False, force=True)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            with pytest.raises(SystemExit):
                await cmd_drafts_send(args)

    @pytest.mark.asyncio
    async def test_send_unknown_channel_type(self):
        """지원하지 않는 채널"""
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = {
            "id": 1,
            "status": "approved",
            "source_channel": "unsupported_channel",
            "sender_id": "U123",
            "draft_text": "Hello",
        }

        args = MagicMock(id="1", dry_run=False, force=True)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            with pytest.raises(SystemExit) as exc_info:
                await cmd_drafts_send(args)
            assert exc_info.value.code == 1

    @pytest.mark.asyncio
    async def test_send_adapter_connection_failed(self):
        """어댑터 연결 실패 시"""
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = {
            "id": 1,
            "status": "approved",
            "source_channel": "slack",
            "sender_id": "U123",
            "draft_text": "Hello",
        }

        mock_adapter = AsyncMock()
        mock_adapter.connect.return_value = False  # 연결 실패

        args = MagicMock(id="1", dry_run=False, force=True)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            with patch("scripts.intelligence.cli._create_adapter", return_value=mock_adapter):
                with pytest.raises(SystemExit) as exc_info:
                    await cmd_drafts_send(args)
                assert exc_info.value.code == 1

        # 실패 기록 확인
        mock_storage.update_draft_send_failed.assert_called_once_with(
            1, "어댑터 연결 실패"
        )

    @pytest.mark.asyncio
    async def test_send_successful_flow(self):
        """정상 전송 플로우"""
        from scripts.gateway.adapters.base import SendResult
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = {
            "id": 1,
            "status": "approved",
            "source_channel": "slack",
            "sender_id": "U123",
            "sender_name": "Test User",
            "draft_text": "Draft message",
            "source_message_id": "ts123",
        }

        mock_adapter = AsyncMock()
        mock_adapter.connect.return_value = True
        mock_adapter.send.return_value = SendResult(
            success=True,
            message_id="ts456",
            sent_at=datetime.now(),
        )

        args = MagicMock(id="1", dry_run=False, force=True)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            with patch("scripts.intelligence.cli._create_adapter", return_value=mock_adapter):
                with patch("scripts.intelligence.send_log.SendLogger") as MockLogger:
                    mock_logger = MockLogger.return_value

                    await cmd_drafts_send(args)

                    # DB 업데이트 확인
                    mock_storage.update_draft_sent.assert_called_once_with(1, "ts456")

                    # 로그 기록 확인
                    mock_logger.log_send.assert_called_once()
                    call_args = mock_logger.log_send.call_args[1]
                    assert call_args["draft_id"] == 1
                    assert call_args["status"] == "sent"
                    assert call_args["message_id"] == "ts456"

    @pytest.mark.asyncio
    async def test_send_failure_flow(self):
        """전송 실패 플로우"""
        from scripts.gateway.adapters.base import SendResult
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = {
            "id": 1,
            "status": "approved",
            "source_channel": "slack",
            "sender_id": "U123",
            "draft_text": "Draft message",
        }

        mock_adapter = AsyncMock()
        mock_adapter.connect.return_value = True
        mock_adapter.send.return_value = SendResult(
            success=False,
            error="Rate limit exceeded",
        )

        args = MagicMock(id="1", dry_run=False, force=True)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            with patch("scripts.intelligence.cli._create_adapter", return_value=mock_adapter):
                with patch("scripts.intelligence.send_log.SendLogger") as MockLogger:
                    mock_logger = MockLogger.return_value

                    with pytest.raises(SystemExit) as exc_info:
                        await cmd_drafts_send(args)
                    assert exc_info.value.code == 1

                    # 실패 기록 확인
                    mock_storage.update_draft_send_failed.assert_called_once_with(
                        1, "Rate limit exceeded"
                    )

                    # 로그 기록 확인
                    mock_logger.log_send.assert_called_once()
                    call_args = mock_logger.log_send.call_args[1]
                    assert call_args["status"] == "failed"
                    assert call_args["error"] == "Rate limit exceeded"

    @pytest.mark.asyncio
    async def test_send_send_failed_status_allowed(self):
        """send_failed 상태도 재전송 가능"""
        from scripts.gateway.adapters.base import SendResult
        from scripts.intelligence.cli import cmd_drafts_send

        mock_storage = AsyncMock()
        mock_storage.get_draft.return_value = {
            "id": 1,
            "status": "send_failed",  # 이전 전송 실패
            "source_channel": "slack",
            "sender_id": "U123",
            "draft_text": "Retry message",
        }

        mock_adapter = AsyncMock()
        mock_adapter.connect.return_value = True
        mock_adapter.send.return_value = SendResult(
            success=True,
            message_id="ts789",
            sent_at=datetime.now(),
        )

        args = MagicMock(id="1", dry_run=False, force=True)

        with patch("scripts.intelligence.cli.get_storage", return_value=mock_storage):
            with patch("scripts.intelligence.cli._create_adapter", return_value=mock_adapter):
                with patch("scripts.intelligence.send_log.SendLogger"):
                    await cmd_drafts_send(args)

                    # 정상 전송 확인
                    mock_storage.update_draft_sent.assert_called_once()


class TestCreateAdapter:
    """_create_adapter 함수 테스트 (실제 어댑터는 mock)"""

    def test_create_slack_adapter(self):
        """Slack 어댑터 생성"""
        from scripts.gateway.adapters.slack import SlackAdapter
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _create_adapter

        with patch("scripts.intelligence.cli.Path.exists", return_value=True):
            with patch("scripts.intelligence.cli.Path.read_text", return_value="{}"):
                adapter = _create_adapter(ChannelType.SLACK)
                assert isinstance(adapter, SlackAdapter)

    def test_create_email_adapter(self):
        """Email 어댑터 생성"""
        from scripts.gateway.adapters.gmail import GmailAdapter
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _create_adapter

        with patch("scripts.intelligence.cli.Path.exists", return_value=True):
            with patch("scripts.intelligence.cli.Path.read_text", return_value="{}"):
                adapter = _create_adapter(ChannelType.EMAIL)
                assert isinstance(adapter, GmailAdapter)

    def test_create_adapter_unsupported_raises_error(self):
        """지원하지 않는 채널 타입은 에러"""
        from scripts.gateway.models import ChannelType
        from scripts.intelligence.cli import _create_adapter

        with pytest.raises(ValueError, match="지원하지 않는 채널"):
            _create_adapter(ChannelType.UNKNOWN)


class TestStorageMethods:
    """IntelligenceStorage의 전송 관련 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_update_draft_sent(self, tmp_path):
        """update_draft_sent 메서드 동작 확인"""
        from scripts.intelligence.context_store import IntelligenceStorage

        db_path = tmp_path / "test.db"
        storage = IntelligenceStorage(db_path=db_path)
        await storage.connect()

        try:
            # Draft 생성
            draft_id = await storage.save_draft({
                "source_channel": "slack",
                "sender_id": "U123",
                "draft_text": "Test",
                "status": "approved",
            })

            # 전송 성공 기록
            success = await storage.update_draft_sent(draft_id, "ts123")
            assert success is True

            # 상태 확인
            draft = await storage.get_draft(draft_id)
            assert draft["status"] == "sent"
            assert draft["sent_at"] is not None

        finally:
            await storage.close()

    @pytest.mark.asyncio
    async def test_update_draft_send_failed(self, tmp_path):
        """update_draft_send_failed 메서드 동작 확인"""
        from scripts.intelligence.context_store import IntelligenceStorage

        db_path = tmp_path / "test.db"
        storage = IntelligenceStorage(db_path=db_path)
        await storage.connect()

        try:
            # Draft 생성
            draft_id = await storage.save_draft({
                "source_channel": "slack",
                "sender_id": "U123",
                "draft_text": "Test",
                "status": "approved",
            })

            # 전송 실패 기록
            success = await storage.update_draft_send_failed(draft_id, "Network error")
            assert success is True

            # 상태 확인
            draft = await storage.get_draft(draft_id)
            assert draft["status"] == "send_failed"
            assert draft["send_error"] == "Network error"

        finally:
            await storage.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
