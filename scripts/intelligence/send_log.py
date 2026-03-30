"""
SendLogger - 전송 이력 JSONL 로그

모든 전송 시도를 data/send_log.jsonl에 append 방식으로 기록한다.
"""

import json
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_PATH = Path(r"C:\claude\secretary\data\send_log.jsonl")


class SendLogger:
    """전송 이력 JSONL 로그"""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or DEFAULT_LOG_PATH

    def log_send(
        self,
        draft_id: int,
        channel: str,
        recipient: str,
        status: str,          # "sent" | "failed" | "draft_created"
        message_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """전송 시도 기록 (동기, append)"""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "timestamp": datetime.now().isoformat(),
            "draft_id": draft_id,
            "channel": channel,
            "recipient": recipient,
            "status": status,
            "message_id": message_id,
            "error": error,
            "operator": "cli",
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_recent(self, limit: int = 20) -> list[dict]:
        """최근 전송 이력 조회 (역순)"""
        if not self.log_path.exists():
            return []

        lines = self.log_path.read_text(encoding="utf-8").strip().split("\n")
        lines = [l for l in lines if l.strip()]

        records = []
        for line in reversed(lines):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= limit:
                break

        return records
