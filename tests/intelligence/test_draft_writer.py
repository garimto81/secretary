"""
ClaudeCodeDraftWriter 테스트

Mock subprocess, async 동작, reasoning 전달 검증.
"""

import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ==========================================
# Mock 기반 테스트 (subprocess 미실행)
# ==========================================

class TestClaudeCodeDraftWriter:
    """ClaudeCodeDraftWriter 테스트"""

    @pytest.fixture
    def writer(self, tmp_path):
        """mock claude path로 DraftWriter 생성"""
        prompt_file = tmp_path / "draft_prompt.txt"
        prompt_file.write_text(
            "프로젝트: {project_name}\n컨텍스트: {context}\n"
            "추론: {ollama_reasoning}\n발신자: {sender_name}\n"
            "채널: {source_channel}\n메시지: {original_text}",
            encoding="utf-8",
        )

        with patch('shutil.which', return_value="C:\\mock\\claude.exe"):
            with patch('scripts.intelligence.response.draft_writer.PROMPT_TEMPLATE_PATH', prompt_file):
                from scripts.intelligence.response.draft_writer import ClaudeCodeDraftWriter
                w = ClaudeCodeDraftWriter(model="opus", timeout=30)
                return w

    def test_init_with_claude_path(self, writer):
        """claude CLI 경로 확인"""
        assert writer.claude_path == "C:\\mock\\claude.exe"
        assert writer.model == "opus"
        assert writer.timeout == 30

    def test_init_without_claude_raises(self):
        """claude CLI 미설치 시 RuntimeError"""
        with patch('shutil.which', return_value=None):
            with pytest.raises(RuntimeError, match="Claude Code CLI"):
                from scripts.intelligence.response.draft_writer import ClaudeCodeDraftWriter
                ClaudeCodeDraftWriter()

    def test_is_available(self, writer):
        """is_available 속성"""
        assert writer.is_available is True

    def test_prompt_template_loaded(self, writer):
        """프롬프트 템플릿 로드 확인"""
        assert "{project_name}" in writer._prompt_template
        assert "{ollama_reasoning}" in writer._prompt_template

    @pytest.mark.asyncio
    async def test_write_draft_success(self, writer):
        """정상 draft 생성"""
        async def mock_run(prompt):
            return "Generated draft response text"

        writer._run_claude_async = mock_run

        with patch('scripts.intelligence.response.draft_writer.retry_async', None):
            result = await writer.write_draft(
                project_name="Secretary",
                project_context="AI 비서 프로젝트",
                original_text="진행 상황 알려주세요",
                sender_name="TestUser",
                source_channel="slack",
                ollama_reasoning="이 메시지는 진행 상황 문의입니다.",
            )

        assert result == "Generated draft response text"

    @pytest.mark.asyncio
    async def test_write_draft_with_ollama_reasoning(self, writer):
        """ollama_reasoning이 프롬프트에 포함되는지 검증"""
        captured_prompt = None

        async def mock_run(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "draft text"

        writer._run_claude_async = mock_run

        with patch('scripts.intelligence.response.draft_writer.retry_async', None):
            await writer.write_draft(
                project_name="Secretary",
                project_context="컨텍스트",
                original_text="메시지",
                sender_name="User",
                source_channel="slack",
                ollama_reasoning="Ollama가 분석한 추론 내용입니다",
            )

        assert "Ollama가 분석한 추론 내용" in captured_prompt

    @pytest.mark.asyncio
    async def test_write_draft_reasoning_truncated(self, writer):
        """ollama_reasoning 3000자 절삭"""
        long_reasoning = "R" * 5000
        captured_prompt = None

        async def mock_run(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "draft"

        writer._run_claude_async = mock_run

        with patch('scripts.intelligence.response.draft_writer.retry_async', None):
            await writer.write_draft(
                project_name="Test",
                project_context="ctx",
                original_text="msg",
                sender_name="User",
                source_channel="slack",
                ollama_reasoning=long_reasoning,
            )

        # reasoning이 3000자로 절삭되었는지 확인
        reasoning_in_prompt = captured_prompt.count("R")
        assert reasoning_in_prompt <= 3000

    @pytest.mark.asyncio
    async def test_write_draft_empty_reasoning(self, writer):
        """ollama_reasoning 없을 때 기본값"""
        captured_prompt = None

        async def mock_run(prompt):
            nonlocal captured_prompt
            captured_prompt = prompt
            return "draft"

        writer._run_claude_async = mock_run

        with patch('scripts.intelligence.response.draft_writer.retry_async', None):
            await writer.write_draft(
                project_name="Test",
                project_context="ctx",
                original_text="msg",
                sender_name="User",
                source_channel="slack",
                ollama_reasoning="",
            )

        assert "(사전 분석 없음)" in captured_prompt

    @pytest.mark.asyncio
    async def test_run_claude_async_error(self, writer):
        """claude CLI 에러 반환 시 RuntimeError"""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Error: model not found")
        )
        mock_process.returncode = 1

        async def mock_create(*args, **kwargs):
            return mock_process

        with patch('asyncio.create_subprocess_exec', side_effect=mock_create):
            with pytest.raises(RuntimeError, match="Claude CLI"):
                await writer._run_claude_async("test prompt")

    @pytest.mark.asyncio
    async def test_run_claude_async_empty_output(self, writer):
        """claude CLI 빈 응답 시 RuntimeError"""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        async def mock_create(*args, **kwargs):
            return mock_process

        with patch('asyncio.create_subprocess_exec', side_effect=mock_create):
            with pytest.raises(RuntimeError, match="빈 응답"):
                await writer._run_claude_async("test prompt")

    def test_rate_limit_check(self, writer):
        """rate limit 초과 시 RuntimeError"""
        # 5개의 요청을 빠르게 기록
        now = time.time()
        for _ in range(5):
            writer._rate_limit_times.append(now)

        with pytest.raises(RuntimeError, match="Rate limit"):
            writer._check_rate_limit()

    def test_rate_limit_after_cooldown(self, writer):
        """60초 경과 후 rate limit 해제"""
        old_time = time.time() - 61  # 61초 전
        for _ in range(5):
            writer._rate_limit_times.append(old_time)

        # 예외 발생하지 않아야 함
        writer._check_rate_limit()
