"""ChannelUpdateJudge — 새 메시지를 받아 채널 PRD 갱신 필요 여부를 2단계로 판단"""
import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from scripts.shared.paths import CHANNEL_DOCS_DIR
except ImportError:
    try:
        from shared.paths import CHANNEL_DOCS_DIR
    except ImportError:
        CHANNEL_DOCS_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "channel_docs"


@dataclass
class UpdateDecision:
    needs_update: bool
    section: str | None       # "주요 토픽", "핵심 의사결정", "멤버 역할", "최근 변경사항" 등
    new_content: str | None   # 해당 섹션에 추가할 내용
    judged_by: str            # "qwen", "sonnet", "fallback"
    confidence: float         # 0.0~1.0
    reasoning: str | None     # 판단 근거


class ChannelUpdateJudge:
    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen3:8b",
        ollama_timeout: int = 60,
        sonnet_timeout: int = 120,
        confidence_threshold: float = 0.7,
    ):
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.ollama_timeout = ollama_timeout
        self.sonnet_timeout = sonnet_timeout
        self.confidence_threshold = confidence_threshold
        self.claude_path = shutil.which("claude")

    async def judge(self, message_text: str, channel_id: str, prd_content: str = "") -> UpdateDecision:
        """
        1단계: Qwen 빠른 판단 (ollama HTTP API 직접 호출)
          - confidence >= confidence_threshold → 결정 확정
          - confidence < threshold → Sonnet 에스컬레이션
        2단계: Sonnet 정확한 판단 (Claude subprocess)
        """
        if not prd_content:
            prd_content = self._load_prd(channel_id)

        # 1단계: Qwen 빠른 판단
        try:
            qwen_decision = await self._judge_with_qwen(message_text, channel_id, prd_content)
            if qwen_decision.confidence >= self.confidence_threshold:
                logger.info(
                    f"Qwen 고신뢰 판단 (confidence={qwen_decision.confidence:.2f}): "
                    f"needs_update={qwen_decision.needs_update}"
                )
                return qwen_decision
            else:
                logger.info(
                    f"Qwen 저신뢰 (confidence={qwen_decision.confidence:.2f}), Sonnet 에스컬레이션"
                )
        except Exception as e:
            logger.warning(f"Qwen 판단 실패, Sonnet으로 에스컬레이션: {e}")

        # 2단계: Sonnet 정확한 판단
        try:
            sonnet_decision = await self._judge_with_sonnet(message_text, channel_id, prd_content)
            logger.info(
                f"Sonnet 판단 완료: needs_update={sonnet_decision.needs_update}, "
                f"section={sonnet_decision.section}"
            )
            return sonnet_decision
        except Exception as e:
            logger.error(f"Sonnet 판단도 실패: {e}")
            return UpdateDecision(
                needs_update=False,
                section=None,
                new_content=None,
                judged_by="fallback",
                confidence=0.0,
                reasoning=f"판단 실패: {e}",
            )

    async def _judge_with_qwen(self, message_text: str, channel_id: str, prd_content: str) -> UpdateDecision:
        """Qwen(Ollama) HTTP API로 빠른 판단"""
        prompt = self._build_qwen_prompt(message_text, prd_content)

        text = ""
        try:
            import aiohttp  # type: ignore
            async with aiohttp.ClientSession() as session:
                resp = await session.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                    timeout=aiohttp.ClientTimeout(total=self.ollama_timeout),
                )
                data = await resp.json()
                text = data.get("response", "")
        except ImportError:
            import requests  # type: ignore

            def _sync_call() -> str:
                resp = requests.post(
                    f"{self.ollama_url}/api/generate",
                    json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                    timeout=self.ollama_timeout,
                )
                return resp.json().get("response", "")

            text = await asyncio.to_thread(_sync_call)

        return self._parse_decision(text, judged_by="qwen")

    async def _judge_with_sonnet(self, message_text: str, channel_id: str, prd_content: str) -> UpdateDecision:
        """Sonnet(Claude subprocess)으로 정확한 판단"""
        if not self.claude_path:
            raise RuntimeError("Claude CLI를 찾을 수 없음")

        import os
        # CLAUDECODE 환경변수 제거 (중첩 세션 차단 우회)
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_SESSION_ID", None)

        prompt = self._build_sonnet_prompt(message_text, channel_id, prd_content)
        cmd = [self.claude_path, "-p", prompt, "--output-format", "text", "--model", "sonnet"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.sonnet_timeout)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            raise TimeoutError(f"Sonnet subprocess 타임아웃 ({self.sonnet_timeout}초)")

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace")
            logger.error(f"Sonnet subprocess stderr:\n{err_msg}")
            raise RuntimeError(f"Sonnet subprocess 실패: {err_msg[:500]}")

        output = stdout.decode(errors="replace").strip()
        decision = self._parse_decision(output, judged_by="sonnet")
        if decision.confidence == 0.0 and decision.judged_by != "fallback":
            decision = UpdateDecision(
                needs_update=decision.needs_update,
                section=decision.section,
                new_content=decision.new_content,
                judged_by="sonnet",
                confidence=0.85,
                reasoning=decision.reasoning,
            )
        return decision

    def _parse_decision(self, text: str, judged_by: str) -> UpdateDecision:
        """JSON 응답 파싱. 실패 시 fallback UpdateDecision 반환."""
        # JSON 블록 추출
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end])
                return UpdateDecision(
                    needs_update=bool(data.get("needs_update", False)),
                    section=data.get("section") or None,
                    new_content=data.get("new_content") or None,
                    judged_by=judged_by,
                    confidence=float(data.get("confidence", 0.5)),
                    reasoning=data.get("reasoning") or None,
                )
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.warning(f"JSON 파싱 실패 ({judged_by}): {e} / 원문: {text[:200]}")

        return UpdateDecision(
            needs_update=False,
            section=None,
            new_content=None,
            judged_by="fallback",
            confidence=0.0,
            reasoning="JSON 파싱 실패",
        )

    def _build_qwen_prompt(self, message_text: str, prd_content: str) -> str:
        """Qwen용 간결한 판단 프롬프트"""
        prd_summary = prd_content[:500] if prd_content else "(PRD 없음)"
        return f"""다음 Slack 메시지가 채널 지식 문서(PRD)를 업데이트해야 하는지 판단하세요.

메시지: {message_text}

현재 PRD 요약:
{prd_summary}

다음 JSON으로만 응답 (다른 텍스트 없이):
{{
  "needs_update": true/false,
  "section": "주요 토픽|핵심 의사결정|멤버 역할|최근 변경사항|커뮤니케이션 특성|기술 스택|반복 이슈 패턴 및 해결 가이드|Q&A 패턴|null",
  "new_content": "추가할 내용 또는 null",
  "confidence": 0.0~1.0,
  "reasoning": "판단 근거 한줄"
}}

needs_update=true 조건: 새로운 의사결정, 프로젝트 방향 변경, 역할 변경, 주요 완료 사항
needs_update=false 조건: 단순 잡담, 인사, 중복 정보, 일상 업무 대화"""

    def _build_sonnet_prompt(self, message_text: str, channel_id: str, prd_content: str) -> str:
        """Sonnet용 상세 판단 프롬프트"""
        prd_summary = prd_content[:1000] if prd_content else "(PRD 없음)"
        return f"""당신은 Slack 채널({channel_id})의 지식 문서 관리자입니다.
새로운 메시지를 보고 채널 PRD 문서를 업데이트해야 하는지 정확하게 판단하세요.

[새 메시지]
{message_text}

[현재 채널 PRD 문서]
{prd_summary}

업데이트가 필요한 경우:
- "주요 토픽": 새로운 반복 논의 주제 발견
- "핵심 의사결정": 팀의 공식 결정사항
- "멤버 역할": 역할/담당자 변경
- "최근 변경사항": 주요 완료/변경 사항
- "커뮤니케이션 특성": 채널 문화/규칙 변경
- "기술 스택": 새로운 기술/도구 도입
- "반복 이슈 패턴 및 해결 가이드": 반복 오류 또는 해결책 발견
- "Q&A 패턴": 자주 묻는 질문 패턴 발견

다음 JSON으로만 응답 (다른 텍스트 없이):
{{
  "needs_update": true/false,
  "section": "섹션명 또는 null",
  "new_content": "추가할 마크다운 내용 또는 null",
  "reasoning": "판단 근거를 2-3문장으로"
}}"""

    def _load_prd(self, channel_id: str) -> str:
        """PRD 파일 로드 (없으면 빈 문자열)"""
        prd_path = CHANNEL_DOCS_DIR / f"{channel_id}.md"
        if not prd_path.exists():
            return ""
        try:
            return prd_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"PRD 파일 읽기 실패: {prd_path} / {e}")
            return ""
