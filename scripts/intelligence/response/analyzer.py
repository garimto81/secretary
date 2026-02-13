"""
OllamaAnalyzer - Message classification using local Ollama LLM.

Analyzes incoming messages to determine:
- project_id: Which registered project this belongs to
- needs_response: Whether a response is needed
- intent: Message classification (질문/요청/정보공유/잡담)
- summary: Brief summary of the message
- confidence: Confidence score 0.0-1.0
- reasoning: Why the classification was made
"""

import asyncio
import httpx
import json
import logging
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of message analysis."""
    project_id: Optional[str] = None
    needs_response: bool = False
    intent: str = "unknown"  # "질문", "요청", "정보공유", "잡담"
    summary: str = ""
    confidence: float = 0.0
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class OllamaAnalyzer:
    """Analyzes messages using Ollama local LLM."""

    def __init__(
        self,
        model: str = "qwen3:8b",
        ollama_url: str = "http://localhost:11434",
        timeout: float = 90.0,
        max_context_chars: int = 12000,
        max_requests_per_minute: int = 10
    ):
        """
        Initialize Ollama analyzer.

        Args:
            model: Ollama model name (default: qwen3:8b)
            ollama_url: Ollama API base URL
            timeout: Request timeout in seconds
            max_context_chars: Maximum characters to send to LLM
            max_requests_per_minute: Rate limit
        """
        self.model = model
        self.ollama_url = ollama_url.rstrip("/")
        self.timeout = timeout
        self.max_context_chars = max_context_chars
        self.max_requests_per_minute = max_requests_per_minute

        # Rate limiting
        self._request_times: deque = deque(maxlen=max_requests_per_minute)

        # Load prompt template
        prompt_path = Path(r"C:\claude\secretary\scripts\intelligence\prompts\analyze_prompt.txt")
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

        logger.info(f"OllamaAnalyzer initialized: model={model}, url={ollama_url}")

    async def _wait_for_rate_limit(self):
        """Wait if necessary to respect rate limit."""
        now = datetime.now()

        # Remove timestamps older than 1 minute
        while self._request_times and (now - self._request_times[0]).total_seconds() > 60:
            self._request_times.popleft()

        # If at limit, wait until oldest request is 60 seconds old
        if len(self._request_times) >= self.max_requests_per_minute:
            oldest = self._request_times[0]
            wait_time = 60 - (now - oldest).total_seconds()
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

        self._request_times.append(now)

    def _build_project_list(self, projects: List[Dict[str, Any]]) -> str:
        """Build formatted project list for prompt."""
        if not projects:
            return "등록된 프로젝트가 없습니다."

        lines = []
        for proj in projects:
            proj_id = proj.get("id", "unknown")
            name = proj.get("name", "Unknown")
            keywords = ", ".join(proj.get("keywords", []))
            desc = proj.get("description", "")

            lines.append(f"- {proj_id}: {name}")
            if keywords:
                lines.append(f"  키워드: {keywords}")
            if desc:
                lines.append(f"  설명: {desc}")

        return "\n".join(lines)

    def _truncate_text(self, text: str) -> str:
        """Truncate text to max_context_chars."""
        if len(text) <= self.max_context_chars:
            return text

        truncated = text[:self.max_context_chars]
        logger.warning(f"Text truncated from {len(text)} to {self.max_context_chars} chars")
        return truncated + "\n\n[... 텍스트 생략 ...]"

    async def analyze(
        self,
        text: str,
        sender_name: str,
        source_channel: str,
        channel_id: str,
        project_list: List[Dict[str, Any]],
        rule_hint: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze message using Ollama LLM.

        Args:
            text: Message text to analyze
            sender_name: Name of sender
            source_channel: Source (e.g., "slack", "gmail")
            channel_id: Channel/thread identifier
            project_list: List of registered projects
            rule_hint: Optional hint from ContextMatcher (e.g., "channel_match=secretary, confidence=0.9")

        Returns:
            AnalysisResult with classification results
        """
        try:
            # Rate limiting
            await self._wait_for_rate_limit()

            # Build prompt
            projects_str = self._build_project_list(project_list)
            hint_str = f"\n\n[기존 규칙 매칭 결과]\n{rule_hint}" if rule_hint else ""
            truncated_text = self._truncate_text(text)

            prompt = self.prompt_template.format(
                project_list=projects_str,
                rule_hint=hint_str,
                sender_name=sender_name,
                source_channel=source_channel,
                original_text=truncated_text
            )

            # Call Ollama API
            logger.debug(f"Calling Ollama analyze: model={self.model}, sender={sender_name}")

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                        "options": {
                            "temperature": 0.1,  # Low temperature for consistent classification
                            "num_predict": 512   # Short response expected
                        }
                    }
                )
                response.raise_for_status()

            result_data = response.json()
            content = result_data.get("message", {}).get("content", "")

            # Parse JSON response
            try:
                # Try to find JSON block
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    content = content[json_start:json_end].strip()

                parsed = json.loads(content)

                # Build AnalysisResult
                result = AnalysisResult(
                    project_id=parsed.get("project_id"),
                    needs_response=parsed.get("needs_response", False),
                    intent=parsed.get("intent", "unknown"),
                    summary=parsed.get("summary", ""),
                    confidence=float(parsed.get("confidence", 0.0)),
                    reasoning=parsed.get("reasoning", "")
                )

                logger.info(
                    f"Analysis complete: project={result.project_id}, "
                    f"intent={result.intent}, confidence={result.confidence:.2f}"
                )
                return result

            except (json.JSONDecodeError, ValueError, KeyError) as parse_err:
                logger.error(f"Failed to parse Ollama response: {parse_err}")
                logger.debug(f"Raw content: {content[:500]}")

                # Try to extract partial information
                result = AnalysisResult(
                    project_id=None,
                    needs_response=False,
                    intent="unknown",
                    summary=content[:100] if content else "파싱 실패",
                    confidence=0.0,
                    reasoning=f"JSON 파싱 실패: {str(parse_err)}"
                )
                return result

        except httpx.HTTPStatusError as http_err:
            logger.error(f"Ollama HTTP error: {http_err}")
            return AnalysisResult(
                reasoning=f"HTTP 오류: {str(http_err)}"
            )

        except httpx.RequestError as req_err:
            logger.error(f"Ollama request error: {req_err}")
            return AnalysisResult(
                reasoning=f"요청 오류: {str(req_err)}"
            )

        except Exception as e:
            logger.exception(f"Unexpected error in analyze: {e}")
            return AnalysisResult(
                reasoning=f"예외 발생: {str(e)}"
            )

    async def analyze_batch(
        self,
        messages: List[Dict[str, Any]],
        project_list: List[Dict[str, Any]]
    ) -> List[AnalysisResult]:
        """
        Analyze multiple messages in batch (with rate limiting).

        Args:
            messages: List of message dicts with keys: text, sender_name, source_channel, channel_id, rule_hint
            project_list: List of registered projects

        Returns:
            List of AnalysisResult (same order as input)
        """
        results = []
        for msg in messages:
            result = await self.analyze(
                text=msg["text"],
                sender_name=msg["sender_name"],
                source_channel=msg["source_channel"],
                channel_id=msg["channel_id"],
                project_list=project_list,
                rule_hint=msg.get("rule_hint")
            )
            results.append(result)

        return results


# CLI for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Ollama message analyzer")
    parser.add_argument("--text", required=True, help="Message text to analyze")
    parser.add_argument("--sender", default="Test Sender", help="Sender name")
    parser.add_argument("--source", default="slack", help="Source channel")
    parser.add_argument("--channel-id", default="test-channel", help="Channel ID")
    parser.add_argument("--rule-hint", help="Optional rule hint")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama model")

    args = parser.parse_args()

    # Mock project list
    projects = [
        {
            "id": "secretary",
            "name": "Secretary",
            "keywords": ["daily report", "automation", "비서"],
            "description": "AI 비서 자동화 프로젝트"
        },
        {
            "id": "wsoptv",
            "name": "WSOP TV Automation",
            "keywords": ["wsop", "방송", "자막", "영상"],
            "description": "WSOP 방송 자동화"
        }
    ]

    async def test():
        analyzer = OllamaAnalyzer(model=args.model)
        result = await analyzer.analyze(
            text=args.text,
            sender_name=args.sender,
            source_channel=args.source,
            channel_id=args.channel_id,
            project_list=projects,
            rule_hint=args.rule_hint
        )

        print("\n=== Analysis Result ===")
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    asyncio.run(test())
