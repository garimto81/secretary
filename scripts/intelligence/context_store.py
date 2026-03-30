"""
IntelligenceStorage - Project Intelligence DB

SQLite WAL mode, 4 테이블:
- projects: 프로젝트 등록 정보
- context_entries: 수집된 컨텍스트 항목
- analysis_state: 증분 분석 체크포인트
- draft_responses: 생성된 응답 초안
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

DEFAULT_DB_PATH = Path(r"C:\claude\secretary\data\intelligence.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    github_repos TEXT,
    slack_channels TEXT,
    gmail_queries TEXT,
    keywords TEXT,
    contacts TEXT,
    config_json TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS context_entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    entry_type TEXT NOT NULL,
    title TEXT,
    content TEXT,
    metadata_json TEXT,
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS analysis_state (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,
    checkpoint_key TEXT NOT NULL,
    checkpoint_value TEXT,
    last_run_at DATETIME,
    entries_collected INTEGER DEFAULT 0,
    error_message TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    UNIQUE(project_id, source, checkpoint_key)
);

CREATE TABLE IF NOT EXISTS draft_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,
    source_channel TEXT NOT NULL,
    source_message_id TEXT,
    sender_id TEXT,
    sender_name TEXT,
    original_text TEXT,
    draft_text TEXT,
    draft_file TEXT,
    match_confidence REAL DEFAULT 0.0,
    match_tier TEXT,
    match_status TEXT DEFAULT 'matched',
    status TEXT DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    reviewer_note TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX IF NOT EXISTS idx_context_project ON context_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_context_source ON context_entries(source);
CREATE INDEX IF NOT EXISTS idx_context_collected ON context_entries(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_state_project_source ON analysis_state(project_id, source);
CREATE INDEX IF NOT EXISTS idx_draft_status ON draft_responses(status);
CREATE INDEX IF NOT EXISTS idx_draft_match_status ON draft_responses(match_status);
CREATE INDEX IF NOT EXISTS idx_draft_project ON draft_responses(project_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_draft_unique_message
ON draft_responses(source_channel, source_message_id)
WHERE source_message_id IS NOT NULL;
"""


class IntelligenceStorage:
    """
    Project Intelligence SQLite Storage

    WAL mode로 Gateway(async writer)와 CLI(reader) 동시 접근 지원.
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
        """DB 연결 및 스키마 초기화 (WAL mode)"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row

        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()
        await self._migrate_draft_columns()
        await self._migrate_feedback_table()

    async def _migrate_feedback_table(self):
        """feedback_responses 테이블 추가 (멱등)"""
        migrations = [
            """CREATE TABLE IF NOT EXISTS feedback_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id INTEGER NOT NULL UNIQUE,
                decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
                reason TEXT,
                modification_summary TEXT,
                feedback_quality_score INTEGER DEFAULT 5
                    CHECK (feedback_quality_score IS NULL OR feedback_quality_score BETWEEN 1 AND 5),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (draft_id) REFERENCES draft_responses(id) ON DELETE CASCADE
            )""",
            "CREATE INDEX IF NOT EXISTS idx_feedback_draft ON feedback_responses(draft_id)",
            "CREATE INDEX IF NOT EXISTS idx_feedback_decision ON feedback_responses(decision)",
            "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_responses(created_at DESC)",
        ]
        for sql in migrations:
            try:
                await self._connection.execute(sql)
                await self._connection.commit()
            except Exception as e:
                if "already exists" in str(e).lower():
                    pass
                else:
                    raise

    async def _migrate_draft_columns(self):
        """draft_responses에 전송 관련 컬럼 추가 (멱등)"""
        migrations = [
            "ALTER TABLE draft_responses ADD COLUMN sent_at DATETIME",
            "ALTER TABLE draft_responses ADD COLUMN send_error TEXT",
            "ALTER TABLE draft_responses ADD COLUMN ollama_reasoning TEXT",
        ]
        for sql in migrations:
            try:
                await self._connection.execute(sql)
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

    def _ensure_connected(self):
        if not self._connection:
            raise RuntimeError("Storage not connected. Use 'async with' or call connect() first.")

    # ==========================================
    # Projects
    # ==========================================

    async def save_project(self, project: dict[str, Any]) -> str:
        """프로젝트 저장 (upsert)"""
        self._ensure_connected()

        await self._connection.execute(
            """INSERT OR REPLACE INTO projects
            (id, name, description, github_repos, slack_channels,
             gmail_queries, keywords, contacts, config_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                project["id"],
                project["name"],
                project.get("description", ""),
                json.dumps(project.get("github_repos", []), ensure_ascii=False),
                json.dumps(project.get("slack_channels", []), ensure_ascii=False),
                json.dumps(project.get("gmail_queries", []), ensure_ascii=False),
                json.dumps(project.get("keywords", []), ensure_ascii=False),
                json.dumps(project.get("contacts", []), ensure_ascii=False),
                json.dumps(project.get("config", {}), ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        await self._connection.commit()
        return project["id"]

    async def get_project(self, project_id: str) -> dict[str, Any] | None:
        """프로젝트 조회"""
        self._ensure_connected()

        async with self._connection.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return self._row_to_project(row)
            return None

    async def list_projects(self) -> list[dict[str, Any]]:
        """전체 프로젝트 목록"""
        self._ensure_connected()

        async with self._connection.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [self._row_to_project(row) for row in rows]

    async def delete_project(self, project_id: str) -> bool:
        """프로젝트 삭제"""
        self._ensure_connected()

        await self._connection.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        await self._connection.commit()
        return True

    def _row_to_project(self, row) -> dict[str, Any]:
        data = dict(row)
        for field in ("github_repos", "slack_channels", "gmail_queries", "keywords", "contacts"):
            if data.get(field) and isinstance(data[field], str):
                data[field] = json.loads(data[field])
        if data.get("config_json") and isinstance(data["config_json"], str):
            data["config"] = json.loads(data["config_json"])
            del data["config_json"]
        return data

    # ==========================================
    # Context Entries
    # ==========================================

    async def save_context_entry(self, entry: dict[str, Any]) -> str:
        """컨텍스트 항목 저장 (upsert)"""
        self._ensure_connected()

        await self._connection.execute(
            """INSERT OR REPLACE INTO context_entries
            (id, project_id, source, source_id, entry_type, title, content, metadata_json, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry["id"],
                entry["project_id"],
                entry["source"],
                entry.get("source_id"),
                entry["entry_type"],
                entry.get("title", ""),
                entry.get("content", ""),
                json.dumps(entry.get("metadata", {}), ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        await self._connection.commit()
        return entry["id"]

    async def get_context_entries(
        self,
        project_id: str,
        source: str | None = None,
        entry_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """프로젝트별 컨텍스트 항목 조회"""
        self._ensure_connected()

        query = "SELECT * FROM context_entries WHERE project_id = ?"
        params: list = [project_id]

        if source:
            query += " AND source = ?"
            params.append(source)
        if entry_type:
            query += " AND entry_type = ?"
            params.append(entry_type)

        query += " ORDER BY collected_at DESC LIMIT ?"
        params.append(limit)

        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                data = dict(row)
                if data.get("metadata_json") and isinstance(data["metadata_json"], str):
                    data["metadata"] = json.loads(data["metadata_json"])
                    del data["metadata_json"]
                result.append(data)
            return result

    # ==========================================
    # Analysis State
    # ==========================================

    async def save_analysis_state(
        self,
        project_id: str,
        source: str,
        checkpoint_key: str,
        checkpoint_value: str,
        entries_collected: int = 0,
        error_message: str | None = None,
    ) -> None:
        """분석 상태 체크포인트 저장"""
        self._ensure_connected()

        state_id = f"{project_id}:{source}:{checkpoint_key}"
        await self._connection.execute(
            """INSERT OR REPLACE INTO analysis_state
            (id, project_id, source, checkpoint_key, checkpoint_value,
             last_run_at, entries_collected, error_message, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                state_id,
                project_id,
                source,
                checkpoint_key,
                checkpoint_value,
                datetime.now().isoformat(),
                entries_collected,
                error_message,
                datetime.now().isoformat(),
            ),
        )
        await self._connection.commit()

    async def get_analysis_state(
        self,
        project_id: str,
        source: str,
        checkpoint_key: str,
    ) -> dict[str, Any] | None:
        """분석 상태 조회"""
        self._ensure_connected()

        async with self._connection.execute(
            """SELECT * FROM analysis_state
            WHERE project_id = ? AND source = ? AND checkpoint_key = ?""",
            (project_id, source, checkpoint_key),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    # ==========================================
    # Draft Responses
    # ==========================================

    async def save_draft(self, draft: dict[str, Any]) -> int:
        """응답 초안 저장"""
        self._ensure_connected()

        cursor = await self._connection.execute(
            """INSERT OR REPLACE INTO draft_responses
            (project_id, source_channel, source_message_id, sender_id, sender_name,
             original_text, draft_text, draft_file, match_confidence, match_tier,
             match_status, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                draft.get("project_id"),
                draft["source_channel"],
                draft.get("source_message_id"),
                draft.get("sender_id"),
                draft.get("sender_name"),
                draft.get("original_text"),
                draft.get("draft_text"),
                draft.get("draft_file"),
                draft.get("match_confidence", 0.0),
                draft.get("match_tier"),
                draft.get("match_status", "matched"),
                draft.get("status", "pending"),
            ),
        )
        await self._connection.commit()
        return cursor.lastrowid

    async def get_draft(self, draft_id: int) -> dict[str, Any] | None:
        """초안 조회"""
        self._ensure_connected()

        async with self._connection.execute(
            "SELECT * FROM draft_responses WHERE id = ?", (draft_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def list_drafts(
        self,
        status: str | None = None,
        match_status: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """초안 목록 조회"""
        self._ensure_connected()

        query = "SELECT * FROM draft_responses WHERE 1=1"
        params: list = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if match_status:
            query += " AND match_status = ?"
            params.append(match_status)
        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_draft_status(
        self,
        draft_id: int,
        status: str,
        reviewer_note: str | None = None,
    ) -> bool:
        """초안 상태 업데이트 (approve/reject)"""
        self._ensure_connected()

        await self._connection.execute(
            """UPDATE draft_responses
            SET status = ?, reviewed_at = ?, reviewer_note = ?
            WHERE id = ?""",
            (status, datetime.now().isoformat(), reviewer_note, draft_id),
        )
        await self._connection.commit()
        return True

    async def update_draft_sent(
        self,
        draft_id: int,
        message_id: str | None = None,
    ) -> bool:
        """전송 성공 기록"""
        self._ensure_connected()
        if message_id:
            await self._connection.execute(
                """UPDATE draft_responses
                SET status = 'sent', sent_at = ?, reviewer_note = COALESCE(reviewer_note, '') || CASE WHEN reviewer_note IS NOT NULL AND reviewer_note != '' THEN char(10) ELSE '' END || '[sent_message_id: ' || ? || ']'
                WHERE id = ?""",
                (datetime.now().isoformat(), message_id, draft_id),
            )
        else:
            await self._connection.execute(
                """UPDATE draft_responses
                SET status = 'sent', sent_at = ?
                WHERE id = ?""",
                (datetime.now().isoformat(), draft_id),
            )
        await self._connection.commit()
        return True

    async def update_draft_send_failed(
        self,
        draft_id: int,
        error_message: str,
    ) -> bool:
        """전송 실패 기록"""
        self._ensure_connected()
        await self._connection.execute(
            """UPDATE draft_responses
            SET status = 'send_failed', send_error = ?
            WHERE id = ?""",
            (error_message, draft_id),
        )
        await self._connection.commit()
        return True

    async def get_awaiting_drafts(
        self,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """매칭되었지만 draft 미생성 메시지 조회"""
        self._ensure_connected()

        query = """SELECT * FROM draft_responses
            WHERE status = 'awaiting_draft' AND match_status = 'matched'"""
        params: list = []

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        async with self._connection.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def save_draft_text(
        self,
        draft_id: int,
        draft_text: str,
        draft_file: str | None = None,
    ) -> bool:
        """awaiting_draft 메시지에 draft 텍스트 저장, 상태를 pending으로 전환"""
        self._ensure_connected()

        await self._connection.execute(
            """UPDATE draft_responses
            SET draft_text = ?, draft_file = ?, status = 'pending'
            WHERE id = ?""",
            (draft_text, draft_file, draft_id),
        )
        await self._connection.commit()
        return True

    async def get_pending_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        """미매칭 pending 메시지 조회"""
        self._ensure_connected()

        async with self._connection.execute(
            """SELECT * FROM draft_responses
            WHERE match_status = 'pending_match'
            ORDER BY created_at ASC LIMIT ?""",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def find_by_message_id(
        self,
        source_channel: str,
        source_message_id: str,
    ) -> dict[str, Any] | None:
        """source_channel + source_message_id로 draft 조회 (중복 체크용)"""
        self._ensure_connected()

        async with self._connection.execute(
            """SELECT * FROM draft_responses
            WHERE source_channel = ? AND source_message_id = ?
            LIMIT 1""",
            (source_channel, source_message_id),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def cleanup_old_entries(
        self,
        retention_days: int = 90,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """오래된 context_entries 및 draft_responses 정리

        Returns:
            삭제된 항목 수 dict (context_entries, draft_responses)
        """
        self._ensure_connected()

        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

        counts = {}

        # Count entries to delete
        async with self._connection.execute(
            "SELECT COUNT(*) as c FROM context_entries WHERE collected_at < ?",
            (cutoff,),
        ) as cursor:
            row = await cursor.fetchone()
            counts["context_entries"] = row["c"]

        async with self._connection.execute(
            "SELECT COUNT(*) as c FROM draft_responses WHERE created_at < ? AND status IN ('approved', 'rejected')",
            (cutoff,),
        ) as cursor:
            row = await cursor.fetchone()
            counts["draft_responses"] = row["c"]

        if not dry_run:
            await self._connection.execute(
                "DELETE FROM context_entries WHERE collected_at < ?",
                (cutoff,),
            )
            await self._connection.execute(
                "DELETE FROM draft_responses WHERE created_at < ? AND status IN ('approved', 'rejected')",
                (cutoff,),
            )
            await self._connection.commit()

        return counts

    async def update_match(
        self,
        draft_id: int,
        project_id: str,
        match_confidence: float,
        match_tier: str,
    ) -> bool:
        """pending 메시지의 프로젝트 매칭 업데이트"""
        self._ensure_connected()

        await self._connection.execute(
            """UPDATE draft_responses
            SET project_id = ?, match_confidence = ?, match_tier = ?,
                match_status = 'manual'
            WHERE id = ?""",
            (project_id, match_confidence, match_tier, draft_id),
        )
        await self._connection.commit()
        return True

    # ==========================================
    # Statistics
    # ==========================================

    async def get_stats(self) -> dict[str, Any]:
        """통계 조회"""
        self._ensure_connected()

        stats = {}

        async with self._connection.execute("SELECT COUNT(*) as c FROM projects") as cursor:
            row = await cursor.fetchone()
            stats["projects"] = row["c"]

        async with self._connection.execute("SELECT COUNT(*) as c FROM context_entries") as cursor:
            row = await cursor.fetchone()
            stats["context_entries"] = row["c"]

        async with self._connection.execute(
            "SELECT COUNT(*) as c FROM draft_responses WHERE status = 'pending'"
        ) as cursor:
            row = await cursor.fetchone()
            stats["pending_drafts"] = row["c"]

        async with self._connection.execute(
            "SELECT COUNT(*) as c FROM draft_responses WHERE match_status = 'pending_match'"
        ) as cursor:
            row = await cursor.fetchone()
            stats["pending_matches"] = row["c"]

        return stats
