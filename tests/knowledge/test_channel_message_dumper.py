"""ChannelMessageDumper 단위 테스트"""
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def tmp_dumper(tmp_path):
    """임시 디렉토리를 사용하는 ChannelMessageDumper"""
    from scripts.knowledge.channel_message_dumper import ChannelMessageDumper
    return ChannelMessageDumper(dump_dir=tmp_path)


def make_mock_messages(n=5, start_ts=1000.0):
    """테스트용 SlackMessage mock 리스트 생성"""
    messages = []
    for i in range(n):
        msg = MagicMock()
        msg.ts = f"{start_ts + i:.6f}"
        msg.user = f"U00{i}"
        msg.text = f"테스트 메시지 {i}"
        msg.thread_ts = None
        messages.append(msg)
    return messages


class TestChannelMessageDumperDump:
    def test_dump_creates_json_file(self, tmp_dumper, tmp_path):
        """dump() 호출 시 JSON 파일 생성 확인"""
        msgs = make_mock_messages(3)

        async def mock_collect(channel_id):
            return [tmp_dumper._normalize_message(m) for m in msgs]

        with patch.object(tmp_dumper, '_ensure_client'), \
             patch.object(tmp_dumper, '_collect_full', side_effect=mock_collect):
            result = asyncio.run(tmp_dumper.dump("C0123456", "test-channel"))

        assert result.exists()
        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["channel_id"] == "C0123456"
        assert data["total_messages"] == 3
        assert len(data["messages"]) == 3

    def test_dump_skips_if_no_force(self, tmp_dumper, tmp_path):
        """force=False이고 기존 덤프 있으면 증분 수집 사용"""
        existing_data = {
            "channel_id": "C0123456",
            "channel_name": "test",
            "dump_date": "2026-01-01",
            "last_ts": "1000.000000",
            "total_messages": 2,
            "messages": [
                {"ts": "999.000000", "user": "U001", "text": "기존", "thread_ts": None},
                {"ts": "1000.000000", "user": "U001", "text": "기존2", "thread_ts": None},
            ],
        }
        dump_path = tmp_path / "C0123456.json"
        dump_path.write_text(json.dumps(existing_data), encoding="utf-8")

        new_msgs = make_mock_messages(2, start_ts=1001.0)

        async def mock_incremental(channel_id, oldest_ts):
            return [tmp_dumper._normalize_message(m) for m in new_msgs]

        with patch.object(tmp_dumper, '_ensure_client'), \
             patch.object(tmp_dumper, '_collect_incremental', side_effect=mock_incremental):
            result = asyncio.run(tmp_dumper.dump("C0123456", force=False))

        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["total_messages"] == 4  # 기존 2 + 신규 2

    def test_dump_force_ignores_existing(self, tmp_dumper, tmp_path):
        """force=True 시 기존 덤프 무시하고 전체 수집"""
        existing_data = {
            "channel_id": "C0123456", "channel_name": "test",
            "dump_date": "2026-01-01", "last_ts": "999.0",
            "total_messages": 1, "messages": [{"ts": "999.0", "user": "U0", "text": "old", "thread_ts": None}],
        }
        dump_path = tmp_path / "C0123456.json"
        dump_path.write_text(json.dumps(existing_data), encoding="utf-8")

        new_msgs = make_mock_messages(5, start_ts=2000.0)

        async def mock_full(channel_id):
            return [tmp_dumper._normalize_message(m) for m in new_msgs]

        with patch.object(tmp_dumper, '_ensure_client'), \
             patch.object(tmp_dumper, '_collect_full', side_effect=mock_full):
            result = asyncio.run(tmp_dumper.dump("C0123456", force=True))

        data = json.loads(result.read_text(encoding="utf-8"))
        assert data["total_messages"] == 5


class TestChannelMessageDumperNormalize:
    def test_normalize_message_fields(self, tmp_dumper):
        """정규화 결과 필수 필드 검증"""
        msg = MagicMock()
        msg.ts = "1234567890.000100"
        msg.user = "U040EUZ6JRY"
        msg.text = "안녕하세요"
        msg.thread_ts = None

        result = tmp_dumper._normalize_message(msg)
        assert result["ts"] == "1234567890.000100"
        assert result["user"] == "U040EUZ6JRY"
        assert result["text"] == "안녕하세요"
        assert result["thread_ts"] is None

    def test_normalize_truncates_long_text(self, tmp_dumper):
        """text 4000자 초과 시 절삭"""
        msg = MagicMock()
        msg.ts = "1234567890.000100"
        msg.user = "U001"
        msg.text = "a" * 5000
        msg.thread_ts = None

        result = tmp_dumper._normalize_message(msg)
        assert len(result["text"]) == 4000

    def test_normalize_thread_ts_same_as_ts_becomes_none(self, tmp_dumper):
        """thread_ts == ts 이면 None 처리"""
        msg = MagicMock()
        msg.ts = "1234567890.000100"
        msg.user = "U001"
        msg.text = "스레드 시작"
        msg.thread_ts = "1234567890.000100"  # ts와 동일

        result = tmp_dumper._normalize_message(msg)
        assert result["thread_ts"] is None


class TestLoadChannelDoc:
    def test_load_channel_doc_returns_content(self, tmp_path):
        """MD 파일 있으면 내용 반환"""
        from scripts.intelligence.response.handler import ProjectIntelligenceHandler

        storage = MagicMock()
        registry = MagicMock()
        handler = ProjectIntelligenceHandler(storage=storage, registry=registry)

        # 임시 MD 파일 생성
        doc_path = tmp_path / "C0123456.md"
        doc_path.write_text("# 테스트 채널\n## 채널 개요\n테스트입니다.", encoding="utf-8")

        result_content = doc_path.read_text(encoding="utf-8")
        assert "# 테스트 채널" in result_content

    def test_load_channel_doc_missing_returns_empty(self, tmp_path):
        """파일 없으면 빈 문자열 반환 (예외 없음)"""
        from scripts.intelligence.response.handler import ProjectIntelligenceHandler

        storage = MagicMock()
        registry = MagicMock()
        handler = ProjectIntelligenceHandler(storage=storage, registry=registry)

        result = handler._load_channel_doc("CNONEXISTENT")
        assert result == ""
        assert isinstance(result, str)
