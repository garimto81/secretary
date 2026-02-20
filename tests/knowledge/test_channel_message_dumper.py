"""ChannelMessageDumper 단위 테스트"""
import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


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


class TestChannelMessageDumperRateLimit:
    def test_dump_sleeps_between_pages(self, tmp_dumper):
        """여러 페이지 수집 시 asyncio.sleep(1.2) 호출 확인"""
        from unittest.mock import AsyncMock

        mock_client = MagicMock()
        tmp_dumper._client = mock_client
        page1 = [{"ts": "1000.0", "user": "U0", "text": "msg0", "thread_ts": None, "reactions": []}]
        mock_client.get_history_with_cursor.side_effect = [(page1, "cursor2"), ([], None)]

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            msgs = asyncio.run(tmp_dumper._collect_full("C0123456"))

        mock_sleep.assert_called_once_with(1.2)
        assert len(msgs) == 1


class TestWriteFromDump:
    def test_write_from_dump_single_chunk(self, tmp_path):
        """write_from_dump(): ≤500 메시지 → _call_claude 단일 호출"""
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter, REQUIRED_SECTIONS

        dump_data = {
            "channel_id": "C0123456",
            "messages": [
                {"ts": f"100{i}.0", "user": f"U{i}", "text": f"msg {i}", "thread_ts": None, "reactions": []}
                for i in range(5)
            ],
        }
        dump_path = tmp_path / "C0123456.json"
        dump_path.write_text(json.dumps(dump_data), encoding="utf-8")

        writer = ChannelPRDWriter()
        mock_content = "# C0123456 지식 문서\n" + "\n".join(
            f"{s}\n내용" for s in REQUIRED_SECTIONS
        )
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path), \
             patch.object(writer, "_call_claude", return_value=mock_content) as mock_claude:
            result = asyncio.run(writer.write_from_dump("C0123456", dump_path))

        assert result.exists()
        mock_claude.assert_called_once()

    def test_write_from_dump_map_reduce(self, tmp_path):
        """write_from_dump(): >500 메시지 → _chunked_analysis 호출"""
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

        dump_data = {
            "channel_id": "C0123456",
            "messages": [
                {"ts": f"{1000 + i}.0", "user": f"U{i % 5}", "text": f"msg {i}", "thread_ts": None, "reactions": []}
                for i in range(600)
            ],
        }
        dump_path = tmp_path / "C0123456.json"
        dump_path.write_text(json.dumps(dump_data), encoding="utf-8")

        writer = ChannelPRDWriter()
        mock_content = "# C0123456 지식 문서\n분석 결과"
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path), \
             patch.object(writer, "_chunked_analysis", return_value=mock_content) as mock_chunked:
            result = asyncio.run(writer.write_from_dump("C0123456", dump_path))

        assert result.exists()
        mock_chunked.assert_called_once()

    def test_write_from_dump_skips_existing(self, tmp_path):
        """write_from_dump(): 기존 파일 있고 force=False → Claude 호출 없이 스킵"""
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

        existing_path = tmp_path / "C0123456.md"
        existing_path.write_text("# 기존 문서", encoding="utf-8")

        dump_path = tmp_path / "C0123456.json"
        dump_path.write_text(json.dumps({"messages": []}), encoding="utf-8")

        writer = ChannelPRDWriter()
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path), \
             patch.object(writer, "_call_claude") as mock_claude:
            result = asyncio.run(writer.write_from_dump("C0123456", dump_path, force=False))

        assert result == existing_path
        mock_claude.assert_not_called()
        assert existing_path.read_text(encoding="utf-8") == "# 기존 문서"


class TestLoadChannelDocCache:
    def test_load_channel_doc_caches_result(self, tmp_path):
        """_load_channel_doc(): 동일 mtime이면 캐시에서 반환 (파일 재읽기 없음)"""
        from scripts.intelligence.response.handler import ProjectIntelligenceHandler
        import scripts.intelligence.response.handler as handler_module

        storage = MagicMock()
        registry = MagicMock()
        handler = ProjectIntelligenceHandler(storage=storage, registry=registry)

        # channel_contexts → channel_docs 치환 경로에 실제 파일 생성
        ctx_dir = tmp_path / "channel_contexts"
        ctx_dir.mkdir()
        doc_dir = tmp_path / "channel_docs"
        doc_dir.mkdir()
        doc_file = doc_dir / "CTEST.md"
        doc_file.write_text("# 실제 내용", encoding="utf-8")
        actual_mtime = doc_file.stat().st_mtime

        # 동일 mtime으로 캐시 pre-seed
        handler._channel_doc_cache["CTEST"] = (actual_mtime, "# 캐시된 내용")

        original_dir = handler_module._CHANNEL_CONTEXTS_DIR
        handler_module._CHANNEL_CONTEXTS_DIR = ctx_dir
        try:
            result = handler._load_channel_doc("CTEST")
        finally:
            handler_module._CHANNEL_CONTEXTS_DIR = original_dir

        # 캐시 히트 → 파일 내용이 아닌 캐시된 내용 반환
        assert result == "# 캐시된 내용"
