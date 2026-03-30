"""ChannelPRDWriter 단위 테스트"""
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mastery_context():
    return {
        "channel_name": "테스트채널",
        "top_keywords": ["배포", "API", "버그", "리뷰", "설계"],
        "key_decisions": ["v2.0 출시 일정 확정", "PostgreSQL 마이그레이션 결정"],
        "member_roles": {"홍길동": "주요 결정자", "김철수": "개발 담당"},
    }


@pytest.fixture
def writer_with_tmp(tmp_path):
    """tmp_path를 CHANNEL_DOCS_DIR로 패치한 ChannelPRDWriter"""
    with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter
        yield ChannelPRDWriter(model="sonnet", timeout=5), tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChannelPRDWriterWrite:
    @pytest.mark.asyncio
    async def test_write_creates_prd_file(self, tmp_path, mastery_context):
        """Claude subprocess mock으로 PRD 파일 생성 확인"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

            writer = ChannelPRDWriter(model="sonnet", timeout=5)

            claude_output = "# 테스트채널 지식 문서\n최종 갱신: 2026-02-19\n\n## 채널 개요\n테스트용 채널입니다.\n"
            with patch.object(writer, "_call_claude", new=AsyncMock(return_value=claude_output)):
                result = await writer.write("C_TEST001", mastery_context)

            assert result == tmp_path / "C_TEST001.md"
            assert result.exists()
            content = result.read_text(encoding="utf-8")
            assert "테스트채널" in content

    @pytest.mark.asyncio
    async def test_write_skips_existing(self, tmp_path, mastery_context):
        """기존 파일 있으면 force=False 시 스킵"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

            writer = ChannelPRDWriter()
            existing = tmp_path / "C_EXIST.md"
            existing.write_text("# 기존 내용\n", encoding="utf-8")

            with patch.object(writer, "_call_claude", new=AsyncMock()) as mock_claude:
                result = await writer.write("C_EXIST", mastery_context, force=False)
                mock_claude.assert_not_called()

            assert result == existing
            assert existing.read_text(encoding="utf-8") == "# 기존 내용\n"

    @pytest.mark.asyncio
    async def test_write_force_overwrites(self, tmp_path, mastery_context):
        """force=True 시 기존 파일 덮어쓰기 (Claude 응답에 섹션 보완 포함)"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import REQUIRED_SECTIONS, ChannelPRDWriter

            writer = ChannelPRDWriter()
            existing = tmp_path / "C_FORCE.md"
            existing.write_text("# 기존 내용\n", encoding="utf-8")

            # Claude가 모든 필수 섹션을 포함한 완전한 출력 반환
            new_output = "# 새 내용\n최종 갱신: 2026-02-19\n\n" + "\n".join(
                f"{s}\n내용\n" for s in REQUIRED_SECTIONS
            )
            with patch.object(writer, "_call_claude", new=AsyncMock(return_value=new_output)):
                result = await writer.write("C_FORCE", mastery_context, force=True)

            content = result.read_text(encoding="utf-8")
            assert "새 내용" in content
            assert "기존 내용" not in content

    @pytest.mark.asyncio
    async def test_write_uses_fallback_on_claude_failure(self, tmp_path, mastery_context):
        """Claude 실패 시 fallback PRD 생성"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

            writer = ChannelPRDWriter()
            with patch.object(writer, "_call_claude", new=AsyncMock(side_effect=RuntimeError("오류"))):
                result = await writer.write("C_FAIL", mastery_context)

            content = result.read_text(encoding="utf-8")
            assert "테스트채널" in content
            assert "## 채널 개요" in content


class TestChannelPRDWriterUpdateSection:
    @pytest.mark.asyncio
    async def test_update_section_replaces_content(self, tmp_path, mastery_context):
        """특정 섹션 내용 교체 확인"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

            writer = ChannelPRDWriter()
            prd_file = tmp_path / "C_UPD.md"
            prd_file.write_text(
                "# 채널\n\n## 주요 토픽\n- 기존 토픽\n\n## 핵심 의사결정\n- 결정1\n",
                encoding="utf-8",
            )

            result = await writer.update_section("C_UPD", "주요 토픽", "- 새 토픽\n- 추가 토픽")

            assert result is True
            content = prd_file.read_text(encoding="utf-8")
            assert "새 토픽" in content
            assert "기존 토픽" not in content
            # 다른 섹션은 유지
            assert "핵심 의사결정" in content

    @pytest.mark.asyncio
    async def test_update_section_nonexistent_file(self, tmp_path):
        """파일 없으면 False 반환"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

            writer = ChannelPRDWriter()
            result = await writer.update_section("C_NONE", "주요 토픽", "새 내용")

            assert result is False

    @pytest.mark.asyncio
    async def test_update_section_missing_section_returns_false(self, tmp_path):
        """존재하지 않는 섹션 업데이트 시 False 반환"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

            writer = ChannelPRDWriter()
            prd_file = tmp_path / "C_SEC.md"
            prd_file.write_text("# 채널\n\n## 채널 개요\n설명\n", encoding="utf-8")

            result = await writer.update_section("C_SEC", "없는 섹션", "내용")
            assert result is False


class TestChannelPRDWriterFallback:
    def test_fallback_prd_structure(self):
        """fallback PRD에 필수 섹션 포함 여부"""
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

        writer = ChannelPRDWriter()
        mastery_context = {
            "channel_name": "테스트채널",
            "top_keywords": ["배포", "API"],
            "key_decisions": ["출시 결정"],
            "member_roles": {"홍길동": "결정자"},
        }
        content = writer._build_fallback_prd("C_TEST", mastery_context)

        required_sections = [
            "# 테스트채널 지식 문서",
            "## 채널 개요",
            "## 주요 토픽",
            "## 핵심 의사결정",
            "## 멤버 역할",
            "## 최근 변경사항",
            "## 커뮤니케이션 특성",
            "## 기술 스택",
            "## 반복 이슈 패턴 및 해결 가이드",
            "## Q&A 패턴",
        ]
        for section in required_sections:
            assert section in content, f"필수 섹션 누락: {section}"

    def test_fallback_prd_includes_keywords(self):
        """fallback PRD에 키워드 포함 여부"""
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

        writer = ChannelPRDWriter()
        mastery_context = {
            "channel_name": "채널명",
            "top_keywords": ["키워드A", "키워드B"],
            "key_decisions": [],
            "member_roles": {},
        }
        content = writer._build_fallback_prd("C_KW", mastery_context)
        assert "키워드A" in content
        assert "키워드B" in content


class TestChannelPRDWriterSectionValidation:
    def test_validate_sections_complete(self):
        """모든 섹션 있으면 빈 목록 반환"""
        from scripts.knowledge.channel_prd_writer import REQUIRED_SECTIONS, ChannelPRDWriter

        writer = ChannelPRDWriter()
        content = "\n".join(REQUIRED_SECTIONS)
        missing = writer._validate_sections(content)
        assert missing == []

    def test_validate_sections_missing(self):
        """누락된 섹션 목록 반환"""
        from scripts.knowledge.channel_prd_writer import ChannelPRDWriter

        writer = ChannelPRDWriter()
        content = "## 채널 개요\n내용\n## 주요 토픽\n내용"
        missing = writer._validate_sections(content)
        assert "## 기술 스택" in missing
        assert "## Q&A 패턴" in missing

    @pytest.mark.asyncio
    async def test_write_completes_partial_claude_output(self, tmp_path, mastery_context):
        """Claude가 부분 응답 반환 시 누락 섹션 자동 보완"""
        with patch("scripts.knowledge.channel_prd_writer.CHANNEL_DOCS_DIR", tmp_path):
            from scripts.knowledge.channel_prd_writer import REQUIRED_SECTIONS, ChannelPRDWriter

            writer = ChannelPRDWriter()
            partial_output = (
                "# 채널 지식 문서\n최종 갱신: 2026-02-20\n\n"
                "## 채널 개요\n설명\n\n"
                "## 주요 토픽\n- 토픽1\n\n"
                "## 핵심 의사결정\n- 결정1\n"
            )
            with patch.object(writer, "_call_claude", new=AsyncMock(return_value=partial_output)):
                result = await writer.write("C_PARTIAL", mastery_context)

            content = result.read_text(encoding="utf-8")
            for section in REQUIRED_SECTIONS:
                assert section in content, f"섹션 누락: {section}"
