"""
DraftStore 테스트

파일 저장, DB 저장, Toast 알림 검증.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.response.draft_store import DraftStore


class TestDraftStore:
    """DraftStore 테스트"""

    @pytest.fixture
    def mock_storage(self):
        storage = AsyncMock()
        storage.save_draft = AsyncMock(return_value=42)
        return storage

    @pytest.fixture
    def store(self, mock_storage, tmp_path):
        return DraftStore(mock_storage, drafts_dir=tmp_path)

    # ==========================================
    # save() 테스트
    # ==========================================

    @pytest.mark.asyncio
    async def test_save_creates_file(self, store, tmp_path):
        """draft 파일이 생성되는지 확인"""
        with patch.object(store, '_send_toast'):
            result = await store.save(
                project_id="secretary",
                source_channel="slack",
                source_message_id="msg-001",
                sender_id="U12345",
                sender_name="TestUser",
                original_text="원본 메시지",
                draft_text="응답 초안입니다",
                match_confidence=0.85,
                match_tier="channel",
            )

        assert "draft_id" in result
        assert result["draft_id"] == 42

        # 파일 존재 확인
        draft_files = list(tmp_path.glob("secretary_slack_*.md"))
        assert len(draft_files) == 1

    @pytest.mark.asyncio
    async def test_save_file_content(self, store, tmp_path):
        """draft 파일 내용 확인"""
        with patch.object(store, '_send_toast'):
            await store.save(
                project_id="wsoptv",
                source_channel="gmail",
                source_message_id="msg-002",
                sender_id="U99999",
                sender_name="Admin",
                original_text="방송 일정 확인 부탁",
                draft_text="확인하겠습니다",
                match_confidence=0.7,
                match_tier="keyword",
            )

        draft_files = list(tmp_path.glob("wsoptv_gmail_*.md"))
        content = draft_files[0].read_text(encoding="utf-8")

        assert "Project: wsoptv" in content
        assert "Channel: gmail" in content
        assert "Sender: Admin" in content
        assert "keyword" in content
        assert "방송 일정 확인 부탁" in content
        assert "확인하겠습니다" in content

    @pytest.mark.asyncio
    async def test_save_calls_storage(self, store, mock_storage):
        """DB에 draft가 저장되는지 확인"""
        with patch.object(store, '_send_toast'):
            await store.save(
                project_id="secretary",
                source_channel="slack",
                source_message_id="msg-003",
                sender_id="U12345",
                sender_name="User",
                original_text="테스트",
                draft_text="응답",
                match_confidence=0.9,
                match_tier="channel",
            )

        mock_storage.save_draft.assert_called_once()
        saved = mock_storage.save_draft.call_args[0][0]
        assert saved["project_id"] == "secretary"
        assert saved["source_channel"] == "slack"
        assert saved["status"] == "pending"
        assert saved["match_status"] == "matched"

    @pytest.mark.asyncio
    async def test_save_truncates_original_text(self, store, mock_storage):
        """original_text가 4000자로 절삭되는지 확인"""
        long_text = "A" * 5000

        with patch.object(store, '_send_toast'):
            await store.save(
                project_id="test",
                source_channel="slack",
                source_message_id="msg-004",
                sender_id="U12345",
                sender_name="User",
                original_text=long_text,
                draft_text="응답",
                match_confidence=0.5,
                match_tier="keyword",
            )

        saved = mock_storage.save_draft.call_args[0][0]
        assert len(saved["original_text"]) == 4000

    # ==========================================
    # _format_draft_file() 테스트
    # ==========================================

    def test_format_draft_file(self, store):
        """draft 파일 포맷 확인"""
        content = store._format_draft_file(
            project_id="secretary",
            source_channel="slack",
            sender_name="TestUser",
            original_text="원본",
            draft_text="초안",
            match_confidence=0.85,
            match_tier="channel",
        )

        assert "# Draft Response" in content
        assert "Project: secretary" in content
        assert "## Original Message" in content
        assert "## Draft Response" in content

    def test_format_draft_file_truncates_original(self, store):
        """원본 메시지 2000자 절삭"""
        long_text = "B" * 3000
        content = store._format_draft_file(
            project_id="test",
            source_channel="slack",
            sender_name="User",
            original_text=long_text,
            draft_text="draft",
            match_confidence=0.5,
            match_tier="keyword",
        )
        # 2000자 절삭 확인
        assert content.count("B") == 2000

    # ==========================================
    # _send_toast() 테스트
    # ==========================================

    def test_send_toast_non_windows(self, store):
        """Windows가 아닌 환경에서는 무시"""
        with patch('sys.platform', 'linux'):
            # 예외 없이 종료
            store._send_toast("test", "User", "slack")

    def test_send_toast_import_error(self, store):
        """winotify 미설치 시 무시"""
        with patch('sys.platform', 'win32'):
            with patch.dict('sys.modules', {'winotify': None}):
                # ImportError가 발생해도 무시
                store._send_toast("test", "User", "slack")

    # ==========================================
    # 파일 경로 생성 테스트
    # ==========================================

    @pytest.mark.asyncio
    async def test_safe_project_id_in_filename(self, store):
        """project_id에 특수문자가 있을 때 안전한 파일명"""
        with patch.object(store, '_send_toast'):
            result = await store.save(
                project_id="my/project\\name",
                source_channel="slack",
                source_message_id="msg-005",
                sender_id="U12345",
                sender_name="User",
                original_text="test",
                draft_text="draft",
                match_confidence=0.5,
                match_tier="keyword",
            )

        # 파일명에 /나 \가 없어야 함
        draft_file = result["draft_file"]
        filename = Path(draft_file).name
        assert "/" not in filename
        assert "\\" not in filename
