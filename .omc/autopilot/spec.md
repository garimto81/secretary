# Life Secretary - 전략 사양서

**Version**: 1.0.0
**Date**: 2026-02-02
**Status**: APPROVED

---

## Executive Summary

"인생 비서" 시스템은 Gmail, Calendar, GitHub, Slack 등 다양한 커뮤니케이션 채널을 통합 분석하여 할일을 자동 추출하고 일일 업무 현황을 제공하는 AI 비서 도구입니다.

---

## 1. 요구사항 분석 결과

### 1.1 데이터 소스 가용성

| 플랫폼 | API 상태 | 메시지 읽기 | V2 포함 |
|--------|----------|------------|---------|
| **Gmail** | Full API | 가능 | **YES** (구현 완료) |
| **Google Calendar** | Full API | 가능 | **YES** (구현 완료) |
| **GitHub** | Full API | 가능 | **YES** (구현 완료) |
| **Slack** | Full API | 가능 | **YES** (신규 구현) |
| **KakaoTalk** | Send Only | **불가** | PARTIAL (알림만) |
| **WhatsApp** | Business Only | **불가** | **NO** |
| **Android 알림** | 앱 필요 | 가능 | **NO** (별도 프로젝트) |

### 1.2 핵심 제약사항

| 제약 | 상세 |
|------|------|
| **인증** | Browser OAuth만 허용 (API 키 금지) |
| **플랫폼** | Windows PowerShell |
| **카카오톡** | 공식 API로 메시지 읽기 불가 |
| **WhatsApp** | 개인 API 없음 (Business API는 유료) |

---

## 2. 기술 아키텍처

### 2.1 현재 아키텍처 (V1 - 구현 완료)

```
daily_report.py (Orchestrator)
    ├── subprocess.run(gmail_analyzer.py --json)
    ├── subprocess.run(calendar_analyzer.py --json)
    └── subprocess.run(github_analyzer.py --json)
```

### 2.2 확장 아키텍처 (V2 - 목표)

```
┌─────────────────────────────────────────────────────┐
│                 CLI Interface                        │
│           secretary "오늘 할 일 알려줘"              │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│                Orchestrator Agent                    │
│           (Intent Classification, Routing)           │
└─────────────────────┬───────────────────────────────┘
                      │
    ┌─────────────────┼─────────────────┐
    ▼                 ▼                 ▼
┌────────┐      ┌──────────┐      ┌──────────┐
│Analyzer│      │ Notifier │      │Scheduler │
└───┬────┘      └──────────┘      └──────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│                  Adapter Layer                       │
│ ┌──────┐ ┌────────┐ ┌──────┐ ┌─────┐ ┌───────────┐ │
│ │Gmail │ │Calendar│ │GitHub│ │Slack│ │ Kakao     │ │
│ └──────┘ └────────┘ └──────┘ └─────┘ │(Send Only)│ │
│                                       └───────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## 3. 구현 우선순위

### Phase 0: Slack Analyzer 독립 스크립트 (즉시)

기존 `gmail_analyzer.py` 패턴을 따라 `slack_analyzer.py` 구현:
- OAuth Browser Flow 인증
- 채널/DM 메시지 조회
- 멘션/미응답 메시지 필터링
- `--json` 출력 지원
- `daily_report.py` 통합

### Phase 1: Foundation (Day 1-2)

- Config 시스템 (`config.py`)
- Event Bus (`events.py`)
- Adapter Base Class

### Phase 2: Adapters (Day 2-3)

- V1 스크립트를 Adapter로 리팩토링
- Slack Adapter 완성

### Phase 3: Memory & LLM (Day 3-4)

- Working Memory (세션)
- Episodic Memory (SQLite)
- Claude LLM 통합

### Phase 4: Agents (Day 4-5)

- Orchestrator Agent
- Analyzer Agent
- Notifier Agent

### Phase 5: CLI & Scheduler (Day 5-6)

- Click CLI
- Windows Task Scheduler 통합

---

## 4. 대안 전략 (API 제약 플랫폼)

### 4.1 KakaoTalk

| 전략 | 설명 |
|------|------|
| **알림 전송** | 카카오 메시지 API로 본인에게 알림 전송 |
| **수동 포워딩** | 중요 메시지를 이메일로 포워딩 |

### 4.2 WhatsApp

| 전략 | 설명 |
|------|------|
| **지원 제외** | 개인 API 부재로 V2에서 제외 |
| **향후** | Android 알림 연동 시 통합 |

### 4.3 LLM 히스토리

| 전략 | 설명 |
|------|------|
| **Claude Code 로그** | 세션 로그 파일 분석 |
| **수동 Export** | ChatGPT 등 대화 내보내기 |

---

## 5. 기술 스택

| 구성요소 | 선택 | 버전 |
|---------|------|------|
| Python | 3.12+ | - |
| HTTP Client | httpx | >=0.25.0 |
| CLI | Click | >=8.1.0 |
| Slack SDK | slack-sdk | >=3.27.0 |
| LLM | anthropic | >=0.25.0 |
| Config | PyYAML + python-dotenv | - |
| DB | SQLite | - |
| Notification | winotify | >=1.1.0 |

---

## 6. 파일 구조 (목표)

```
C:\claude\secretary\
├── src/secretary/
│   ├── core/          # Config, Events, Exceptions
│   ├── adapters/      # Gmail, Calendar, GitHub, Slack, Kakao
│   ├── memory/        # Working, Episodic, Semantic
│   ├── agents/        # Orchestrator, Analyzer, Notifier
│   ├── llm/           # Claude Client, Prompts
│   ├── scheduler/     # Proactive, Task Scheduler
│   ├── notifications/ # Windows, Cross-platform
│   ├── security/      # Token Manager, PII Masker
│   └── cli/           # Click CLI
├── scripts/           # V1 독립 스크립트 (보존)
│   ├── gmail_analyzer.py
│   ├── calendar_analyzer.py
│   ├── github_analyzer.py
│   ├── daily_report.py
│   └── slack_analyzer.py  # NEW
├── tests/
├── config/
└── requirements.txt
```

---

## 7. Trade-offs

| 결정 | 선택 | 포기 | 근거 |
|------|------|------|------|
| Slack 우선 | 공식 API 완비 | - | 안정성, ToS 준수 |
| KakaoTalk 알림만 | 구현 가능 | 메시지 읽기 | API 제약 |
| WhatsApp 제외 | 복잡도 감소 | 사용자 편의 | 개인 API 부재 |
| Android 앱 제외 | V2 범위 유지 | 통합 알림 | 별도 프로젝트 필요 |
| Subprocess 보존 | V1 호환 | 성능 | 점진적 마이그레이션 |

---

## 8. 다음 단계

1. **Phase 0 실행**: `slack_analyzer.py` 구현
2. **인증 설정**: Slack OAuth App 생성 및 토큰 발급
3. **daily_report.py 통합**: Slack 분석 결과 추가
4. **V2 리팩토링**: Adapter Pattern으로 구조화
