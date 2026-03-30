"""
Work Tracker AI 분석기 — Ollama 기반 의미적 분석

OllamaAnalyzer 패턴을 답습하여:
- httpx + deque rate limit + retry_async
- 5-전략 JSON 추출
- <think> 태그 제거
- Graceful degradation (모든 메서드 try/except → fallback)
"""

import asyncio
import json
import logging
import re
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import httpx

# 3-way import
try:
    from scripts.work_tracker.models import DailyCommit, WorkStream
except ImportError:
    try:
        from work_tracker.models import DailyCommit, WorkStream
    except ImportError:
        from .models import DailyCommit, WorkStream

try:
    from scripts.shared.retry import retry_async
except ImportError:
    try:
        from shared.retry import retry_async
    except ImportError:
        try:
            from ..shared.retry import retry_async
        except ImportError:
            retry_async = None

logger = logging.getLogger(__name__)

# 프롬프트 디렉토리
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


class WorkTrackerAIAnalyzer:
    """Ollama 기반 Work Tracker AI 분석"""

    def __init__(
        self,
        model: str = "qwen3.5:9b",
        ollama_url: str = "http://localhost:9000",
        timeout: float = 90.0,
        max_requests_per_minute: int = 10,
    ):
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout = timeout
        self.max_requests_per_minute = max_requests_per_minute
        self._request_times: deque = deque(maxlen=max_requests_per_minute)

        # 프롬프트 템플릿 로드
        self._prompts: dict[str, str] = {}
        for name in ("keyword_cluster", "stream_naming", "highlights_and_tasks"):
            path = _PROMPTS_DIR / f"{name}.txt"
            if path.exists():
                self._prompts[name] = path.read_text(encoding="utf-8")
            else:
                logger.warning(f"Prompt template not found: {path}")
                self._prompts[name] = ""

        logger.info(
            f"WorkTrackerAIAnalyzer initialized: model={model}, url={ollama_url}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def cluster_keywords(
        self, commits: list[DailyCommit]
    ) -> dict[str, list[str]]:
        """Gap 1: 의미적 키워드 클러스터링.

        Returns:
            {"클러스터명": ["hash1", "hash2"]} or {} on failure
        """
        try:
            if not commits or not self._prompts.get("keyword_cluster"):
                return {}

            commit_lines = "\n".join(
                f"- [{c.commit_hash[:7]}] {c.message}" for c in commits
            )
            prompt = self._prompts["keyword_cluster"].format(
                commit_messages=commit_lines
            )

            text = await self._call_ollama(prompt)
            data = self._extract_json(text)
            if not data or "clusters" not in data:
                return {}

            result: dict[str, list[str]] = {}
            for cluster in data["clusters"]:
                name = cluster.get("name", "")
                hashes = cluster.get("hashes", [])
                if name and len(hashes) >= 2:
                    result[name] = hashes
            return result

        except Exception as e:
            logger.warning(f"cluster_keywords failed: {e}")
            return {}

    async def generate_stream_names(
        self, streams: list[WorkStream]
    ) -> dict[str, str]:
        """Gap 4: AI 스트림 명명.

        Returns:
            {"original_name": "human_readable_name"} or {} on failure
        """
        try:
            if not streams or not self._prompts.get("stream_naming"):
                return {}

            stream_lines = "\n".join(
                f"- {s.name} ({s.project}, {s.total_commits} commits)"
                for s in streams
            )
            prompt = self._prompts["stream_naming"].format(
                stream_list=stream_lines
            )

            text = await self._call_ollama(prompt)
            data = self._extract_json(text)
            if not data or not isinstance(data, dict):
                return {}

            # dict에서 clusters/highlights 등 특수 키 제외하고 str→str만 반환
            return {
                k: v for k, v in data.items()
                if isinstance(k, str) and isinstance(v, str)
            }

        except Exception as e:
            logger.warning(f"generate_stream_names failed: {e}")
            return {}

    async def generate_highlights_and_tasks(
        self,
        commits: list[DailyCommit],
        streams: list[WorkStream],
    ) -> tuple[list[str], list[str]]:
        """Gap 2+3: 하이라이트 + 다음 할 일.

        Args:
            commits: 당일 커밋 목록
            streams: 활성 Work Stream 목록

        Returns:
            (highlights, next_tasks) — 실패 시 ([], [])
        """
        try:
            if not commits or not self._prompts.get("highlights_and_tasks"):
                return [], []

            # 커밋 요약
            commit_summary = "\n".join(
                f"- [{c.commit_type.value}] {c.message} ({c.project}/{c.repo})"
                for c in commits[:50]
            )

            # 스트림 요약
            stream_summary = "\n".join(
                f"- {s.name}: {s.total_commits} commits, {s.duration_days}일째"
                for s in streams
            ) if streams else "(활성 스트림 없음)"

            prompt = self._prompts["highlights_and_tasks"].format(
                commit_summary=commit_summary,
                stream_summary=stream_summary,
            )

            text = await self._call_ollama(prompt)
            data = self._extract_json(text)
            if not data:
                return [], []

            highlights = data.get("highlights", [])
            next_tasks = data.get("next_tasks", [])

            # 타입 안전성
            if not isinstance(highlights, list):
                highlights = []
            if not isinstance(next_tasks, list):
                next_tasks = []

            return (
                [str(h) for h in highlights[:3]],
                [str(t) for t in next_tasks[:3]],
            )

        except Exception as e:
            logger.warning(f"generate_highlights_and_tasks failed: {e}")
            return [], []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _wait_for_rate_limit(self):
        """Rate limit 대기 (deque 기반)"""
        now = datetime.now()
        while self._request_times and (now - self._request_times[0]).total_seconds() > 60:
            self._request_times.popleft()

        if len(self._request_times) >= self.max_requests_per_minute:
            oldest = self._request_times[0]
            wait_time = 60 - (now - oldest).total_seconds()
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

        self._request_times.append(now)

    async def _call_ollama(self, prompt: str) -> str:
        """Ollama API 호출 + <think> 제거"""
        await self._wait_for_rate_limit()

        async def _do_request():
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {
                            "temperature": 0.3,
                            "num_predict": 2048,
                        },
                    },
                )
                resp.raise_for_status()
                return resp

        if retry_async:
            response = await retry_async(
                _do_request,
                max_retries=2,
                base_delay=2.0,
                retryable_exceptions=(httpx.RequestError, httpx.HTTPStatusError),
            )
        else:
            response = await _do_request()

        result_data = response.json()
        content = result_data.get("message", {}).get("content", "")

        # <think> 태그 제거
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        return content

    def _extract_json(self, text: str) -> dict | None:
        """5-전략 JSON 추출 (OllamaAnalyzer 패턴)"""
        if not text or not text.strip():
            return None

        text = text.strip()

        # 전략 1: 직접 파싱
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass

        # 전략 2: ```json 블록
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                try:
                    return json.loads(text[start:end].strip())
                except (json.JSONDecodeError, ValueError):
                    pass

        # 전략 3: ``` 블록
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                try:
                    return json.loads(text[start:end].strip())
                except (json.JSONDecodeError, ValueError):
                    pass

        # 전략 4: 특정 키 포함 JSON regex
        for key in ("clusters", "highlights", "next_tasks"):
            match = re.search(
                rf'\{{[^{{}}]*"{key}"\s*:[^{{}}]*\}}',
                text,
                re.DOTALL,
            )
            if match:
                try:
                    return json.loads(match.group(0))
                except (json.JSONDecodeError, ValueError):
                    pass

        # 전략 5: 중괄호 매칭
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start : i + 1])
                        except (json.JSONDecodeError, ValueError):
                            break

        return None
