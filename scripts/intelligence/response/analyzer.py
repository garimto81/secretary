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
import json
import logging
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

try:
    from scripts.shared.retry import retry_async
except ImportError:
    try:
        from shared.retry import retry_async
    except ImportError:
        retry_async = None

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of message analysis."""
    project_id: str | None = None
    needs_response: bool = False
    intent: str = "unknown"  # "질문", "요청", "정보공유", "잡담"
    summary: str = ""
    confidence: float = 0.0
    reasoning: str = ""  # Ollama의 전체 자유 추론 텍스트

    def to_dict(self) -> dict[str, Any]:
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

        with open(prompt_path, encoding="utf-8") as f:
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

    def _build_project_list(self, projects: list[dict[str, Any]]) -> str:
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

    def _extract_decision(self, content: str) -> AnalysisResult:
        """자유 추론 텍스트에서 결정 마커 추출"""
        if not content or not content.strip():
            return AnalysisResult(
                needs_response=False,
                reasoning="빈 응답",
                confidence=0.0,
                summary="빈 응답",
            )

        lines = content.strip().split('\n')

        # 뒤에서부터 마커 검색
        for line in reversed(lines):
            line = line.strip()
            if '[RESPONSE_NEEDED]' in line:
                project_id = self._extract_field(line, 'project_id')
                confidence = self._extract_field(line, 'confidence', '0.5')
                return AnalysisResult(
                    project_id=project_id if project_id != 'unknown' else None,
                    needs_response=True,
                    confidence=float(confidence),
                    reasoning=content,
                    intent=self._infer_intent(content),
                    summary=self._extract_summary(content),
                )
            elif '[NO_RESPONSE]' in line:
                project_id = self._extract_field(line, 'project_id')
                confidence = self._extract_field(line, 'confidence', '0.5')
                return AnalysisResult(
                    project_id=project_id if project_id != 'unknown' else None,
                    needs_response=False,
                    confidence=float(confidence),
                    reasoning=content,
                    intent=self._infer_intent(content),
                    summary=self._extract_summary(content),
                )

        # 마커 없음 → 안전하게 no_response 처리
        logger.warning("No decision marker found in Ollama response")
        return AnalysisResult(
            needs_response=False,
            reasoning=content,
            confidence=0.0,
            summary="마커 미발견",
        )

    def _extract_field(self, line: str, field_name: str, default: str = '') -> str:
        """마커 라인에서 field=value 추출"""
        import re
        pattern = rf'{field_name}=(\S+)'
        match = re.search(pattern, line)
        if match:
            return match.group(1)
        return default

    def _infer_intent(self, content: str) -> str:
        """추론 텍스트에서 의도 추론"""
        content_lower = content.lower()
        if any(kw in content_lower for kw in ['질문', '문의', '물어', '어떻게', '무엇']):
            return '질문'
        if any(kw in content_lower for kw in ['요청', '부탁', '해줘', '처리']):
            return '요청'
        if any(kw in content_lower for kw in ['공유', '알림', '참고', '전달']):
            return '정보공유'
        return '잡담'

    def _extract_summary(self, content: str) -> str:
        """추론 텍스트에서 첫 의미있는 문장을 요약으로 추출"""
        lines = content.strip().split('\n')
        for line in lines:
            line = line.strip()
            # 마커 라인이나 빈 줄 건너뜀
            if not line or line.startswith('[') or line.startswith('#') or line.startswith('-'):
                continue
            # 첫 의미있는 문장 (50자 제한)
            return line[:50]
        return content[:50] if content else ""

    def _extract_and_parse_json(self, text: str) -> dict | None:
        """
        텍스트에서 JSON 객체를 추출하여 파싱.

        여러 전략을 순차적으로 시도:
        1. 전체 텍스트를 JSON으로 직접 파싱
        2. ```json 코드 블록에서 추출
        3. ``` 코드 블록에서 추출
        4. "project_id" 키를 포함하는 { ... } 패턴 regex 추출
        5. 임의의 { ... } JSON 객체 regex 추출
        """
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

        # 전략 4: "project_id" 포함 JSON 객체 regex
        match = re.search(
            r'\{[^{}]*"project_id"\s*:[^{}]*\}',
            text,
            re.DOTALL
        )
        if match:
            try:
                return json.loads(match.group(0))
            except (json.JSONDecodeError, ValueError):
                pass

        # 전략 5: 중괄호 매칭으로 JSON 객체 추출
        brace_start = text.find('{')
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start:i + 1])
                        except (json.JSONDecodeError, ValueError):
                            break

        return None

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
        project_list: list[dict[str, Any]],
        rule_hint: str | None = None,
        rag_context: str = "",
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
            rag_context: Optional RAG context from Knowledge Store

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
                original_text=truncated_text,
                rag_context=rag_context or "(과거 이력 없음)",
            )

            # Call Ollama API
            logger.debug(f"Calling Ollama analyze: model={self.model}, sender={sender_name}")

            async def _call_ollama():
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.ollama_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "user", "content": prompt}
                            ],
                            "stream": False,
                            "options": {
                                "temperature": 0.3,
                                "num_predict": 2048
                            }
                        }
                    )
                    resp.raise_for_status()
                    return resp

            if retry_async:
                response = await retry_async(
                    _call_ollama,
                    max_retries=2,
                    base_delay=2.0,
                    retryable_exceptions=(httpx.RequestError, httpx.HTTPStatusError),
                )
            else:
                response = await _call_ollama()

            result_data = response.json()
            msg_data = result_data.get("message", {})
            content = msg_data.get("content", "")
            thinking = msg_data.get("thinking", "")

            # thinking이 있으면 content와 합침
            full_response = content
            if thinking and thinking.strip():
                full_response = thinking + "\n" + content

            # 마커 기반 결정 추출
            result = self._extract_decision(full_response)
            logger.info(
                f"Analysis complete: project={result.project_id}, "
                f"needs_response={result.needs_response}, confidence={result.confidence:.2f}"
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

    async def chatbot_respond(
        self,
        text: str,
        sender_name: str,
        max_chars: int = 2000,
        context: str = "",
        channel_context: str = "",  # BOT-K03 추가
    ) -> str | None:
        """
        Chatbot 채널 전용 대화 응답 생성.

        프로젝트 분류 없이 사용자 질문에 직접 응답.

        Args:
            text: 사용자 메시지 텍스트
            sender_name: 발신자 이름
            max_chars: 응답 최대 길이 (기본 2000자)
            context: 실시간 컨텍스트 (날씨, 뉴스 등)

        Returns:
            응답 텍스트 또는 None (실패 시)
        """
        try:
            await self._wait_for_rate_limit()

            from datetime import datetime
            now = datetime.now()
            weekday_kr = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

            system_prompt = (
                f'{f"채널 전문가 컨텍스트:{chr(10)}{channel_context}{chr(10)}{chr(10)}" if channel_context else ""}'
                f'당신은 AI 비서 "Secretary"입니다. 사용자의 Slack 메시지에 자연스럽고 도움이 되는 한국어로 응답하세요.\n\n'
                f'## 현재 시간 정보\n'
                f'- 현재 날짜: {now.strftime("%Y년 %m월 %d일")}\n'
                f'- 현재 시간: {now.strftime("%H시 %M분")}\n'
                f'- 요일: {weekday_kr[now.weekday()]}\n\n'
                f'## 역할\n'
                f'- 사용자의 질문에 명확하고 간결하게 답변\n'
                f'- 날짜, 시간, 요일 관련 질문은 위 시간 정보를 활용하여 정확히 답변\n'
                f'- [웹 검색 결과]가 제공되면 그 데이터를 기반으로 사실적인 답변을 하세요\n'
                f'- 검색 결과의 출처를 자연스럽게 언급하세요\n'
                f'- 검색 결과가 질문과 관련 없으면 무시하고 자체 지식으로 답변하세요\n'
                f'- 확실하지 않은 정보는 솔직히 모른다고 답하세요\n\n'
                f'## 스타일\n'
                f'- 존댓말 사용\n'
                f'- 간결하게 (3-5문장)\n'
                f'- Slack 포맷: 굵게는 *텍스트*, 기울임은 _텍스트_\n'
                f'- 마크다운(**굵게**, ### 제목)은 사용하지 마세요'
            )

            # 웹 검색 결과가 있으면 user 메시지에 컨텍스트 주입 (POC 패턴)
            user_content = f"{sender_name}: {self._truncate_text(text)}"
            if context:
                user_content = (
                    f"{user_content}\n\n"
                    f"---\n"
                    f"[웹 검색 결과 - 이 정보를 활용하여 답변하세요]\n"
                    f"{context}"
                )

            async def _call_ollama():
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.ollama_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_content},
                            ],
                            "stream": False,
                            "options": {
                                "temperature": 0.3,
                                "num_predict": 2048,
                            },
                        }
                    )
                    resp.raise_for_status()
                    return resp

            if retry_async:
                response = await retry_async(
                    _call_ollama,
                    max_retries=2,
                    base_delay=2.0,
                    retryable_exceptions=(httpx.RequestError, httpx.HTTPStatusError),
                )
            else:
                response = await _call_ollama()

            result_data = response.json()
            msg_data = result_data.get("message", {})
            content = msg_data.get("content", "").strip()

            if not content:
                return None

            # qwen3 thinking 태그 제거
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

            if not content:
                return None

            # markdown → Slack mrkdwn 변환
            content = re.sub(r'\*\*(.+?)\*\*', r'*\1*', content)  # **bold** → *bold*
            content = re.sub(r'^#{1,6}\s+', '', content, flags=re.MULTILINE)  # ### heading 제거
            content = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', '`'), content)  # code block 단순화

            # max_chars 제한 적용
            if len(content) > max_chars:
                content = content[:max_chars]

            logger.info(f"Chatbot respond: {len(content)} chars for sender={sender_name}")
            return content

        except httpx.HTTPStatusError as e:
            logger.error(f"Chatbot Ollama HTTP error: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"Chatbot Ollama request error: {e}")
            return None
        except Exception as e:
            logger.exception(f"Chatbot respond unexpected error: {e}")
            return None

    async def analyze_batch(
        self,
        messages: list[dict[str, Any]],
        project_list: list[dict[str, Any]]
    ) -> list[AnalysisResult]:
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
