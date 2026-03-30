# Project Intelligence - Implementation Plan

**Version**: 2.0.0
**Created**: 2026-02-10
**Updated**: 2026-02-10
**Status**: READY

---

## Context

### Original Request

프로젝트를 완벽하게 이해한 뒤, Slack과 Gmail에서 해당 프로젝트 관련 사항을 실시간으로 대응하는 시스템을 설계하고 구현한다.

### Research Findings (Codebase Analysis)

**Layer 1: Analyzers** - 각 소스(Gmail, Slack, GitHub, Calendar, LLM)를 subprocess + JSON protocol로 실행하는 스크립트. caching 없이 매 실행마다 전체 데이터를 다시 가져옴.

**Layer 3: Orchestrator** - `daily_report.py`가 analyzer들을 subprocess로 실행하고 JSON 결과를 수집하여 종합 리포트 생성.

**Layer 7: Gateway** - async 기반 메시징 게이트웨이. `NormalizedMessage` 16-field 모델, `UnifiedStorage`(aiosqlite), 6-stage `MessagePipeline`, `ChannelAdapter` 추상 인터페이스 (Telegram adapter 구현 완료). `_dispatch_actions()`는 stub.

**Layer: LLM** - `src/secretary/llm/claude_client.py`에 `ClaudeClient`(Anthropic API wrapper with model tiering: HAIKU, SONNET, OPUS). `src/secretary/core/`에는 `Config`(YAML + env), `EventBus`(pub/sub), exceptions만 export. `ClaudeClient` import 경로: `from secretary.llm.claude_client import ClaudeClient`

**Layer: Prompts** - `src/secretary/llm/prompts.py`에 `PromptLoader`. `config/prompts/` 디렉토리의 `.md` 파일을 이름으로 로드. `{{variable}}` Mustache 구문 지원. 현재 `system.md`, `analyze.md`, `notify.md` 존재. 새 파일(예: `project_response.md`)은 해당 디렉토리에 `.md`로 생성하면 `PromptLoader.load("project_response")`로 자동 로드 가능.

**Layer: Shared Library** - `lib.slack`은 `C:\claude\lib\slack\`에 위치 (secretary 프로젝트 외부). `SlackClient`는 **동기** 클라이언트. `get_history(channel, limit=100)` 시그니처에 `oldest` 파라미터 없음. 내부적으로 `slack_sdk.WebClient` 사용.

**핵심 문제점:**
1. caching 없음 - 매번 전체 데이터 재수집
2. Gateway `_dispatch_actions()` stub
3. 프로젝트 context 개념 부재 - 메시지가 어떤 프로젝트에 속하는지 분류 불가
4. Slack/Gmail adapter 부재 (Telegram만 존재)
5. 증분 분석 메커니즘 없음
6. `lib.slack.SlackClient`는 동기 전용 - async gateway에서 사용 시 `asyncio.to_thread()` 필요
7. `lib.slack.SlackClient.get_history()`에 `oldest` 파라미터 없음 - 증분 조회 시 `slack_sdk.WebClient` 직접 사용 필요
8. `requirements.txt`에 `pyyaml`, `python-dotenv` 누락 (config.py, claude_client.py가 이미 사용 중)

### lib.slack Path Dependency

`lib.slack`은 `C:\claude\lib\slack\`에 위치하며, secretary 프로젝트의 패키지가 아님. 기존 `slack_analyzer.py`는 다음과 같이 해결:

```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # C:\claude 추가
from lib.slack import SlackClient, get_token
```

**새 모듈에서도 동일한 패턴 사용 필요.** 단, 증분 조회가 필요한 Slack adapter/tracker는 `slack_sdk.WebClient`를 직접 사용하므로 `lib.slack` 경로 의존 없이 토큰만 `C:\claude\json\slack_token.json`에서 로드하면 됨.

### Sync/Async Bridge Pattern

`lib.slack.SlackClient`는 동기 클라이언트. Gateway는 async. 브릿지 패턴:

```python
import asyncio

# lib.slack의 동기 메서드를 async context에서 호출
messages = await asyncio.to_thread(slack_client.get_history, channel_id, limit=100)
```

이 패턴은 모든 `lib.slack` 호출에 적용.

---

## Work Objectives

### Core Objective

프로젝트별 context를 구축하고, 해당 context를 기반으로 Slack 메시지와 Gmail 이메일에 대해 프로젝트-aware한 증분 분석 및 응답 초안 생성 시스템을 만든다.

### Deliverables

| # | Deliverable | Description |
|---|------------|-------------|
| D1 | Project Context Engine | 프로젝트 폴더, GitHub, Slack, Gmail에서 context를 수집하고 저장하는 엔진 |
| D2 | Incremental Analysis Engine | 마지막 분석 이후 새 콘텐츠만 처리하는 증분 분석 시스템 |
| D3 | Slack Channel Adapter | Gateway 호환 Slack adapter (`slack_sdk.WebClient` 직접 사용) |
| D4 | Gmail Adapter | Gateway 호환 Gmail adapter (기존 OAuth 활용) |
| D5 | Project-Aware Response Pipeline | context 기반 응답 초안 생성 파이프라인 |
| D6 | Configuration & CLI | 프로젝트 등록, 실행 설정, 스케줄링 |

### Definition of Done

- [ ] 프로젝트를 등록하면 해당 프로젝트의 코드/이슈/PR/Slack/Gmail context가 DB에 저장됨
- [ ] 일일 스케줄 분석이 새 콘텐츠만 처리하고, 분석 상태가 영속 저장됨
- [ ] Slack 멘션/DM이 들어오면 프로젝트 context를 기반으로 응답 초안이 파일로 생성됨
- [ ] Gmail 이메일이 프로젝트와 매칭되면 context 기반 응답 초안이 파일로 생성됨
- [ ] 자동 전송 절대 없음 (draft file + Toast notification만)
- [ ] 모든 데이터 로컬 SQLite에만 저장
- [ ] 기존 subprocess + JSON protocol 유지 (하위 호환)
- [ ] `requirements.txt`에 `pyyaml>=6.0`, `python-dotenv>=1.0`, `slack-sdk>=3.27.0` 명시

---

## Guardrails

### Must Have

- 기존 gateway 인프라 위에 구축 (`ChannelAdapter`, `NormalizedMessage`, `UnifiedStorage`, `MessagePipeline`)
- 기존 `EventBus`, `Config` 활용 (`from secretary.core import Config, EventBus`)
- `ClaudeClient`는 `from secretary.llm.claude_client import ClaudeClient`로 import
- Browser OAuth만 사용 (API key 방식 금지, `ANTHROPIC_API_KEY` 제외)
- 자동 전송 절대 금지 (draft only)
- 증분 분석 (full re-fetch 대신 since-based 쿼리)
- 로컬 데이터만 (privacy)
- 한글 출력, 기술 용어 영어 유지
- Slack 증분 조회: `slack_sdk.WebClient`를 직접 사용 (`oldest` 파라미터 지원)
- 동기 라이브러리의 async 호출: `asyncio.to_thread()` 사용

### Must NOT Have

- 메시지/이메일 자동 전송 기능
- 외부 DB (PostgreSQL, Redis 등) - SQLite만
- 새로운 인증 방식 (기존 OAuth flow 그대로)
- `daily_report.py` subprocess protocol 변경
- Telegram adapter 수정 (신규 adapter만 추가)
- `lib.slack` 공유 라이브러리 수정 (증분 조회는 `slack_sdk` 직접 사용)

---

## Architecture Overview

```
                         +---------------------------------+
                         |     Project Intelligence        |
                         |         System                  |
                         +---------------------------------+
                                      |
          +---------------------------+---------------------------+
          |                           |                           |
+---------v----------+   +-----------v-----------+   +-----------v----------+
| Project Context    |   | Incremental Analysis  |   | Response Pipeline    |
| Engine             |   | Engine                |   |                      |
| (context_engine/)  |   | (incremental/)        |   | (response/)          |
+--------------------+   +-----------------------+   +----------------------+
| - ProjectRegistry  |   | - AnalysisState       |   | - ContextMatcher     |
| - ContextCollector |   | - IncrementalRunner   |   | - DraftGenerator     |
| - ContextStore     |   | - SourceTrackers      |   | - DraftStore         |
| - ProjectIndexer   |   |   (gmail, slack, gh)  |   | - NotificationBridge |
+--------+-----------+   +-----------+-----------+   +-----------+----------+
         |                            |                           |
         +----------------------------+---------------------------+
                                      |
                         +------------v-----------+
                         |   Existing Gateway     |
                         |   Infrastructure       |
                         +------------------------+
                         | - ChannelAdapter       |
                         | - MessagePipeline      |
                         | - UnifiedStorage       |
                         | - NormalizedMessage    |
                         +------------------------+
                                      |
                    +-----------------+------------------+
                    |                                    |
          +---------v----------+              +---------v----------+
          | SlackAdapter       |              | GmailAdapter       |
          | (NEW)              |              | (NEW)              |
          | - slack_sdk direct |              | - Gmail API bridge |
          | - listen() async   |              | - polling-based    |
          +--------------------+              +--------------------+
```

### Key Import Paths

```python
# Core (from secretary.core)
from secretary.core import Config, EventBus
from secretary.core.exceptions import AuthenticationError, AdapterError

# LLM (from secretary.llm - NOT from core!)
from secretary.llm.claude_client import ClaudeClient
from secretary.llm.prompts import PromptLoader

# lib.slack (shared library - needs sys.path hack)
import sys
from pathlib import Path
sys.path.insert(0, str(Path("C:/claude")))
from lib.slack import SlackClient, get_token

# Direct slack_sdk (for incremental queries with oldest parameter)
from slack_sdk import WebClient
```

### Data Flow

```
1. 프로젝트 등록
   User --register--> ProjectRegistry --> ContextCollector --> ContextStore (SQLite)
                                              |
                                   +----------+----------+
                                   |          |          |
                                GitHub    Slack CH    Gmail
                                (code,    (history)   (threads)
                                issues,
                                PRs)

2. 증분 분석 (daily/manual - Windows Task Scheduler)
   Scheduler --> IncrementalRunner --> SourceTracker(gmail) --> new emails since last
                                   --> SourceTracker(slack) --> new messages since last
                                   --> SourceTracker(github) --> new commits/issues since last
                                   --> ContextStore.update()
                                   --> AnalysisState.save_checkpoint()
                                   (실패한 소스의 checkpoint는 업데이트 안 함 -> 다음 실행에서 재시도)

3. 실시간 대응
   SlackAdapter.listen() --> MessagePipeline --> ProjectMatcher --> ContextStore.query()
                                             --> DraftGenerator (ClaudeClient) --> draft file
                                             --> Toast notification

   GmailAdapter.listen() --> MessagePipeline --> ProjectMatcher --> ContextStore.query()
                                             --> DraftGenerator (ClaudeClient) --> draft file
                                             --> Toast notification
```

---

## New Files to Create

### Phase 1: Project Context Engine

| File | Purpose |
|------|---------|
| `scripts/intelligence/__init__.py` | Package init |
| `scripts/intelligence/project_registry.py` | 프로젝트 CRUD, config 관리 |
| `scripts/intelligence/context_collector.py` | GitHub/Slack/Gmail에서 context 수집 |
| `scripts/intelligence/context_store.py` | SQLite 기반 context 저장/조회 (async) |
| `scripts/intelligence/project_indexer.py` | 프로젝트 폴더 구조/코드 인덱싱 |
| `config/projects.json` | 프로젝트 등록 설정 파일 |

### Phase 2: Incremental Analysis Engine

| File | Purpose |
|------|---------|
| `scripts/intelligence/incremental/__init__.py` | Package init |
| `scripts/intelligence/incremental/analysis_state.py` | 분석 상태(checkpoint) 관리 |
| `scripts/intelligence/incremental/runner.py` | 증분 분석 오케스트레이터 |
| `scripts/intelligence/incremental/trackers/__init__.py` | Package init |
| `scripts/intelligence/incremental/trackers/gmail_tracker.py` | Gmail 증분 추적 (History API) |
| `scripts/intelligence/incremental/trackers/slack_tracker.py` | Slack 증분 추적 (slack_sdk direct) |
| `scripts/intelligence/incremental/trackers/github_tracker.py` | GitHub 증분 추적 |

### Phase 3: Gateway Adapters

| File | Purpose |
|------|---------|
| `scripts/gateway/adapters/slack.py` | Slack ChannelAdapter 구현 (slack_sdk direct) |
| `scripts/gateway/adapters/gmail.py` | Gmail ChannelAdapter 구현 |

### Phase 4: Response Pipeline

| File | Purpose |
|------|---------|
| `scripts/intelligence/response/__init__.py` | Package init |
| `scripts/intelligence/response/context_matcher.py` | 메시지를 프로젝트에 매칭 |
| `scripts/intelligence/response/draft_generator.py` | context 기반 응답 초안 생성 |
| `scripts/intelligence/response/draft_store.py` | 초안 저장/관리 |
| `config/prompts/project_response.md` | 프로젝트 context 기반 응답 생성 prompt |
| `config/prompts/project_match.md` | 프로젝트 매칭 prompt |

### Phase 5: CLI & Integration

| File | Purpose |
|------|---------|
| `scripts/intelligence/cli.py` | Project Intelligence CLI 진입점 |

### Tests

| File | Purpose |
|------|---------|
| `tests/intelligence/__init__.py` | Package init |
| `tests/intelligence/test_context_store.py` | Context storage 테스트 |
| `tests/intelligence/test_context_collector.py` | Context 수집 테스트 |
| `tests/intelligence/test_analysis_state.py` | 분석 상태 관리 테스트 |
| `tests/intelligence/test_context_matcher.py` | 프로젝트 매칭 테스트 |
| `tests/intelligence/test_draft_generator.py` | 초안 생성 테스트 |
| `tests/gateway/test_slack_adapter.py` | Slack adapter 테스트 |
| `tests/gateway/test_gmail_adapter.py` | Gmail adapter 테스트 |

---

## Modifications to Existing Files

| File | Change | Reason |
|------|--------|--------|
| `scripts/gateway/pipeline.py` | `_dispatch_actions()` stub 구현 | Project Intelligence handler 연결 |
| `scripts/gateway/server.py` | Slack/Gmail adapter 등록 지원 | 새 adapter를 gateway에 연결 |
| `config/gateway.json` | Slack/Gmail channel 설정 추가 | 새 채널 활성화 |
| `requirements.txt` | `pyyaml>=6.0`, `python-dotenv>=1.0`, `slack-sdk>=3.27.0` 추가 | config.py/claude_client.py가 이미 사용 중이고 Slack adapter가 slack_sdk 직접 사용 |
| `src/secretary/core/events.py` | Project Intelligence 이벤트 타입 추가 | `EventTypes`에 새 이벤트 상수 |
| `config/prompts/system.md` | project context 관련 시스템 prompt 확장 | ClaudeClient가 프로젝트 context 인식 |

---

## Database Schema

### Context Store (`data/intelligence.db`)

```sql
-- 등록된 프로젝트
CREATE TABLE projects (
    id TEXT PRIMARY KEY,                    -- slug (예: "secretary", "automation-hub")
    name TEXT NOT NULL,                     -- 표시명
    root_path TEXT,                         -- 로컬 프로젝트 경로
    github_repo TEXT,                       -- owner/repo 형식
    slack_channels TEXT,                    -- JSON array of channel names
    gmail_query TEXT,                       -- Gmail 검색 쿼리 (subject/from 필터)
    description TEXT,                       -- 프로젝트 설명
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 프로젝트 context 조각 (코드, 이슈, PR, 메시지, 이메일)
CREATE TABLE context_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    source TEXT NOT NULL,                   -- 'github_commit', 'github_issue', 'github_pr',
                                           -- 'slack_message', 'gmail_email', 'code_file'
    source_id TEXT NOT NULL,                -- 소스별 고유 ID
    title TEXT,                             -- 제목/summary
    content TEXT,                           -- 핵심 내용 (summarized)
    raw_content TEXT,                       -- 원본 내용 (요약 전)
    author TEXT,                            -- 작성자
    timestamp DATETIME,                     -- 원본 시각
    metadata TEXT,                          -- JSON (소스별 추가 정보)
    embedding_key TEXT,                     -- 향후 벡터 검색용 (Phase 2+)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, source, source_id)
);

CREATE INDEX idx_context_project ON context_entries(project_id);
CREATE INDEX idx_context_source ON context_entries(source);
CREATE INDEX idx_context_timestamp ON context_entries(timestamp DESC);

-- 분석 상태 (checkpoint)
CREATE TABLE analysis_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    source TEXT NOT NULL,                   -- 'gmail', 'slack', 'github'
    last_analyzed_at DATETIME,              -- 마지막 분석 시각
    last_source_id TEXT,                    -- 마지막 처리된 소스 ID
    metadata TEXT,                          -- JSON (소스별 checkpoint 정보)
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, source)
);

CREATE INDEX idx_state_project ON analysis_state(project_id);

-- 응답 초안
CREATE TABLE draft_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT,                        -- 매칭된 프로젝트 (null이면 미매칭)
    source_channel TEXT NOT NULL,           -- 'slack', 'gmail'
    source_message_id TEXT NOT NULL,        -- 원본 메시지/이메일 ID
    sender TEXT,                            -- 발신자
    original_content TEXT,                  -- 원본 내용
    draft_content TEXT NOT NULL,            -- 생성된 초안
    context_used TEXT,                      -- JSON: 사용된 context entry IDs
    status TEXT DEFAULT 'pending',          -- 'pending', 'approved', 'rejected', 'sent'
    draft_file_path TEXT,                   -- 파일 시스템 경로
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_draft_status ON draft_responses(status);
CREATE INDEX idx_draft_project ON draft_responses(project_id);
```

### Analysis State Management Design

```
                    +-----------------------+
                    |   analysis_state DB   |
                    +-----------------------+
                    | project: secretary    |
                    | source: gmail         |
                    | last_analyzed: 02-09  |
                    | last_id: msg_abc123   |
                    +-----------------------+
                              |
                    +---------v---------+
                    | IncrementalRunner |
                    +-------------------+
                    | 1. Load state     |
                    | 2. Query since    |
                    | 3. Process new    |
                    | 4. Save state     |
                    |    (only on       |
                    |     success)      |
                    +-------------------+

    For Gmail (History API):
      첫 실행:
        1. getProfile() -> historyId 저장
        2. messages.list(q=gmail_query) -> 최근 메시지 수집
        3. state.metadata = {"history_id": "12345"}
      이후 실행:
        1. history.list(startHistoryId=saved_id) -> messagesAdded 이벤트만 필터
        2. 각 message ID로 messages.get() 호출하여 상세 정보 획득
        3. state.metadata = {"history_id": new_history_id}
      fallback (historyId 만료 시 - 7일 초과):
        messages.list(q="after:YYYY/MM/DD") -> 날짜 기반 재수집

    For Slack (slack_sdk.WebClient 직접 사용):
      slack_sdk.WebClient.conversations_history(channel=X, oldest=timestamp)
      - oldest: Unix timestamp 문자열 (예: "1707500000.000000")
      - lib.slack.SlackClient는 oldest 미지원이므로 slack_sdk 직접 사용
      - 토큰: C:\claude\json\slack_token.json에서 access_token 로드
      state.last_source_id = "1707500000.000000"
      state.metadata = {"channel_cursors": {"general": "xxx"}}

    For GitHub:
      state.last_analyzed_at = "2026-02-09T00:00:00"  --> GitHub: since=2026-02-09
      state.metadata = {"last_commit_sha": "abc123"}
```

### Error Recovery for Partial Failures

```
IncrementalRunner.run_project("secretary"):
  1. gmail_tracker.fetch_new()  --> SUCCESS --> save checkpoint for gmail
  2. slack_tracker.fetch_new()  --> FAILURE --> DO NOT update slack checkpoint
  3. github_tracker.fetch_new() --> SUCCESS --> save checkpoint for github

다음 실행 시:
  - gmail: 새 checkpoint부터 시작 (정상)
  - slack: 이전 checkpoint부터 재시도 (실패했으므로 미업데이트)
  - github: 새 checkpoint부터 시작 (정상)
```

---

## Project Configuration Schema (`config/projects.json`)

```json
{
  "projects": [
    {
      "id": "secretary",
      "name": "Secretary AI",
      "root_path": "C:\\claude\\secretary",
      "github_repo": "garimto81/claude",
      "slack_channels": ["secretary-dev", "general"],
      "gmail_query": "subject:(secretary OR AI비서) OR from:(team@example.com)",
      "description": "Gmail, Calendar, GitHub, Slack 통합 AI 비서"
    },
    {
      "id": "automation-hub",
      "name": "Automation Hub",
      "root_path": "C:\\claude\\automation_hub",
      "github_repo": "garimto81/automation-hub",
      "slack_channels": ["automation", "broadcast"],
      "gmail_query": "subject:(WSOP OR 방송자동화)",
      "description": "WSOP 방송 자동화 인프라"
    }
  ],
  "settings": {
    "analysis_schedule": "daily",
    "analysis_time": "09:00",
    "max_context_entries_per_project": 500,
    "context_retention_days": 90,
    "draft_output_dir": "C:\\claude\\secretary\\output\\drafts",
    "auto_send_disabled": true,
    "draft_token_budget": {
      "max_context_tokens": 4000,
      "max_response_tokens": 1024,
      "truncation_strategy": "recent_first"
    }
  }
}
```

---

## Scheduling Mechanism

### 증분 분석 스케줄링

일일 증분 분석(`analyze --all`)을 자동 실행하는 방법:

**Option A: Windows Task Scheduler (권장)**

```powershell
# Task Scheduler에 등록
$action = New-ScheduledTaskAction -Execute "python" `
  -Argument "C:\claude\secretary\scripts\intelligence\cli.py analyze --all" `
  -WorkingDirectory "C:\claude\secretary"

$trigger = New-ScheduledTaskTrigger -Daily -At "09:00"

Register-ScheduledTask -TaskName "SecretaryIntelligence" `
  -Action $action -Trigger $trigger -Description "Daily project intelligence analysis"
```

**Option B: 수동 실행**

```powershell
python C:\claude\secretary\scripts\intelligence\cli.py analyze --all
```

### Gateway 실시간 서비스

Gateway server(`server.py start`)는 foreground 프로세스로 실행. 서비스 모드가 필요하면 `nssm`으로 Windows Service 등록:

```powershell
# nssm으로 서비스 등록 (선택사항)
nssm install SecretaryGateway python C:\claude\secretary\scripts\gateway\server.py start
nssm set SecretaryGateway AppDirectory C:\claude\secretary
```

---

## Real-time Response Pipeline Design

```
Incoming Message (Slack/Gmail)
         |
         v
+-------------------+
| 1. Normalize      |  ChannelAdapter -> NormalizedMessage
+-------------------+
         |
         v
+-------------------+
| 2. Pipeline       |  MessagePipeline (priority, action detection, storage)
|    (existing)     |
+-------------------+
         |
         v
+-------------------+
| 3. Project Match  |  ContextMatcher:
|                   |  - channel_id -> project mapping (config-based)
|                   |  - keyword matching (project name, repo name)
|                   |  - sender matching (known collaborators)
|                   |  - LLM fallback (ClaudeClient.HAIKU for ambiguous)
+-------------------+
         |
         v (matched project_id or null)
+-------------------+
| 4. Context Query  |  ContextStore.get_recent_context(project_id, limit=20)
|                   |  -> recent issues, PRs, commits, conversations
+-------------------+
         |
         v
+-------------------+
| 5. Draft Generate |  DraftGenerator:
|                   |  - System prompt + project context + original message
|                   |  - Context token budget: max 4000 tokens
|                   |  - Truncation: 최신 항목 우선, 오래된 것 제거
|                   |  - ClaudeClient (from secretary.llm.claude_client): SONNET tier
|                   |  - max_tokens=1024 for response
|                   |  - Output: draft text
+-------------------+
         |
         v
+-------------------+
| 6. Save & Notify  |  DraftStore:
|                   |  - Save to DB (draft_responses table)
|                   |  - Write draft file to output/drafts/{channel}/{timestamp}.md
|                   |  - Toast notification with draft preview
|                   |  - NEVER auto-send
+-------------------+
```

### LLM Token Budget Strategy

DraftGenerator가 context를 prompt에 삽입할 때:

1. **Max context tokens**: 4000 tokens (약 12000 chars for Korean)
2. **Truncation strategy**: `recent_first`
   - context_entries를 timestamp DESC로 정렬
   - 최신 항목부터 순서대로 추가
   - 누적 길이가 12000 chars를 초과하면 중단
3. **Max response tokens**: 1024 tokens
4. **Rate limiting**: 분당 최대 5개 draft 생성

---

## Task Flow and Dependencies

```
Phase 1 (Foundation)
  T1: Context Store ---------> T2: Project Registry ---------> T3: Context Collector
       (DB schema)                 (CRUD + config)                 (GitHub/Slack/Gmail)
            \                           |                              /
             \                          |                             /
              +-------------------------+----------------------------+
                                        |
Phase 2 (Incremental)                   v
  T4: Analysis State ---------> T5: Source Trackers ---------> T6: Incremental Runner
       (checkpoint)                 (gmail/slack/gh)               (orchestrator)
                                        |
Phase 3 (Adapters)                      v
  T7: Slack Adapter ---------> T8: Gmail Adapter
       (slack_sdk direct)          (Gmail API bridge)
            \                           /
             +------------+------------+
                          |
Phase 4 (Response)        v
  T9: Context Matcher --> T10: Draft Generator --> T11: Draft Store
                                    |
Phase 5 (Integration)              v
  T12: Pipeline Integration --> T13: CLI --> T14: Config/Docs
```

---

## Detailed TODOs

### Phase 1: Project Context Engine

#### T1: Context Store (`scripts/intelligence/context_store.py`)

**Priority**: HIGH | **Estimated**: 2-3 hours | **Agent**: executor

- [ ] `IntelligenceStorage` class (async context manager, mirrors `UnifiedStorage` pattern)
- [ ] `connect()`: DB 연결 + schema 초기화 (위 schema 전체)
- [ ] `save_project()`: 프로젝트 CRUD
- [ ] `get_project()`, `list_projects()`: 프로젝트 조회
- [ ] `save_context_entry()`: context 조각 저장 (UPSERT)
- [ ] `get_context_for_project()`: 프로젝트별 최근 context 조회 (limit, source filter)
- [ ] `search_context()`: 키워드 기반 context 검색
- [ ] `save_analysis_state()`, `get_analysis_state()`: checkpoint CRUD
- [ ] `save_draft()`, `get_draft()`, `list_drafts()`: 초안 CRUD
- [ ] `cleanup_old_entries()`: retention policy 적용
- [ ] DB path: `C:\claude\secretary\data\intelligence.db`

**Acceptance Criteria**:
- `async with IntelligenceStorage() as store:` pattern 동작
- 프로젝트 CRUD 테스트 통과
- Context entry UPSERT (동일 source+source_id 시 update) 테스트 통과
- 분석 상태 checkpoint 저장/복원 테스트 통과

#### T2: Project Registry (`scripts/intelligence/project_registry.py`)

**Priority**: HIGH | **Estimated**: 1-2 hours | **Agent**: executor

- [ ] `ProjectRegistry` class
- [ ] `load_config()`: `config/projects.json` 로드
- [ ] `register_project()`: 새 프로젝트 등록 (config + DB)
- [ ] `unregister_project()`: 프로젝트 삭제
- [ ] `get_project()`: 프로젝트 정보 조회
- [ ] `list_projects()`: 전체 프로젝트 목록
- [ ] `update_project()`: 프로젝트 설정 변경
- [ ] Config validation (required fields 검증)

**Acceptance Criteria**:
- `config/projects.json`에서 프로젝트 로드 가능
- register/unregister 시 config 파일과 DB 동기화
- 유효하지 않은 config 시 명확한 에러 메시지

#### T3: Context Collector (`scripts/intelligence/context_collector.py`)

**Priority**: HIGH | **Estimated**: 3-4 hours | **Agent**: executor

- [ ] `ContextCollector` class
- [ ] `collect_github_context()`: 기존 `github_analyzer.py`의 API 함수 재활용
  - commits (message, author, files changed)
  - open issues (title, body, labels, assignees)
  - open PRs (title, body, review status)
  - branches (active branches)
- [ ] `collect_slack_context()`: `slack_sdk.WebClient` 직접 사용 (lib.slack의 get_history에 oldest 미지원이므로)
  - 토큰 로드: `C:\claude\json\slack_token.json`에서 `access_token` 읽기
  - channel history (messages, threads)
  - pinned messages
  - shared files/links
- [ ] `collect_gmail_context()`: 기존 `gmail_analyzer.py` OAuth 재활용
  - matching email threads (subject/from filter)
  - attachments metadata
- [ ] `collect_code_context()`: 프로젝트 폴더 분석
  - directory structure
  - README.md, CLAUDE.md 내용
  - recent git log (local)
- [ ] `collect_all()`: 모든 소스에서 수집 후 `ContextStore`에 저장
- [ ] Error handling: 개별 소스 실패 시 계속 진행 (partial collection)
- [ ] Path dependency: `sys.path.insert(0, "C:\\claude")` for lib.slack fallback access

**Acceptance Criteria**:
- GitHub repo에서 commits, issues, PRs 수집하여 DB 저장
- Slack channel에서 history 수집하여 DB 저장
- Gmail에서 필터 매칭 이메일 수집하여 DB 저장
- 프로젝트 폴더에서 구조/README 수집
- 개별 소스 실패 시 나머지 소스 정상 수집

#### T3.5: Project Indexer (`scripts/intelligence/project_indexer.py`)

**Priority**: MEDIUM | **Estimated**: 1-2 hours | **Agent**: executor

- [ ] `ProjectIndexer` class
- [ ] `index_structure()`: 프로젝트 디렉토리 트리 생성 (gitignore 존중)
- [ ] `index_readme()`: README.md, CLAUDE.md 등 핵심 문서 추출
- [ ] `index_git_log()`: 로컬 git log 최근 N개 추출
- [ ] `get_project_summary()`: 프로젝트 요약 (구조 + 핵심 문서 + 최근 활동)

**Acceptance Criteria**:
- `.gitignore` 패턴 존중하여 파일 트리 생성
- README.md 내용 추출 성공
- git log 파싱 성공

### Phase 2: Incremental Analysis Engine

#### T4: Analysis State (`scripts/intelligence/incremental/analysis_state.py`)

**Priority**: HIGH | **Estimated**: 1-2 hours | **Agent**: executor

- [ ] `AnalysisStateManager` class
- [ ] `get_checkpoint()`: 특정 project+source의 마지막 분석 상태 조회
- [ ] `save_checkpoint()`: 분석 완료 후 상태 저장
- [ ] `get_all_checkpoints()`: 프로젝트별 전체 상태 조회
- [ ] `reset_checkpoint()`: 특정 소스 상태 초기화 (전체 재분석용)
- [ ] Checkpoint data: `last_analyzed_at`, `last_source_id`, `metadata` (JSON)

**Acceptance Criteria**:
- checkpoint 저장 후 복원 시 동일 데이터
- 존재하지 않는 checkpoint 조회 시 None 반환 (full analysis trigger)

#### T5: Source Trackers

**Priority**: HIGH | **Estimated**: 3-4 hours | **Agent**: executor

##### T5a: Gmail Tracker (`scripts/intelligence/incremental/trackers/gmail_tracker.py`)

Gmail History API를 사용한 증분 조회. **기존 gmail_analyzer.py는 `messages.list()`만 사용하므로, History API는 새 코드.**

- [ ] `GmailTracker` class
- [ ] `fetch_new()`: checkpoint 이후 새 이메일만 조회
  - **첫 실행 (checkpoint 없음)**:
    1. `getProfile()` 호출 -> `historyId` 획득
    2. `messages.list(q=gmail_query)` 로 최근 메시지 수집 (최대 50개)
    3. 각 message에 대해 `messages.get()` 호출하여 상세 정보 획득
    4. checkpoint 저장: `metadata.history_id = historyId`
  - **이후 실행 (checkpoint 있음)**:
    1. `history.list(userId="me", startHistoryId=saved_history_id, historyTypes=["messageAdded"])` 호출
    2. response에서 `messagesAdded` 이벤트만 필터
    3. 각 message ID로 `messages.get(userId="me", id=msg_id)` 호출하여 상세 정보 획득
    4. gmail_query로 추가 필터 (프로젝트 관련 이메일만)
    5. 새 historyId로 checkpoint 업데이트
  - **fallback (historyId 만료 시 - HTTP 404)**:
    1. `messages.list(q="after:YYYY/MM/DD {gmail_query}")` 로 날짜 기반 재수집
    2. 새 `getProfile()` -> historyId 재설정
- [ ] `to_context_entries()`: 이메일을 `context_entry` 형태로 변환
- [ ] 기존 `gmail_analyzer.py`의 `get_credentials()`, `extract_email_body()` 재활용
- [ ] Gmail scope: `gmail.readonly` (기존과 동일, History API도 지원)

##### T5b: Slack Tracker (`scripts/intelligence/incremental/trackers/slack_tracker.py`)

`lib.slack.SlackClient.get_history()`는 `oldest` 파라미터를 지원하지 않으므로, `slack_sdk.WebClient`를 직접 사용.

- [ ] `SlackTracker` class
- [ ] `_load_token()`: `C:\claude\json\slack_token.json`에서 `access_token` 로드
- [ ] `_get_webclient()`: `slack_sdk.WebClient(token=access_token)` 생성
- [ ] `fetch_new()`: checkpoint 이후 새 메시지만 조회
  - `slack_sdk.WebClient.conversations_history(channel=X, oldest=checkpoint_ts, limit=200)`
  - channel별 cursor 관리
  - rate limiting: 요청 간 1.2초 간격 (Tier 3: 50 req/min)
- [ ] `to_context_entries()`: 메시지를 `context_entry` 형태로 변환
- [ ] **동기 API이므로 async context에서 호출 시 `asyncio.to_thread()` 사용**

##### T5c: GitHub Tracker (`scripts/intelligence/incremental/trackers/github_tracker.py`)
- [ ] `GitHubTracker` class
- [ ] `fetch_new()`: checkpoint 이후 새 활동 조회
  - `since` parameter 활용 (commits, issues)
  - new/updated PRs
- [ ] `to_context_entries()`: 활동을 `context_entry` 형태로 변환
- [ ] 기존 `github_analyzer.py`의 `api_get()`, `get_github_token()` 재활용

**Acceptance Criteria**:
- Gmail: History API 기반 증분 조회 동작 (새 이메일만), historyId 만료 시 fallback
- Slack: `slack_sdk.WebClient` `oldest` timestamp 기반 증분 조회 (새 메시지만)
- GitHub: since 기반 증분 조회 (새 commit/issue/PR만)
- 각 tracker가 context_entry 형태로 변환하여 반환

#### T6: Incremental Runner (`scripts/intelligence/incremental/runner.py`)

**Priority**: HIGH | **Estimated**: 2-3 hours | **Agent**: executor

- [ ] `IncrementalRunner` class
- [ ] `run_project()`: 단일 프로젝트 증분 분석
  1. Load checkpoint for each source
  2. Call each tracker's `fetch_new()`
  3. Save new context entries to ContextStore
  4. **성공한 소스만** checkpoint 업데이트 (실패 소스는 미업데이트 -> 다음 실행에서 재시도)
- [ ] `run_all()`: 모든 등록된 프로젝트 증분 분석
- [ ] `run_full()`: 전체 재분석 (checkpoint 무시)
- [ ] Progress reporting (print 또는 callback)
- [ ] Error handling: 소스별 독립 실행 (하나 실패해도 계속)

**Acceptance Criteria**:
- 첫 실행: 전체 데이터 수집 (checkpoint 없으므로)
- 두 번째 실행: 새 데이터만 수집 (checkpoint 기반)
- 개별 소스 실패 시 나머지 정상 실행 + 에러 보고
- 실패한 소스의 checkpoint는 업데이트되지 않음

### Phase 3: Gateway Adapters

#### T7: Slack Adapter (`scripts/gateway/adapters/slack.py`)

**Priority**: HIGH | **Estimated**: 3-4 hours | **Agent**: executor

`lib.slack` wrapper를 우회하여 `slack_sdk.WebClient`를 직접 사용. `oldest` 파라미터 지원 및 async 호환성을 위해.

- [ ] `SlackAdapter(ChannelAdapter)` class
- [ ] `__init__()`: 토큰 경로 설정 (`C:\claude\json\slack_token.json`)
- [ ] `_load_token()`: JSON에서 `access_token` 읽기
- [ ] `_get_webclient()`: `slack_sdk.WebClient(token=...)` 초기화
- [ ] `connect()`: 토큰 로드 + WebClient 초기화 + `auth.test()` 검증
- [ ] `disconnect()`: 정리
- [ ] `listen()`: async generator
  - polling 기반 (5초 간격)
  - `await asyncio.to_thread(webclient.conversations_history, channel=X, oldest=last_ts)`
  - `NormalizedMessage`로 변환
  - 멘션/DM 필터링
- [ ] `send()`: 초안만 저장 (auto_send_disabled 강제)
  - `confirmed=False` 강제 또는 draft 파일 생성
- [ ] `get_status()`: 연결 상태 반환
- [ ] `_slack_to_normalized()`: Slack 메시지 -> NormalizedMessage 변환

**Acceptance Criteria**:
- `SlackAdapter`가 `ChannelAdapter` interface 완전 구현
- `listen()`이 새 Slack 메시지를 `NormalizedMessage`로 yield
- `send()`가 절대 실제 전송하지 않고 초안만 생성
- 연결 실패 시 graceful error handling
- `oldest` 파라미터로 증분 polling 동작

#### T8: Gmail Adapter (`scripts/gateway/adapters/gmail.py`)

**Priority**: HIGH | **Estimated**: 3-4 hours | **Agent**: executor

- [ ] `GmailAdapter(ChannelAdapter)` class
- [ ] `__init__()`: OAuth credentials 설정
- [ ] `connect()`: Gmail API service 초기화 (기존 `get_credentials()` 패턴)
- [ ] `disconnect()`: 정리
- [ ] `listen()`: async generator
  - Gmail API `history.list()` polling (60초 간격)
  - `await asyncio.to_thread(service.users().history().list(...).execute)`
  - 구현 상세:
    1. 첫 호출: `getProfile()` -> historyId 저장
    2. 이후 호출: `history.list(startHistoryId=saved_id)`
    3. `messagesAdded` 이벤트에서 message ID 추출
    4. 각 ID로 `messages.get()` 호출
    5. `NormalizedMessage`로 변환
    6. historyId 만료(HTTP 404) 시 `messages.list(q="after:...")` fallback
  - 새 이메일만 yield
- [ ] `send()`: 초안만 저장 (절대 이메일 전송 안 함)
- [ ] `get_status()`: 연결 상태 반환
- [ ] `_gmail_to_normalized()`: Gmail 메시지 -> NormalizedMessage 변환

**Acceptance Criteria**:
- `GmailAdapter`가 `ChannelAdapter` interface 완전 구현
- `listen()`이 새 Gmail 이메일을 `NormalizedMessage`로 yield
- `send()`가 절대 실제 이메일 전송하지 않음
- OAuth 토큰 만료 시 자동 갱신
- History API 기반 증분 polling 동작

### Phase 4: Response Pipeline

#### T9: Context Matcher (`scripts/intelligence/response/context_matcher.py`)

**Priority**: HIGH | **Estimated**: 2-3 hours | **Agent**: executor

- [ ] `ContextMatcher` class
- [ ] `match_message()`: 메시지를 프로젝트에 매칭
  - Rule 1: `channel_id` -> project mapping (config의 `slack_channels`/`gmail_query`)
  - Rule 2: 키워드 매칭 (프로젝트 이름, repo 이름, 주요 용어)
  - Rule 3: 발신자 매칭 (프로젝트 collaborator)
  - Rule 4: LLM fallback (`ClaudeClient.HAIKU` for ambiguous cases)
    - import: `from secretary.llm.claude_client import ClaudeClient`
- [ ] `_match_by_channel()`: 채널 기반 매칭
- [ ] `_match_by_keywords()`: 키워드 기반 매칭
- [ ] `_match_by_llm()`: LLM 기반 매칭 (비용 최소화를 위해 Haiku)
- [ ] Confidence score 반환 (0.0 - 1.0)

**Acceptance Criteria**:
- Slack #secretary-dev 채널 메시지 -> secretary 프로젝트 매칭 (config-based)
- "secretary" 키워드 포함 메시지 -> secretary 프로젝트 매칭
- 모호한 메시지에 대해 LLM 매칭 fallback 동작
- 매칭 불가 시 None 반환 (무시, draft 생성 안 함)

#### T10: Draft Generator (`scripts/intelligence/response/draft_generator.py`)

**Priority**: HIGH | **Estimated**: 2-3 hours | **Agent**: executor

- [ ] `DraftGenerator` class
- [ ] `__init__()`: `ClaudeClient` 초기화 (`from secretary.llm.claude_client import ClaudeClient`)
- [ ] `generate_draft()`:
  1. ContextStore에서 프로젝트 context 조회 (최근 20개)
  2. `_truncate_context()`: token budget 적용 (max 4000 tokens / ~12000 chars)
  3. 프로젝트 summary 구성
  4. `ClaudeClient` SONNET tier로 응답 초안 생성 (max_tokens=1024)
  5. Draft metadata (사용된 context IDs, confidence) 반환
- [ ] `_build_context_prompt()`: context entries를 prompt에 삽입할 형태로 구성
- [ ] `_truncate_context()`: 최신 항목 우선으로 token budget 내에서 자르기
  - timestamp DESC 정렬
  - 항목 순서대로 추가하며 누적 12000 chars 초과 시 중단
  - 잘린 경우 `[...N개 항목 생략...]` 표시
- [ ] `_format_project_summary()`: 프로젝트 summary 포맷
- [ ] Prompt template: `config/prompts/project_response.md` 사용 (`PromptLoader.load("project_response")`)
- [ ] Rate limiting: 분당 최대 5개 draft 생성

**Acceptance Criteria**:
- 프로젝트 context가 prompt에 포함되어 관련성 있는 초안 생성
- Slack 메시지 tone에 맞는 캐주얼한 응답 초안
- Gmail 이메일 tone에 맞는 formal 응답 초안
- Rate limit 초과 시 skip + 로그
- Context가 token budget을 초과해도 truncation으로 안전하게 처리

#### T11: Draft Store (`scripts/intelligence/response/draft_store.py`)

**Priority**: MEDIUM | **Estimated**: 1-2 hours | **Agent**: executor

- [ ] `DraftStore` class
- [ ] `save_draft()`: DB + 파일 시스템 동시 저장
  - DB: `draft_responses` table
  - File: `output/drafts/{channel}/{YYYYMMDD}_{HHMMSS}_{sender}.md`
- [ ] `get_pending_drafts()`: 미처리 초안 목록
- [ ] `update_status()`: 초안 상태 변경 (approved/rejected)
- [ ] Draft file format: Markdown with metadata header

**Draft File Format**:
```markdown
---
project: secretary
channel: slack
sender: kimcoder
message_id: 1707500000.000000
generated_at: 2026-02-10T14:30:00
confidence: 0.85
status: pending
---

## 원본 메시지

> secretary 프로젝트에서 Gmail adapter 구현 진행 상황이 어떻게 되나요?

## 응답 초안

현재 Gmail adapter는 Phase 3에서 구현 중이며, OAuth 인증 부분은 완료되었습니다.
polling 기반 listen() 구현을 진행 중이고, 이번 주 내에 PR을 올릴 예정입니다.

## 사용된 Context

- [github_pr] #45: feat: implement Gmail OAuth integration (2026-02-08)
- [github_commit] abc123: add Gmail adapter skeleton (2026-02-09)
- [slack_message] @kimcoder: Gmail OAuth 테스트 완료 (2026-02-09)
```

**Acceptance Criteria**:
- Draft가 DB와 파일 시스템에 동시 저장
- Markdown 파일이 위 포맷으로 생성
- pending/approved/rejected 상태 관리

### Phase 5: Integration

#### T12: Pipeline Integration

**Priority**: HIGH | **Estimated**: 2-3 hours | **Agent**: executor

- [ ] `scripts/gateway/pipeline.py`의 `_dispatch_actions()` 구현
  - `action_request` 또는 `question` 액션 감지 시 Project Intelligence 호출
  - `ContextMatcher.match_message()` -> 프로젝트 매칭
  - `DraftGenerator.generate_draft()` -> 초안 생성
  - `DraftStore.save_draft()` -> 저장 + 알림
- [ ] `MessagePipeline`에 `project_intelligence_handler` 추가
- [ ] Gateway server에 Slack/Gmail adapter 등록 로직 추가
- [ ] `EventBus` 이벤트 발행 (draft 생성 시)

**Acceptance Criteria**:
- Slack 메시지 수신 -> pipeline -> project matching -> draft 생성 전체 flow 동작
- Gmail 이메일 수신 -> pipeline -> project matching -> draft 생성 전체 flow 동작
- 매칭 실패 시 draft 생성 없이 정상 종료
- Toast 알림 발송

#### T13: CLI (`scripts/intelligence/cli.py`)

**Priority**: MEDIUM | **Estimated**: 2-3 hours | **Agent**: executor

- [ ] argparse CLI 진입점
- [ ] `register` command: 프로젝트 등록
- [ ] `unregister` command: 프로젝트 삭제
- [ ] `list` command: 등록된 프로젝트 목록
- [ ] `analyze` command: 증분 분석 실행 (단일/전체)
- [ ] `analyze --full` command: 전체 재분석
- [ ] `status` command: 분석 상태 조회
- [ ] `drafts` command: 미처리 초안 목록
- [ ] `drafts approve/reject ID` command: 초안 상태 변경
- [ ] `context PROJECT` command: 프로젝트 context 요약 출력
- [ ] `--json` flag: JSON 출력 지원

**CLI Usage**:
```powershell
# 프로젝트 등록
python scripts/intelligence/cli.py register --id secretary --name "Secretary AI" \
  --path "C:\claude\secretary" --github garimto81/claude \
  --slack secretary-dev,general --gmail "subject:secretary"

# 증분 분석
python scripts/intelligence/cli.py analyze --project secretary
python scripts/intelligence/cli.py analyze --all

# 상태 조회
python scripts/intelligence/cli.py status --project secretary

# 초안 관리
python scripts/intelligence/cli.py drafts --pending
python scripts/intelligence/cli.py drafts approve 42
```

**Acceptance Criteria**:
- 모든 command가 `--json` flag와 함께 동작
- `register` 시 config 파일과 DB 동시 업데이트
- `analyze`가 증분 분석 실행 후 결과 요약 출력
- `drafts`가 pending 초안 목록 표시

#### T14: Configuration & Prompts

**Priority**: MEDIUM | **Estimated**: 1-2 hours | **Agent**: executor

- [ ] `config/projects.json` 기본 템플릿 생성
- [ ] `config/gateway.json` 업데이트 (Slack/Gmail channel 추가)
- [ ] `config/prompts/project_response.md` prompt 작성
- [ ] `config/prompts/project_match.md` prompt 작성
  - 두 파일 모두 `PromptLoader.load("project_response")`, `PromptLoader.load("project_match")`로 로드 가능 (PromptLoader는 `config/prompts/` 디렉토리의 `{name}.md` 파일을 자동 탐색)
- [ ] `src/secretary/core/events.py`에 Project Intelligence 이벤트 추가
- [ ] `requirements.txt` 업데이트: **`pyyaml>=6.0`, `python-dotenv>=1.0`, `slack-sdk>=3.27.0` 추가** (현재 누락됨)

**New Prompt Templates**:

`config/prompts/project_response.md`:
```markdown
당신은 프로젝트 "{{project_name}}"의 맥락을 잘 알고 있는 AI 비서입니다.

## 프로젝트 설명
{{project_description}}

## 최근 프로젝트 활동
{{project_context}}

## 원본 메시지
채널: {{channel}}
발신자: {{sender}}
내용: {{message}}

## 지시사항
위 프로젝트 맥락을 기반으로 원본 메시지에 대한 응답 초안을 작성하세요.
- 채널이 slack이면 캐주얼한 톤으로, gmail이면 비즈니스 톤으로 작성
- 프로젝트의 현재 상황을 반영하여 구체적으로 답변
- 한국어로 작성하되 기술 용어는 영어 유지
- 200자 이내로 간결하게
```

`config/prompts/project_match.md`:
```markdown
다음 메시지가 어떤 프로젝트에 관한 것인지 판단하세요.

## 등록된 프로젝트 목록
{{project_list}}

## 메시지
채널: {{channel}}
발신자: {{sender}}
내용: {{message}}

## 지시사항
가장 관련 있는 프로젝트 ID를 반환하세요. 관련 프로젝트가 없으면 "none"을 반환하세요.
응답 형식: project_id만 (예: "secretary" 또는 "none")
```

**Acceptance Criteria**:
- 모든 config 파일이 유효한 JSON
- prompt template이 `PromptLoader.load("project_response")` 및 `PromptLoader.load("project_match")`로 정상 로드
- EventTypes에 새 이벤트 상수 추가
- requirements.txt에 pyyaml, python-dotenv, slack-sdk 명시

---

## Commit Strategy

| Phase | Commit Message | Files |
|-------|---------------|-------|
| P1-T1 | `feat(intelligence): add context store with async SQLite` | context_store.py, test_context_store.py |
| P1-T2 | `feat(intelligence): add project registry with config` | project_registry.py, projects.json |
| P1-T3 | `feat(intelligence): add context collector for GitHub/Slack/Gmail` | context_collector.py, project_indexer.py, test_context_collector.py |
| P2-T4 | `feat(intelligence): add incremental analysis state management` | analysis_state.py, test_analysis_state.py |
| P2-T5 | `feat(intelligence): add source trackers for Gmail/Slack/GitHub` | trackers/*.py |
| P2-T6 | `feat(intelligence): add incremental runner orchestrator` | runner.py |
| P3-T7 | `feat(gateway): add Slack channel adapter with slack_sdk` | adapters/slack.py, test_slack_adapter.py |
| P3-T8 | `feat(gateway): add Gmail channel adapter with History API` | adapters/gmail.py, test_gmail_adapter.py |
| P4-T9 | `feat(intelligence): add project-aware context matcher` | context_matcher.py, test_context_matcher.py |
| P4-T10 | `feat(intelligence): add context-based draft generator` | draft_generator.py, project_response.md, test_draft_generator.py |
| P4-T11 | `feat(intelligence): add draft store with file output` | draft_store.py |
| P5-T12 | `feat(intelligence): integrate pipeline with project intelligence` | pipeline.py (mod), server.py (mod) |
| P5-T13 | `feat(intelligence): add CLI for project management` | cli.py |
| P5-T14 | `chore(intelligence): add configuration, prompts, and missing deps` | config files, events.py (mod), requirements.txt (mod) |

---

## Success Criteria

### Functional

| # | Criterion | Verification |
|---|----------|-------------|
| F1 | 프로젝트 등록 후 context 수집 완료 | `cli.py context PROJECT` 출력 확인 |
| F2 | 증분 분석: 두 번째 실행 시 새 데이터만 처리 | 로그에서 "N new entries" 확인 |
| F3 | Slack 메시지 -> 프로젝트 매칭 -> 초안 생성 | `output/drafts/slack/` 파일 생성 확인 |
| F4 | Gmail 이메일 -> 프로젝트 매칭 -> 초안 생성 | `output/drafts/gmail/` 파일 생성 확인 |
| F5 | 초안에 프로젝트 context가 반영됨 | 초안 내용에 최근 commit/issue 언급 |
| F6 | 자동 전송 절대 없음 | send()에서 draft 파일만 생성 확인 |
| F7 | Toast 알림 발송 | 초안 생성 시 Windows Toast 팝업 |
| F8 | 실패 소스 재시도 | 소스 실패 후 재실행 시 해당 소스만 처음부터 재수집 |

### Non-Functional

| # | Criterion | Threshold |
|---|----------|-----------|
| N1 | 증분 분석 실행 시간 | < 60초 (일반적 프로젝트) |
| N2 | Slack polling 지연 | < 10초 |
| N3 | Gmail polling 지연 | < 120초 |
| N4 | 초안 생성 시간 | < 15초 (LLM 응답 포함) |
| N5 | SQLite DB 크기 | < 100MB (90일 retention) |
| N6 | 메모리 사용 | < 200MB (gateway 실행 중) |

### Risk Identification

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| Gmail API rate limit (250 quota units/second) | 증분 분석 실패 | LOW | exponential backoff + batch 조회 |
| Gmail historyId 만료 (7일+ 미실행) | 증분 조회 실패 | MEDIUM | fallback to messages.list(q="after:...") |
| Slack rate limit (tier 3: 50 req/min) | polling 지연 | MEDIUM | 5초 interval + rate limit 에러 시 backoff |
| LLM API cost (draft 생성마다 Sonnet 호출) | 비용 증가 | MEDIUM | rate limit (5/min), 매칭 confidence 임계값 |
| OAuth 토큰 만료 | 수집 실패 | LOW | auto-refresh (기존 패턴), 실패 시 재인증 안내 |
| SQLite concurrent write (gateway + analysis) | DB lock | MEDIUM | WAL mode, write retry with backoff |
| 프로젝트 context 크기 초과 (LLM token limit) | 초안 품질 저하 | MEDIUM | token budget 4000, truncation: recent_first |
| lib.slack API 변경 | Slack adapter 동작 불가 | LOW | slack_sdk 직접 사용으로 의존성 최소화 |
| 동기/비동기 혼재 | deadlock/blocking | MEDIUM | asyncio.to_thread() 일관 사용 |

---

## Implementation Order Summary

```
Week 1: Phase 1 + Phase 2 (Foundation)
  Day 1-2: T1 (Context Store) + T2 (Project Registry)
  Day 2-3: T3 (Context Collector) + T3.5 (Project Indexer)
  Day 3-4: T4 (Analysis State) + T5 (Source Trackers)
  Day 4-5: T6 (Incremental Runner)

Week 2: Phase 3 + Phase 4 (Adapters + Response)
  Day 1-2: T7 (Slack Adapter) + T8 (Gmail Adapter)
  Day 2-3: T9 (Context Matcher) + T10 (Draft Generator)
  Day 3-4: T11 (Draft Store) + T12 (Pipeline Integration)

Week 3: Phase 5 (Integration + Polish)
  Day 1-2: T13 (CLI) + T14 (Config/Prompts)
  Day 2-3: Integration testing + bug fixes
  Day 3: Documentation + final review
```

---

## How to Start Implementation

```
/oh-my-claudecode:start-work project-intelligence
```

이 명령어로 plan을 로드하고 Task별 executor agent를 순차/병렬로 실행합니다.
