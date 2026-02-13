"""
Draft Writer - Claude Code Opus 4.6 기반 고품질 응답 초안 생성기

ClaudeCodeDraftWriter: claude -p --model opus subprocess로 고품질 draft 생성
"""

import asyncio
import shutil
import time
from pathlib import Path
from typing import Optional
from collections import deque


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
        timeout: int = 60,
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
        analysis_summary: str = "",
    ) -> str:
        """
        claude -p --model opus subprocess로 고품질 draft 생성

        Args:
            project_name: 프로젝트 이름
            project_context: 프로젝트 컨텍스트 (요약)
            original_text: 원본 메시지
            sender_name: 발신자 이름
            source_channel: 소스 채널 (Slack, Gmail 등)
            analysis_summary: OllamaAnalyzer의 분석 요약 (선택)

        Returns:
            생성된 draft 텍스트

        Raises:
            RuntimeError: CLI 에러 또는 rate limit 초과
        """
        self._check_rate_limit()

        context_truncated = project_context[:self.max_context_chars] if project_context else "(컨텍스트 없음)"

        # 분석 요약이 있으면 컨텍스트에 추가
        if analysis_summary:
            context_with_analysis = f"{context_truncated}\n\n## 분석 요약\n{analysis_summary}"
        else:
            context_with_analysis = context_truncated

        prompt = self._prompt_template.format(
            project_name=project_name,
            context=context_with_analysis,
            sender_name=sender_name or "Unknown",
            source_channel=source_channel,
            original_text=original_text[:2000] if original_text else "",
        )

        result = await asyncio.to_thread(
            self._run_claude,
            prompt,
        )

        self._rate_limit_times.append(time.time())
        return result

    def _run_claude(self, prompt: str) -> str:
        """claude -p --model opus 실행 (blocking)"""
        import subprocess

        try:
            result = subprocess.run(
                [self.claude_path, "-p", "--model", self.model, prompt],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI 타임아웃 ({self.timeout}초)")

        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            raise RuntimeError(f"Claude CLI 에러 (code {result.returncode}): {error_msg}")

        output = result.stdout.strip()
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

    @property
    def is_available(self) -> bool:
        """Claude CLI 사용 가능 여부"""
        return self.claude_path is not None
