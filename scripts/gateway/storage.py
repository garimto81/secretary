"""
통합 메시지 스토리지

SQLite 기반 비동기 스토리지로 모든 채널의 메시지를 저장하고 조회합니다.

Note:
    NormalizedMessage는 models.py에서 정의된 것을 사용합니다.
    이 모듈은 models.NormalizedMessage를 DB 형식으로 변환/저장하는 역할을 합니다.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

# models.py의 NormalizedMessage 사용 (단일 정의)
try:
    from scripts.gateway.models import ChannelType, MessageType, NormalizedMessage, Priority
except ImportError:
    try:
        from gateway.models import ChannelType, MessageType, NormalizedMessage, Priority
    except ImportError:
        from .models import ChannelType, MessageType, NormalizedMessage, Priority

# 기본 DB 경로
DEFAULT_DB_PATH = Path(r"C:\claude\secretary\data\gateway.db")

# SQL Schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT,
    text TEXT,
    message_type TEXT DEFAULT 'text',
    timestamp DATETIME NOT NULL,
    is_group BOOLEAN DEFAULT FALSE,
    is_mention BOOLEAN DEFAULT FALSE,
    reply_to_id TEXT,
    media_urls TEXT,
    raw_json TEXT,
    priority TEXT,
    has_action BOOLEAN DEFAULT FALSE,
    processed_at DATETIME,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_channel ON messages(channel);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_messages_priority ON messages(priority);
CREATE INDEX IF NOT EXISTS idx_messages_processed ON messages(processed_at);
"""


def _message_to_db_dict(message: NormalizedMessage, received_at: datetime | None = None,
                        project_id: str | None = None) -> dict[str, Any]:
    """NormalizedMessage를 DB 저장용 딕셔너리로 변환"""
    data = {
        'id': message.id,
        'channel': message.channel.value if isinstance(message.channel, ChannelType) else message.channel,
        'channel_id': message.channel_id,
        'sender_id': message.sender_id,
        'sender_name': message.sender_name,
        'text': message.text,
        'message_type': message.message_type.value if isinstance(message.message_type, MessageType) else message.message_type,
        'timestamp': message.timestamp.isoformat() if message.timestamp else None,
        'is_group': message.is_group,
        'is_mention': message.is_mention,
        'reply_to_id': message.reply_to_id,
        'media_urls': json.dumps(message.media_urls) if message.media_urls else None,
        'raw_json': message.raw_json,
        'priority': message.priority.value if isinstance(message.priority, Priority) else message.priority,
        'has_action': message.has_action,
        'project_id': project_id or message.project_id,
        'processed_at': None,
        'received_at': (received_at or datetime.now()).isoformat(),
    }
    return data


def _db_row_to_message(row: dict[str, Any]) -> NormalizedMessage:
    """
    DB 행을 NormalizedMessage로 변환

    Args:
        row: DB 행 데이터

    Returns:
        NormalizedMessage 인스턴스
    """
    data = dict(row)

    # 채널 타입 변환
    channel = data.get('channel', 'unknown')
    try:
        channel = ChannelType(channel)
    except ValueError:
        channel = ChannelType.UNKNOWN

    # 메시지 타입 변환
    message_type = data.get('message_type', 'text')
    try:
        message_type = MessageType(message_type)
    except ValueError:
        message_type = MessageType.TEXT

    # 우선순위 변환
    priority = data.get('priority')
    if priority:
        try:
            priority = Priority(priority)
        except ValueError:
            priority = None

    # 타임스탬프 변환
    timestamp = data.get('timestamp')
    if timestamp and isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)

    # 미디어 URL 변환
    media_urls = data.get('media_urls')
    if media_urls and isinstance(media_urls, str):
        media_urls = json.loads(media_urls)

    return NormalizedMessage(
        id=data['id'],
        channel=channel,
        channel_id=data['channel_id'],
        sender_id=data['sender_id'],
        sender_name=data.get('sender_name'),
        text=data.get('text', ''),
        message_type=message_type,
        timestamp=timestamp or datetime.now(),
        is_group=bool(data.get('is_group', False)),
        is_mention=bool(data.get('is_mention', False)),
        reply_to_id=data.get('reply_to_id'),
        media_urls=media_urls or [],
        raw_json=data.get('raw_json'),
        priority=priority,
        has_action=bool(data.get('has_action', False)),
        project_id=data.get('project_id'),
    )


class UnifiedStorage:
    """
    통합 메시지 스토리지

    Features:
    - 모든 채널의 메시지 저장
    - 인덱싱으로 빠른 조회
    - 비동기 SQLite 사용

    Example:
        async with UnifiedStorage() as storage:
            await storage.save_message(message)
            recent = await storage.get_recent_messages(channel='kakao', limit=10)
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: aiosqlite.Connection | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self) -> None:
        """DB 연결 및 스키마 초기화"""
        # data 디렉토리 생성
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # DB 연결
        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row

        # 스키마 초기화
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

        # 마이그레이션
        await self._migrate_enrichments_column()
        await self._migrate_project_id_column()

    async def _migrate_enrichments_column(self) -> None:
        """enrichments 컬럼 추가 (멱등)"""
        try:
            await self._connection.execute(
                "ALTER TABLE messages ADD COLUMN enrichments TEXT"
            )
            await self._connection.commit()
        except Exception as e:
            if "duplicate column" in str(e).lower():
                pass
            else:
                raise

    async def _migrate_project_id_column(self) -> None:
        """project_id 컬럼 + 인덱스 추가 (멱등)"""
        try:
            await self._connection.execute(
                "ALTER TABLE messages ADD COLUMN project_id TEXT"
            )
            await self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_project_id ON messages(project_id)"
            )
            await self._connection.commit()
        except Exception as e:
            if "duplicate column" in str(e).lower():
                pass
            else:
                raise

    async def close(self) -> None:
        """DB 연결 종료"""
        if self._connection:
            try:
                await self._connection.close()
            except Exception:
                pass
            self._connection = None

    async def save_message(self, message: NormalizedMessage, received_at: datetime | None = None,
                           project_id: str | None = None) -> str:
        """메시지 저장 (project_id 포함)"""
        if not self._connection:
            raise RuntimeError("Storage not connected. Use 'async with' or call connect() first.")

        data = _message_to_db_dict(message, received_at, project_id=project_id)
        columns = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])

        query = f"INSERT OR REPLACE INTO messages ({columns}) VALUES ({placeholders})"
        await self._connection.execute(query, list(data.values()))
        await self._connection.commit()

        return message.id

    async def get_message(self, message_id: str) -> NormalizedMessage | None:
        """
        메시지 조회

        Args:
            message_id: 메시지 ID

        Returns:
            조회된 메시지 또는 None
        """
        if not self._connection:
            raise RuntimeError("Storage not connected. Use 'async with' or call connect() first.")

        async with self._connection.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return _db_row_to_message(row)
            return None

    async def get_recent_messages(
        self,
        channel: str | None = None,
        limit: int = 50,
        since: datetime | None = None,
        project_id: str | None = None,
    ) -> list[NormalizedMessage]:
        """최근 메시지 조회 (project_id 필터 지원)"""
        if not self._connection:
            raise RuntimeError("Storage not connected. Use 'async with' or call connect() first.")

        query = "SELECT * FROM messages WHERE 1=1"
        params = []

        if channel:
            query += " AND channel = ?"
            params.append(channel)

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [_db_row_to_message(row) for row in rows]

    async def get_unprocessed_messages(self) -> list[NormalizedMessage]:
        """
        처리되지 않은 메시지 조회

        Returns:
            미처리 메시지 리스트 (오래된 순)
        """
        if not self._connection:
            raise RuntimeError("Storage not connected. Use 'async with' or call connect() first.")

        query = """
            SELECT * FROM messages
            WHERE processed_at IS NULL
            ORDER BY timestamp ASC
        """

        async with self._connection.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [_db_row_to_message(row) for row in rows]

    async def mark_processed(self, message_id: str) -> None:
        """
        메시지 처리 완료 표시

        Args:
            message_id: 메시지 ID
        """
        if not self._connection:
            raise RuntimeError("Storage not connected. Use 'async with' or call connect() first.")

        await self._connection.execute(
            "UPDATE messages SET processed_at = ? WHERE id = ?",
            (datetime.now().isoformat(), message_id)
        )
        await self._connection.commit()

    async def get_stats(self) -> dict[str, Any]:
        """
        스토리지 통계 조회

        Returns:
            통계 딕셔너리 (총 메시지 수, 채널별 메시지 수, 미처리 메시지 수)
        """
        if not self._connection:
            raise RuntimeError("Storage not connected. Use 'async with' or call connect() first.")

        # 총 메시지 수
        async with self._connection.execute("SELECT COUNT(*) as total FROM messages") as cursor:
            total_row = await cursor.fetchone()
            total = total_row['total']

        # 채널별 메시지 수
        async with self._connection.execute(
            "SELECT channel, COUNT(*) as count FROM messages GROUP BY channel"
        ) as cursor:
            channel_rows = await cursor.fetchall()
            by_channel = {row['channel']: row['count'] for row in channel_rows}

        # 미처리 메시지 수
        async with self._connection.execute(
            "SELECT COUNT(*) as unprocessed FROM messages WHERE processed_at IS NULL"
        ) as cursor:
            unprocessed_row = await cursor.fetchone()
            unprocessed = unprocessed_row['unprocessed']

        return {
            'total_messages': total,
            'by_channel': by_channel,
            'unprocessed': unprocessed
        }
