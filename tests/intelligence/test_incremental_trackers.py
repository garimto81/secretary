"""
IncrementalTracker 초기/증분 수집 분기 테스트

SlackTracker: 최초 수집 시 cursor 기반 무제한 페이지네이션
GmailTracker: 최초 수집 시 날짜 필터 없이 전체 수집
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.intelligence.incremental.trackers.gmail_tracker import GmailTracker
from scripts.intelligence.incremental.trackers.slack_tracker import SlackTracker

# ==========================================
# Fixtures
# ==========================================

@pytest.fixture
def mock_storage():
    storage = AsyncMock()
    storage.save_context_entry = AsyncMock()
    return storage


@pytest.fixture
def mock_state_manager():
    sm = AsyncMock()
    sm.get_slack_last_ts = AsyncMock(return_value=None)
    sm.save_slack_last_ts = AsyncMock()
    sm.get_gmail_history_id = AsyncMock(return_value=None)
    sm.save_gmail_history_id = AsyncMock()
    return sm


def make_slack_msg(ts: str, text: str = "테스트 메시지", files: list | None = None):
    """Mock SlackMessage 생성 헬퍼"""
    msg = MagicMock()
    msg.ts = ts
    msg.text = text
    msg.user = "U12345"
    msg.thread_ts = None
    msg.files = files or []
    return msg


# ==========================================
# SlackTracker 최초 수집 테스트
# ==========================================

class TestSlackTrackerInitial:
    """최초 수집 (last_ts=None) — cursor 기반 무제한 페이지네이션"""

    @pytest.mark.asyncio
    async def test_initial_fetch_uses_cursor_pagination(self, mock_storage, mock_state_manager):
        """최초 수집 시 get_history_with_cursor 호출 확인"""
        tracker = SlackTracker(mock_storage, mock_state_manager)

        # 2페이지 시뮬레이션
        page1_msgs = [make_slack_msg(f"1700{i:06d}.000000") for i in range(100, 0, -1)]
        page2_msgs = [make_slack_msg(f"1699{i:06d}.000000") for i in range(100, 0, -1)]

        mock_client = MagicMock()
        mock_client.get_history_with_cursor = MagicMock(side_effect=[
            (page1_msgs, "cursor_abc"),   # 1페이지: next_cursor 있음
            (page2_msgs, None),            # 2페이지: next_cursor 없음 (종료)
        ])
        mock_client.get_replies = MagicMock(return_value=[])

        tracker._client = mock_client

        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                count = await tracker._fetch_channel("proj1", "C12345")

        # 2페이지 × 100건 = 200건 저장 확인
        assert mock_client.get_history_with_cursor.call_count == 2
        assert count == 200

        # 첫 번째 호출: cursor=None
        first_call = mock_client.get_history_with_cursor.call_args_list[0]
        assert first_call[0][3] is None  # cursor=None

        # 두 번째 호출: cursor="cursor_abc"
        second_call = mock_client.get_history_with_cursor.call_args_list[1]
        assert second_call[0][3] == "cursor_abc"

    @pytest.mark.asyncio
    async def test_initial_fetch_no_cap(self, mock_storage, mock_state_manager):
        """최초 수집 시 500건 캡 없음 — 600건 수집 가능"""
        tracker = SlackTracker(mock_storage, mock_state_manager)

        # 6페이지 × 100건 = 600건
        def side_effect(channel, limit, oldest, cursor):
            if cursor is None:
                return ([make_slack_msg(f"170001{i:04d}.0") for i in range(100)], "c1")
            elif cursor == "c1":
                return ([make_slack_msg(f"170002{i:04d}.0") for i in range(100)], "c2")
            elif cursor == "c2":
                return ([make_slack_msg(f"170003{i:04d}.0") for i in range(100)], "c3")
            elif cursor == "c3":
                return ([make_slack_msg(f"170004{i:04d}.0") for i in range(100)], "c4")
            elif cursor == "c4":
                return ([make_slack_msg(f"170005{i:04d}.0") for i in range(100)], "c5")
            else:
                return ([make_slack_msg(f"170006{i:04d}.0") for i in range(100)], None)

        mock_client = MagicMock()
        mock_client.get_history_with_cursor = MagicMock(side_effect=side_effect)
        mock_client.get_replies = MagicMock(return_value=[])
        tracker._client = mock_client

        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                count = await tracker._fetch_channel("proj1", "C12345")

        assert count == 600  # 500건 캡 없이 전체 수집
        assert mock_client.get_history_with_cursor.call_count == 6

    @pytest.mark.asyncio
    async def test_initial_fetch_collects_file_attachments(self, mock_storage, mock_state_manager):
        """최초 수집 시 파일 첨부 수집 확인"""
        tracker = SlackTracker(mock_storage, mock_state_manager)

        file_info = {"id": "F12345", "name": "report.pdf", "filetype": "pdf", "title": "월간 보고서"}
        msg_with_file = make_slack_msg("1700000001.000000", files=[file_info])

        mock_client = MagicMock()
        mock_client.get_history_with_cursor = MagicMock(return_value=([msg_with_file], None))
        mock_client.get_replies = MagicMock(return_value=[])
        tracker._client = mock_client

        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                count = await tracker._fetch_channel("proj1", "C12345")

        # 메시지 1건 + 파일 1건 = 2건 저장
        assert count == 2
        saved_entries = [c[0][0] for c in mock_storage.save_context_entry.call_args_list]
        entry_types = [e["entry_type"] for e in saved_entries]
        assert "message" in entry_types
        assert "file" in entry_types

        file_entry = next(e for e in saved_entries if e["entry_type"] == "file")
        assert "report.pdf" in file_entry["content"]
        assert file_entry["metadata"]["file_id"] == "F12345"


# ==========================================
# SlackTracker 증분 수집 테스트
# ==========================================

class TestSlackTrackerIncremental:
    """증분 수집 (last_ts 있음) — 기존 500건 캡 유지"""

    @pytest.mark.asyncio
    async def test_incremental_uses_get_history(self, mock_storage, mock_state_manager):
        """증분 수집 시 get_history (oldest 기반) 사용 확인"""
        mock_state_manager.get_slack_last_ts = AsyncMock(return_value="1700000000.000000")
        tracker = SlackTracker(mock_storage, mock_state_manager)

        new_msgs = [make_slack_msg("1700000100.000000"), make_slack_msg("1700000200.000000")]

        mock_client = MagicMock()
        mock_client.get_history = MagicMock(return_value=new_msgs)
        mock_client.get_replies = MagicMock(return_value=[])
        tracker._client = mock_client

        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            count = await tracker._fetch_channel("proj1", "C12345")

        # get_history (증분) 사용 확인
        assert mock_client.get_history.call_count >= 1
        assert not hasattr(mock_client, 'get_history_with_cursor') or \
               mock_client.get_history_with_cursor.call_count == 0
        assert count == 2

    @pytest.mark.asyncio
    async def test_incremental_no_file_collection(self, mock_storage, mock_state_manager):
        """증분 수집 시 파일 수집 안함 (is_initial=False)"""
        mock_state_manager.get_slack_last_ts = AsyncMock(return_value="1700000000.000000")
        tracker = SlackTracker(mock_storage, mock_state_manager)

        file_info = {"id": "F99999", "name": "doc.pdf"}
        msg_with_file = make_slack_msg("1700000100.000000", files=[file_info])

        mock_client = MagicMock()
        mock_client.get_history = MagicMock(return_value=[msg_with_file])
        mock_client.get_replies = MagicMock(return_value=[])
        tracker._client = mock_client

        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            count = await tracker._fetch_channel("proj1", "C12345")

        # 메시지만 저장, 파일 entry 없음
        assert count == 1
        saved_entries = [c[0][0] for c in mock_storage.save_context_entry.call_args_list]
        assert all(e["entry_type"] != "file" for e in saved_entries)


# ==========================================
# GmailTracker 최초 수집 테스트
# ==========================================

class TestGmailTrackerInitial:
    """최초 수집 (history_id=None) — 날짜 필터 없음, limit=500"""

    @pytest.mark.asyncio
    async def test_initial_fetch_no_date_filter(self, mock_storage, mock_state_manager):
        """최초 수집 시 날짜 필터(after:) 없는 query 사용 확인"""
        tracker = GmailTracker(mock_storage, mock_state_manager)

        mock_email = MagicMock()
        mock_email.id = "email001"
        mock_email.subject = "테스트 메일"
        mock_email.body_text = "메일 본문"
        mock_email.snippet = ""
        mock_email.sender = "test@example.com"
        mock_email.to = "me@example.com"
        mock_email.thread_id = "thread001"
        mock_email.date = None
        mock_email.is_unread = True

        captured_queries = []

        def mock_list_emails(query, limit):
            captured_queries.append((query, limit))
            return [mock_email]

        mock_client = MagicMock()
        mock_client.list_emails = MagicMock(side_effect=mock_list_emails)
        mock_client.get_profile = MagicMock(return_value={"historyId": "12345"})
        tracker._client = mock_client

        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            count = await tracker.fetch_new("proj1", ["label:project-x"])

        assert count == 1
        assert len(captured_queries) == 1

        query_used, limit_used = captured_queries[0]
        # 날짜 필터 없음 확인
        assert "after:" not in query_used
        # limit 500 확인
        assert limit_used == 500

    @pytest.mark.asyncio
    async def test_incremental_has_date_filter(self, mock_storage, mock_state_manager):
        """증분 수집 시 7일 날짜 필터 + 20건 제한 확인"""
        mock_state_manager.get_gmail_history_id = AsyncMock(return_value=None)
        tracker = GmailTracker(mock_storage, mock_state_manager)

        captured_queries = []

        def mock_list_emails(query, limit):
            captured_queries.append((query, limit))
            return []

        mock_client = MagicMock()
        mock_client.list_emails = MagicMock(side_effect=mock_list_emails)
        mock_client.get_profile = MagicMock(return_value={"historyId": "99999"})
        tracker._client = mock_client

        # initial=False 직접 호출
        with patch("asyncio.to_thread", side_effect=lambda fn, *args, **kwargs: fn(*args, **kwargs)):
            await tracker._fetch_via_list("proj1", ["label:inbox"], initial=False)

        assert len(captured_queries) == 1
        query_used, limit_used = captured_queries[0]
        # 날짜 필터 있음
        assert "after:" in query_used
        # limit 20
        assert limit_used == 20
