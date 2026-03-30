"""
Draft Generator - 응답 초안 생성기

OllamaDraftGenerator: 로컬 LLM(ollama)으로 자동 draft 생성 (Gateway에서 사용)
ClaudeCodeDraftGenerator: [DEPRECATED] claude -p subprocess 방식 (테스트 용도)
"""

import asyncio
import shutil
import time
from collections import deque
from pathlib import Path

import httpx

PROMPT_TEMPLATE_PATH = Path(r"C:\claude\secretary\scripts\intelligence\prompts\draft_prompt.txt")


class ClaudeCodeDraftGenerator:
    """
    Claude Code CLI를 활용한 draft 생성 (API key 불필요)

    claude -p --model haiku subprocess로 draft를 생성합니다.
    Claude Code browser 인증을 사용하므로 별도 API key가 필요 없습니다.
    """

    def __init__(self, model: str = "haiku", max_context_chars: int = 12000):
        self.model = model
        self.max_context_chars = max_context_chars
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

    async def generate_draft(
        self,
        project_name: str,
        context: str,
        sender_name: str,
        source_channel: str,
        original_text: str,
    ) -> str:
        """
        claude -p subprocess로 draft 생성

        Args:
            project_name: 프로젝트 이름
            context: 프로젝트 컨텍스트 (요약)
            sender_name: 발신자 이름
            source_channel: 소스 채널
            original_text: 원본 메시지

        Returns:
            생성된 draft 텍스트

        Raises:
            RuntimeError: CLI 에러 또는 rate limit 초과
        """
        self._check_rate_limit()

        context_truncated = context[:self.max_context_chars] if context else "(컨텍스트 없음)"

        prompt = self._prompt_template.format(
            project_name=project_name,
            context=context_truncated,
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
        """claude -p 실행 (blocking)"""
        import subprocess

        try:
            result = subprocess.run(
                [self.claude_path, "-p", "--model", self.model, prompt],
                capture_output=True,
                text=True,
                timeout=60,
                encoding="utf-8",
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError("Claude CLI 타임아웃 (60초)")

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


class OllamaDraftGenerator:
    """
    Ollama 로컬 LLM을 활용한 draft 생성

    httpx AsyncClient로 Ollama REST API (http://localhost:11434)를 호출합니다.
    API key 불필요하고, 인터넷 연결 없이 완전 로컬에서 동작합니다.
    """

    def __init__(
        self,
        model: str = "qwen2.5",
        max_context_chars: int = 12000,
        ollama_url: str = "http://localhost:11434",
        timeout: float = 90.0,
    ):
        self.model = model
        self.max_context_chars = max_context_chars
        self.ollama_url = ollama_url
        self.timeout = timeout

        self._rate_limit_times: deque = deque(maxlen=10)
        self._rate_limit_per_minute = 10

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

    async def generate_draft(
        self,
        project_name: str,
        context: str,
        sender_name: str,
        source_channel: str,
        original_text: str,
    ) -> str:
        """
        Ollama API로 draft 생성

        Args:
            project_name: 프로젝트 이름
            context: 프로젝트 컨텍스트 (요약)
            sender_name: 발신자 이름
            source_channel: 소스 채널
            original_text: 원본 메시지

        Returns:
            생성된 draft 텍스트

        Raises:
            RuntimeError: API 에러 또는 rate limit 초과
        """
        self._check_rate_limit()

        context_truncated = context[:self.max_context_chars] if context else "(컨텍스트 없음)"

        prompt = self._prompt_template.format(
            project_name=project_name,
            context=context_truncated,
            sender_name=sender_name or "Unknown",
            source_channel=source_channel,
            original_text=original_text[:2000] if original_text else "",
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "당신은 프로젝트 AI 비서입니다. 한국어로 응답하세요."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
            except httpx.TimeoutException:
                raise RuntimeError(f"Ollama API 타임아웃 ({self.timeout}초)")
            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"Ollama API HTTP 에러: {e.response.status_code} {e.response.text}")
            except httpx.RequestError as e:
                raise RuntimeError(f"Ollama API 요청 실패: {e}")

        try:
            data = response.json()
            draft = data["message"]["content"]
        except (KeyError, ValueError) as e:
            raise RuntimeError(f"Ollama API 응답 파싱 실패: {e}")

        if not draft or not draft.strip():
            raise RuntimeError("Ollama API가 빈 응답을 반환했습니다")

        self._rate_limit_times.append(time.time())
        return draft.strip()

    def _check_rate_limit(self) -> None:
        """Rate limit 확인 (10 drafts/minute)"""
        now = time.time()

        while self._rate_limit_times and (now - self._rate_limit_times[0]) > 60:
            self._rate_limit_times.popleft()

        if len(self._rate_limit_times) >= self._rate_limit_per_minute:
            oldest = self._rate_limit_times[0]
            wait_time = 60 - (now - oldest)
            if wait_time > 0:
                raise RuntimeError(
                    f"Rate limit 초과 (10 drafts/min). {wait_time:.0f}초 후 재시도하세요."
                )

    @property
    def is_available(self) -> bool:
        """Ollama 서버 사용 가능 여부"""
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                response = client.get(f"{self.ollama_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False
