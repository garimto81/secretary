# Secretary v2.0 - 프로젝트 전문 비서 Design Document

**Version**: 1.0.0
**Created**: 2026-02-13
**Status**: APPROVED
**Plan Reference**: `docs/01-plan/project-expert-assistant.plan.md`

---

## 1. System Architecture

```
+==========================================================================+
|                   SECRETARY v2.0 ARCHITECTURE                             |
|                   Project Expert Assistant                                |
+==========================================================================+
|                                                                          |
|  +---------------------------+     +---------------------------+         |
|  |  Knowledge Module (NEW)   |     |  Intelligence Module      |         |
|  |  scripts/knowledge/       |     |  scripts/intelligence/    |         |
|  |                           |     |                           |         |
|  |  +-KnowledgeStore-------+ |     |  +-Handler--------------+ |         |
|  |  | SQLite FTS5 (Phase1) | |     |  | 2-Tier LLM (v1 유지) | |         |
|  |  | ChromaDB   (Phase3)  | |◄────|  | + RAG Context 주입   | |         |
|  |  +-----+----------------+ |     |  +----------+-----------+ |         |
|  |        |                  |     |             |             |         |
|  |  +-IngestionWorker------+ |     |  +-Analyzer-+-----------+ |         |
|  |  | async Queue          | |     |  | Ollama + RAG context | |         |
|  |  | Embedding (Phase3)   | |     |  +----------+-----------+ |         |
|  |  +-----+----------------+ |     |             |             |         |
|  |        ▲                  |     |  +-DraftWriter----------+ |         |
|  +--------|------------------+     |  | Claude + RAG context | |         |
|           |                        |  +-----------------------+ |         |
|           |                        +---------------------------+         |
|           |                                                              |
|  +--------+----------------------------------------------------------+   |
|  |              Gateway Pipeline (기존 유지)                          |   |
|  |  Stage 1-5 → Stage 6 (Intelligence) → Stage 7 (Ingestion) NEW    |   |
|  +-------------------------------------------------------------------+   |
|                                                                          |
|  +-------------------------------------------------------------------+   |
|  |  CLI Extensions                                                   |   |
|  |  cli.py learn --project X --source gmail|slack                    |   |
|  |  cli.py search --project X --query "RFID 가격"                    |   |
|  |  cli.py knowledge stats                                          |   |
|  +-------------------------------------------------------------------+   |
+==========================================================================+
```

---

## 2. Knowledge Store Design

### 2.1 Phase 1: SQLite FTS5

**DB**: `data/knowledge.db` (별도 DB, intelligence.db와 분리)

```sql
PRAGMA journal_mode=WAL;

-- 원본 문서 저장
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,                    -- "{source}:{source_id}"
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,                   -- "gmail", "slack"
    source_id TEXT NOT NULL,                -- Gmail message_id, Slack ts
    thread_id TEXT,                         -- Gmail thread_id, Slack thread_ts
    sender_id TEXT,
    sender_name TEXT,
    subject TEXT,                           -- 이메일 제목 (Slack은 NULL)
    content TEXT NOT NULL,                  -- 본문 텍스트
    content_type TEXT DEFAULT 'message',    -- "message", "email", "thread_summary"
    metadata_json TEXT,                     -- JSON: {labels, channel_name, attachments}
    created_at DATETIME,                    -- 원본 메시지 시각
    ingested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id)
);

-- FTS5 전문검색 인덱스
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    content,
    subject,
    sender_name,
    content='documents',
    content_rowid='rowid',
    tokenize='unicode61 remove_diacritics 2'
);

-- FTS5 동기화 트리거
CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, content, subject, sender_name)
    VALUES (new.rowid, new.content, new.subject, new.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content, subject, sender_name)
    VALUES ('delete', old.rowid, old.content, old.subject, old.sender_name);
END;

CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
    INSERT INTO documents_fts(documents_fts, rowid, content, subject, sender_name)
    VALUES ('delete', old.rowid, old.content, old.subject, old.sender_name);
    INSERT INTO documents_fts(rowid, content, subject, sender_name)
    VALUES (new.rowid, new.content, new.subject, new.sender_name);
END;

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_doc_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_doc_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_doc_thread ON documents(thread_id);
CREATE INDEX IF NOT EXISTS idx_doc_sender ON documents(sender_id);
CREATE INDEX IF NOT EXISTS idx_doc_created ON documents(created_at DESC);

-- 학습 상태 추적
CREATE TABLE IF NOT EXISTS ingestion_state (
    id TEXT PRIMARY KEY,                    -- "{project_id}:{source}"
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,
    last_checkpoint TEXT,                   -- Gmail: historyId, Slack: oldest_ts
    total_documents INTEGER DEFAULT 0,
    last_ingested_at DATETIME,
    UNIQUE(project_id, source)
);
```

### 2.2 KnowledgeStore 클래스

```python
# scripts/knowledge/store.py

class KnowledgeStore:
    """프로젝트별 지식 저장소 (SQLite FTS5)"""

    def __init__(self, db_path: str = "data/knowledge.db"):
        self.db_path = db_path

    async def init_db(self) -> None:
        """스키마 초기화"""

    async def ingest(self, document: KnowledgeDocument) -> bool:
        """문서 저장 (UPSERT)"""

    async def search(
        self,
        query: str,
        project_id: str,
        source: str = None,        # "gmail", "slack", None=전체
        limit: int = 10,
        date_from: str = None,
        date_to: str = None,
    ) -> list[SearchResult]:
        """FTS5 전문검색"""

    async def search_by_thread(
        self,
        thread_id: str,
        project_id: str,
    ) -> list[KnowledgeDocument]:
        """스레드별 문서 조회"""

    async def search_by_sender(
        self,
        sender_name: str,
        project_id: str,
        limit: int = 20,
    ) -> list[KnowledgeDocument]:
        """발신자별 문서 조회"""

    async def get_stats(self, project_id: str = None) -> dict:
        """통계: 프로젝트별 문서 수, 소스별 분포"""

    async def get_recent(
        self,
        project_id: str,
        limit: int = 20,
        source: str = None,
    ) -> list[KnowledgeDocument]:
        """최근 문서 조회"""

    async def cleanup(self, retention_days: int = 180) -> int:
        """오래된 문서 정리"""
```

### 2.3 데이터 모델

```python
# scripts/knowledge/models.py

@dataclass
class KnowledgeDocument:
    """Knowledge Store 문서"""
    id: str                          # "{source}:{source_id}"
    project_id: str
    source: str                      # "gmail", "slack"
    source_id: str
    content: str
    sender_name: str = ""
    sender_id: str = ""
    subject: str = ""                # 이메일 제목
    thread_id: str = ""
    content_type: str = "message"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = None

@dataclass
class SearchResult:
    """검색 결과"""
    document: KnowledgeDocument
    score: float                     # FTS5 rank score
    snippet: str                     # 매칭 하이라이트
```

---

## 3. Knowledge Ingestion Pipeline

### 3.1 Bootstrap (초기 학습)

```
CLI: cli.py learn --project ebs --source gmail --label ebs --limit 100

Flow:
1. Gmail API: label:ebs 검색 → message_id 목록
2. 각 message_id → read → HTML body → text 추출
3. KnowledgeDocument 생성
4. KnowledgeStore.ingest() → SQLite FTS5 저장
5. ingestion_state 업데이트 (checkpoint)
```

```python
# scripts/knowledge/bootstrap.py

class KnowledgeBootstrap:
    """초기 학습 실행기"""

    def __init__(self, store: KnowledgeStore):
        self.store = store

    async def learn_gmail(
        self,
        project_id: str,
        label: str = None,
        query: str = None,
        limit: int = 100,
    ) -> BootstrapResult:
        """Gmail 이메일 일괄 학습

        lib.gmail search/read subprocess 사용
        HTML → text 변환 포함
        """

    async def learn_slack(
        self,
        project_id: str,
        channel_id: str,
        limit: int = 500,
    ) -> BootstrapResult:
        """Slack 채널 히스토리 일괄 학습

        lib.slack history subprocess 사용
        스레드 메시지 포함
        """

@dataclass
class BootstrapResult:
    project_id: str
    source: str
    total_fetched: int
    total_ingested: int
    duplicates_skipped: int
    errors: int
    elapsed_seconds: float
```

### 3.2 실시간 Ingestion Worker

```python
# scripts/knowledge/ingestion_worker.py

class IngestionWorker:
    """실시간 Knowledge Ingestion Worker

    Gateway Pipeline 완료 후 비동기로 Knowledge Store에 저장
    """

    def __init__(self, store: KnowledgeStore):
        self.store = store
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Worker 시작"""
        self._task = asyncio.create_task(self._process_loop())

    async def stop(self) -> None:
        """Worker 중지 (graceful)"""

    async def enqueue(self, message: NormalizedMessage, project_id: str) -> None:
        """Pipeline에서 호출: 메시지를 Ingestion 큐에 추가"""
        doc = self._message_to_document(message, project_id)
        await self._queue.put(doc)

    async def _process_loop(self) -> None:
        """큐에서 문서를 꺼내 저장"""
        while True:
            doc = await self._queue.get()
            try:
                await self.store.ingest(doc)
            except Exception as e:
                logger.error(f"Ingestion failed: {e}")
            self._queue.task_done()

    def _message_to_document(
        self,
        message: NormalizedMessage,
        project_id: str,
    ) -> KnowledgeDocument:
        """NormalizedMessage → KnowledgeDocument 변환"""
        source = message.channel.value  # "slack", "email"
        return KnowledgeDocument(
            id=f"{source}:{message.id}",
            project_id=project_id,
            source=source,
            source_id=message.id,
            content=message.text or "",
            sender_name=message.sender_name or "",
            sender_id=message.sender_id or "",
            thread_id=message.channel_id or "",
            created_at=datetime.now(),
        )
```

---

## 4. RAG Integration (handler.py 확장)

### 4.1 `_build_context()` 변경

```python
# handler.py (수정)

async def _build_context(self, project_id: str, query_text: str = "") -> str:
    """프로젝트 컨텍스트 + RAG 검색 결합"""
    parts = []

    # 1. 기존: 프로젝트 기본 정보
    project = await self.registry.get(project_id)
    if project:
        parts.append(f"프로젝트: {project.get('name', project_id)}")
        parts.append(f"설명: {project.get('description', '')}")

    # 2. 신규: Knowledge Store 검색 (RAG)
    if self._knowledge_store and query_text:
        results = await self._knowledge_store.search(
            query=query_text,
            project_id=project_id,
            limit=5,
        )
        if results:
            parts.append("\n## 관련 과거 커뮤니케이션")
            for r in results:
                doc = r.document
                date_str = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""
                source_label = "이메일" if doc.source == "gmail" else "Slack"
                parts.append(
                    f"[{source_label} {date_str}] {doc.sender_name}: "
                    f"{doc.content[:300]}"
                )

    # 3. 기존: context_entries (하위호환)
    entries = await self.storage.get_context_entries(project_id, limit=5)
    if entries:
        parts.append("\n## 등록된 컨텍스트")
        for entry in entries:
            parts.append(f"[{entry.get('source', '')}] {entry.get('content', '')[:200]}")

    return "\n".join(parts)
```

### 4.2 analyze_prompt.txt 확장

기존 프롬프트 끝에 추가:

```
## 관련 과거 커뮤니케이션 (Knowledge Base)
{rag_context}

위 과거 대화를 참고하여 현재 메시지의 맥락을 더 정확하게 파악하세요.
```

### 4.3 draft_prompt.txt 확장

기존 프롬프트에 추가:

```
## 과거 커뮤니케이션 이력
{rag_context}

위 이력을 참고하여:
- 이전에 논의된 내용을 반영하세요
- 일관된 톤을 유지하세요
- 구체적인 수치/날짜는 과거 대화에서 정확히 인용하세요
```

---

## 5. Module Structure

```
scripts/knowledge/
    __init__.py              # KnowledgeStore, IngestionWorker export
    models.py                # KnowledgeDocument, SearchResult
    store.py                 # KnowledgeStore (SQLite FTS5)
    bootstrap.py             # KnowledgeBootstrap (초기 학습)
    ingestion_worker.py      # IngestionWorker (실시간)
    vector_store.py          # (Phase 3) ChromaDB 통합

scripts/intelligence/
    response/
        handler.py           # _build_context() RAG 확장
    prompts/
        analyze_prompt.txt   # {rag_context} 변수 추가
        draft_prompt.txt     # {rag_context} 변수 추가
    cli.py                   # learn, search 명령 추가

scripts/gateway/
    server.py                # IngestionWorker lifecycle 관리
```

---

## 6. CLI Extensions

```python
# cli.py 추가 명령

# 초기 학습
cli.py learn --project ebs --source gmail --label ebs [--limit 100]
cli.py learn --project ebs --source slack --channel C0985UXQN6Q [--limit 500]
cli.py learn --project wsoptv --source gmail --query "subject:wsop" [--limit 50]

# 검색
cli.py search --project ebs "RFID 칩 가격"
cli.py search --project ebs "SUN-FLY" --source gmail
cli.py search --project ebs --sender "Susie" --limit 5

# 통계
cli.py knowledge stats [--project ebs]
cli.py knowledge cleanup [--days 180] [--dry-run]
```

---

## 7. Integration Points

### 7.1 Gateway Server (server.py)

```python
# server.py 추가

# Knowledge Store + Ingestion Worker 초기화
knowledge_store = KnowledgeStore(db_path="data/knowledge.db")
await knowledge_store.init_db()

ingestion_worker = IngestionWorker(knowledge_store)
await ingestion_worker.start()

# Intelligence Handler에 Knowledge Store 주입
handler = ProjectIntelligenceHandler(
    storage=intelligence_storage,
    registry=registry,
    knowledge_store=knowledge_store,     # 신규
    ollama_config=...,
    claude_config=...,
)

# Pipeline 완료 후 Ingestion hook
async def post_intelligence_hook(enriched, result, project_id):
    if project_id:
        await ingestion_worker.enqueue(enriched.original, project_id)
```

### 7.2 Handler (handler.py)

```python
# handler.py 생성자 확장

def __init__(
    self,
    storage,
    registry,
    knowledge_store: Optional[KnowledgeStore] = None,  # 신규
    ollama_config=None,
    claude_config=None,
):
    ...
    self._knowledge_store = knowledge_store
```

---

## 8. Safety Design

| 규칙 | 적용 |
|------|------|
| 자동 전송 금지 | 기존 정책 100% 유지 |
| Knowledge 읽기 전용 | Expert Query 응답도 draft 형태 |
| Rate Limit | Embedding 생성: 10/min, 검색: 무제한 |
| 데이터 보존 | 180일 기본, cleanup CLI로 관리 |
| 개인정보 | metadata에 민감정보 저장 금지 |

---

## 9. Phase 3: Vector DB (조건부)

Phase 1-2 완료 후 FTS5 검색 품질이 불충분하면:

```python
# scripts/knowledge/vector_store.py

class VectorKnowledgeStore:
    """ChromaDB 기반 Vector Store"""

    def __init__(self, persist_dir="data/chroma"):
        import chromadb
        self.client = chromadb.PersistentClient(path=persist_dir)

    async def embed_and_store(self, doc: KnowledgeDocument) -> None:
        """Ollama embedding → ChromaDB 저장"""
        embedding = await self._get_embedding(doc.content)
        collection = self.client.get_or_create_collection(doc.project_id)
        collection.add(
            ids=[doc.id],
            embeddings=[embedding],
            documents=[doc.content],
            metadatas=[{
                "source": doc.source,
                "sender": doc.sender_name,
                "date": doc.created_at.isoformat() if doc.created_at else "",
            }],
        )

    async def search(
        self,
        query: str,
        project_id: str,
        n_results: int = 5,
    ) -> list[SearchResult]:
        """Semantic search"""
        query_embedding = await self._get_embedding(query)
        collection = self.client.get_collection(project_id)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
        )
        return self._to_search_results(results)

    async def _get_embedding(self, text: str) -> list[float]:
        """Ollama nomic-embed-text embedding"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "http://localhost:11434/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text[:2000]},
            )
            return resp.json()["embedding"]
```

---

## 10. Testing Strategy

```python
# tests/knowledge/test_store.py
- test_init_db_creates_tables
- test_ingest_document
- test_ingest_duplicate_upsert
- test_search_fts5_korean
- test_search_fts5_english
- test_search_by_project_filter
- test_search_by_source_filter
- test_search_by_sender
- test_search_by_thread
- test_get_recent
- test_get_stats
- test_cleanup_old_documents

# tests/knowledge/test_bootstrap.py
- test_learn_gmail_with_mock
- test_learn_slack_with_mock
- test_bootstrap_result

# tests/knowledge/test_ingestion_worker.py
- test_worker_start_stop
- test_enqueue_and_process
- test_duplicate_prevention
- test_message_to_document_conversion

# tests/intelligence/test_handler_rag.py
- test_build_context_with_knowledge_store
- test_build_context_without_knowledge_store
- test_rag_context_in_analysis
```

---

## 11. 데이터 흐름 요약

```
                    ┌────────────────────────────────┐
                    │        Bootstrap (1회)          │
                    │  cli.py learn --project ebs     │
                    │  Gmail/Slack 히스토리 수집       │
                    └─────────────┬──────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────┐
│              Knowledge Store (SQLite FTS5)            │
│              data/knowledge.db                       │
│                                                      │
│  documents: id, project_id, source, content, ...     │
│  documents_fts: FTS5 전문검색 인덱스                   │
│  ingestion_state: 학습 체크포인트                      │
└──────────────┬──────────────────────────┬────────────┘
               │                          ▲
               │ search()                 │ ingest()
               ▼                          │
┌──────────────────────────┐    ┌────────┴──────────┐
│ Intelligence Handler     │    │ Ingestion Worker   │
│ _build_context()         │    │ (비동기 큐)         │
│ + RAG 검색 결과 포함      │    │                    │
│                          │    │ Pipeline Stage 7   │
│ Ollama: 메시지+RAG분석    │    │ (새 메시지 자동)    │
│ Claude: 메시지+RAG초안    │    └────────────────────┘
└──────────────────────────┘
```
