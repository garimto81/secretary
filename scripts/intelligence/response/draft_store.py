"""
DraftStore - 응답 초안 저장 및 관리

생성된 draft를 파일 + DB에 저장하고, Toast 알림을 전송합니다.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from ..context_store import IntelligenceStorage


DEFAULT_DRAFTS_DIR = Path(r"C:\claude\secretary\data\drafts")


class DraftStore:
    """응답 초안 저장소"""

    def __init__(self, storage: IntelligenceStorage, drafts_dir: Optional[Path] = None):
        self.storage = storage
        self.drafts_dir = drafts_dir or DEFAULT_DRAFTS_DIR
        self.drafts_dir.mkdir(parents=True, exist_ok=True)

    async def save(
        self,
        project_id: str,
        source_channel: str,
        source_message_id: Optional[str],
        sender_id: str,
        sender_name: Optional[str],
        original_text: str,
        draft_text: str,
        match_confidence: float,
        match_tier: str,
    ) -> Dict[str, Any]:
        """
        Draft 저장 (파일 + DB + Toast)

        Returns:
            저장 결과 dict (draft_id, draft_file)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_project = project_id.replace("/", "_").replace("\\", "_")
        draft_filename = f"{safe_project}_{source_channel}_{timestamp}.md"
        draft_path = self.drafts_dir / draft_filename

        draft_content = self._format_draft_file(
            project_id=project_id,
            source_channel=source_channel,
            sender_name=sender_name or sender_id,
            original_text=original_text,
            draft_text=draft_text,
            match_confidence=match_confidence,
            match_tier=match_tier,
        )
        draft_path.write_text(draft_content, encoding="utf-8")

        draft_id = await self.storage.save_draft({
            "project_id": project_id,
            "source_channel": source_channel,
            "source_message_id": source_message_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "original_text": original_text[:4000] if original_text else "",
            "draft_text": draft_text,
            "draft_file": str(draft_path),
            "match_confidence": match_confidence,
            "match_tier": match_tier,
            "match_status": "matched",
            "status": "pending",
        })

        self._send_toast(project_id, sender_name or sender_id, source_channel)

        return {
            "draft_id": draft_id,
            "draft_file": str(draft_path),
        }

    def _format_draft_file(self, **kwargs) -> str:
        """Draft 파일 내용 포맷"""
        return (
            f"# Draft Response\n\n"
            f"- Project: {kwargs['project_id']}\n"
            f"- Channel: {kwargs['source_channel']}\n"
            f"- Sender: {kwargs['sender_name']}\n"
            f"- Match: {kwargs['match_tier']} (confidence: {kwargs['match_confidence']:.2f})\n"
            f"- Generated: {datetime.now().isoformat()}\n\n"
            f"## Original Message\n\n"
            f"{kwargs['original_text'][:2000]}\n\n"
            f"## Draft Response\n\n"
            f"{kwargs['draft_text']}\n"
        )

    def _send_toast(self, project_id: str, sender: str, channel: str) -> None:
        """Toast 알림 전송"""
        if sys.platform != "win32":
            return

        try:
            from winotify import Notification, audio

            toast = Notification(
                app_id="Secretary AI",
                title=f"[{channel.upper()}] {sender}",
                msg=f"프로젝트 '{project_id}'에 대한 응답 초안이 생성되었습니다.",
                duration="short",
            )
            toast.set_audio(audio.Default, loop=False)
            toast.show()
        except ImportError:
            pass
        except Exception:
            pass
