# Secretary 프로젝트 마스터 워크플로우 보고서

**작성일**: 2026-02-18
**프로젝트**: Secretary AI - 통합 일일 업무 자동화 비서 도구
**상태**: 전체 모듈 구현 완료, 운영 환경 가동

---

## 1. 프로젝트 개요

### 비전
Gmail, Google Calendar, GitHub, Slack, LLM 세션을 통합 분석하여 일일 업무 현황 리포트를 자동으로 생성하고, 자동화 액션을 실행하는 AI 비서 도구.

### 주요 기능
- **Daily Report**: 각 소스별 분석기를 subprocess로 실행, JSON 결과를 종합하여 일일 통합 리포트 생성
- **Gateway**: 멀티 채널(Slack, Gmail) 실시간 메시지 수신 및 6단계 파이프라인 처리
- **Intelligence**: 2-Tier LLM으로 메시지 분석(Ollama qwen3:8b) 및 응답 초안 생성(Claude Opus)
- **Knowledge**: SQLite FTS5 기반 프로젝트별 지식 저장소 (Gmail/Slack 히스토리 학습)
- **Reporter**: Slack DM으로 긴급 알림, 초안 알림, 일일 Digest 전송
- **Life Management**: MS To Do 연동, 생활 이벤트 리마인더, 법인 세무 일정

### 요구사항
- Python 3.10+
- Windows 환경 (Toast 알림 winotify 의존)

---

## 2. 핵심 모듈 아키텍처 (6개 모듈)

### 아키텍처 개요

| 모듈 | 경로 | 역할 | 핵심 기능 |
|------|------|------|----------|
| **Gateway** | `scripts/gateway/` | 멀티 채널 메시지 수신 + 6단계 파이프라인 처리 | Slack/Gmail 실시간 수신, 메시지 정규화, 우선순위 분석 |
| **Intelligence** | `scripts/intelligence/` | 2-Tier LLM 분석 (Ollama + Claude Opus) | 자동 분석, 응답 초안 생성, 프로젝트 매칭 |
| **Knowledge** | `scripts/knowledge/` | SQLite FTS5 프로젝트별 지식 저장소 | 문서 저장, 전문 검색, 메타데이터 필터링 |
| **Reporter** | `scripts/reporter/` | Slack DM 보고 (긴급, 초안, Digest) | 알림 전송, 일일 통계 집계 |
| **Shared** | `scripts/shared/` | 공통 유틸리티 | 경로 관리, 상수, Rate limiter, 재시도 |
| **Life** | `scripts/` (life 관련) | MS To Do, 생활 이벤트, 세무 일정 | 투두 동기화, 이벤트 리마인더 |

---

## 3. 마스터 데이터 흐름 (핵심!)

### 3.1 전체 흐름도

```
메시지 수신 (Slack/Gmail)
    ↓
[Gateway 채널 어댑터]
  ├─ SlackAdapter (실시간 리스너 + 폴링)
  └─ GmailAdapter (폴링)
    ↓
[MessagePipeline 6단계]
  ├─ Stage 0.5: ProjectContextResolver
  │   └─ 메시지의 project_id 결정 (프로젝트별 규칙 기반)
  │
  ├─ Stage 1: Priority Analysis
  │   └─ 긴급 키워드 감지 (project_id별 urgent_keywords)
  │
  ├─ Stage 2: Action Detection
  │   ├─ 할일 감지 (action_keywords)
  │   └─ 마감일 감지 (deadline_patterns)
  │
  ├─ Stage 3: Storage
  │   └─ aiosqlite WAL mode로 gateway.db에 저장
  │
  ├─ Stage 4: Notification
  │   └─ Windows Toast 알림 (프로젝트별 규칙, project_id 포함)
  │
  ├─ Stage 5: Action Dispatch
  │   └─ ActionDispatcher
  │       ├─ TODO 생성 (MS To Do)
  │       └─ Calendar dry-run (확인 필수)
  │
  └─ Stage 6: Custom Handlers (Intelligence)
      └─ ProjectIntelligenceHandler
          ↓
[Intelligence 2-Tier LLM 분석]
  ├─ DedupFilter
  │   └─ LRU 메모리 캐시 + DB 2단 중복 체크
  │
  ├─ ContextMatcher
  │   └─ 규칙 기반 프로젝트 매칭 힌트 생성
  │
  ├─ OllamaAnalyzer (Tier 1: qwen3:8b)
  │   └─ 모든 메시지 분석
  │       ├─ needs_response (bool): 응답 필요 여부
  │       ├─ project_id (str): 프로젝트 식별자
  │       ├─ intent (str): 메시지 의도
  │       ├─ summary (str): 요약
  │       └─ confidence (0.0-1.0): 신뢰도
  │
  ├─ Project ID 결정 로직
  │   ├─ IF Ollama confidence >= 0.7 → Ollama project_id 사용
  │   ├─ ELSE IF 규칙 기반 매칭 성공 → 규칙 기반 project_id
  │   ├─ ELSE IF Ollama confidence >= 0.3 → Ollama project_id
  │   └─ ELSE → pending_match로 저장 후 종료
  │
  ├─ IntelligenceStorage DB 저장
  │   ├─ analyses 테이블
  │   ├─ pending_matches 테이블
  │   └─ analysis_metadata
  │
  ├─ ClaudeCodeDraftWriter (Tier 2: Claude Opus)
  │   └─ needs_response=true일 때만 실행
  │       ├─ 메시지 컨텍스트 수집 (Knowledge)
  │       ├─ 프롬프트 생성
  │       └─ Claude Opus subprocess로 초안 작성
  │
  ├─ DraftStore
  │   ├─ intelligence.db drafts 테이블에 저장
  │   └─ data/drafts/ 마크다운 파일 생성
  │
  └─ Reporter
      ├─ 긴급 알림 (send_urgent_alert)
      │   └─ 즉시 Slack DM 전송
      ├─ 초안 알림 (send_draft_notification)
      │   └─ 초안 생성 시 Slack DM 알림
      └─ 일일 Digest (send_daily_digest)
          └─ 매일 18:00 자동 전송
```

### 3.2 메시지 정규화 (NormalizedMessage)

모든 채널의 메시지는 `NormalizedMessage` 모델로 정규화됨:

```python
@dataclass
class NormalizedMessage:
    message_id: str              # 고유 ID (Slack ts / Gmail message id)
    channel_id: str              # 채널 ID
    channel_type: ChannelType    # slack | gmail
    sender_id: str               # 발신자 ID
    sender_name: str             # 발신자명
    timestamp: datetime          # 수신 시간
    subject: str                 # 제목 (Gmail: subject / Slack: thread 첫 메시지)
    body: str                    # 메시지 본문 (MAX_TEXT_STORAGE=4000)
    project_id: Optional[str]    # Stage 0.5에서 결정
    priority: Optional[str]      # Stage 1에서 결정 (HIGH, NORMAL, LOW)
    has_action: bool             # Stage 2에서 결정
    needs_response: Optional[bool] # Intelligence Tier 1에서 결정
```

### 3.3 ActionDispatcher (Stage 5)

탐지된 deadline/action_request를 자동으로 처리:

- **TODO 생성**: `scripts/` 내 calendar_creator 등으로 MS To Do 생성
- **Calendar dry-run**: `--confirm` 플래그 없으면 실행 안함 (안전 장치)

---

## 4. 운영 환경 (전체 인증 완료)

### 4.1 외부 서비스 상태

| 서비스 | 상태 | 인증 파일 | 용도 |
|--------|------|----------|------|
| **Slack** | ✅ Gateway enabled | `C:\claude\json\slack_credentials.json` | 메시지 수신 + DM 전송 |
| **Gmail** | ✅ Gateway enabled | `C:\claude\json\desktop_credentials.json`, `token_gmail.json` | 메시지 수신 + 분석 |
| **Calendar** | ✅ 연동 완료 | `C:\claude\json\token_calendar.json` | 일정 생성 (dry-run) |
| **GitHub** | ✅ 연동 완료 | `C:\claude\json\github_token.txt` | 저장소 분석 |
| **Ollama** | ✅ 상시 실행 | `http://localhost:11434` | Tier 1 분석 (qwen3:8b) |
| **Claude CLI** | ✅ 사용 가능 | Claude Code 세션 내 | Tier 2 초안 작성 (subprocess) |
| **MS To Do** | ✅ 연동 완료 | `C:\claude\json\token_mstodo.json` | TODO 관리 |

**인증 방식**: Browser OAuth (API 키 금지). 토큰 저장: `C:\claude\json\`

### 4.2 주요 상수

| 상수 | 값 | 용도 |
|------|-----|------|
| `MAX_TEXT_STORAGE` | 4000 | 메시지 본문 절삭 |
| `Pipeline Rate Limit` | 10/min | Stage 처리 제한 |
| `Claude Draft Rate Limit` | 5/min | Tier 2 LLM 제한 |
| `Ollama Rate Limit` | 10/min | Tier 1 분석 제한 |

---

## 5. 설정 체계

### 5.1 설정 파일 구조

```
config/
├── gateway.json              # Gateway 채널, 파이프라인, Intelligence LLM 설정
├── projects.json             # 프로젝트 등록 (ID, Slack 채널, Gmail 쿼리, 키워드)
├── life_events.json          # 생활 이벤트 (생일, 기념일)
├── tax_calendar.json         # 법인 세무 일정
├── privacy.json              # 프라이버시 설정
├── mstodo.json               # MS To Do 연동 설정
└── prompts/                  # LLM 프롬프트 템플릿
    ├── system.md             # Ollama/Claude 시스템 프롬프트
    ├── analyze.md            # 분석 프롬프트
    └── notify.md             # 알림 생성 프롬프트
```

### 5.2 gateway.json (주요 설정)

```json
{
  "enabled": true,
  "port": 8800,
  "channels": {
    "slack": {
      "enabled": true,
      "channels": ["C0985UXQN6Q"],
      "polling_interval": 5
    },
    "gmail": {
      "enabled": true,
      "polling_interval": 60
    }
  },
  "intelligence": {
    "ollama": {
      "enabled": true,
      "endpoint": "http://localhost:11434",
      "model": "qwen3:8b",
      "rate_limit_per_minute": 10
    },
    "claude_draft": {
      "enabled": true,
      "model": "opus",
      "rate_limit_per_minute": 5
    }
  },
  "safety": {
    "auto_send_disabled": true,    # 자동 전송 금지
    "require_confirmation": true    # 수동 확인 필수
  }
}
```

### 5.3 projects.json (프로젝트 등록)

```json
{
  "projects": [
    {
      "id": "secretary",
      "name": "Secretary AI",
      "slack_channels": ["C0985UXQN6Q"],
      "gmail_queries": ["subject:(secretary OR daily report)"],
      "keywords": ["secretary", "비서", "리포트", "gateway", "intelligence"],
      "pipeline_config": {
        "urgent_keywords": ["서버다운", "장애", "에러"],
        "action_keywords": ["배포", "릴리즈", "리뷰"],
        "notification_rules": {
          "toast_enabled": true,
          "digest_enabled": true
        }
      }
    }
  ]
}
```

---

## 6. 런타임 데이터 저장소

### 6.1 데이터베이스

| 경로 | 용도 | 엔진 | 모드 |
|------|------|------|------|
| `data/gateway.db` | Gateway 메시지 저장 | aiosqlite | WAL (비동기 안전) |
| `data/intelligence.db` | Intelligence 분석 결과, 초안 | SQLite | WAL |
| `data/knowledge.db` | Knowledge Store (FTS5 전문검색) | SQLite | WAL (최초 학습 시 생성) |

> **참고**: `knowledge.db`는 Knowledge Bootstrap 학습 실행 시 최초 생성됩니다. `gateway.pid`는 Gateway 서버 실행 중에만 존재합니다.

### 6.2 파일 저장소

| 경로 | 용도 | 예시 |
|------|------|------|
| `data/drafts/` | 생성된 응답 초안 마크다운 | `draft_20260218_abc123.md` |
| `data/gateway.pid` | Gateway 서버 PID 파일 (서버 실행 중에만 존재) | `8240` |

### 6.3 Gateway DB 스키마 (주요 테이블)

```sql
-- 메시지 저장
CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    channel_id TEXT,
    channel_type TEXT,
    sender_id TEXT,
    timestamp DATETIME,
    subject TEXT,
    body TEXT,
    project_id TEXT,
    priority TEXT,
    has_action BOOLEAN,
    raw_data JSON,
    created_at DATETIME
);

-- 파이프라인 결과
CREATE TABLE pipeline_results (
    id INTEGER PRIMARY KEY,
    message_id TEXT,
    stage TEXT,
    result JSON,
    error TEXT,
    processed_at DATETIME
);
```

### 6.4 Intelligence DB 스키마 (주요 테이블)

```sql
-- 분석 결과
CREATE TABLE analyses (
    id INTEGER PRIMARY KEY,
    message_id TEXT,
    project_id TEXT,
    intent TEXT,
    summary TEXT,
    needs_response BOOLEAN,
    confidence REAL,
    analysis_data JSON,
    created_at DATETIME
);

-- 초안 저장
CREATE TABLE drafts (
    id TEXT PRIMARY KEY,
    message_id TEXT,
    project_id TEXT,
    status TEXT,  -- pending, approved, rejected, sent
    draft_content TEXT,
    created_at DATETIME,
    approved_at DATETIME,
    sent_at DATETIME
);

-- 미매칭 메시지
CREATE TABLE pending_matches (
    id INTEGER PRIMARY KEY,
    message_id TEXT,
    analysis_data JSON,
    created_at DATETIME
);
```

---

## 7. 모듈별 상세 아키텍처

### 7.1 Gateway 모듈 (`scripts/gateway/`)

**구성**:
- `server.py`: Central Gateway Server (main 엔트리포인트)
- `pipeline.py`: MessagePipeline (6단계 처리)
- `adapters/`: ChannelAdapter 구현 (Slack, Gmail)
- `models.py`: NormalizedMessage, Priority, ChannelType
- `storage.py`: UnifiedStorage (aiosqlite 래퍼)
- `action_dispatcher.py`: Stage 5 액션 처리
- `project_context.py`: ProjectContextResolver (Stage 0.5)

**특징**:
- 비동기 처리 (asyncio)
- WAL mode SQLite (동시 읽기/쓰기 안전)
- 프로젝트별 규칙 기반 처리
- 플러그인 방식 핸들러 (Stage 6)

**사용법**:
```bash
python scripts/gateway/server.py start [--port 8800]
python scripts/gateway/server.py stop
python scripts/gateway/server.py status
python scripts/gateway/server.py channels
```

### 7.2 Intelligence 모듈 (`scripts/intelligence/`)

**구성**:
```
intelligence/
├── cli.py                 # CLI 인터페이스
├── context_store.py       # IntelligenceStorage (WAL SQLite)
├── context_collector.py   # 컨텍스트 수집
├── project_registry.py    # ProjectRegistry (config/projects.json)
├── response/
│   ├── handler.py        # ProjectIntelligenceHandler (main)
│   ├── analyzer.py       # OllamaAnalyzer (Tier 1)
│   ├── draft_writer.py   # ClaudeCodeDraftWriter (Tier 2, subprocess)
│   ├── draft_store.py    # DraftStore (DB + 파일)
│   ├── context_matcher.py # ContextMatcher (규칙 기반)
│   └── dedup_filter.py   # DedupFilter (중복 제거)
└── incremental/          # 증분 분석 (선택적)
    ├── runner.py
    └── trackers/         # Gmail, Slack, GitHub tracker
```

**2-Tier LLM 아키텍처**:

| Tier | 모델 | 처리 대상 | 목적 | 비용 |
|------|------|----------|------|------|
| **Tier 1** | Ollama qwen3:8b | 모든 메시지 | 빠른 분석 (needs_response, intent, project_id) | 낮음 |
| **Tier 2** | Claude Opus | needs_response=true 메시지만 | 고품질 응답 초안 생성 | 높음 |

**처리 흐름**:
1. DedupFilter: 중복 메시지 제거 (LRU + DB 체크)
2. Chatbot 채널 분기: chatbot_channels 목록 확인 → Ollama 응답 생성 후 EARLY RETURN
3. ContextMatcher: 규칙 기반 매칭 힌트 (3-tier: Channel > Keyword > Sender)
4. RAG 컨텍스트 검색: Knowledge Store에서 과거 히스토리 검색 (최대 5개, 각 300자)
5. OllamaAnalyzer: Tier 1 분석
6. Project ID 결정: Ollama(conf≥0.7) > 규칙(conf≥0.6) > Ollama(conf≥0.3) > pending_match
7. 미매칭 메시지 → pending_match 테이블 저장 후 종료
8. needs_response=true → ClaudeCodeDraftWriter (Tier 2)
9. DraftStore: DB + 파일 저장
10. Reporter: 알림 전송

**CLI 명령**:
```bash
# 분석
python scripts/intelligence/cli.py analyze [--project ID] [--source slack|gmail|github]

# 초안 관리
python scripts/intelligence/cli.py drafts [--status pending|approved|rejected]
python scripts/intelligence/cli.py drafts approve <id>
python scripts/intelligence/cli.py drafts reject <id>

# 통계
python scripts/intelligence/cli.py stats [--json]
python scripts/intelligence/cli.py knowledge stats [--project ID]
```

### 7.3 Knowledge 모듈 (`scripts/knowledge/`)

**역할**: SQLite FTS5 기반 프로젝트별 지식 저장소

**구성**:
- `store.py`: KnowledgeStore (ingest, search, cleanup)
- `bootstrap.py`: KnowledgeBootstrap (일괄 학습)
- `models.py`: KnowledgeDocument, SearchResult

**기능**:
- 문서 저장 (ingest)
- 전문 검색 (FTS5)
- 메타데이터 필터 (sender, thread_id)
- 유지보수 (retention_days 기반 정리)

**용도**: Intelligence Tier 2에서 컨텍스트 수집

### 7.4 Reporter 모듈 (`scripts/reporter/`)

**역할**: Slack DM 보고 시스템

**구성**:
- `reporter.py`: SecretaryReporter (오케스트레이터)
  - `send_urgent_alert()`: 긴급 메시지 즉시 전송
  - `send_draft_notification()`: 초안 생성 알림
  - `send_daily_digest()`: 매일 18:00 자동 전송
- `digest.py`: DigestReport (일일 통계 집계)
- `channels/slack_dm.py`: Slack DM 어댑터

**특징**:
- 비동기 처리
- Rate limiting 준수
- 타임스탬프 기반 중복 제거

### 7.5 Shared 공통 모듈 (`scripts/shared/`)

| 모듈 | 역할 |
|------|------|
| `paths.py` | 프로젝트 루트 자동 탐색, 경로 상수 (`PROJECT_ROOT`, `CONFIG_DIR`, `DATA_DIR`, `GATEWAY_DB` 등) |
| `constants.py` | 텍스트 절삭 상수 (`MAX_TEXT_STORAGE=4000`), Rate limit 상수 |
| `rate_limiter.py` | 싱글톤 Rate limiter (Pipeline 10/min, Claude 5/min, Ollama 10/min) |
| `retry.py` | Exponential backoff 비동기 재시도 래퍼 |

---

## 8. 안전 장치 (Safety Guardrails)

| 규칙 | 설명 | 구현 |
|------|------|------|
| **자동 전송 금지** | `response_drafter.py`, `draft_writer.py`는 절대 자동으로 이메일/메시지 전송하지 않음 | `auto_send_disabled: true` in gateway.json |
| **확인 필수** | `calendar_creator.py`는 `--confirm` 없으면 dry-run만 수행 | CLI `--confirm` 플래그 체크 |
| **Rate Limiting** | Pipeline 10/min, Claude draft 5/min, Ollama 10/min | `shared/rate_limiter.py` |
| **Draft 승인 워크플로우** | Intelligence 초안은 `cli.py drafts approve/reject`로 수동 리뷰 필수 | DB status: pending → approved → sent |
| **컨텍스트 길이 제한** | 메시지 본문 4000자 절삭, Ollama 입력 12000자 제한 | `MAX_TEXT_STORAGE`, `max_context_chars` |

---

## 9. CLI 인터페이스

### 9.1 Gateway 서버

```bash
# 시작 (기본 포트 8800)
python scripts/gateway/server.py start

# 시작 (커스텀 포트)
python scripts/gateway/server.py start --port 9000

# 상태 확인
python scripts/gateway/server.py status

# 활성 채널 확인
python scripts/gateway/server.py channels

# 종료
python scripts/gateway/server.py stop
```

### 9.2 Intelligence CLI

```bash
# 분석 실행
python scripts/intelligence/cli.py analyze

# 프로젝트별 분석
python scripts/intelligence/cli.py analyze --project secretary

# 소스별 분석
python scripts/intelligence/cli.py analyze --source slack

# 미승인 초안 조회
python scripts/intelligence/cli.py drafts --status pending

# 초안 승인
python scripts/intelligence/cli.py drafts approve <draft_id>

# 초안 거절
python scripts/intelligence/cli.py drafts reject <draft_id>

# 통계 조회
python scripts/intelligence/cli.py stats --json

# 지식 저장소 학습 (Gmail)
python scripts/intelligence/cli.py learn --project secretary --source gmail --label label --limit 50

# 지식 검색
python scripts/intelligence/cli.py search --project secretary "query" --json
```

### 9.3 Daily Report

```bash
# 일일 리포트 생성
python scripts/daily_report.py

# JSON 출력
python scripts/daily_report.py --json
```

### 9.4 개별 분석기

```bash
# Gmail 분석
python scripts/gmail_analyzer.py --unread --days 3

# Calendar 분석
python scripts/calendar_analyzer.py --today

# GitHub 분석
python scripts/github_analyzer.py --days 5

# Slack 분석
python scripts/slack_analyzer.py --days 3 --channels general,team

# LLM 세션 분석
python scripts/llm_analyzer.py --days 7 --source claude_code
```

---

## 10. Import 패턴 (3중 Fallback)

모든 모듈은 **직접 실행**과 **패키지 import**를 모두 지원합니다:

```python
try:
    # 패턴 1: 프로젝트 루트에서 실행
    from scripts.gateway.models import NormalizedMessage
except ImportError:
    try:
        # 패턴 2: scripts/ 내에서 실행
        from gateway.models import NormalizedMessage
    except ImportError:
        # 패턴 3: 패키지 내부 import
        from .models import NormalizedMessage
```

**이점**:
- `python scripts/gateway/pipeline.py` (직접 실행) ✅
- `from scripts.gateway.pipeline import MessagePipeline` (패키지 import) ✅
- 테스트에서 상대 import 가능 ✅

---

## 11. 테스트 현황

### 11.1 테스트 커버리지

```
22개 테스트 중 21개가 외부 서비스 없이 즉시 실행 가능
```

| 테스트 범주 | 파일 수 | 외부 의존 | 즉시 실행 |
|------------|:------:|----------|:--------:|
| 순수 단위 테스트 | 11 | 없음 | ✅ |
| mock 기반 테스트 | 6 | mock으로 대체 | ✅ |
| 통합 테스트 (SQLite) | 5 | aiosqlite (tmp_path) | ✅ |
| 실제 서비스 필요 | 1 | Windows Toast | ❌ |

### 11.2 테스트 실행 방법

```bash
# 전체 테스트 (test_actions.py만 제외)
pytest tests/ --ignore=tests/test_actions.py -v

# 개별 테스트
pytest tests/gateway/test_pipeline.py -v

# 린트 검사
ruff check scripts/ --fix
```

---

## 12. 프로젝트 구조 (전체)

```
C:\claude\secretary\
├── scripts/
│   ├── gateway/                    # Gateway 모듈
│   │   ├── server.py              # 메인 서버
│   │   ├── pipeline.py            # 6단계 파이프라인
│   │   ├── adapters/              # 채널 어댑터
│   │   │   ├── base.py
│   │   │   ├── slack.py
│   │   │   └── gmail.py
│   │   ├── models.py              # NormalizedMessage 등
│   │   ├── storage.py             # UnifiedStorage
│   │   ├── action_dispatcher.py   # Stage 5
│   │   └── project_context.py     # Stage 0.5
│   │
│   ├── intelligence/               # Intelligence 모듈
│   │   ├── cli.py                 # CLI 인터페이스
│   │   ├── context_store.py       # IntelligenceStorage
│   │   ├── context_collector.py
│   │   ├── project_registry.py
│   │   ├── response/              # 2-Tier LLM
│   │   │   ├── handler.py
│   │   │   ├── analyzer.py        # Ollama (Tier 1)
│   │   │   ├── draft_writer.py    # Claude (Tier 2)
│   │   │   ├── draft_store.py
│   │   │   ├── context_matcher.py
│   │   │   └── dedup_filter.py
│   │   └── incremental/           # 증분 분석
│   │
│   ├── knowledge/                  # Knowledge 모듈
│   │   ├── store.py               # KnowledgeStore
│   │   ├── bootstrap.py
│   │   └── models.py
│   │
│   ├── reporter/                   # Reporter 모듈
│   │   ├── reporter.py
│   │   ├── digest.py
│   │   └── channels/
│   │       └── slack_dm.py
│   │
│   ├── shared/                     # Shared 공통 모듈
│   │   ├── paths.py
│   │   ├── constants.py
│   │   ├── rate_limiter.py
│   │   └── retry.py
│   │
│   ├── daily_report.py            # Daily Report 오케스트레이터
│   ├── gmail_analyzer.py
│   ├── calendar_analyzer.py
│   ├── github_analyzer.py
│   ├── slack_analyzer.py
│   └── llm_analyzer.py
│
├── config/
│   ├── gateway.json               # Gateway 설정
│   ├── projects.json              # 프로젝트 등록
│   ├── life_events.json
│   ├── tax_calendar.json
│   ├── privacy.json
│   ├── mstodo.json
│   └── prompts/                   # LLM 프롬프트
│
├── data/
│   ├── gateway.db                 # Gateway 메시지 저장소
│   ├── intelligence.db            # Intelligence 분석/초안 저장소
│   ├── knowledge.db               # Knowledge FTS5 저장소
│   ├── drafts/                    # 생성된 초안 파일
│   └── gateway.pid                # Gateway 서버 PID
│
├── tests/                          # 테스트 스위트 (22개 테스트)
│   ├── gateway/
│   ├── intelligence/
│   ├── knowledge/
│   └── reporter/
│
├── docs/
│   ├── 01-plan/                   # 계획 문서
│   ├── 02-design/                 # 설계 문서
│   ├── 04-report/                 # 보고서
│   │   ├── project-master-workflow.report.md (이 파일)
│   │   ├── intelligence-redesign.report.md
│   │   ├── gateway-multi-label.report.md
│   │   └── ...
│   └── BUILD_TEST.md
│
├── CLAUDE.md                       # 프로젝트 가이드
├── README.md
└── requirements.txt
```

---

## 13. 워크플로우 스냅샷 (실시간 처리 예시)

### 예시: Slack 메시지 "Secretary 프로젝트 배포 검토 부탁합니다. 오늘까지 처리 바랍니다."

```
1. Slack 메시지 수신
   ├─ message_id: ts=1708099200
   ├─ channel_id: C0985UXQN6Q
   ├─ sender_id: U040EUZ6JRY
   └─ body: "Secretary 프로젝트 배포 검토 부탁합니다. 오늘까지 처리 바랍니다."

2. [Stage 0.5] ProjectContextResolver
   ├─ 키워드 매칭: "배포", "검토" → project_id = "secretary"
   └─ NormalizedMessage 생성

3. [Stage 1] Priority Analysis
   ├─ 급함 감지: "오늘까지" (deadline_pattern 매칭)
   ├─ 긴급 키워드: None (urgent_keywords에 없음)
   └─ Priority = NORMAL

4. [Stage 2] Action Detection
   ├─ 액션 키워드: "검토", "부탁" (action_keywords 매칭)
   ├─ 마감일 감지: "오늘까지" → deadline = 2026-02-18 23:59:59
   └─ has_action = true

5. [Stage 3] Storage
   ├─ gateway.db의 messages 테이블에 저장
   └─ pipeline_results에 Stage 1-4 결과 기록

6. [Stage 4] Notification
   ├─ Priority = NORMAL → Toast 알림 스킵 (urgent/high만 전송)
   └─ project_id별 notification_rules 적용

7. [Stage 5] Action Dispatch
   ├─ ActionDispatcher 분석
   ├─ deadline 감지 → Calendar creator 호출 (--confirm 없으면 dry-run)
   └─ TODO 추가 제안

8. [Stage 6] Intelligence Handler
   ├─ DedupFilter: 중복 체크 (첫 메시지이므로 통과)
   ├─ ContextMatcher: "배포", "검토" → secretary 힌트 생성
   │
   ├─ OllamaAnalyzer (Tier 1)
   │  ├─ 입력: body + context_hint
   │  ├─ 모델: qwen3:8b
   │  └─ 결과:
   │      ├─ project_id: "secretary" (confidence: 0.95)
   │      ├─ intent: "request_review"
   │      ├─ needs_response: true
   │      └─ summary: "Secretary 배포 코드 리뷰 요청, 당일 완료 필요"
   │
   ├─ Project ID 결정
   │  └─ Ollama confidence (0.95) >= 0.7 → project_id = "secretary" 확정
   │
   ├─ IntelligenceStorage 저장
   │  └─ analyses 테이블: analysis_id, message_id, project_id, intent, summary, needs_response
   │
   ├─ needs_response=true 확인
   │  └─ ClaudeCodeDraftWriter (Tier 2) 호출
   │
   ├─ ClaudeCodeDraftWriter
   │  ├─ Knowledge 컨텍스트 수집
   │  │  └─ "secretary 배포" 관련 이전 메시지, 코드 검토 가이드 등
   │  ├─ 프롬프트 생성
   │  └─ Claude Opus subprocess 호출
   │      └─ 초안: """
   │         안녕하세요. Secretary 배포 검토를 확인했습니다.
   │
   │         체크리스트:
   │         - 단위 테스트 상태 확인
   │         - Gateway 모듈 변경사항 검토
   │         - Intelligence 분석 로직 검증
   │
   │         오늘 검토 완료 후 피드백 제공하겠습니다.
   │         """
   │
   ├─ DraftStore
   │  ├─ intelligence.db drafts 테이블 저장
   │  │  └─ status: "pending", created_at: 2026-02-18T12:30:00Z
   │  └─ data/drafts/draft_20260218_ts1708099200.md 생성
   │
   └─ Reporter
       └─ send_draft_notification()
           └─ Slack DM 전송: "[secretary] 배포 검토 응답 초안 생성\n초안 ID: draft_20260218_ts1708099200\n승인: @secretary drafts approve draft_20260218_ts1708099200"

9. 사용자 액션
   ├─ 초안 검토: data/drafts/draft_20260218_ts1708099200.md 열기
   ├─ 초안 승인
   │  └─ python scripts/intelligence/cli.py drafts approve draft_20260218_ts1708099200
   │      └─ DB status: pending → approved
   │      └─ Reporter send_draft_notification() (재전송 안함, 기록만)
   └─ 자동 전송은 발생하지 않음 (안전 장치)

10. 결과
    ├─ Gateway: 메시지 저장 + 파이프라인 결과 기록
    ├─ Intelligence: 분석 결과 저장 + 초안 생성 + 대기
    ├─ Reporter: 알림 전송 완료
    └─ 데이터: gateway.db, intelligence.db, data/drafts/ 모두 업데이트
```

---

## 14. 운영 체크리스트

### Daily Operations

```
매일 아침
├─ [ ] Gateway 서버 상태 확인
│       python scripts/gateway/server.py status
├─ [ ] Intelligence 분석 대기 중인 메시지 확인
│       python scripts/intelligence/cli.py pending --json
└─ [ ] 생성된 초안 리뷰 및 승인
        python scripts/intelligence/cli.py drafts --status pending

매일 저녁 (18:00)
├─ [ ] Daily Report 생성
│       python scripts/daily_report.py
└─ [ ] Reporter.send_daily_digest() 자동 실행 (scheduled)
```

### Weekly Operations

```
매주 월요일
├─ [ ] 프로젝트 설정 검토 (config/projects.json)
├─ [ ] Knowledge 저장소 학습 (필요 시)
│       python scripts/intelligence/cli.py learn --project secretary --source slack --limit 50
├─ [ ] 미매칭 메시지 분석
│       SELECT * FROM intelligence.db pending_matches ORDER BY created_at DESC;
└─ [ ] Rate limit 통계 확인
        python scripts/intelligence/cli.py stats --json
```

### Monthly Operations

```
매월 말
├─ [ ] 데이터베이스 정리 (retention 30일)
│       python scripts/intelligence/cli.py cleanup --days 30
├─ [ ] Knowledge 저장소 정리
│       python scripts/intelligence/cli.py knowledge cleanup --days 30
├─ [ ] 로그 파일 아카이브
└─ [ ] 프로젝트 구성 백업
        git add -A && git commit -m "chore: monthly backup"
```

---

## 15. 트러블슈팅

### Gateway 서버 시작 실패

```bash
# 포트 충돌 확인
netstat -ano | findstr :8800

# 다른 포트로 시작
python scripts/gateway/server.py start --port 9000

# PID 파일 정리 (강제)
rm data/gateway.pid
```

### Intelligence 분석이 시작되지 않음

```bash
# Ollama 연결 확인
curl http://localhost:11434/api/tags

# Ollama 모델 로드 확인
python -c "import requests; print(requests.get('http://localhost:11434/api/tags').json())"

# Intelligence 스토리지 초기화
python -c "from scripts.intelligence.context_store import IntelligenceStorage; import asyncio; asyncio.run(IntelligenceStorage().connect())"
```

### 메시지가 저장되지 않음

```bash
# Gateway DB 상태 확인
sqlite3 data/gateway.db ".tables"

# 최근 메시지 조회
sqlite3 data/gateway.db "SELECT * FROM messages ORDER BY created_at DESC LIMIT 5;"

# 파이프라인 결과 조회
sqlite3 data/gateway.db "SELECT * FROM pipeline_results ORDER BY processed_at DESC LIMIT 10;"
```

---

## 16. 성과 및 한계

### 구현 완료

✅ 전체 6개 모듈 구현
✅ 멀티 채널 메시지 수신 (Slack, Gmail)
✅ 6단계 파이프라인 처리
✅ 2-Tier LLM 분석 (Ollama + Claude)
✅ 초안 생성 및 워크플로우
✅ 안전 장치 (자동 전송 금지, 확인 필수)
✅ Rate limiting
✅ 21/22 테스트 자동 실행

### 알려진 한계

⚠️ **프로젝트 자동 매칭**: Ollama confidence >= 0.7 기준 (고정)
⚠️ **초안 자동 전송 미지원**: 수동 승인 필수
⚠️ **Knowledge 검색 정확도**: FTS5 기본 가중치 (커스터마이징 가능)
⚠️ **스케일**: 대량 메시지(>1000/일) 시 성능 테스트 필요

---

## 17. 향후 개선 방향

| 우선순위 | 항목 | 예상 효과 |
|---------|------|----------|
| **P0** | 프로젝트 자동 매칭 정확도 향상 (ML 기반) | 초안 생성 자동화율 ↑ |
| **P1** | 채팅봇 응답 자동 전송 (사용자 옵션) | 사용자 상호작용 시간 ↓ |
| **P1** | 멀티 언어 지원 (영문, 일문) | 글로벌 확장 |
| **P2** | 음성 메시지 지원 (Slack Thread) | 사용자 편의성 ↑ |
| **P2** | Dashboard UI (웹 기반) | 모니터링 용이성 ↑ |

---

## 18. 기술 스택 요약

| 영역 | 기술 | 버전 |
|------|------|------|
| **언어** | Python | 3.10+ |
| **비동기** | asyncio | stdlib |
| **데이터베이스** | SQLite (WAL) | 3.x |
| **ORM** | aiosqlite | 0.19+ |
| **전문검색** | FTS5 | SQLite built-in |
| **LLM (Tier 1)** | Ollama qwen3:8b | local |
| **LLM (Tier 2)** | Claude Opus | API (subprocess) |
| **메시징** | Slack SDK | 3.x |
| **메일** | Google Gmail API | v1 |
| **캘린더** | Google Calendar API | v3 |
| **테스트** | pytest | 7.x |
| **린트** | ruff | latest |

---

## 19. 결론

**Secretary 프로젝트**는 Gmail, Calendar, GitHub, Slack, LLM을 통합한 완전한 AI 비서 시스템입니다.

**핵심 가치**:
1. **일관된 메시지 처리**: 모든 채널을 정규화된 파이프라인으로 처리
2. **지능형 분석**: 2-Tier LLM으로 빠른 분석 + 고품질 초안 생성
3. **안전 운영**: 자동 전송 금지, 수동 확인 필수
4. **확장 가능**: 플러그인 방식 핸들러, 프로젝트별 규칙 설정

**현재 상태**: 모든 모듈 구현 완료, 외부 서비스 인증 완료, 운영 환경 가동 중.

**다음 단계**: 실제 운영 데이터 수집, 프로젝트 매칭 정확도 개선, 추가 채널 통합 (Telegram, Teams 등).

---

**문서 버전**: 1.0
**마지막 업데이트**: 2026-02-18
**작성자**: Claude Code Technical Writer
**상태**: 완료
