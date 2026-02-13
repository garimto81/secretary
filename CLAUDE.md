# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Gmail, Google Calendar, GitHub, Slack, LLM 세션을 통합 분석하여 일일 업무 현황 리포트를 자동 생성하고, 자동화 액션을 실행하는 AI 비서 도구.

주요 기능:
- **Daily Report**: 각 소스별 분석기를 subprocess로 실행, JSON 결과를 종합
- **Gateway**: 멀티 채널(Slack, Gmail, Telegram) 실시간 메시지 수신 및 파이프라인 처리
- **Intelligence**: 2-Tier LLM으로 메시지 분석(Ollama) 및 응답 초안 생성(Claude Opus)
- **Automation Actions**: Toast 알림, TODO 생성, Calendar 일정, 응답 초안
- **Life Management**: MS To Do 연동, 생활 이벤트 리마인더, 법인 세무 일정

**요구사항**: Python 3.10+, Windows (Toast 알림 등 winotify 의존)

## 빌드 및 테스트

```powershell
pip install -r requirements.txt

# 테스트 실행
pytest tests/gateway/test_pipeline.py -v          # 개별 테스트
pytest tests/ -v                                   # 전체 테스트

# Daily Report
python scripts/daily_report.py
python scripts/daily_report.py --json

# Gateway 서버
python scripts/gateway/server.py start [--port 8800]
python scripts/gateway/server.py stop
python scripts/gateway/server.py status
python scripts/gateway/server.py channels

# Intelligence CLI (주요 명령)
python scripts/intelligence/cli.py analyze [--project ID] [--source slack|gmail|github]
python scripts/intelligence/cli.py pending [--json]
python scripts/intelligence/cli.py drafts [--status pending|approved|rejected]
python scripts/intelligence/cli.py drafts approve <id>
python scripts/intelligence/cli.py stats [--json]

# 개별 분석기
python scripts/gmail_analyzer.py --unread --days 3
python scripts/calendar_analyzer.py --today
python scripts/github_analyzer.py --days 5
python scripts/slack_analyzer.py --days 3 --channels general,team
python scripts/llm_analyzer.py --days 7 --source claude_code
```

## 아키텍처

### 1. Daily Report (subprocess 오케스트레이션)

```
daily_report.py (오케스트레이터)
    ├── gmail_analyzer.py --json
    ├── calendar_analyzer.py --json
    ├── github_analyzer.py --json
    ├── slack_analyzer.py --json
    └── llm_analyzer.py --json
        ├── parsers/claude_code_parser.py
        └── parsers/chatgpt_parser.py
```

`daily_report.py`가 각 분석기를 subprocess로 실행하고 JSON 결과를 수집하여 종합 리포트 생성.

### 2. Gateway (실시간 메시지 파이프라인)

```
SecretaryGateway (server.py)
    ├── ChannelAdapter (adapters/base.py) ─ 추상 인터페이스
    │   ├── SlackAdapter (adapters/slack.py)
    │   ├── GmailAdapter (adapters/gmail.py)
    │   └── TelegramAdapter (adapters/telegram.py)
    ├── MessagePipeline (pipeline.py) ─ 6단계 처리
    │   ├── Stage 1: Priority Analysis (긴급 키워드)
    │   ├── Stage 2: Action Detection (할일, 마감일)
    │   ├── Stage 3: Storage (SQLite)
    │   ├── Stage 4: Notification (Toast)
    │   ├── Stage 5: Action Dispatch
    │   └── Stage 6: Custom Handlers (Intelligence 등)
    ├── UnifiedStorage (storage.py) ─ async SQLite (aiosqlite)
    └── NormalizedMessage (models.py) ─ 통합 메시지 모델
```

- 어댑터는 `ChannelAdapter` 추상 클래스를 구현하여 `connect()`, `disconnect()`, `listen()`, `send()` 제공
- 새 채널 추가 시 `adapters/` 디렉토리에 어댑터 구현 후 `server.py`의 `_create_adapter()`에 등록
- Intelligence는 Pipeline Stage 6의 Custom Handler로 연결됨 (`ProjectIntelligenceHandler`)

### 3. Intelligence (2-Tier LLM 분석)

```
ProjectIntelligenceHandler (response/handler.py) ← Pipeline Stage 6 커스텀 핸들러
    │
    ├── DedupFilter ─ 중복 메시지 방지 (메모리 캐시 + DB)
    ├── ContextMatcher (response/context_matcher.py) ─ 규칙 기반 프로젝트 매칭
    ├── OllamaAnalyzer (response/analyzer.py) ─ Tier 1: 로컬 LLM 분석 (qwen3:8b)
    │   └── project_id, needs_response, intent, summary, confidence 판정
    ├── ClaudeCodeDraftWriter (response/draft_writer.py) ─ Tier 2: Claude Opus 초안 생성
    │   └── claude -p --model opus subprocess 실행
    └── DraftStore (response/draft_store.py) ─ 초안 DB 저장
```

처리 흐름:
1. 중복 체크 (DedupFilter)
2. 규칙 기반 힌트 생성 (ContextMatcher)
3. Ollama로 메시지 분석 (Tier 1, ALL messages)
4. project_id 해석: Ollama(confidence >= 0.7) > 규칙 기반 > Ollama(confidence >= 0.3)
5. 매칭 실패 시 `pending_match`로 저장 후 종료
6. `needs_response=false`면 종료
7. `needs_response=true`면 Claude Opus로 초안 작성 (Tier 2)

관련 저장소:
- `IntelligenceStorage` (context_store.py): SQLite WAL mode, 4 테이블 (projects, context_entries, analysis_state, draft_responses)
- `ProjectRegistry` (project_registry.py): `config/projects.json`에서 프로젝트 로드

증분 분석:
- `incremental/runner.py`: 증분 분석 실행기
- `incremental/trackers/`: Gmail, Slack, GitHub 소스별 tracker
- `incremental/analysis_state.py`: 체크포인트 관리

### 4. 데이터 모델 핵심 타입

| 클래스 | 파일 | 용도 |
|--------|------|------|
| `NormalizedMessage` | `gateway/models.py` | 모든 채널 메시지를 정규화 |
| `OutboundMessage` | `gateway/models.py` | 전송용 응답 초안 |
| `PipelineResult` | `gateway/pipeline.py` | 파이프라인 처리 결과 |
| `AnalysisResult` | `intelligence/response/analyzer.py` | Ollama 분석 결과 |
| `ChannelType` | `gateway/models.py` | Enum: email, telegram, slack, kakao 등 |
| `Priority` | `gateway/models.py` | Enum: low, normal, high, urgent |

## 런타임 데이터

| 경로 | 용도 |
|------|------|
| `data/gateway.db` | Gateway 메시지 저장 (async SQLite) |
| `data/gateway.pid` | Gateway 서버 PID 파일 |
| `data/intelligence.db` | Intelligence 분석 결과, 초안 저장 |
| `data/drafts/` | 생성된 응답 초안 markdown 파일 |

## 설정 파일

| 파일 | 용도 |
|------|------|
| `config/gateway.json` | Gateway 채널 활성화, 파이프라인, Intelligence LLM 설정 |
| `config/projects.json` | Intelligence 프로젝트 등록 (ID, Slack 채널, Gmail 쿼리, 키워드) |
| `config/life_events.json` | 생활 이벤트 (생일, 기념일) |
| `config/tax_calendar.json` | 법인 세무 일정 |
| `config/privacy.json` | 프라이버시 설정 |
| `config/mstodo.json` | MS To Do 연동 설정 |
| `config/prompts/` | LLM 프롬프트 템플릿 (system.md, analyze.md, notify.md) |

## 인증 설정

모든 인증은 Browser OAuth 사용 (API 키 금지). 토큰은 `C:\claude\json\`에 저장.

| 서비스 | 인증 파일 |
|--------|----------|
| Gmail/Calendar | `C:\claude\json\desktop_credentials.json`, `token_gmail.json`, `token_calendar.json` |
| GitHub | 환경변수 `GITHUB_TOKEN` 또는 `C:\claude\json\github_token.txt` |
| Slack | `C:\claude\json\slack_credentials.json` (bot_token 직접 설정 또는 `python -m lib.slack login`) |
| MS To Do | `C:\claude\json\token_mstodo.json` (자동 생성) |
| LLM 세션 | Claude Code: `C:\Users\AidenKim\.claude\projects\{hash}\*.jsonl` |

## 안전 규칙

| 규칙 | 내용 |
|------|------|
| **자동 전송 금지** | `response_drafter.py`, `draft_writer.py`는 절대 자동으로 이메일/메시지 전송하지 않음 |
| **확인 필수** | `calendar_creator.py`는 `--confirm` 없으면 dry-run만 수행 |
| **Rate Limiting** | Gateway 파이프라인은 분당 10건, Claude draft는 분당 5건 제한 |
| **Draft 승인 워크플로우** | Intelligence가 생성한 초안은 `cli.py drafts approve/reject`로 수동 리뷰 필수 |

## Import 패턴

Gateway와 Intelligence 모듈은 3중 import fallback 패턴 사용:

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
