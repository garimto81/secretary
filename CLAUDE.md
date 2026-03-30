# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Gmail, Google Calendar, GitHub, Slack, LLM 세션을 통합 분석하여 일일 업무 현황 리포트를 자동 생성하고, 자동화 액션을 실행하는 AI 비서 도구.

주요 기능:
- **Daily Report**: 각 소스별 분석기를 subprocess로 실행, JSON 결과를 종합
- **Gateway**: 멀티 채널(Slack, Gmail) 실시간 메시지 수신 및 6단계 파이프라인 처리
- **Intelligence**: 2-Tier LLM으로 메시지 분석(Ollama qwen3:8b) 및 응답 초안 생성(Claude Sonnet)
- **Knowledge**: SQLite FTS5 기반 프로젝트별 지식 저장소 + Channel Mastery 전문가 컨텍스트
- **Reporter**: Slack DM으로 긴급 알림, 초안 알림, 일일 Digest 전송
- **Life Management**: MS To Do 연동, 생활 이벤트 리마인더, 법인 세무 일정

**요구사항**: Python 3.11+, Windows (Toast 알림 등 winotify 의존)

## 빌드 및 테스트

```bash
pip install -r requirements.txt

# 린트
ruff check scripts/ tests/ --fix

# 테스트 실행
pytest tests/gateway/test_pipeline.py -v          # 개별 테스트 (권장)
pytest tests/ --ignore=tests/test_actions.py -v   # 전체 테스트 (test_actions.py 제외)

# Gateway 서버
python scripts/gateway/server.py start [--port 8800]
python scripts/gateway/server.py stop
python scripts/gateway/server.py status

# Intelligence CLI
python scripts/intelligence/cli.py analyze [--project ID] [--source slack|gmail|github]
python scripts/intelligence/cli.py pending [--json]
python scripts/intelligence/cli.py drafts [--status pending|approved|rejected]
python scripts/intelligence/cli.py drafts approve <id>
python scripts/intelligence/cli.py stats [--json]

# Daily Report
python scripts/daily_report.py [--json]

# 개별 분석기
python scripts/gmail_analyzer.py --unread --days 3
python scripts/calendar_analyzer.py --today
python scripts/github_analyzer.py --days 5
python scripts/slack_analyzer.py --days 3 --channels general,team
python scripts/llm_analyzer.py --days 7 --source claude_code
```

## 아키텍처

### 전체 데이터 흐름

```
Message (Slack/Gmail)
    ↓
Gateway (server.py → pipeline.py, 6 Stages)
    ├─ Stage 1-3: 우선순위 분석, 액션 탐지, DB 저장
    ├─ Stage 5: ActionDispatcher → TODO 생성, Calendar dry-run
    └─ Stage 6: ProjectIntelligenceHandler
        ├─ DedupFilter → 중복 제거
        ├─ EscalationRouter → Tier 2 에스컬레이션 판단
        ├─ OllamaAnalyzer (Tier 1) → 모든 메시지 분석
        └─ ClaudeCodeDraftWriter (Tier 2) → 응답 필요 시 초안 작성
            └─ Reporter → Slack DM 알림
```

### 1. Daily Report (subprocess 오케스트레이션)

`daily_report.py`가 각 분석기(`gmail_analyzer.py`, `calendar_analyzer.py`, `github_analyzer.py`, `slack_analyzer.py`, `llm_analyzer.py`)를 subprocess로 실행하고 JSON 결과를 수집하여 종합 리포트 생성.

### 2. Gateway (실시간 메시지 파이프라인)

```
SecretaryGateway (server.py)
    ├── ChannelAdapter (adapters/base.py) ─ 추상 인터페이스
    │   ├── SlackAdapter, GmailAdapter
    ├── ChannelRegistry (channel_registry.py) ─ config/channels.json 기반 채널 메타
    │   └── get_by_role(role, channel_type) → 역할별 채널 ID 목록
    ├── ChannelWatcher (channel_watcher.py) ─ 채널 상태 감시
    ├── ProjectContext (project_context.py) ─ 메시지-프로젝트 컨텍스트 매핑
    ├── MessagePipeline (pipeline.py) ─ 6단계 처리
    │   ├── Stage 1-3: Priority, Action Detection, Storage
    │   ├── Stage 5: ActionDispatcher (action_dispatcher.py)
    │   └── Stage 6: Custom Handlers (Intelligence)
    ├── UnifiedStorage (storage.py) ─ async SQLite (aiosqlite)
    └── NormalizedMessage (models.py) ─ 통합 메시지 모델
```

- 어댑터는 `ChannelAdapter` 추상 클래스를 구현 (`connect()`, `disconnect()`, `listen()`, `send()`)
- 새 채널 추가: `adapters/`에 어댑터 구현 → `server.py`의 `_create_adapter()`에 등록
- `ChannelRegistry`는 `config/channels.json`의 `roles` 필드로 채널 역할(intelligence, reporter 등)을 구분

### 3. Intelligence (2-Tier LLM 분석)

```
ProjectIntelligenceHandler (response/handler.py) ← Pipeline Stage 6
    ├── DedupFilter (dedup_filter.py) ─ LRU 메모리 캐시 + DB 2단 중복 체크
    ├── EscalationRouter (escalation_router.py) ─ Tier 2 에스컬레이션 판단
    │   └── 판단 기준: confidence < 0.6, complexity > 0.7, 기술 용어 밀도, 토큰 수
    ├── ContextMatcher (context_matcher.py) ─ 규칙 기반 프로젝트 매칭
    ├── OllamaAnalyzer (analyzer.py) ─ Tier 1: 로컬 LLM (qwen3:8b)
    ├── ClaudeCodeDraftWriter (draft_writer.py) ─ Tier 2: Claude Sonnet subprocess
    ├── DraftStore (draft_store.py) ─ 초안 DB 저장
    └── FeedbackStore (feedback_store.py) ─ approve/reject 사유 저장 (패턴 분석용)
```

처리 흐름:
1. DedupFilter로 중복 체크
2. ContextMatcher로 규칙 기반 힌트 생성
3. Ollama 분석 (Tier 1, 모든 메시지)
4. EscalationRouter로 Tier 2 에스컬레이션 필요 여부 판단
5. project_id 해석: Ollama(confidence >= 0.7) > 규칙 기반 > Ollama(confidence >= 0.3)
6. 매칭 실패 → `pending_match` 저장 후 종료
7. `needs_response=true` → Claude Sonnet 초안 작성 (Tier 2)

관련 저장소:
- `IntelligenceStorage` (context_store.py): SQLite WAL mode, 4 테이블
- `ProjectRegistry` (project_registry.py): `config/projects.json`에서 프로젝트 로드
- 증분 분석: `incremental/runner.py`, `incremental/trackers/` (Gmail, Slack, GitHub)
- `FeedbackStore`는 `IntelligenceStorage`의 connection을 공유 (독립 연결 금지)

### 4. Knowledge (프로젝트별 지식 저장소 + Channel Mastery)

```
KnowledgeStore (store.py) ─ SQLite FTS5 전문검색
    ├── ingest(doc) ─ 문서 저장
    ├── search(query, project_id) ─ FTS5 검색
    └── cleanup(retention_days) ─ 유지보수

KnowledgeBootstrap (bootstrap.py) ─ 일괄 학습

Channel Mastery 확장:
    ├── ChannelProfileStore (channel_profile.py) ─ 채널 메타데이터 SQLite 저장
    ├── ChannelMasteryAnalyzer (mastery_analyzer.py) ─ 채널 전문가 컨텍스트 생성
    │   └── TF-IDF 기반 키워드 추출, 한국어 불용어 처리
    ├── ChannelSonnetProfiler (channel_sonnet_profiler.py) ─ Sonnet 기반 채널 프로파일링
    ├── ChannelUpdateJudge (channel_update_judge.py) ─ 채널 지식 업데이트 필요 여부 판단
    └── ChannelPRDWriter (channel_prd_writer.py) ─ 채널 PRD 자동 작성
```

데이터 모델: `KnowledgeDocument`, `SearchResult`, `ChannelProfile` (models.py)

#### 새 채널 분석 등록 방법

1. `config/channels.json`에 채널 정보 추가:
   ```json
   {"id": "C채널ID", "name": "채널명", "type": "slack", "roles": ["monitor","chatbot"], "project_id": "secretary", "enabled": true}
   ```
2. Gateway 서버 실행 중이면 30초 내 자동 분석 시작 (ChannelWatcher)
3. 즉시 실행:
   ```bash
   python -m scripts.knowledge.bootstrap mastery {channel_id} --project secretary --force
   ```
4. 결과: `config/channel_contexts/{channel_id}.json` 생성

### 5. Reporter (Slack DM 보고 시스템)

```
SecretaryReporter (reporter.py) ─ 오케스트레이터
    ├── send_urgent_alert(alert) ─ 긴급 메시지 즉시 전송
    ├── send_draft_notification(notif) ─ 초안 생성 알림
    └── send_daily_digest() ─ 매일 18:00 자동 전송
        └── DigestReport (digest.py) ─ 일일 통계 집계

SlackDMChannel (channels/slack_dm.py) ─ 전송 어댑터
```

### 6. Shared 공통 모듈 (`scripts/shared/`)

| 모듈 | 역할 |
|------|------|
| `paths.py` | 프로젝트 루트 자동 탐색, 경로 상수 (`PROJECT_ROOT`, `CONFIG_DIR`, `DATA_DIR`, `GATEWAY_DB` 등) |
| `constants.py` | 텍스트 절삭 상수 (`MAX_TEXT_STORAGE=4000`), Rate limit 상수 |
| `rate_limiter.py` | 싱글톤 Rate limiter (Pipeline 10/min, Claude 5/min, Ollama 10/min) |
| `retry.py` | Exponential backoff 비동기 재시도 래퍼 |

## 런타임 데이터

| 경로 | 용도 |
|------|------|
| `data/gateway.db` | Gateway 메시지 저장 (async SQLite, WAL mode) |
| `data/intelligence.db` | Intelligence 분석 결과, 초안, 피드백 저장 |
| `data/knowledge.db` | Knowledge Store (FTS5 전문검색, 채널 프로파일) |
| `data/drafts/` | 생성된 응답 초안 markdown 파일 |
| `data/gateway.pid` | Gateway 서버 PID 파일 |

## 설정 파일

| 파일 | 용도 |
|------|------|
| `config/gateway.json` | Gateway 채널 활성화, 파이프라인, Intelligence LLM 설정 |
| `config/channels.json` | ChannelRegistry 설정 (채널 ID, 역할, enabled 플래그) |
| `config/projects.json` | Intelligence 프로젝트 등록 (ID, Slack 채널, Gmail 쿼리, 키워드) |
| `config/life_events.json` | 생활 이벤트 (생일, 기념일) |
| `config/tax_calendar.json` | 법인 세무 일정 |
| `config/privacy.json` | 프라이버시 설정 |
| `config/mstodo.json` | MS To Do 연동 설정 |
| `config/prompts/` | LLM 프롬프트 템플릿 (system.md, analyze.md, notify.md) |

## 운영 환경 (검증 완료 — 추가 확인 불필요)

**모든 외부 서비스는 인증 완료 및 운영 중. 세션 시작 시 "설정 필요" 안내 금지.**

| 서비스 | 상태 | 인증 파일 |
|--------|------|----------|
| **Slack** | 인증 완료, Gateway enabled | `C:\claude\json\slack_credentials.json` (bot_token + user_token) |
| **Gmail** | 인증 완료, Gateway enabled | `C:\claude\json\desktop_credentials.json`, `token_gmail.json` |
| **Calendar** | 인증 완료 | `C:\claude\json\token_calendar.json` |
| **GitHub** | 인증 완료 | `C:\claude\json\github_token.txt` |
| **Ollama** | 상시 실행, qwen3:8b 로드됨 | `http://localhost:11434` |
| **Claude CLI** | 현재 환경에서 사용 가능 | Claude Code 세션 내 `claude -p` subprocess |
| **MS To Do** | 인증 완료 | `C:\claude\json\token_mstodo.json` |

인증 방식: Browser OAuth (API 키 금지). 토큰 저장: `C:\claude\json\`

### 테스트 실행 가능 범위

대부분의 테스트가 외부 서비스 없이 즉시 실행 가능 (aiosqlite tmp_path + mock/patch 기반).

```bash
# 전체 테스트 (test_actions.py만 제외 — 실제 Windows Toast 실행)
pytest tests/ --ignore=tests/test_actions.py -v

# 모듈별 실행
pytest tests/gateway/ -v
pytest tests/intelligence/ -v
pytest tests/knowledge/ -v
pytest tests/reporter/ -v
```

`test_actions.py`만 실제 Windows Toast 알림을 트리거하므로 CI/자동 실행에서 제외.

## 안전 규칙

| 규칙 | 내용 |
|------|------|
| **자동 전송 금지** | `response_drafter.py`, `draft_writer.py`는 절대 자동으로 이메일/메시지 전송하지 않음 |
| **확인 필수** | `calendar_creator.py`는 `--confirm` 없으면 dry-run만 수행 |
| **Rate Limiting** | Pipeline 10/min, Claude draft 5/min, Ollama 10/min (`shared/rate_limiter.py`) |
| **Draft 승인 워크플로우** | Intelligence 초안은 `cli.py drafts approve/reject`로 수동 리뷰 필수 |

## Import 패턴

Gateway, Intelligence, Knowledge, Reporter 모듈은 3중 import fallback 패턴 사용:

```python
try:
    from scripts.gateway.models import NormalizedMessage  # 프로젝트 루트에서 실행
except ImportError:
    try:
        from gateway.models import NormalizedMessage  # scripts/ 내에서 실행
    except ImportError:
        from .models import NormalizedMessage  # 패키지 내부 import
```

새 모듈 추가 시 이 패턴을 따라야 직접 실행과 패키지 import 모두 지원됩니다.
