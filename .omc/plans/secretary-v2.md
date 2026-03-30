# Secretary V2 - AI 비서 시스템 구현 계획

**Version**: 2.1.0
**Created**: 2026-02-02
**Updated**: 2026-02-02 (Iteration 2)
**Status**: READY FOR REVIEW

---

## 1. Context

### 1.1 Original Request
"내 인생의 비서" - Gmail, Calendar, GitHub 데이터를 통합하여 자연어로 상호작용하고, 프로액티브하게 알림을 제공하는 AI 비서 시스템

### 1.2 Current State (V1)
기존 스크립트 분석 결과:

| 스크립트 | 기능 | 재사용 가치 |
|---------|------|------------|
| `gmail_analyzer.py` | Gmail OAuth 인증, 이메일 조회, 할일/마감일 추출 | HIGH - 인증 로직, 파싱 로직 재사용 |
| `calendar_analyzer.py` | Calendar OAuth 인증, 일정 조회, 준비 필요 항목 감지 | HIGH - 인증 로직, 이벤트 파싱 재사용 |
| `github_analyzer.py` | GitHub API 조회, PR/이슈 분석, 주의 필요 항목 | HIGH - API 클라이언트, 분석 로직 재사용 |
| `daily_report.py` | 통합 리포트 생성 | MEDIUM - 포맷팅 로직 참조 |

### 1.3 Research Conclusions
- **Architecture**: Event-Driven Multi-Agent
- **LLM Strategy**: Hybrid (Haiku/Sonnet/Opus 티어별)
- **Memory**: 3-Tier (Working/Episodic/Semantic)
- **Extension**: Adapter Pattern Plugin System

### 1.4 LangChain 미사용 정당화

리서치에서 LangChain이 권장되었으나, Custom 구현을 선택한 이유:

| 측면 | LangChain | Custom (선택) |
|------|-----------|---------------|
| **의존성 크기** | ~50+ 패키지 | ~10 패키지 |
| **학습 곡선** | LangChain 추상화 학습 필요 | Python 표준 패턴 |
| **디버깅** | 추상화 레이어로 어려움 | 직접 제어 가능 |
| **유연성** | 프레임워크 제약 | 완전 제어 |
| **프로젝트 규모** | 대규모에 적합 | 중소규모에 적합 |

**결론**: Secretary는 3개 어댑터, 3개 에이전트의 중소규모 프로젝트로, LangChain 오버헤드 없이 Custom 구현이 효율적. 향후 확장 시 LangGraph 도입 검토.

---

## 2. Work Objectives

### 2.1 Core Objective
기존 V1 스크립트를 확장하여 Claude API 기반 자연어 인터페이스와 프로액티브 알림 시스템을 갖춘 AI 비서 구축

### 2.2 Deliverables

| Deliverable | Description | Priority |
|-------------|-------------|----------|
| D1 | Core Framework (adapters, memory, config) | P0 |
| D2 | Data Source Adapters (Gmail, Calendar, GitHub) | P0 |
| D3 | Claude API Integration (자연어 인터페이스) | P0 |
| D4 | Proactive Alert System (하이브리드 스케줄러) | P1 |
| D5 | CLI Interface | P1 |
| D6 | Plugin System (확장 가능 아키텍처) | P2 |

### 2.3 Definition of Done
- [ ] 모든 기존 스크립트 기능이 새 아키텍처에서 동작
- [ ] `secretary "오늘 할 일 알려줘"` 자연어 명령 동작
- [ ] 매일 아침 9시 자동 브리핑 알림
- [ ] 긴급 이메일/일정 실시간 알림
- [ ] 테스트 커버리지 80% 이상
- [ ] ruff check 통과
- [ ] V1 호환성 검증 통과 (golden output 비교)

---

## 3. Guardrails

### 3.1 Must Have
- Google API: OAuth Browser Flow만 사용
- Claude API: `.env` 파일 + `python-dotenv` (gitignore 필수)
- 기존 토큰 파일 재사용:
  - `C:\claude\json\token_gmail.json`
  - `C:\claude\json\token_calendar.json`
- 로컬 우선 프라이버시 (외부 서버 전송 금지)
- Windows 환경 지원 (UTF-8 처리)
- 절대 경로만 사용 (`C:\claude\secretary\...`)

### 3.2 Must NOT Have
- 하드코딩된 API 키 (소스 코드 내)
- 사용자 데이터 외부 전송
- 전체 프로세스 종료 명령 (`taskkill /F /IM node.exe`)
- Google API에 API 키 방식 사용 (OAuth만)

### 3.3 API 키 정책 명확화

| 서비스 | 인증 방식 | 저장 위치 |
|--------|----------|----------|
| **Google (Gmail, Calendar)** | OAuth Browser Flow | `C:\claude\json\token_*.json` |
| **GitHub** | Personal Access Token | `.env` 또는 Windows Credential Manager |
| **Claude API** | API Key | `.env` (gitignore 필수) |

```
# .env 예시 (절대 커밋 금지)
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
```

```
# .gitignore 필수 포함
.env
*.env
.env.*
```

---

## 4. Architecture

### 4.1 Directory Structure

```
C:\claude\secretary\
├── src/
│   └── secretary/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── config.py           # Configuration management
│       │   ├── events.py           # Event bus (pub/sub)
│       │   └── exceptions.py       # Custom exceptions
│       │
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py             # BaseAdapter ABC
│       │   ├── gmail.py            # Gmail adapter (from V1)
│       │   ├── calendar.py         # Calendar adapter (from V1)
│       │   └── github.py           # GitHub adapter (from V1)
│       │
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── working.py          # Short-term memory
│       │   ├── episodic.py         # Conversation history
│       │   └── semantic.py         # Long-term knowledge
│       │
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── orchestrator.py     # Main agent coordinator
│       │   ├── analyzer.py         # Data analysis agent
│       │   └── notifier.py         # Proactive notification agent
│       │
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── claude_client.py    # Claude API client
│       │   └── prompts.py          # System prompts
│       │
│       ├── scheduler/
│       │   ├── __init__.py
│       │   ├── proactive.py        # Hybrid scheduler
│       │   └── task_scheduler.py   # Windows Task Scheduler integration
│       │
│       ├── notifications/
│       │   ├── __init__.py
│       │   ├── base.py             # NotificationProvider ABC
│       │   ├── windows.py          # winotify (Windows)
│       │   └── cross_platform.py   # plyer (fallback)
│       │
│       ├── security/
│       │   ├── __init__.py
│       │   ├── token_manager.py    # DPAPI/keyring token encryption
│       │   └── pii_masker.py       # PII auto-masking
│       │
│       └── cli/
│           ├── __init__.py
│           └── main.py             # Click-based CLI
│
├── scripts/                        # V1 scripts (preserved)
│   ├── gmail_analyzer.py
│   ├── calendar_analyzer.py
│   ├── github_analyzer.py
│   └── daily_report.py
│
├── tests/
│   ├── __init__.py
│   ├── golden_outputs/             # V1 호환성 검증용
│   │   ├── gmail_expected.json
│   │   ├── calendar_expected.json
│   │   └── github_expected.json
│   ├── test_adapters/
│   ├── test_memory/
│   ├── test_agents/
│   └── test_cli/
│
├── config/
│   ├── default.yaml               # Default configuration
│   └── prompts/                   # LLM prompt templates
│       ├── system.md
│       ├── analyze.md
│       └── notify.md
│
├── .env.example                   # 환경변수 템플릿 (커밋 가능)
├── .gitignore                     # .env 포함 필수
├── pyproject.toml
├── requirements.txt
└── README.md
```

### 4.2 Component Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │                CLI Interface                 │
                    │         (secretary "오늘 할 일")              │
                    └─────────────────────┬───────────────────────┘
                                          │
                    ┌─────────────────────▼───────────────────────┐
                    │              Orchestrator Agent              │
                    │    (Intent Classification, Task Routing)     │
                    └─────────────────────┬───────────────────────┘
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                    ┌─────────────┐ ┌──────────┐ ┌──────────┐
                    │  Analyzer   │ │ Notifier │ │ Scheduler│
                    │   Agent     │ │  Agent   │ │ (Hybrid) │
                    └──────┬──────┘ └────┬─────┘ └────┬─────┘
                           │             │            │
        ┌──────────────────┼─────────────┼────────────┘
        │                  │             │
        ▼                  ▼             ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ Memory Layer  │  │  Event Bus    │  │ Claude API    │
│ W/E/S Tiers   │  │  (Pub/Sub)    │  │ (.env 로드)   │
└───────────────┘  └───────────────┘  └───────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                   Adapter Layer                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │  Gmail   │  │ Calendar │  │  GitHub  │  [...]   │
│  │ Adapter  │  │ Adapter  │  │ Adapter  │          │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘          │
└───────┼─────────────┼─────────────┼─────────────────┘
        │             │             │
        ▼             ▼             ▼
    Gmail API    Calendar API   GitHub API
```

### 4.3 LLM Tier Strategy

| Task | Model | Reason |
|------|-------|--------|
| Intent Classification | Haiku | Fast, simple classification |
| Email/Calendar Analysis | Sonnet | Moderate complexity |
| Complex Summarization | Opus | Deep understanding needed |
| Proactive Notifications | Haiku | Quick, frequent checks |

---

## 5. Task Flow

### Phase 1: Foundation (Day 1-2)

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE 1: Foundation                                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Task 1.1: Project Setup                                     │
│  ├── pyproject.toml 생성                                     │
│  ├── src/secretary/ 디렉토리 구조 생성                        │
│  ├── tests/ 디렉토리 구조 생성                                │
│  └── .env.example, .gitignore 생성                           │
│           │                                                  │
│           ▼                                                  │
│  Task 1.2: Core Module                                       │
│  ├── config.py (YAML + .env 통합 설정 관리)                   │
│  ├── events.py (이벤트 버스)                                  │
│  └── exceptions.py (커스텀 예외)                              │
│           │                                                  │
│           ▼                                                  │
│  Task 1.3: Security Module                                   │
│  ├── token_manager.py (DPAPI/keyring 토큰 암호화)             │
│  └── pii_masker.py (PII 마스킹)                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Phase 2: Adapters (Day 2-3)

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE 2: Adapters                                            │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Task 2.1: Base Adapter                                      │
│  └── adapters/base.py (ABC 정의)                             │
│           │                                                  │
│           ├───────────────┬───────────────┐                  │
│           ▼               ▼               ▼                  │
│  Task 2.2: Gmail     Task 2.3: Calendar  Task 2.4: GitHub   │
│  Adapter             Adapter             Adapter             │
│  (from V1)           (from V1)           (from V1)           │
│                                                              │
│  [병렬 실행 가능]                                             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Phase 3: Memory & LLM (Day 3-4)

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE 3: Memory & LLM Integration                            │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Task 3.1: Memory Layer (병렬)                               │
│  ├── working.py (세션 메모리)                                 │
│  ├── episodic.py (대화 히스토리)                              │
│  └── semantic.py (장기 지식)                                  │
│           │                                                  │
│           ▼                                                  │
│  Task 3.2: Claude Integration                                │
│  ├── claude_client.py (.env에서 API 키 로드)                  │
│  └── prompts.py (시스템 프롬프트)                             │
│           │                                                  │
│           ▼                                                  │
│  Task 3.3: Prompt Templates                                  │
│  └── config/prompts/*.md                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Phase 4: Agents (Day 4-5)

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE 4: Agents                                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Task 4.1: Orchestrator Agent                                │
│  └── Intent classification, task routing                     │
│           │                                                  │
│           ├───────────────┐                                  │
│           ▼               ▼                                  │
│  Task 4.2: Analyzer   Task 4.3: Notifier                     │
│  Agent                Agent                                  │
│  (데이터 분석)        (알림 생성 + 플랫폼 추상화)               │
│                                                              │
│  [병렬 실행 가능]                                             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Phase 5: Scheduler & CLI (Day 5-6)

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE 5: Scheduler & CLI                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Task 5.1: Hybrid Scheduler                                  │
│  ├── CLI 일회성 호출 (Click + sync)                          │
│  └── Windows Task Scheduler 연동 (daemon)                    │
│           │                                                  │
│           ▼                                                  │
│  Task 5.2: CLI Interface                                     │
│  └── Click 기반 CLI (sync wrapper)                           │
│           │                                                  │
│           ▼                                                  │
│  Task 5.3: Integration Test                                  │
│  └── E2E 테스트 + V1 호환성 검증                              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 6. Detailed TODOs

### Phase 1: Foundation

#### Task 1.1: Project Setup
- [ ] `pyproject.toml` 생성 (poetry or setuptools)
  - Dependencies: anthropic, click, pyyaml, httpx, python-dotenv
  - Dev dependencies: pytest, pytest-asyncio, ruff
- [ ] `src/secretary/__init__.py` 생성
- [ ] `tests/__init__.py` 생성
- [ ] `tests/golden_outputs/` 디렉토리 생성 (V1 호환성 검증용)
- [ ] `config/default.yaml` 생성
- [ ] `.env.example` 생성 (템플릿)
- [ ] `.gitignore` 생성 (.env 포함 필수)

**Acceptance Criteria:**
- `pip install -e .` 성공
- `python -c "import secretary"` 성공
- `.env` 파일이 `.gitignore`에 포함됨

#### Task 1.2: Core Module
- [ ] `core/config.py` - Configuration 클래스
  - YAML 파일 로드
  - `.env` 환경변수 통합 (`python-dotenv`)
  - 환경별 설정 오버라이드
  - 민감 정보 마스킹 로깅
- [ ] `core/events.py` - EventBus 클래스
  - publish(event_type, data)
  - subscribe(event_type, handler)
  - 비동기 이벤트 처리
- [ ] `core/exceptions.py` - 커스텀 예외
  - SecretaryError (base)
  - AuthenticationError
  - AdapterError
  - RateLimitError

**Acceptance Criteria:**
- `test_core/test_config.py` 통과
- `test_core/test_events.py` 통과
- `.env` 로드 테스트 통과

#### Task 1.3: Security Module
- [ ] `security/token_manager.py`
  - Windows: DPAPI 기반 토큰 암호화
  - Non-Windows: keyring 라이브러리 사용
  - 토큰 만료 검사
  - 자동 갱신 로직
- [ ] `security/pii_masker.py`
  - 이메일 주소 마스킹 (a***@example.com)
  - 전화번호 마스킹
  - 로깅 전 자동 적용

**Acceptance Criteria:**
- 토큰 암호화/복호화 테스트 통과
- PII 마스킹 테스트 통과
- 플랫폼별 fallback 테스트 통과

---

### Phase 2: Adapters

#### Task 2.1: Base Adapter
- [ ] `adapters/base.py` - BaseAdapter ABC
  ```python
  class BaseAdapter(ABC):
      @abstractmethod
      async def connect(self) -> None: ...

      @abstractmethod
      async def fetch_data(self, **kwargs) -> dict: ...

      @abstractmethod
      async def get_actionable_items(self) -> list[dict]: ...
  ```

**Acceptance Criteria:**
- ABC 상속 강제 검증 테스트 통과

#### Task 2.2: Gmail Adapter
- [ ] V1 `gmail_analyzer.py` 로직 추출
- [ ] `adapters/gmail.py` - GmailAdapter 클래스
  - `connect()`: OAuth 인증 (토큰: `C:\claude\json\token_gmail.json`)
  - `fetch_data(days, max_results)`: 이메일 조회
  - `get_actionable_items()`: 할일 추출
  - `analyze_email(email_data)`: 이메일 분석 (V1 로직)

**Acceptance Criteria:**
- Golden output 비교 통과 (`tests/golden_outputs/gmail_expected.json`)
- `test_adapters/test_gmail.py` 통과

#### Task 2.3: Calendar Adapter
- [ ] V1 `calendar_analyzer.py` 로직 추출
- [ ] `adapters/calendar.py` - CalendarAdapter 클래스
  - `connect()`: OAuth 인증 (토큰: `C:\claude\json\token_calendar.json`)
  - `fetch_data(days)`: 일정 조회
  - `get_actionable_items()`: 준비 필요 항목 추출
  - `parse_event(event)`: 이벤트 파싱 (V1 로직)

**Acceptance Criteria:**
- Golden output 비교 통과 (`tests/golden_outputs/calendar_expected.json`)
- `test_adapters/test_calendar.py` 통과

#### Task 2.4: GitHub Adapter
- [ ] V1 `github_analyzer.py` 로직 추출
- [ ] `adapters/github.py` - GitHubAdapter 클래스
  - `connect()`: 토큰 로드 (`.env`의 `GITHUB_TOKEN`)
  - `fetch_data(days)`: 활동 조회
  - `get_actionable_items()`: 주의 필요 항목 추출
  - `analyze_activity(days)`: 활동 분석 (V1 로직)

**Acceptance Criteria:**
- Golden output 비교 통과 (`tests/golden_outputs/github_expected.json`)
- `test_adapters/test_github.py` 통과

---

### Phase 3: Memory & LLM

#### Task 3.1: Memory Layer
- [ ] `memory/working.py` - WorkingMemory
  - 현재 세션 컨텍스트 저장
  - 최대 10개 항목 유지
  - TTL 기반 만료
- [ ] `memory/episodic.py` - EpisodicMemory
  - 대화 히스토리 저장 (SQLite)
  - 최근 50개 대화 유지
  - 검색 기능
- [ ] `memory/semantic.py` - SemanticMemory
  - 장기 지식 저장
  - 사용자 선호도
  - 패턴 학습 결과

**Acceptance Criteria:**
- 메모리 저장/검색 테스트 통과
- TTL 만료 테스트 통과

#### Task 3.2: Claude Integration
- [ ] `llm/claude_client.py` - ClaudeClient 클래스
  ```python
  from dotenv import load_dotenv
  import os

  class ClaudeClient:
      def __init__(self):
          load_dotenv()  # .env 파일 로드
          api_key = os.getenv("ANTHROPIC_API_KEY")
          if not api_key:
              raise AuthenticationError(
                  "ANTHROPIC_API_KEY not found in .env file. "
                  "Copy .env.example to .env and add your API key."
              )
          self.client = anthropic.Anthropic(api_key=api_key)

      async def chat(self, messages, model="claude-sonnet-4-20250514"):
          ...

      async def classify_intent(self, text) -> str:
          # Haiku로 빠른 분류
          ...
  ```
- [ ] `llm/prompts.py` - 프롬프트 템플릿 로더

**Acceptance Criteria:**
- Claude API 호출 테스트 통과 (mock)
- Intent 분류 테스트 통과
- API 키 누락 시 명확한 에러 메시지

#### Task 3.3: Prompt Templates
- [ ] `config/prompts/system.md` - 시스템 프롬프트
- [ ] `config/prompts/analyze.md` - 분석 프롬프트
- [ ] `config/prompts/notify.md` - 알림 프롬프트

**Acceptance Criteria:**
- 프롬프트 로드 테스트 통과

---

### Phase 4: Agents

#### Task 4.1: Orchestrator Agent
- [ ] `agents/orchestrator.py` - Orchestrator 클래스
  - Intent 분류 (query, summary, alert, action)
  - 적절한 서브 에이전트 라우팅
  - 결과 통합

**Acceptance Criteria:**
- Intent 분류 정확도 90% 이상
- 라우팅 로직 테스트 통과

#### Task 4.2: Analyzer Agent
- [ ] `agents/analyzer.py` - Analyzer 클래스
  - 데이터 수집 (모든 어댑터)
  - 우선순위 분석
  - 요약 생성

**Acceptance Criteria:**
- 데이터 통합 테스트 통과
- 요약 생성 테스트 통과

#### Task 4.3: Notifier Agent
- [ ] `agents/notifier.py` - Notifier 클래스
  - 알림 조건 평가
  - 알림 메시지 생성
  - 플랫폼별 알림 연동
- [ ] `notifications/base.py` - NotificationProvider ABC
- [ ] `notifications/windows.py` - WindowsNotifier (winotify)
- [ ] `notifications/cross_platform.py` - CrossPlatformNotifier (plyer fallback)

**Acceptance Criteria:**
- 알림 조건 평가 테스트 통과
- Windows Toast 알림 표시 테스트 통과
- Non-Windows fallback 테스트 통과

---

### Phase 5: Scheduler & CLI

#### Task 5.1: Hybrid Scheduler
하이브리드 아키텍처: CLI 일회성 호출 + Windows Task Scheduler daemon

- [ ] `scheduler/proactive.py` - ProactiveScheduler 클래스
  ```python
  class ProactiveScheduler:
      """
      하이브리드 스케줄러:
      - 일회성 명령: Click CLI에서 직접 호출 (sync)
      - 정기 작업: Windows Task Scheduler에 등록
      """

      def run_once(self, task: str):
          """일회성 작업 실행 (CLI에서 호출)"""
          ...

      def register_scheduled_task(self, name: str, cron: str, command: str):
          """Windows Task Scheduler에 작업 등록"""
          ...

      def unregister_scheduled_task(self, name: str):
          """Windows Task Scheduler에서 작업 제거"""
          ...
  ```
- [ ] `scheduler/task_scheduler.py` - Windows Task Scheduler 연동
  ```python
  import subprocess

  def create_scheduled_task(name: str, time: str, command: str):
      """schtasks.exe를 사용한 작업 등록"""
      subprocess.run([
          "schtasks", "/create",
          "/tn", f"Secretary\\{name}",
          "/tr", command,
          "/sc", "daily",
          "/st", time,
          "/f"  # force overwrite
      ], check=True)
  ```
- [ ] Non-Windows: cron fallback 또는 APScheduler daemon 모드

**Acceptance Criteria:**
- Windows Task Scheduler 등록/해제 테스트 통과
- 일회성 작업 실행 테스트 통과
- Non-Windows에서 graceful degradation

#### Task 5.2: CLI Interface
- [ ] `cli/main.py` - Click 기반 CLI (sync wrapper)
  ```bash
  # 자연어 쿼리
  secretary "오늘 할 일 알려줘"

  # 명시적 명령
  secretary brief          # 일일 브리핑
  secretary emails         # 이메일 할일
  secretary calendar       # 오늘 일정
  secretary github         # GitHub 현황

  # 스케줄러 관리
  secretary schedule install   # Task Scheduler에 등록
  secretary schedule remove    # Task Scheduler에서 제거
  secretary schedule status    # 등록 상태 확인
  ```
- [ ] Click async/sync 호환: `asyncio.run()` wrapper 사용

**Acceptance Criteria:**
- CLI 명령 파싱 테스트 통과
- 자연어 쿼리 처리 테스트 통과
- async/sync 호환 테스트 통과

#### Task 5.3: Integration Test
- [ ] E2E 테스트 시나리오
  - "오늘 할 일 알려줘" -> 통합 응답
  - 스케줄러 등록/해제
  - 긴급 알림 트리거
- [ ] V1 호환성 검증
  - `scripts/*.py` 실행 결과를 `tests/golden_outputs/*.json`에 저장
  - 새 어댑터 출력과 JSON diff 비교
  - 허용 차이: timestamp 필드만

**Acceptance Criteria:**
- 모든 E2E 테스트 통과
- 성능: 응답 시간 3초 이내
- V1 호환성: golden output diff가 timestamp 외 0건

---

## 7. Commit Strategy

| Phase | Commits |
|-------|---------|
| Phase 1 | `feat(core): add project structure and core modules` |
| Phase 2 | `feat(adapters): add Gmail/Calendar/GitHub adapters` |
| Phase 3 | `feat(memory): add 3-tier memory system` |
| Phase 3 | `feat(llm): add Claude API integration with .env` |
| Phase 4 | `feat(agents): add orchestrator and analyzer agents` |
| Phase 4 | `feat(notifications): add cross-platform notification system` |
| Phase 5 | `feat(scheduler): add hybrid scheduler (CLI + Task Scheduler)` |
| Phase 5 | `feat(cli): add Click-based CLI interface` |
| Final | `test: add comprehensive test suite with golden outputs` |

---

## 8. Success Criteria

### Functional
- [ ] `secretary "오늘 할 일 알려줘"` 3초 이내 응답
- [ ] 매일 아침 9시 자동 브리핑 동작 (Windows Task Scheduler)
- [ ] 긴급 이메일 30분 이내 알림
- [ ] 기존 V1 기능 100% 호환 (golden output 검증)

### Non-Functional
- [ ] 테스트 커버리지 80% 이상
- [ ] ruff check 통과
- [ ] Windows 10/11 지원
- [ ] 메모리 사용량 100MB 이하

### Security
- [ ] API 키 하드코딩 없음 (`.env` 사용)
- [ ] `.env` 파일 `.gitignore`에 포함
- [ ] 토큰 암호화 저장 (DPAPI/keyring)
- [ ] PII 로그 마스킹
- [ ] 외부 데이터 전송 없음

### V1 Compatibility Verification
검증 방법:
1. V1 스크립트 실행하여 golden output 생성
   ```bash
   python scripts/gmail_analyzer.py > tests/golden_outputs/gmail_expected.json
   python scripts/calendar_analyzer.py > tests/golden_outputs/calendar_expected.json
   python scripts/github_analyzer.py > tests/golden_outputs/github_expected.json
   ```
2. V2 어댑터 출력과 JSON diff 비교
3. 허용 차이: `timestamp`, `fetched_at` 필드만
4. 불허 차이: 데이터 구조, 필드명, 값 형식

---

## 9. Dependencies

### Runtime
```
anthropic>=0.25.0
click>=8.1.0
pyyaml>=6.0
httpx>=0.27.0
python-dotenv>=1.0.0
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
winotify>=1.1.0     # Windows Toast notifications (win10toast 대체)
pywin32>=306        # DPAPI support (Windows)
keyring>=25.0.0     # Cross-platform credential storage
plyer>=2.1.0        # Cross-platform notifications (fallback)
```

### Development
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=4.1.0
ruff>=0.3.0
```

---

## 10. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude API 비용 | Medium | Haiku 우선 사용, 캐싱 적용 |
| OAuth 토큰 만료 | High | 자동 갱신 로직 구현 |
| Windows 의존성 | Medium | 조건부 import, fallback 제공 (아래 참조) |
| 스케줄러 안정성 | High | Windows Task Scheduler 사용, 상태 복구 |
| Click async 충돌 | Low | `asyncio.run()` wrapper로 sync 처리 |

### Non-Windows Fallback 전략

| 기능 | Windows | macOS/Linux |
|------|---------|-------------|
| **토큰 암호화** | DPAPI (`pywin32`) | `keyring` 라이브러리 |
| **알림** | `winotify` | `plyer` (GTK/Qt) |
| **스케줄러** | Task Scheduler (`schtasks.exe`) | `cron` 또는 APScheduler daemon |
| **Credential 저장** | Windows Credential Manager | macOS Keychain / Linux Secret Service |

구현 패턴:
```python
import platform

if platform.system() == "Windows":
    from secretary.security.dpapi import DPAPITokenManager as TokenManager
    from secretary.notifications.windows import WindowsNotifier as Notifier
else:
    from secretary.security.keyring_impl import KeyringTokenManager as TokenManager
    from secretary.notifications.cross_platform import PlyerNotifier as Notifier
```

---

## 11. Future Extensions (P2)

- Slack 어댑터 추가
- Notion 어댑터 추가
- 음성 인터페이스 (Web UI)
- 모바일 푸시 알림
- LangGraph 도입 (복잡도 증가 시)

---

**PLAN_READY: .omc/plans/secretary-v2.md**
