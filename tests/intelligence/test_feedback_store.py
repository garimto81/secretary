"""FeedbackStore 단위 테스트"""

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def storage(tmp_path):
    from scripts.intelligence.context_store import IntelligenceStorage
    db_path = tmp_path / "test_intelligence.db"
    s = IntelligenceStorage(db_path)
    await s.connect()
    yield s
    await s.close()

@pytest_asyncio.fixture
async def fb_store(storage):
    from scripts.intelligence.feedback_store import FeedbackStore
    return FeedbackStore(storage)

@pytest.mark.asyncio
async def test_save_feedback_approved(fb_store, storage):
    """승인 피드백 저장 및 조회"""
    draft_id = await storage.save_draft({"source_channel": "slack"})
    fb_id = await fb_store.save_feedback(draft_id=draft_id, decision="approved")
    assert fb_id > 0

    fb = await fb_store.get_feedback_by_draft(draft_id)
    assert fb is not None
    assert fb["decision"] == "approved"
    assert fb["draft_id"] == draft_id
    assert fb["reason"] is None
    assert fb["modification_summary"] is None
    assert fb["feedback_quality_score"] == 5

@pytest.mark.asyncio
async def test_save_feedback_rejected_with_reason(fb_store, storage):
    """거부+사유+수정내용 저장"""
    draft_id = await storage.save_draft({"source_channel": "slack"})
    fb_id = await fb_store.save_feedback(
        draft_id=draft_id,
        decision="rejected",
        reason="어조부적절",
        modification_summary="더 공손하게 수정 필요",
    )
    assert fb_id > 0

    fb = await fb_store.get_feedback_by_draft(draft_id)
    assert fb["decision"] == "rejected"
    assert fb["reason"] == "어조부적절"
    assert fb["modification_summary"] == "더 공손하게 수정 필요"

@pytest.mark.asyncio
async def test_invalid_decision_raises(fb_store, storage):
    """잘못된 decision 값 → 예외 발생"""
    draft_id = await storage.save_draft({"source_channel": "slack"})
    with pytest.raises(Exception):
        await fb_store.save_feedback(draft_id=draft_id, decision="invalid_value")

@pytest.mark.asyncio
async def test_duplicate_draft_id_raises(fb_store, storage):
    """동일 draft_id로 중복 저장 → 예외 발생 (UNIQUE 위반)"""
    draft_id = await storage.save_draft({"source_channel": "slack"})
    await fb_store.save_feedback(draft_id=draft_id, decision="approved")
    with pytest.raises(Exception):
        await fb_store.save_feedback(draft_id=draft_id, decision="rejected")

@pytest.mark.asyncio
async def test_cascade_delete(fb_store, storage):
    """draft 삭제 시 feedback 자동 삭제 (ON DELETE CASCADE)"""
    draft_id = await storage.save_draft({"source_channel": "slack"})
    await fb_store.save_feedback(draft_id=draft_id, decision="approved")

    # feedback 존재 확인
    fb = await fb_store.get_feedback_by_draft(draft_id)
    assert fb is not None

    # draft 삭제
    await storage._connection.execute("DELETE FROM draft_responses WHERE id = ?", (draft_id,))
    await storage._connection.commit()

    # feedback 자동 삭제 확인
    fb_after = await fb_store.get_feedback_by_draft(draft_id)
    assert fb_after is None

@pytest.mark.asyncio
async def test_list_feedback_filter_by_decision(fb_store, storage):
    """decision 필터로 목록 조회"""
    for _ in range(2):
        d_id = await storage.save_draft({"source_channel": "slack"})
        await fb_store.save_feedback(draft_id=d_id, decision="rejected", reason="부정확함")
    d_id = await storage.save_draft({"source_channel": "slack"})
    await fb_store.save_feedback(draft_id=d_id, decision="approved")

    rejected = await fb_store.list_feedback(decision="rejected")
    assert len(rejected) == 2
    assert all(r["decision"] == "rejected" for r in rejected)

    all_fb = await fb_store.list_feedback()
    assert len(all_fb) == 3

@pytest.mark.asyncio
async def test_get_feedback_by_draft_not_found(fb_store):
    """존재하지 않는 draft_id → None 반환"""
    result = await fb_store.get_feedback_by_draft(99999)
    assert result is None
