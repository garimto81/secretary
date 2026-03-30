"""
KnowledgeStore - SQLite FTS5 기반 프로젝트별 지식 저장소

Phase 1 MVP: 전문검색, 메타데이터 필터, 스레드/발신자 조회
"""

import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

# 스크립트 직접 실행 시 경로 추가
if __name__ == "__main__":
    _script_dir = Path(__file__).resolve().parent
    _project_root = _script_dir.parent.parent
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

try:
    from scripts.knowledge.models import KnowledgeDocument, SearchResult
except ImportError:
    try:
        from knowledge.models import KnowledgeDocument, SearchResult
    except ImportError:
        from .models import KnowledgeDocument, SearchResult


DEFAULT_DB_PATH = Path(r"C:\claude\secretary\data\knowledge.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    content TEXT NOT NULL,
    sender_name TEXT DEFAULT '',
    sender_id TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    thread_id TEXT DEFAULT '',
    content_type TEXT DEFAULT 'message',
    metadata_json TEXT DEFAULT '{}',
    created_at DATETIME,
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_thread ON documents(thread_id);
CREATE INDEX IF NOT EXISTS idx_documents_sender ON documents(sender_name);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_project_source ON documents(project_id, source);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    content,
    subject,
    sender_name,
    content='documents',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- 동기화 트리거: documents INSERT/UPDATE/DELETE 시 FTS 자동 갱신
CREATE TRIGGER IF NOT EXISTS trg_documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, content, subject, sender_name)
    VALUES (NEW.rowid, NEW.content, NEW.subject, NEW.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS trg_documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content, subject, sender_name)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.subject, OLD.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS trg_documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content, subject, sender_name)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.subject, OLD.sender_name);
    INSERT INTO documents_fts(rowid, content, subject, sender_name)
    VALUES (NEW.rowid, NEW.content, NEW.subject, NEW.sender_name);
END;

-- Ingestion 상태 추적
CREATE TABLE IF NOT EXISTS ingestion_state (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    project_id TEXT NOT NULL,
    checkpoint_key TEXT NOT NULL,
    checkpoint_value TEXT,
    last_run_at DATETIME,
    documents_ingested INTEGER DEFAULT 0,
    error_message TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, source, checkpoint_key)
);
"""


def _sanitize_fts_query(query: str) -> str:
    """FTS5 MATCH 쿼리에서 특수문자를 안전하게 처리

    FTS5 연산자(AND, OR, NOT, NEAR, *, ")를 제거하고
    각 단어를 쌍따옴표로 감싸 리터럴 검색으로 변환.
    """
    # FTS5 특수문자 제거
    cleaned = re.sub(r'[*"(){}[\]^~\\]', ' ', query)
    # FTS5 연산자를 일반 텍스트로 변환
    words = cleaned.split()
    safe_words = []
    for word in words:
        upper = word.upper()
        if upper in ("AND", "OR", "NOT", "NEAR"):
            # 연산자는 쌍따옴표로 감싸서 리터럴 처리
            safe_words.append(f'"{word}"')
        else:
            stripped = word.strip()
            if stripped:
                safe_words.append(f'"{stripped}"')
    return " ".join(safe_words)


def _row_to_document(row: dict[str, Any]) -> KnowledgeDocument:
    """DB 행을 KnowledgeDocument로 변환"""
    data = dict(row)

    metadata = {}
    if data.get("metadata_json") and isinstance(data["metadata_json"], str):
        try:
            metadata = json.loads(data["metadata_json"])
        except json.JSONDecodeError:
            metadata = {}

    created_at = data.get("created_at")
    if created_at and isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            created_at = None

    return KnowledgeDocument(
        id=data["id"],
        project_id=data["project_id"],
        source=data["source"],
        source_id=data["source_id"],
        content=data["content"],
        sender_name=data.get("sender_name", ""),
        sender_id=data.get("sender_id", ""),
        subject=data.get("subject", ""),
        thread_id=data.get("thread_id", ""),
        content_type=data.get("content_type", "message"),
        metadata=metadata,
        created_at=created_at,
    )


class KnowledgeStore:
    """
    프로젝트별 지식 저장소 - SQLite FTS5 전문검색

    Features:
    - FTS5 전문검색 (한국어/영어 unicode61 tokenizer)
    - 프로젝트/소스/스레드/발신자 필터
    - 날짜 범위 검색
    - WAL mode로 동시 읽기/쓰기 지원
    - 자동 FTS 동기화 (트리거 기반)

    Example:
        async with KnowledgeStore() as store:
            await store.ingest(doc)
            results = await store.search("배포 일정", project_id="secretary")
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._connection: aiosqlite.Connection | None = None

    async def __aenter__(self):
        await self.init_db()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def init_db(self) -> None:
        """DB 연결 및 스키마 초기화 (WAL mode)"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(str(self.db_path))
        self._connection.row_factory = aiosqlite.Row

        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.executescript(SCHEMA)
        await self._connection.commit()

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
            raise RuntimeError("KnowledgeStore not connected. Use 'async with' or call init_db() first.")

    # ==========================================
    # Ingestion
    # ==========================================

    async def ingest(self, doc: KnowledgeDocument) -> str:
        """문서 저장 (UPSERT)

        INSERT OR REPLACE로 동일 ID 문서는 덮어씀.
        FTS 인덱스는 트리거가 자동 동기화.

        Args:
            doc: 저장할 KnowledgeDocument

        Returns:
            저장된 문서 ID
        """
        self._ensure_connected()

        metadata_json = json.dumps(doc.metadata, ensure_ascii=False) if doc.metadata else "{}"
        created_at = doc.created_at.isoformat() if doc.created_at else datetime.now().isoformat()

        await self._connection.execute(
            """INSERT OR REPLACE INTO documents
            (id, project_id, source, source_id, content, sender_name, sender_id,
             subject, thread_id, content_type, metadata_json, created_at, ingested_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                doc.id,
                doc.project_id,
                doc.source,
                doc.source_id,
                doc.content,
                doc.sender_name,
                doc.sender_id,
                doc.subject,
                doc.thread_id,
                doc.content_type,
                metadata_json,
                created_at,
                datetime.now().isoformat(),
            ),
        )
        await self._connection.commit()
        return doc.id

    # ==========================================
    # Search
    # ==========================================

    async def search(
        self,
        query: str,
        project_id: str,
        source: str | None = None,
        limit: int = 10,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[SearchResult]:
        """FTS5 전문검색 + 메타데이터 필터

        Args:
            query: 검색어
            project_id: 프로젝트 ID (필수)
            source: 소스 필터 ("gmail", "slack" 등)
            limit: 최대 결과 수
            date_from: 시작 날짜
            date_to: 종료 날짜

        Returns:
            SearchResult 리스트 (rank 순)
        """
        self._ensure_connected()

        safe_query = _sanitize_fts_query(query)
        if not safe_query.strip():
            return []

        sql = """
            SELECT d.*, rank
            FROM documents d
            JOIN documents_fts ON documents_fts.rowid = d.rowid
            WHERE documents_fts MATCH ? AND d.project_id = ?
        """
        params: list = [safe_query, project_id]

        if source:
            sql += " AND d.source = ?"
            params.append(source)

        if date_from:
            sql += " AND d.created_at >= ?"
            params.append(date_from.isoformat())

        if date_to:
            sql += " AND d.created_at <= ?"
            params.append(date_to.isoformat())

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        async with self._connection.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            results = []
            for row in rows:
                data = dict(row)
                score = data.pop("rank", 0.0)
                doc = _row_to_document(data)

                # snippet 생성: 매칭 주변 텍스트 추출
                snippet = self._extract_snippet(doc.content, query)

                results.append(SearchResult(
                    document=doc,
                    score=float(score),
                    snippet=snippet,
                ))
            return results

    async def search_by_thread(
        self,
        thread_id: str,
        project_id: str,
    ) -> list[KnowledgeDocument]:
        """스레드별 문서 조회

        Args:
            thread_id: 스레드 ID
            project_id: 프로젝트 ID

        Returns:
            KnowledgeDocument 리스트 (시간순)
        """
        self._ensure_connected()

        async with self._connection.execute(
            """SELECT * FROM documents
            WHERE thread_id = ? AND project_id = ?
            ORDER BY created_at ASC""",
            (thread_id, project_id),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_document(dict(row)) for row in rows]

    async def search_by_sender(
        self,
        sender_name: str,
        project_id: str,
        limit: int = 20,
    ) -> list[KnowledgeDocument]:
        """발신자별 문서 조회

        Args:
            sender_name: 발신자 이름
            project_id: 프로젝트 ID
            limit: 최대 결과 수

        Returns:
            KnowledgeDocument 리스트 (최신순)
        """
        self._ensure_connected()

        async with self._connection.execute(
            """SELECT * FROM documents
            WHERE sender_name = ? AND project_id = ?
            ORDER BY created_at DESC LIMIT ?""",
            (sender_name, project_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_document(dict(row)) for row in rows]

    # ==========================================
    # Query
    # ==========================================

    async def get_recent(
        self,
        project_id: str,
        limit: int = 20,
        source: str | None = None,
    ) -> list[KnowledgeDocument]:
        """최근 문서 조회

        Args:
            project_id: 프로젝트 ID
            limit: 최대 결과 수
            source: 소스 필터

        Returns:
            KnowledgeDocument 리스트 (최신순)
        """
        self._ensure_connected()

        sql = "SELECT * FROM documents WHERE project_id = ?"
        params: list = [project_id]

        if source:
            sql += " AND source = ?"
            params.append(source)

        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with self._connection.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_document(dict(row)) for row in rows]

    async def get_stats(
        self,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """프로젝트별 문서 통계

        Args:
            project_id: 프로젝트 ID (None이면 전체)

        Returns:
            통계 딕셔너리 (총 문서 수, 소스별 분포, 프로젝트별 문서 수)
        """
        self._ensure_connected()

        stats: dict[str, Any] = {}

        # 총 문서 수
        if project_id:
            total_sql = "SELECT COUNT(*) as total FROM documents WHERE project_id = ?"
            total_params: list = [project_id]
        else:
            total_sql = "SELECT COUNT(*) as total FROM documents"
            total_params = []

        async with self._connection.execute(total_sql, total_params) as cursor:
            row = await cursor.fetchone()
            stats["total_documents"] = row["total"]

        # 소스별 분포
        if project_id:
            source_sql = """SELECT source, COUNT(*) as count
                FROM documents WHERE project_id = ?
                GROUP BY source"""
            source_params: list = [project_id]
        else:
            source_sql = "SELECT source, COUNT(*) as count FROM documents GROUP BY source"
            source_params = []

        async with self._connection.execute(source_sql, source_params) as cursor:
            rows = await cursor.fetchall()
            stats["by_source"] = {row["source"]: row["count"] for row in rows}

        # 프로젝트별 문서 수
        if not project_id:
            async with self._connection.execute(
                "SELECT project_id, COUNT(*) as count FROM documents GROUP BY project_id"
            ) as cursor:
                rows = await cursor.fetchall()
                stats["by_project"] = {row["project_id"]: row["count"] for row in rows}

        return stats

    # ==========================================
    # Maintenance
    # ==========================================

    async def cleanup(self, retention_days: int = 180) -> int:
        """오래된 문서 정리

        Args:
            retention_days: 보존 기간 (일)

        Returns:
            삭제된 문서 수
        """
        self._ensure_connected()

        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()

        async with self._connection.execute(
            "SELECT COUNT(*) as c FROM documents WHERE created_at < ?",
            (cutoff,),
        ) as cursor:
            row = await cursor.fetchone()
            count = row["c"]

        if count > 0:
            await self._connection.execute(
                "DELETE FROM documents WHERE created_at < ?",
                (cutoff,),
            )
            await self._connection.commit()

        return count

    # ==========================================
    # Internal
    # ==========================================

    @staticmethod
    def _extract_snippet(content: str, query: str, max_length: int = 200) -> str:
        """검색어 주변 텍스트 추출"""
        if not content or not query:
            return content[:max_length] if content else ""

        query_lower = query.lower()
        content_lower = content.lower()

        # 첫 번째 매칭 위치 찾기
        words = re.sub(r'[*"(){}[\]^~\\]', ' ', query_lower).split()
        first_pos = -1
        for word in words:
            word = word.strip()
            if word and word.upper() not in ("AND", "OR", "NOT", "NEAR"):
                pos = content_lower.find(word)
                if pos >= 0:
                    first_pos = pos
                    break

        if first_pos < 0:
            return content[:max_length]

        # 매칭 주변 텍스트 추출
        start = max(0, first_pos - 50)
        end = min(len(content), first_pos + max_length - 50)

        snippet = content[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."

        return snippet
