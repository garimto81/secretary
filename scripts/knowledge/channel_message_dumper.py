"""ChannelMessageDumper — Slack 채널 전체 메시지를 JSON으로 덤프"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from scripts.shared.paths import CHANNEL_DUMPS_DIR
except ImportError:
    try:
        from shared.paths import CHANNEL_DUMPS_DIR
    except ImportError:
        CHANNEL_DUMPS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "channel_dumps"


class ChannelMessageDumper:
    """Slack 채널의 전체 메시지를 JSON 파일로 덤프."""

    def __init__(self, dump_dir: Path | None = None):
        self._dump_dir = dump_dir or CHANNEL_DUMPS_DIR
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from lib.slack import SlackClient
            self._client = SlackClient()

    async def dump(self, channel_id: str, channel_name: str = "", force: bool = False) -> Path:
        """전체 메시지 덤프. force=False면 기존 있으면 증분만 추가."""
        self._dump_dir.mkdir(parents=True, exist_ok=True)
        dump_path = self._dump_dir / f"{channel_id}.json"

        existing = self._load_existing(dump_path)
        oldest_ts = None
        existing_messages = []

        if existing and not force:
            existing_messages = existing.get("messages", [])
            oldest_ts = existing.get("last_ts")
            if oldest_ts:
                logger.info(f"[Dumper] {channel_id}: 증분 수집 (oldest_ts={oldest_ts}, 기존 {len(existing_messages)}개)")

        await asyncio.to_thread(self._ensure_client)

        if force or not existing:
            new_messages = await self._collect_full(channel_id)
        else:
            new_messages = await self._collect_incremental(channel_id, oldest_ts)

        if existing_messages and new_messages:
            existing_ts_set = {m["ts"] for m in existing_messages}
            new_messages = [m for m in new_messages if m["ts"] not in existing_ts_set]

        all_messages = existing_messages + new_messages
        # 최대 10000건 유지 (최신 우선)
        all_messages.sort(key=lambda m: m["ts"])
        if len(all_messages) > 10000:
            all_messages = all_messages[-10000:]

        last_ts = all_messages[-1]["ts"] if all_messages else (oldest_ts or "")
        data = {
            "channel_id": channel_id,
            "channel_name": channel_name or channel_id,
            "dump_date": datetime.now().isoformat(),
            "last_ts": last_ts,
            "total_messages": len(all_messages),
            "messages": all_messages,
        }
        self._save(dump_path, data)
        logger.info(f"[Dumper] {channel_id}: {len(all_messages)}개 메시지 저장 ({dump_path})")
        return dump_path

    async def _collect_full(self, channel_id: str) -> list[dict]:
        """cursor 기반 전체 페이지네이션 수집."""
        all_messages = []
        cursor = None
        page = 0
        while True:
            page += 1
            messages_raw, next_cursor = await asyncio.to_thread(
                self._client.get_history_with_cursor,
                channel_id, 200, None, cursor,
            )
            if not messages_raw:
                break
            for msg in messages_raw:
                all_messages.append(self._normalize_message(msg))
            logger.info(f"[Dumper] {channel_id}: page {page}, 누적 {len(all_messages)}개")
            if not next_cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(1.2)
        return all_messages

    async def _collect_incremental(self, channel_id: str, oldest_ts: str | None) -> list[dict]:
        """oldest_ts 이후 메시지만 수집."""
        all_messages = []
        cursor = None
        while True:
            messages_raw, next_cursor = await asyncio.to_thread(
                self._client.get_history_with_cursor,
                channel_id, 200, oldest_ts, cursor,
            )
            if not messages_raw:
                break
            for msg in messages_raw:
                n = self._normalize_message(msg)
                if oldest_ts and n["ts"] <= oldest_ts:
                    continue
                all_messages.append(n)
            if not next_cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(1.2)
        return all_messages

    def _normalize_message(self, msg) -> dict:
        """SlackMessage 또는 dict를 정규화된 dict로 변환."""
        if hasattr(msg, 'ts'):
            ts = msg.ts
            user = getattr(msg, 'user', '') or ''
            text = getattr(msg, 'text', '') or ''
            thread_ts = getattr(msg, 'thread_ts', None)
        else:
            ts = msg.get('ts', '')
            user = msg.get('user', '') or ''
            text = msg.get('text', '') or ''
            thread_ts = msg.get('thread_ts')
        # thread_ts가 ts와 같으면 None
        if thread_ts == ts:
            thread_ts = None
        return {
            "ts": ts,
            "user": user,
            "text": text[:4000],
            "thread_ts": thread_ts,
        }

    def _load_existing(self, dump_path: Path) -> dict | None:
        if not dump_path.exists():
            return None
        try:
            return json.loads(dump_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[Dumper] 기존 덤프 로드 실패: {e}")
            return None

    def _save(self, dump_path: Path, data: dict) -> None:
        dump_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Slack 채널 전체 메시지 덤프")
    parser.add_argument("--channel", required=True, help="채널 ID (예: C0985UXQN6Q)")
    parser.add_argument("--name", default="", help="채널 이름 (선택)")
    parser.add_argument("--force", action="store_true", help="기존 덤프 무시하고 전체 재수집")
    args = parser.parse_args()

    async def _main():
        dumper = ChannelMessageDumper()
        path = await dumper.dump(args.channel, args.name, args.force)
        print(f"덤프 완료: {path}")

    asyncio.run(_main())
