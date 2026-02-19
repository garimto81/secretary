"""ChannelProfileStore - 채널 메타데이터 SQLite 저장/조회"""

import json
import aiosqlite
from pathlib import Path
from typing import Optional
from datetime import datetime

# 3중 import fallback
try:
    from scripts.knowledge.models import ChannelProfile
except ImportError:
    try:
        from knowledge.models import ChannelProfile
    except ImportError:
        from .models import ChannelProfile


DEFAULT_DB_PATH = Path(r"C:\claude\secretary\data\knowledge.db")

CHANNEL_PROFILE_SCHEMA = """
CREATE TABLE IF NOT EXISTS channel_profiles (
    channel_id TEXT PRIMARY KEY,
    channel_name TEXT,
    topic TEXT DEFAULT '',
    purpose TEXT DEFAULT '',
    created DATETIME,
    members_json TEXT DEFAULT '[]',
    pinned_json TEXT DEFAULT '[]',
    collected_at DATETIME,
    total_messages INTEGER DEFAULT 0,
    total_threads INTEGER DEFAULT 0
);
"""


class ChannelProfileStore:
    """채널 프로파일 SQLite 저장/조회

    기존 knowledge.db에 channel_profiles 테이블을 추가합니다.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: Optional[aiosqlite.Connection] = None

    async def init_db(self) -> None:
        """DB 연결 및 channel_profiles 테이블 생성"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.executescript(CHANNEL_PROFILE_SCHEMA)
        await self._connection.commit()

    async def close(self) -> None:
        """DB 연결 종료"""
        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None

    async def __aenter__(self):
        await self.init_db()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def save(self, profile: ChannelProfile) -> None:
        """채널 프로파일 저장 (UPSERT)"""
        if not self._connection:
            raise RuntimeError("ChannelProfileStore not connected. Call init_db() first.")

        members_json = json.dumps(profile.members, ensure_ascii=False)
        pinned_json = json.dumps(profile.pinned_messages, ensure_ascii=False)
        created_str = profile.created.isoformat() if profile.created else None
        collected_str = profile.collected_at.isoformat() if profile.collected_at else datetime.now().isoformat()

        await self._connection.execute(
            """INSERT OR REPLACE INTO channel_profiles
            (channel_id, channel_name, topic, purpose, created,
             members_json, pinned_json, collected_at, total_messages, total_threads)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                profile.channel_id,
                profile.channel_name,
                profile.topic,
                profile.purpose,
                created_str,
                members_json,
                pinned_json,
                collected_str,
                profile.total_messages,
                profile.total_threads,
            ),
        )
        await self._connection.commit()

    async def get(self, channel_id: str) -> Optional[ChannelProfile]:
        """채널 프로파일 조회"""
        if not self._connection:
            raise RuntimeError("ChannelProfileStore not connected. Call init_db() first.")

        async with self._connection.execute(
            "SELECT * FROM channel_profiles WHERE channel_id = ?",
            (channel_id,),
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None

            data = dict(row)

            members = []
            if data.get("members_json"):
                try:
                    members = json.loads(data["members_json"])
                except json.JSONDecodeError:
                    members = []

            pinned = []
            if data.get("pinned_json"):
                try:
                    pinned = json.loads(data["pinned_json"])
                except json.JSONDecodeError:
                    pinned = []

            created = None
            if data.get("created"):
                try:
                    created = datetime.fromisoformat(data["created"])
                except (ValueError, TypeError):
                    pass

            collected_at = None
            if data.get("collected_at"):
                try:
                    collected_at = datetime.fromisoformat(data["collected_at"])
                except (ValueError, TypeError):
                    pass

            return ChannelProfile(
                channel_id=data["channel_id"],
                channel_name=data["channel_name"] or "",
                topic=data.get("topic") or "",
                purpose=data.get("purpose") or "",
                created=created,
                members=members,
                pinned_messages=pinned,
                collected_at=collected_at,
                total_messages=data.get("total_messages", 0),
                total_threads=data.get("total_threads", 0),
            )
