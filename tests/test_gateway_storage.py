"""
Gateway Storage 테스트

통합 스토리지 기능 검증

Note:
    모든 테스트는 models.py의 NormalizedMessage를 사용합니다.
    storage.py는 더 이상 자체 NormalizedMessage를 정의하지 않습니다.
"""

import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from scripts.gateway.storage import UnifiedStorage
from scripts.gateway.models import NormalizedMessage, ChannelType, MessageType, Priority


@pytest.fixture
def temp_storage(tmp_path):
    """임시 스토리지 fixture"""
    db_path = tmp_path / "test_gateway.db"
    storage = UnifiedStorage(db_path=db_path)
    return storage


@pytest.fixture
def sample_message():
    """샘플 메시지 fixture (models.NormalizedMessage 사용)"""
    return NormalizedMessage(
        id="test_msg_001",
        channel=ChannelType.KAKAO,
        channel_id="room_123",
        sender_id="user_456",
        sender_name="테스터",
        text="테스트 메시지입니다",
        message_type=MessageType.TEXT,
        timestamp=datetime.now(),
        is_group=True,
        is_mention=False,
        priority=Priority.NORMAL,
        has_action=False
    )


@pytest.mark.asyncio
async def test_save_and_get_message(temp_storage, sample_message):
    """메시지 저장 및 조회 테스트"""
    async with temp_storage:
        # 저장
        msg_id = await temp_storage.save_message(sample_message)
        assert msg_id == sample_message.id

        # 조회
        retrieved = await temp_storage.get_message(msg_id)
        assert retrieved is not None
        assert retrieved.id == sample_message.id
        assert retrieved.channel == sample_message.channel  # ChannelType enum 비교
        assert retrieved.text == sample_message.text
        assert retrieved.sender_name == sample_message.sender_name


@pytest.mark.asyncio
async def test_get_recent_messages(temp_storage):
    """최근 메시지 조회 테스트"""
    async with temp_storage:
        # 여러 메시지 저장
        now = datetime.now()
        messages = [
            NormalizedMessage(
                id=f"msg_{i}",
                channel=ChannelType.KAKAO if i % 2 == 0 else ChannelType.EMAIL,
                channel_id="room_1",
                sender_id=f"user_{i}",
                sender_name=f"User {i}",
                text=f"Message {i}",
                timestamp=now - timedelta(hours=i)
            )
            for i in range(10)
        ]

        for msg in messages:
            await temp_storage.save_message(msg)

        # 전체 조회
        recent_all = await temp_storage.get_recent_messages(limit=5)
        assert len(recent_all) == 5
        assert recent_all[0].id == "msg_0"  # 최신순

        # 채널 필터 (DB에는 문자열로 저장됨)
        recent_kakao = await temp_storage.get_recent_messages(channel="kakao", limit=10)
        assert all(msg.channel == ChannelType.KAKAO for msg in recent_kakao)
        assert len(recent_kakao) == 5  # 0, 2, 4, 6, 8

        # 시간 필터
        since = now - timedelta(hours=5)
        recent_since = await temp_storage.get_recent_messages(since=since, limit=10)
        assert len(recent_since) == 6  # 0~5


@pytest.mark.asyncio
async def test_get_unprocessed_messages(temp_storage, sample_message):
    """미처리 메시지 조회 테스트"""
    async with temp_storage:
        # 미처리 메시지 저장
        await temp_storage.save_message(sample_message)

        # 처리 완료 메시지 저장 후 mark_processed로 표시
        processed_msg = NormalizedMessage(
            id="msg_processed",
            channel=ChannelType.EMAIL,
            channel_id="inbox",
            sender_id="user_999",
            sender_name="Processed User",
            text="Processed message",
            timestamp=datetime.now(),
        )
        await temp_storage.save_message(processed_msg)
        await temp_storage.mark_processed("msg_processed")

        # 미처리 메시지만 조회
        unprocessed = await temp_storage.get_unprocessed_messages()
        assert len(unprocessed) == 1
        assert unprocessed[0].id == sample_message.id


@pytest.mark.asyncio
async def test_mark_processed(temp_storage, sample_message):
    """메시지 처리 완료 표시 테스트"""
    async with temp_storage:
        await temp_storage.save_message(sample_message)

        # 처리 전 확인
        unprocessed_before = await temp_storage.get_unprocessed_messages()
        assert len(unprocessed_before) == 1

        # 처리 완료 표시
        await temp_storage.mark_processed(sample_message.id)

        # 처리 후 확인
        unprocessed_after = await temp_storage.get_unprocessed_messages()
        assert len(unprocessed_after) == 0

        # Note: models.NormalizedMessage에는 processed_at 필드가 없음
        # DB에서 조회 시 processed_at는 저장되지만 모델에는 없으므로 삭제된 메시지만 확인


@pytest.mark.asyncio
async def test_get_stats(temp_storage):
    """통계 조회 테스트"""
    async with temp_storage:
        # 여러 채널의 메시지 저장
        kakao_messages = [
            NormalizedMessage(
                id=f"kakao_{i}",
                channel=ChannelType.KAKAO,
                channel_id="room_1",
                sender_id=f"user_{i}",
                sender_name=f"Kakao User {i}",
                text=f"Kakao {i}",
                timestamp=datetime.now()
            )
            for i in range(5)
        ]

        gmail_messages = [
            NormalizedMessage(
                id=f"gmail_{i}",
                channel=ChannelType.EMAIL,
                channel_id="inbox",
                sender_id=f"sender_{i}",
                sender_name=f"Gmail User {i}",
                text=f"Gmail {i}",
                timestamp=datetime.now(),
            )
            for i in range(3)
        ]

        for msg in kakao_messages + gmail_messages:
            await temp_storage.save_message(msg)

        # gmail 0, 1을 처리 완료로 표시
        await temp_storage.mark_processed("gmail_0")
        await temp_storage.mark_processed("gmail_1")

        # 통계 조회
        stats = await temp_storage.get_stats()
        assert stats['total_messages'] == 8
        assert stats['by_channel']['kakao'] == 5
        assert stats['by_channel']['email'] == 3
        assert stats['unprocessed'] == 6  # kakao 5개 + gmail 미처리 1개


@pytest.mark.asyncio
async def test_context_manager():
    """Context manager 테스트"""
    db_path = Path("test_context.db")

    async with UnifiedStorage(db_path=db_path) as storage:
        msg = NormalizedMessage(
            id="ctx_test",
            channel=ChannelType.UNKNOWN,
            channel_id="test_ch",
            sender_id="test_user",
            sender_name="Test User",
            text="Context manager test",
            timestamp=datetime.now()
        )
        await storage.save_message(msg)

        retrieved = await storage.get_message("ctx_test")
        assert retrieved is not None

    # DB 파일 정리
    if db_path.exists():
        db_path.unlink()


@pytest.mark.asyncio
async def test_message_with_media(temp_storage):
    """미디어 URL이 있는 메시지 테스트"""
    async with temp_storage:
        msg = NormalizedMessage(
            id="media_msg",
            channel=ChannelType.KAKAO,
            channel_id="room_1",
            sender_id="user_1",
            sender_name="Media User",
            text="사진 보냅니다",
            message_type=MessageType.IMAGE,
            timestamp=datetime.now(),
            media_urls=["https://example.com/photo1.jpg", "https://example.com/photo2.jpg"],
            raw_json='{"extra": "data", "nested": {"key": "value"}}'
        )

        await temp_storage.save_message(msg)
        retrieved = await temp_storage.get_message("media_msg")

        assert retrieved.message_type == MessageType.IMAGE
        assert len(retrieved.media_urls) == 2
        assert retrieved.media_urls[0] == "https://example.com/photo1.jpg"


@pytest.mark.asyncio
async def test_duplicate_insert(temp_storage, sample_message):
    """중복 삽입 테스트 (REPLACE 동작 확인)"""
    async with temp_storage:
        # 첫 번째 저장
        await temp_storage.save_message(sample_message)

        # 같은 ID로 다른 내용 저장
        updated_msg = NormalizedMessage(
            id=sample_message.id,
            channel=sample_message.channel,
            channel_id=sample_message.channel_id,
            sender_id=sample_message.sender_id,
            sender_name=sample_message.sender_name,
            text="업데이트된 메시지",
            timestamp=datetime.now()
        )
        await temp_storage.save_message(updated_msg)

        # 조회 시 업데이트된 내용 확인
        retrieved = await temp_storage.get_message(sample_message.id)
        assert retrieved.text == "업데이트된 메시지"
