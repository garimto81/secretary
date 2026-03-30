# Life Secretary 구현 계획

**Version**: 1.0.0
**Date**: 2026-02-02
**Status**: APPROVED

---

## 사용자 결정 사항

| 항목 | 결정 |
|------|------|
| **메신저 전략** | Android NotificationListener 앱 개발 |
| **LLM 분석** | Claude Code 세션 로그 + ChatGPT Export 둘 다 |
| **자동화 수준** | 전체 자동화 (사용자 확인 후 전송) |

---

## 구현 Phase 개요

| Phase | 이름 | Timeline | 복잡도 | 핵심 산출물 |
|:-----:|------|----------|--------|------------|
| 0 | Slack Analyzer | 즉시 | LOW | `slack_analyzer.py` |
| 1 | LLM Session Analyzer | 1-2주 | MEDIUM | `llm_analyzer.py` + 파서 |
| 2 | Android Notification | 4-6주 | HIGH | Android 앱 + 수신 서버 |
| 3 | Automation Actions | 2-3주 | MEDIUM-HIGH | Toast, TODO, Calendar, Response |

---

## Phase 0: Slack Analyzer (즉시)

### 목표
기존 `C:\claude\lib\slack\` 라이브러리를 재사용하여 `slack_analyzer.py` 구현

### 기존 라이브러리 재사용

| 파일 | 용도 | 재사용 방식 |
|------|------|------------|
| `lib/slack/client.py` | SlackClient (Rate Limit 내장) | import |
| `lib/slack/auth.py` | OAuth Browser Flow | import |
| `lib/slack/models.py` | SlackMessage, SlackChannel | import |

### 구현 파일

```
C:\claude\secretary\scripts\
└── slack_analyzer.py    # NEW
```

### 기능 목록

| 함수 | 설명 | 패턴 참조 |
|------|------|----------|
| `get_credentials()` | `lib.slack.auth.get_token()` 재사용 | gmail_analyzer.py:55-84 |
| `get_unread_mentions()` | 멘션된 메시지 필터링 | - |
| `get_dm_messages()` | DM 히스토리 조회 | - |
| `analyze_urgency()` | 긴급 키워드 감지 | gmail_analyzer.py:182-200 |
| `main()` | CLI 인터페이스 (`--json`, `--days`) | gmail_analyzer.py |

### daily_report.py 통합

- Line 36: `SLACK_SCRIPT = SCRIPT_DIR / "slack_analyzer.py"` 추가
- Line 244: `--slack` 인수 추가
- `analyze_slack()` 함수 추가 (패턴: Lines 93-113)

### 검증 기준

- [ ] `python scripts/slack_analyzer.py --json` 성공
- [ ] `python scripts/daily_report.py --slack` 통합 성공
- [ ] Rate Limit 에러 처리

---

## Phase 1: LLM Session Analyzer (1-2주)

### 목표
Claude Code 세션 로그와 ChatGPT Export를 분석하여 AI 사용 패턴 파악

### 데이터 소스

| 소스 | 경로 | 형식 |
|------|------|------|
| Claude Code | `~\.claude\projects\{hash}\*.jsonl` | JSONL |
| ChatGPT | 사용자 제공 Export 파일 | JSON |

### Claude Code JSONL 포맷

```json
{
  "type": "user" | "assistant",
  "message": {
    "role": "user" | "assistant",
    "content": "...",
    "model": "claude-haiku-4-5-20251001"
  },
  "sessionId": "uuid",
  "timestamp": "2026-01-05T00:59:56.362Z",
  "cwd": "C:\\claude",
  "gitBranch": "main"
}
```

### 구현 파일

```
C:\claude\secretary\scripts\
├── llm_analyzer.py           # Orchestrator
└── parsers/
    ├── __init__.py
    ├── claude_code_parser.py # Claude Code JSONL 파서
    └── chatgpt_parser.py     # ChatGPT Export 파서
```

### 데이터 모델

```python
@dataclass
class LLMSession:
    source: str           # "claude_code" | "chatgpt"
    session_id: str
    title: str | None
    start_time: datetime
    end_time: datetime
    message_count: int
    project: str | None   # Claude Code only
    topics: list[str]     # 키워드 추출
    files_mentioned: list[str]
    tools_used: dict[str, int]  # {Read: 5, Write: 3, ...}
```

### 분석 기능

| 기능 | 설명 |
|------|------|
| **세션 통계** | 일별/주별 AI 사용량 |
| **토픽 추출** | 언급된 파일, 브랜치, 키워드 |
| **도구 사용 패턴** | Read/Write/Bash 빈도 |
| **프로젝트 활동** | 어떤 프로젝트에서 가장 많이 사용 |

### 검증 기준

- [ ] Claude Code 로그 파싱 성공
- [ ] ChatGPT Export 파싱 성공
- [ ] `--json` 출력 일관성
- [ ] daily_report.py 통합

---

## Phase 2: Android Notification Collector (4-6주)

### 목표
NotificationListenerService로 KakaoTalk, WhatsApp, Line 등 알림 수집

### 아키텍처

```
┌─────────────────────────────────────────────────────┐
│                   Android Phone                      │
│  ┌───────────────────────────────────────────────┐  │
│  │        NotificationListenerService            │  │
│  │   - onNotificationPosted()                    │  │
│  │   - Filter: KakaoTalk, Line, WhatsApp, SMS   │  │
│  └───────────────────────────────────────────────┘  │
│                         │                            │
│                         ▼                            │
│  ┌───────────────────────────────────────────────┐  │
│  │              WebSocket Push                   │  │
│  │     ws://desktop:8800/notifications           │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────┐
│                Desktop (Windows)                     │
│  ┌───────────────────────────────────────────────┐  │
│  │        notification_receiver.py               │  │
│  │   - WebSocket server (port 8800)              │  │
│  │   - SQLite: notifications.db                  │  │
│  └───────────────────────────────────────────────┘  │
│                         │                            │
│                         ▼                            │
│  ┌───────────────────────────────────────────────┐  │
│  │       notification_analyzer.py                │  │
│  │   - daily_report.py 통합                      │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 파일 구조

```
C:\claude\secretary\
├── scripts\
│   ├── notification_receiver.py   # WebSocket 서버
│   └── notification_analyzer.py   # 분석 스크립트
│
└── android\                       # Android Studio 프로젝트
    └── SecretaryNotification\
        ├── app\src\main\
        │   ├── kotlin\com\secretary\
        │   │   ├── NotificationListener.kt
        │   │   ├── SyncService.kt
        │   │   └── NotificationDB.kt
        │   └── AndroidManifest.xml
        └── build.gradle.kts
```

### Android 권한

```xml
<uses-permission android:name="android.permission.BIND_NOTIFICATION_LISTENER_SERVICE"/>
<uses-permission android:name="android.permission.INTERNET"/>
<uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
```

### WebSocket 프로토콜

```json
{
  "type": "notification",
  "app": "com.kakao.talk",
  "title": "발신자 이름",
  "text": "메시지 내용",
  "timestamp": "2026-02-02T10:30:00Z",
  "extras": {
    "conversation_id": "123",
    "is_group": false
  }
}
```

### 의존성

```
# Desktop
websockets>=12.0
aiosqlite>=0.19.0

# Android
- Kotlin 1.9+
- Room Database
- OkHttp WebSocket
```

### 검증 기준

- [ ] Android 앱 빌드 성공
- [ ] NotificationListener 권한 요청
- [ ] WebSocket 연결 성공
- [ ] 알림 수신 및 저장
- [ ] daily_report.py 통합

---

## Phase 3: Automation Actions (2-3주)

### 목표
분석 결과 기반 자동화 액션 실행 (사용자 확인 필요 항목은 승인 후)

### 액션 유형

| 액션 | 자동화 수준 | 사용자 확인 |
|------|------------|------------|
| **Windows Toast** | Full auto | 불필요 |
| **TODO 목록 생성** | Full auto | 불필요 |
| **Calendar 일정 추가** | Semi-auto | **필요** |
| **Response Draft** | Manual | **필수** |

### 파일 구조

```
C:\claude\secretary\
└── scripts\
    ├── actions\
    │   ├── __init__.py
    │   ├── toast_notifier.py      # Windows Toast 알림
    │   ├── todo_generator.py      # TODO 목록 생성
    │   ├── calendar_creator.py    # Calendar 일정 추가
    │   └── response_drafter.py    # 응답 초안 생성
    └── automation_engine.py       # 오케스트레이터
```

### Windows Toast

```python
from windows_toasts import Toast

def send_notification(title: str, message: str):
    toast = Toast()
    toast.text_fields = [title, message]
    toast.app_id = "Secretary AI"
    toast.show()
```

### TODO Generator

출력 형식:
- Markdown: `output/todos/YYYY-MM-DD.md`
- GitHub Issues (선택)
- Slack List (선택)

### Response Drafter (CRITICAL)

**사용자 승인 필수 워크플로우:**

```
1. 미응답 메일/메시지 감지 (48시간+)
2. 컨텍스트 추출 (발신자, 제목, 본문)
3. Claude API로 초안 생성
4. 저장: output/drafts/{id}.md
5. Toast 알림: "응답 초안 준비됨: [제목]"
6. 사용자가 검토, 수정, 직접 전송
```

**절대 자동 전송하지 않음!**

### 의존성

```
windows-toasts>=1.1.0     # Windows Toast
anthropic>=0.25.0         # Claude API (응답 초안용)
```

### 검증 기준

- [ ] Toast 알림 표시 성공
- [ ] TODO 파일 생성 성공
- [ ] Calendar 일정 추가 (사용자 확인 후)
- [ ] Response Draft 생성 및 저장
- [ ] **자동 전송 방지 로직 검증**

---

## 전체 의존성 (requirements.txt 추가)

```
# Phase 0: Slack
# (lib/slack 재사용, 추가 없음)

# Phase 1: LLM Analyzer
python-dateutil>=2.8.0

# Phase 2: Android Notification
websockets>=12.0
aiosqlite>=0.19.0

# Phase 3: Automation
windows-toasts>=1.1.0
anthropic>=0.25.0
```

---

## 검증 체크리스트 (전체)

### Phase 완료 조건

| Phase | 조건 |
|:-----:|------|
| 0 | `daily_report.py --slack` 성공 |
| 1 | `llm_analyzer.py --json` 성공 |
| 2 | WebSocket 연결 + 알림 수신 성공 |
| 3 | 모든 액션 + 자동 전송 방지 검증 |

### 통합 검증

- [ ] `python scripts/daily_report.py --all --json` 성공
- [ ] 모든 소스 통합 리포트 생성
- [ ] 자동화 액션 트리거
- [ ] Rate Limit 에러 처리
- [ ] 토큰 만료 자동 갱신

---

## 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| Slack Rate Limit (1 req/min) | 채널 캐싱, 배치 처리 |
| Android 권한 거부 | 권한 요청 UX 가이드 제공 |
| WebSocket 연결 불안정 | Reconnect 로직, 로컬 캐시 |
| Claude API 비용 | Haiku 우선, 캐싱 적용 |
| Response Draft 오용 | 자동 전송 완전 차단 |

---

## 다음 단계

**Phase 0 즉시 실행**: `slack_analyzer.py` 구현

이미 `C:\claude\lib\slack\`에 완전한 라이브러리가 있으므로 재사용하여 빠르게 구현 가능.
