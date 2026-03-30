"""CLI approve/reject --reason 통합 테스트"""
import argparse
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path("C:/claude/secretary")))


@pytest_asyncio.fixture
async def storage(tmp_path):
    from scripts.intelligence.context_store import IntelligenceStorage
    db_path = tmp_path / "test_intelligence.db"
    s = IntelligenceStorage(db_path)
    await s.connect()
    yield s
    await s.close()


def _make_noop_storage(storage):
    """close()를 no-op으로 교체한 storage 반환 (테스트 fixture가 닫으므로)"""
    async def _noop_close():
        pass
    storage.close = _noop_close
    return storage


@pytest.mark.asyncio
async def test_approve_stores_feedback(storage, tmp_path):
    """approve 명령 실행 시 DB에 feedback 생성"""
    draft_id = await storage.save_draft({"source_channel": "slack"})

    from scripts.intelligence.cli import cmd_drafts_approve

    args = argparse.Namespace(
        id=str(draft_id),
        note="",
        reason="부정확함",
        modification=None,
    )

    mock_storage = _make_noop_storage(storage)
    mock_get_storage = AsyncMock(return_value=mock_storage)

    with patch("scripts.intelligence.cli.get_storage", mock_get_storage):
        await cmd_drafts_approve(args)

    from scripts.intelligence.feedback_store import FeedbackStore
    fb_store = FeedbackStore(storage)
    fb = await fb_store.get_feedback_by_draft(draft_id)
    assert fb is not None
    assert fb["decision"] == "approved"
    assert fb["reason"] == "부정확함"


@pytest.mark.asyncio
async def test_reject_with_reason_stores_feedback(storage):
    """reject --reason 실행 시 reason 저장"""
    draft_id = await storage.save_draft({"source_channel": "slack"})

    from scripts.intelligence.cli import cmd_drafts_reject

    args = argparse.Namespace(
        id=str(draft_id),
        note="",
        reason="어조부적절",
        modification="존댓말로 수정 필요",
    )

    mock_storage = _make_noop_storage(storage)
    mock_get_storage = AsyncMock(return_value=mock_storage)

    with patch("scripts.intelligence.cli.get_storage", mock_get_storage):
        await cmd_drafts_reject(args)

    from scripts.intelligence.feedback_store import FeedbackStore
    fb_store = FeedbackStore(storage)
    fb = await fb_store.get_feedback_by_draft(draft_id)
    assert fb["decision"] == "rejected"
    assert fb["reason"] == "어조부적절"
    assert fb["modification_summary"] == "존댓말로 수정 필요"


@pytest.mark.asyncio
async def test_approve_without_reason_allowed(storage):
    """reason 없이 approve 허용"""
    draft_id = await storage.save_draft({"source_channel": "slack"})

    from scripts.intelligence.cli import cmd_drafts_approve

    args = argparse.Namespace(id=str(draft_id), note="", reason=None, modification=None)

    mock_storage = _make_noop_storage(storage)
    mock_get_storage = AsyncMock(return_value=mock_storage)

    with patch("scripts.intelligence.cli.get_storage", mock_get_storage):
        await cmd_drafts_approve(args)  # 예외 없이 완료

    from scripts.intelligence.feedback_store import FeedbackStore
    fb_store = FeedbackStore(storage)
    fb = await fb_store.get_feedback_by_draft(draft_id)
    assert fb["reason"] is None
