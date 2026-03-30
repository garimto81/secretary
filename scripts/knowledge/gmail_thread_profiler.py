"""GmailThreadProfiler — Gmail 스레드 Sonnet 초기 분석 및 컨텍스트 저장"""
import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from scripts.shared.paths import GMAIL_CONTEXTS_DIR as GMAIL_CONTEXT_DIR
except ImportError:
    try:
        from shared.paths import GMAIL_CONTEXTS_DIR as GMAIL_CONTEXT_DIR
    except ImportError:
        GMAIL_CONTEXT_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "gmail_contexts"


class GmailThreadProfiler:
    def __init__(self, model: str = "sonnet", timeout: int = 120):
        self.model = model
        self.timeout = timeout
        self.claude_path = shutil.which("claude")

    async def build_thread_context(
        self,
        thread_id: str,
        messages: list,
        force: bool = False,
    ) -> dict:
        """Gmail 스레드 컨텍스트 생성. 실패 시 기본 context 저장."""
        GMAIL_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = GMAIL_CONTEXT_DIR / f"{thread_id}.json"

        if out_path.exists() and not force:
            return json.loads(out_path.read_text(encoding="utf-8"))

        # 메시지 텍스트 수집
        texts = [
            m.get("content", "") if isinstance(m, dict) else getattr(m, "content", "")
            for m in messages[:10]
        ]
        combined = "\n---\n".join(t[:500] for t in texts if t)

        result = await self._build_via_sonnet(thread_id, combined) if self.claude_path and combined else None

        if not result:
            result = {
                "thread_id": thread_id,
                "built_at": datetime.now().isoformat(),
                "thread_summary": f"Gmail 스레드 {thread_id}",
                "participants": [],
                "pending_action": None,
                "tone": "formal",
                "response_guidelines": "공식 어조. 답변 끝에 다음 단계 명시.",
            }
        else:
            result["thread_id"] = thread_id
            result["built_at"] = datetime.now().isoformat()

        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    async def _build_via_sonnet(self, thread_id: str, combined_text: str) -> dict | None:
        prompt = f"""다음 Gmail 스레드({thread_id})의 내용을 분석하여 JSON으로 요약하세요.

스레드 내용:
{combined_text[:3000]}

다음 JSON 형식으로만 응답:
{{
  "thread_summary": "스레드 주제 + 현재 상태 (2문장)",
  "participants": ["email1@...", "email2@..."],
  "pending_action": "상대방이 요청한 액션 또는 null",
  "tone": "formal/informal/urgent",
  "response_guidelines": "응답 시 고려사항"
}}"""
        try:
            cmd = [self.claude_path, "-p", prompt, "--output-format", "text", "--model", self.model]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            except TimeoutError:
                proc.kill()
                await proc.communicate()  # 리소스 정리
                raise
            output = stdout.decode(errors="replace").strip()
            start, end = output.find("{"), output.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(output[start:end])
        except Exception as e:
            logger.warning(f"Gmail 스레드 Sonnet 분석 실패: {e}")
        return None
