"""
Draft Writer - Claude Code Opus 4.6 기반 고품질 응답 초안 생성기

ClaudeCodeDraftWriter: claude -p --model opus subprocess로 고품질 draft 생성
"""

import asyncio
import logging
import shutil
import time
from collections import deque
from pathlib import Path

try:
    from scripts.shared.retry import retry_async
except ImportError:
    try:
        from shared.retry import retry_async
    except ImportError:
        # 패키지 import 시 사용 불가하면 inline fallback
        retry_async = None

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE_PATH = Path(r"C:\claude\secretary\scripts\intelligence\prompts\draft_prompt.txt")


class ClaudeCodeDraftWriter:
    """
    Claude Code Opus 4.6 subprocess 기반 고품질 draft 작성기

    `claude -p --model opus` 실행.
    분석 결과 needs_response=true인 메시지에 대해서만 호출.
    """

    def __init__(
        self,
        model: str = "opus",
        max_context_chars: int = 12000,
        timeout: int = 120,
    ):
        """
        Args:
            model: Claude 모델 (기본값: "opus")
            max_context_chars: 컨텍스트 최대 길이
            timeout: subprocess 타임아웃 (초)
        """
        self.model = model
        self.max_context_chars = max_context_chars
        self.timeout = timeout

        self.claude_path = shutil.which("claude")
        if not self.claude_path:
            raise RuntimeError("Claude Code CLI가 설치되지 않았습니다")

        self._rate_limit_times: deque = deque(maxlen=5)
        self._rate_limit_per_minute = 5

        self._prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """프롬프트 템플릿 로드"""
        if PROMPT_TEMPLATE_PATH.exists():
            return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
        return (
            "프로젝트 '{project_name}' 관련 메시지입니다.\n\n"
            "컨텍스트:\n{context}\n\n"
            "발신자: {sender_name}\n"
            "채널: {source_channel}\n"
            "메시지: {original_text}\n\n"
            "위 메시지에 대한 응답 초안을 한국어로 작성하세요."
        )

    async def write_draft(
        self,
        project_name: str,
        project_context: str,
        original_text: str,
        sender_name: str,
        source_channel: str,
        ollama_reasoning: str = "",
        analysis_summary: str = "",
        rag_context: str = "",
        channel_context: str = "",
    ) -> str:
        """
        claude -p --model opus subprocess로 고품질 draft 생성

        Args:
            project_name: 프로젝트 이름
            project_context: 프로젝트 컨텍스트 (요약)
            original_text: 원본 메시지
            sender_name: 발신자 이름
            source_channel: 소스 채널 (Slack, Gmail 등)
            ollama_reasoning: OllamaAnalyzer의 자유 추론 텍스트 (선택)
            analysis_summary: OllamaAnalyzer의 분석 요약 (선택)
            rag_context: Knowledge Store RAG 검색 결과 (선택)

        Returns:
            생성된 draft 텍스트

        Raises:
            RuntimeError: CLI 에러 또는 rate limit 초과
        """
        self._check_rate_limit()

        context_truncated = project_context[:self.max_context_chars] if project_context else "(컨텍스트 없음)"

        # Ollama 추론 텍스트 절삭 (3000자 제한)
        reasoning_truncated = ollama_reasoning[:3000] if ollama_reasoning else "(사전 분석 없음)"

        prompt = self._prompt_template.format(
            project_name=project_name,
            context=context_truncated,
            ollama_reasoning=reasoning_truncated,
            sender_name=sender_name or "Unknown",
            source_channel=source_channel,
            original_text=original_text[:2000] if original_text else "",
            rag_context=rag_context or "(과거 이력 없음)",
            channel_context=channel_context or "(채널 컨텍스트 없음)",
        )

        if retry_async:
            result = await retry_async(
                self._run_claude_async,
                prompt,
                max_retries=1,
                base_delay=5.0,
                retryable_exceptions=(RuntimeError,),
            )
        else:
            result = await self._run_claude_async(prompt)

        self._rate_limit_times.append(time.time())
        return result

    async def _run_claude_async(self, prompt: str) -> str:
        """claude -p --model opus 비동기 실행"""
        try:
            process = await asyncio.create_subprocess_exec(
                self.claude_path, "-p", "--model", self.model, prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )
        except TimeoutError as e:
            process.kill()
            raise RuntimeError(f"Claude CLI 타임아웃 ({self.timeout}초)") from e

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace").strip() if stderr else "Unknown error"
            raise RuntimeError(f"Claude CLI 에러 (code {process.returncode}): {error_msg}")

        output = stdout.decode("utf-8", errors="replace").strip() if stdout else ""
        if not output:
            raise RuntimeError("Claude CLI가 빈 응답을 반환했습니다")

        return output

    def _check_rate_limit(self) -> None:
        """Rate limit 확인 (5 drafts/minute)"""
        now = time.time()

        while self._rate_limit_times and (now - self._rate_limit_times[0]) > 60:
            self._rate_limit_times.popleft()

        if len(self._rate_limit_times) >= self._rate_limit_per_minute:
            oldest = self._rate_limit_times[0]
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                raise RuntimeError(
                    f"Rate limit 초과 (5 drafts/min). {wait_time:.0f}초 후 재시도하세요."
                )

    async def chatbot_respond(
        self,
        text: str,
        sender_name: str,
        context: str = "",
        channel_context: str = "",  # BOT-K03 추가
    ) -> str | None:
        """
        Chatbot 채널 응답 생성 (Ollama 대체용)

        Claude Sonnet subprocess로 간단한 대화 응답 생성.
        """
        prompt = f"""{f"채널 전문가 컨텍스트:{chr(10)}{channel_context}{chr(10)}{chr(10)}" if channel_context else ""}Slack 채널에서 받은 메시지에 답변하세요.

발신자: {sender_name}
메시지: {text}
{f"추가 컨텍스트:{chr(10)}{context}" if context else ""}

친근하고 도움이 되는 한국어 응답을 작성하세요. (3-5문장 이내)"""

        try:
            return await self._run_claude_async(prompt)
        except Exception as e:
            logger.warning(f"chatbot_respond 실패: {e}")
            return None

    @property
    def is_available(self) -> bool:
        """Claude CLI 사용 가능 여부"""
        return self.claude_path is not None
