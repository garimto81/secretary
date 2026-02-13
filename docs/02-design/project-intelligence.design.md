# Project Intelligence - PDCA Design Document

**Version**: 3.0.0
**Created**: 2026-02-10
**Updated**: 2026-02-11
**Status**: IMPLEMENTED (v3 - 2-Tier LLM: Ollama + Claude Opus)
**Plan Reference**: `docs/01-plan/project-intelligence.plan.md`

---

## 1. System Architecture

```
+============================================================================+
|                     PROJECT INTELLIGENCE SYSTEM (v3)                        |
|                     2-Tier LLM Architecture                                |
+============================================================================+
|                                                                            |
|  +--------------------------+    +---------------------------+             |
|  |    CLI Entry Point       |    |   Gateway Server          |             |
|  |  (cli.py)                |    |   (server.py)             |             |
|  |  register/analyze/drafts |    |   async message loop      |             |
|  |  undrafted/save-draft    |    |                           |             |
|  |  stats/cleanup           |    +----------+----------------+             |
|  +----------+---------------+               |                              |
|             |                      +--------v---------+                    |
|    +--------v--------+            | MessagePipeline   |                    |
|    | ProjectRegistry |            | + intelligence    |                    |
|    | (config loader) |            |   handler         |                    |
|    +--------+--------+            +---+------+--------+                    |
|             |                         |      |                             |
|  +----------v-----------+    +-------v------v--------+                    |
|  |  ContextCollector     |   | ProjectIntelligenceHandler                 |
|  |  GitHub/Slack/Gmail   |   |  (2-Tier Orchestrator)                     |
|  +----------+------------+   |                       |                    |
|             |                | +---DedupFilter       |                    |
|  +----------v-----------+   | |  (memory+DB dedup)   |                    |
|  |  IncrementalRunner    |   | |                      |                    |
|  |  +--+--+--+           |   | +---ContextMatcher     |                    |
|  |  Gm Sl GH             |   | |  (3-tier rules)     |                    |
|  |  ail ack ub            |   | |                      |                    |
|  |  Tr  Tr  Tr            |   | +---OllamaAnalyzer    |  Tier 1 (ALL)     |
|  |  ac  ac  ac            |   | |  (qwen3:8b local)   |                    |
|  |  ke  ke  ke            |   | |                      |                    |
|  |  r   r   r             |   | +---ClaudeCodeDraft   |  Tier 2            |
|  +----------+------------+   | |   Writer (opus)      |  (needs_response)  |
|             |                | |                      |                    |
|  +----------v----------------+-+---DraftStore         |                    |
|  |           IntelligenceStorage  |  (file+DB+Toast)  |                    |
|  |           (SQLite WAL)         +-------------------+                    |
|  |           data/intelligence.db                      |                   |
|  |   projects | context_entries | analysis_state | drafts                  |
|  +-------------------------------------------------------------+          |
+============================================================================+
|  EXISTING GATEWAY INFRASTRUCTURE                                           |
|  +------------------+  +------------------+  +------------------+          |
|  | ChannelAdapter    |  | NormalizedMessage|  | UnifiedStorage   |          |
|  | (base.py)         |  | (models.py)      |  | (storage.py)     |          |
|  +--+---+---+--------+  +------------------+  +------------------+          |
|     |   |   |                                                              |
|  +--v-+ | +---v---+                                                        |
|  |Tel | | |Slack  |                                                        |
|  |gram| | |Adapter|                                                        |
|  +----+ | +-------+                                                        |
|         |                                                                  |
|      +--v-----+                                                            |
|      |Gmail   |                                                            |
|      |Adapter |                                                            |
|      +--------+                                                            |
+=============================================================================+
```

### Data Flow (3 Paths)

```
PATH A: Context Collection (batch, scheduled/manual)
  CLI "analyze" --> ContextCollector
       --> GmailTracker.fetch_new() ---+
       --> SlackTracker.fetch_new() ---|-->  IntelligenceStorage
       --> GitHubTracker.fetch_new() --+     (context_entries)

PATH B: Real-time Response (gateway server, 2-Tier LLM)
  SlackAdapter.listen() --+
  GmailAdapter.listen() --+--> MessagePipeline.process()
       --> ProjectIntelligenceHandler.handle()
       Step 1: DedupFilter (memory cache + DB dedup)
       Step 2: ContextMatcher.match() --> rule_hint (3-tier)
       Step 3: OllamaAnalyzer.analyze() --> AnalysisResult (Tier 1, ALL msgs)
       Step 4: Dedup mark_processed
       Step 5: _resolve_project() (Ollama >=0.7 > rule > Ollama >=0.3)
       Step 6: No project → pending_match 저장 후 종료
       Step 7: needs_response=false → 종료 (분석만)
       Step 8: ClaudeCodeDraftWriter.write_draft() (Tier 2, needs_response only)
              --> DraftStore.save() --> file + DB + Toast

PATH C: Draft Management (CLI)
  CLI "drafts" --> IntelligenceStorage.list_drafts(status="pending")
  CLI "drafts approve 42" --> IntelligenceStorage.update_draft_status(42, "approved")
  CLI "undrafted" --> IntelligenceStorage.get_awaiting_drafts()
  CLI "save-draft 42 --text ..." --> IntelligenceStorage.save_draft_text()
```

---

## 2. Module Design

### Package Structure

```
scripts/intelligence/
    __init__.py
    project_registry.py          # ProjectRegistry (config/projects.json loader)
    context_collector.py         # ContextCollector
    context_store.py             # IntelligenceStorage (SQLite)
    cli.py                       # CLI entry point (10 commands)
    prompts/
        analyze_prompt.txt       # Ollama 분석 프롬프트 템플릿
        draft_prompt.txt         # Claude 초안 프롬프트 템플릿
    incremental/
        __init__.py
        analysis_state.py        # AnalysisStateManager
        runner.py                # IncrementalRunner
        trackers/
            __init__.py
            gmail_tracker.py     # GmailTracker
            slack_tracker.py     # SlackTracker
            github_tracker.py    # GitHubTracker
    response/
        __init__.py
        handler.py               # ProjectIntelligenceHandler (2-Tier orchestrator)
        analyzer.py              # OllamaAnalyzer (Tier 1: message classification)
        draft_writer.py          # ClaudeCodeDraftWriter (Tier 2: opus subprocess)
        draft_generator.py       # OllamaDraftGenerator + ClaudeCodeDraftGenerator (legacy)
        context_matcher.py       # ContextMatcher (3-tier rule-based)
        draft_store.py           # DraftStore (file + DB + Toast)

scripts/gateway/adapters/
    slack.py                     # SlackAdapter (draft-only send)
    gmail.py                     # GmailAdapter
```

### Key Import Paths

```python
# Triple import fallback (subprocess vs package vs relative)
try:
    from scripts.gateway.models import NormalizedMessage, ChannelType
    from scripts.gateway.adapters.base import ChannelAdapter, SendResult
except ImportError:
    try:
        from gateway.models import NormalizedMessage, ChannelType
        from gateway.adapters.base import ChannelAdapter, SendResult
    except ImportError:
        from ..models import NormalizedMessage, ChannelType
        from .base import ChannelAdapter, SendResult

# Intelligence internal
from scripts.intelligence.context_store import IntelligenceStorage
from scripts.intelligence.project_registry import ProjectRegistry
from scripts.intelligence.response.handler import ProjectIntelligenceHandler
from scripts.intelligence.response.analyzer import OllamaAnalyzer, AnalysisResult
from scripts.intelligence.response.draft_writer import ClaudeCodeDraftWriter
from scripts.intelligence.response.context_matcher import ContextMatcher, MatchResult
from scripts.intelligence.response.draft_store import DraftStore

# lib.slack (Browser OAuth)
from lib.slack import SlackClient
```

### Key Class Interfaces

**IntelligenceStorage** - async SQLite, WAL mode

```python
class IntelligenceStorage:
    async def connect(self) -> None                    # schema init + WAL mode
    async def close(self) -> None
    # Projects
    async def save_project(self, project: dict) -> str
    async def get_project(self, project_id: str) -> Optional[dict]
    async def list_projects(self) -> list[dict]
    async def delete_project(self, project_id: str) -> bool
    # Context
    async def save_context_entry(self, entry: dict) -> str             # UPSERT by id
    async def get_context_entries(self, project_id: str, ...) -> list[dict]
    # Analysis State
    async def save_analysis_state(self, project_id, source, checkpoint_key, checkpoint_value, ...) -> None
    async def get_analysis_state(self, project_id, source, checkpoint_key) -> Optional[dict]
    # Drafts
    async def save_draft(self, draft: dict) -> int
    async def get_draft(self, draft_id: int) -> Optional[dict]
    async def list_drafts(self, status=None, match_status=None, project_id=None) -> list[dict]
    async def update_draft_status(self, draft_id, status, reviewer_note=None) -> bool
    async def get_awaiting_drafts(self, project_id=None, limit=20) -> list[dict]
    async def save_draft_text(self, draft_id, draft_text, draft_file=None) -> bool
    async def get_pending_messages(self, limit=50) -> list[dict]
    async def find_by_message_id(self, source_channel, source_message_id) -> Optional[dict]
    async def update_match(self, draft_id, project_id, match_confidence, match_tier) -> bool
    # Utilities
    async def cleanup_old_entries(self, retention_days=90, dry_run=False) -> dict
    async def get_stats(self) -> dict
```

**OllamaAnalyzer** - Tier 1 message classification (local LLM)

```python
@dataclass
class AnalysisResult:
    project_id: Optional[str] = None
    needs_response: bool = False
    intent: str = "unknown"          # "질문", "요청", "정보공유", "잡담"
    summary: str = ""
    confidence: float = 0.0
    reasoning: str = ""

class OllamaAnalyzer:
    def __init__(self, model="qwen3:8b", ollama_url="http://localhost:11434", timeout=90.0, ...)
    async def analyze(self, text, sender_name, source_channel, channel_id,
                      project_list, rule_hint=None) -> AnalysisResult
    async def analyze_batch(self, messages, project_list) -> list[AnalysisResult]
```

**ContextMatcher** - 3-tier rule-based matching

```python
@dataclass
class MatchResult:
    matched: bool
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    confidence: float = 0.0          # 0.9 channel, 0.6-0.8 keyword, 0.5 sender
    tier: Optional[str] = None       # "channel", "keyword", "sender"
    reason: str = ""

class ContextMatcher:
    async def match(self, channel_id, text, sender_id, source_channel) -> MatchResult
    async def match_and_store_pending(self, ...) -> MatchResult   # with DB fallback
```

**ClaudeCodeDraftWriter** - Tier 2 draft generation (Claude Opus subprocess)

```python
class ClaudeCodeDraftWriter:
    def __init__(self, model="opus", max_context_chars=12000, timeout=60)
    async def write_draft(self, project_name, project_context, original_text,
                          sender_name, source_channel, analysis_summary="") -> str
    # Internal: claude -p --model opus subprocess via asyncio.to_thread
```

**ProjectIntelligenceHandler** - 2-Tier orchestrator

```python
class ProjectIntelligenceHandler:
    def __init__(self, storage, registry, ollama_config=None, claude_config=None)
    async def handle(self, message, result) -> None    # Pipeline handler entry point
    # 8-step flow: dedup → rule match → Ollama → mark → resolve → pending → check → draft
```

**DraftStore** - file + DB + Toast

```python
class DraftStore:
    async def save(self, project_id, source_channel, source_message_id,
                   sender_id, sender_name, original_text, draft_text,
                   match_confidence, match_tier) -> dict    # {draft_id, draft_file}
```

**SlackAdapter / GmailAdapter** - ChannelAdapter implementations

```python
class SlackAdapter(ChannelAdapter):
    async def connect(self) -> bool                                     # lib.slack Browser OAuth
    async def listen(self) -> AsyncIterator[NormalizedMessage]          # polling 5s
    async def send(self, message: OutboundMessage) -> SendResult        # draft-only (NEVER sends)
    async def get_status(self) -> dict

class GmailAdapter(ChannelAdapter):
    async def connect(self) -> bool
    async def listen(self) -> AsyncIterator[NormalizedMessage]          # polling 60s
    async def send(self, message: OutboundMessage) -> SendResult        # draft-only
```

---

## 3. Database Schema

DB: `data/intelligence.db` (separate from `data/gateway.db`)

```sql
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    github_repos TEXT,            -- JSON array ["garimto81/claude"]
    slack_channels TEXT,          -- JSON array ["C123ABC"]
    gmail_queries TEXT,           -- JSON array ["subject:(secretary)"]
    keywords TEXT,                -- JSON array ["secretary", "비서"]
    contacts TEXT,                -- JSON array ["U123ABC"]
    config_json TEXT,             -- JSON object {"auto_draft": true, "draft_model": "opus"}
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS context_entries (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source TEXT NOT NULL,          -- "slack", "gmail", "github"
    source_id TEXT,
    entry_type TEXT NOT NULL,      -- "message", "commit", "email", "issue"
    title TEXT,
    content TEXT,
    metadata_json TEXT,            -- JSON object
    collected_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS analysis_state (
    id TEXT PRIMARY KEY,           -- "{project_id}:{source}:{checkpoint_key}"
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
    project_id TEXT,               -- NULL for pending_match
    source_channel TEXT NOT NULL,   -- "slack", "gmail"
    source_message_id TEXT,
    sender_id TEXT,
    sender_name TEXT,
    original_text TEXT,
    draft_text TEXT,                -- NULL for awaiting_draft
    draft_file TEXT,                -- file path
    match_confidence REAL DEFAULT 0.0,
    match_tier TEXT,                -- "channel", "keyword", "sender", "ollama", "manual"
    match_status TEXT DEFAULT 'matched',  -- "matched", "pending_match", "manual"
    status TEXT DEFAULT 'pending',        -- "pending", "approved", "rejected", "awaiting_draft"
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    reviewed_at DATETIME,
    reviewer_note TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- Indexes
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
```

### Draft Status Flow

```
메시지 수신
    │
    ├─ project_id 없음 → match_status='pending_match', status='pending'
    │   └─ CLI "review" → match_status='manual', project_id 설정
    │
    ├─ Claude 비활성화 → match_status='matched', status='awaiting_draft'
    │   └─ CLI "save-draft" → draft_text 저장, status='pending'
    │
    └─ Claude 성공 → match_status='matched', status='pending'
        ├─ CLI "drafts approve" → status='approved'
        └─ CLI "drafts reject" → status='rejected'
```

---

## 4. 2-Tier LLM Architecture

### Tier 1: OllamaAnalyzer (ALL messages)

| 항목 | 값 |
|------|-----|
| 모델 | qwen3:8b (Ollama local) |
| API | `http://localhost:11434/api/chat` |
| 용도 | 메시지 분류 (project_id, needs_response, intent, summary) |
| 호출 조건 | 모든 메시지 (DedupFilter 통과 후) |
| Rate limit | 10 requests/min |
| 프롬프트 | `scripts/intelligence/prompts/analyze_prompt.txt` |

### Tier 2: ClaudeCodeDraftWriter (needs_response=true only)

| 항목 | 값 |
|------|-----|
| 모델 | Claude Opus 4.6 |
| 실행 | `claude -p --model opus` subprocess |
| 용도 | 고품질 응답 초안 생성 |
| 호출 조건 | Tier 1에서 needs_response=true인 메시지만 |
| Rate limit | 5 drafts/min |
| 프롬프트 | `scripts/intelligence/prompts/draft_prompt.txt` |

### project_id Resolution Priority

```
1. Ollama confidence >= 0.7 → Ollama project_id
2. ContextMatcher rule match → rule project_id
3. Ollama confidence >= 0.3 → Ollama project_id (낮은 신뢰도)
4. 모두 실패 → None (pending_match)
```

### Legacy DraftGenerators

`response/draft_generator.py`에 `OllamaDraftGenerator`, `ClaudeCodeDraftGenerator`가 존재하나, 현재 Pipeline에서는 사용하지 않음. `handler.py`가 `OllamaAnalyzer` + `ClaudeCodeDraftWriter`를 직접 사용.

---

## 5. Integration Points

### Pipeline Integration

`server.py`의 `_register_intelligence_handler()`에서 Pipeline에 연결:

```python
# server.py
handler = ProjectIntelligenceHandler(
    storage=intelligence_storage,
    registry=registry,
    ollama_config=config.get("intelligence", {}).get("ollama", {}),
    claude_config=config.get("intelligence", {}).get("claude_draft", {}),
)
pipeline.add_handler(handler.handle)
```

```
Stage 1-4: 기존 (priority, action, storage, notification)
Stage 5: _dispatch_actions()
Stage 6: custom handlers -- ProjectIntelligenceHandler.handle()
```

### NormalizedMessage Mapping

| Field | Slack Source | Gmail Source |
|-------|-------------|-------------|
| `channel` | `ChannelType.SLACK` | `ChannelType.EMAIL` |
| `channel_id` | Slack channel ID | Gmail thread ID |
| `sender_id` | `msg["user"]` (Slack user ID) | `From` header |
| `sender_name` | `_resolve_user()` (User API) | From display name |
| `text` | `msg["text"]` | `extract_email_body()` |
| `is_mention` | `<@` in text | `To` contains user |

---

## 6. Safety Design

### Auto-send Prevention (3 Layers)

| Layer | Location | Mechanism |
|-------|----------|-----------|
| Config | `gateway.json` | `auto_send_disabled: true` |
| Adapter | `SlackAdapter.send()` | confirmed 무관하게 항상 draft file 저장만 수행 |
| Pipeline | `DraftStore.save()` | Markdown file + DB + Toast, send API 호출 없음 |

### Adapter Safety Enforcement

```python
# SlackAdapter.send() - confirmed=True여도 실제 전송 금지
async def send(self, message) -> SendResult:
    if message.confirmed:
        print("WARNING: confirmed=True이지만 안전 정책에 따라 draft로 저장")
    # 항상 draft 파일로만 저장
    draft_path = drafts_dir / f"slack_{message.to}_{timestamp}.md"
    draft_path.write_text(message.text)
    return SendResult(success=True, draft_path=str(draft_path))
```

### Rate Limiting

| Component | Limit |
|-----------|-------|
| OllamaAnalyzer | 10 requests/minute |
| ClaudeCodeDraftWriter | 5 drafts/minute |
| SlackTracker | 1.2s between API calls |
| GmailAdapter polling | 60s interval |
| SlackAdapter polling | 5s interval |

### Error Isolation

- Adapter별 독립 asyncio.Task (하나 crash해도 다른 adapter 영향 없음)
- Pipeline handler try/except 격리
- DedupFilter: memory cache (1000) + DB unique index로 중복 방지
- Ollama 실패 시 fallback: needs_response=True로 기본값 (항상 초안 시도)
- Claude 실패 시 fallback: awaiting_draft 상태로 DB 저장 (CLI에서 수동 draft 작성)

### Token Budget

- Max context: 12000 chars (~4000 tokens)
- Truncation: recent_first (collected_at DESC, 10 entries, 500 chars each)
- Ollama: `num_predict: 512`, `temperature: 0.1`
- Claude: prompt template + original_text[:2000]

---

## 7. Key Technical Decisions

| 결정 | 근거 |
|------|------|
| 2-Tier LLM (Ollama + Claude) | 모든 메시지 분류는 로컬 LLM, 고품질 초안만 Claude Opus |
| `lib.slack` + `asyncio.to_thread()` | 동기 라이브러리의 async context 호출 |
| `claude -p --model opus` subprocess | API key 불필요, Browser OAuth 활용 |
| SQLite WAL mode | Gateway(async) + CLI(sync) 동시 접근 지원 |
| 별도 DB (intelligence.db) | gateway.db와 스키마/보존정책 분리 |
| 3-tier rule matching + Ollama | 빠른 규칙 힌트 + LLM 정밀 분류 결합 |
| DedupFilter (memory + DB) | Polling 기반 메시지 중복 처리 방지 |
| draft_responses 다중 상태 | pending_match/awaiting_draft/pending/approved/rejected 분리 |
| prompt template 외부 파일 | 코드 수정 없이 프롬프트 튜닝 가능 |

---

## 8. Configuration

### config/gateway.json (Intelligence section)

```json
{
  "intelligence": {
    "ollama": {
      "enabled": true,
      "model": "qwen3:8b",
      "endpoint": "http://localhost:11434",
      "timeout": 90,
      "max_context_chars": 12000,
      "rate_limit_per_minute": 10
    },
    "claude_draft": {
      "enabled": true,
      "model": "opus",
      "timeout": 60,
      "rate_limit_per_minute": 5
    }
  },
  "safety": {
    "auto_send_disabled": true,
    "require_confirmation": true,
    "rate_limit_per_minute": 10
  }
}
```

### config/projects.json

```json
{
  "projects": [
    {
      "id": "secretary",
      "name": "Secretary AI",
      "description": "AI 비서 도구 - Gmail, Calendar, GitHub, Slack 통합 분석",
      "github_repos": ["garimto81/claude"],
      "slack_channels": ["C_CHANNEL_ID"],
      "gmail_queries": ["subject:(secretary OR daily report)"],
      "keywords": ["secretary", "비서", "리포트", "gateway", "intelligence", "draft"],
      "contacts": ["U_USER_ID"],
      "config": {
        "auto_draft": true,
        "draft_model": "opus"
      }
    }
  ]
}
```

### CLI Commands

| Command | Description |
|---------|-------------|
| `cli.py register` | config/projects.json에서 프로젝트 로드 |
| `cli.py analyze [--project ID] [--source slack\|gmail\|github]` | 증분 분석 실행 |
| `cli.py pending [--json]` | 미매칭 pending 메시지 조회 |
| `cli.py review <message_id> <project_id>` | 수동 매칭 |
| `cli.py drafts [--status pending\|approved\|rejected]` | 초안 목록 조회 |
| `cli.py drafts approve <id> [--note TEXT]` | 초안 승인 |
| `cli.py drafts reject <id> [--note TEXT]` | 초안 거부 |
| `cli.py undrafted [--project ID] [--json]` | draft 미생성 메시지 조회 |
| `cli.py save-draft <id> --text TEXT [--file PATH]` | draft 텍스트 저장 |
| `cli.py stats [--json]` | 통계 조회 |
| `cli.py cleanup [--days N] [--dry-run]` | 오래된 데이터 정리 |

---

## 9. requirements.txt additions

```
aiosqlite>=0.20.0
httpx>=0.27.0
```

Note: `lib.slack`, `winotify`는 기존 의존성. `claude` CLI는 시스템 PATH에 설치 필요.
