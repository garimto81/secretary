# PRD-0001: Life Secretary - AI 인생 비서

| 항목 | 값 |
|------|---|
| **Version** | 1.0 |
| **Status** | Draft |
| **Priority** | P2 |
| **Created** | 2026-02-02 |
| **Author** | Claude Code |

---

## 1. Executive Summary

**Life Secretary**는 Gmail, Calendar, GitHub, Slack, 카카오톡, WhatsApp 등 다양한 커뮤니케이션 채널과 LLM 사용 히스토리를 통합 분석하여 할일을 자동 추출하고, 일일 업무 현황을 제공하며, 자동화된 액션을 수행하는 AI 비서 시스템입니다.

### 핵심 가치

- **통합 분석**: 분산된 커뮤니케이션 채널을 한 곳에서 분석
- **자동 추출**: 메시지에서 할일, 마감일, 긴급 사항 자동 감지
- **지능형 자동화**: 알림, TODO 생성, 일정 추가, 응답 초안 작성

---

## 2. Problem Statement

### 2.1 현재 문제

| 문제 | 영향 |
|------|------|
| **채널 분산** | Gmail, Slack, 카카오톡 등 여러 앱을 번갈아 확인해야 함 |
| **할일 누락** | 메시지에 숨겨진 요청사항을 놓침 |
| **미응답 누적** | 48시간+ 미응답 메일이 쌓임 |
| **컨텍스트 스위칭** | 채널 간 전환으로 집중력 저하 |
| **AI 사용 패턴 파악 부재** | LLM 사용량, 패턴 추적 불가 |

### 2.2 Target Users

| 페르소나 | 설명 |
|----------|------|
| **Knowledge Worker** | 이메일, Slack, GitHub를 일상적으로 사용하는 개발자/PM |
| **Remote Worker** | 여러 채널로 비동기 소통하는 원격 근무자 |
| **AI Power User** | Claude, ChatGPT를 업무에 활용하는 사용자 |

---

## 3. Goals & Success Metrics

### 3.1 Goals

| 목표 | 설명 |
|------|------|
| **G1** | 하루 시작 시 5분 내 전체 현황 파악 |
| **G2** | 미응답 메시지 48시간 내 처리율 90% |
| **G3** | 수동 채널 확인 횟수 50% 감소 |

### 3.2 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| 일일 리포트 생성 시간 | < 30초 | CLI 실행 시간 |
| 할일 추출 정확도 | > 80% | 수동 검증 |
| 사용자 만족도 | > 4/5 | 설문 조사 |

---

## 4. Requirements

### 4.1 Functional Requirements

#### FR-01: 데이터 소스 통합

| ID | 소스 | 기능 | 우선순위 |
|----|------|------|----------|
| FR-01.1 | Gmail | 이메일 분석, 할일 추출 | **P0** (구현 완료) |
| FR-01.2 | Calendar | 일정 조회, 준비 필요 항목 식별 | **P0** (구현 완료) |
| FR-01.3 | GitHub | PR/이슈 추적 | **P0** (구현 완료) |
| FR-01.4 | Slack | 멘션/DM 분석 | **P0** (구현 완료) |
| FR-01.5 | LLM 히스토리 | Claude Code/ChatGPT 세션 분석 | **P1** (구현 완료) |
| FR-01.6 | Android 알림 | 카카오톡/WhatsApp 알림 수집 | **P2** (설계 완료) |

#### FR-02: 분석 기능

| ID | 기능 | 설명 |
|----|------|------|
| FR-02.1 | 긴급 키워드 감지 | "긴급", "urgent", "asap" 등 |
| FR-02.2 | 마감일 추출 | "오늘까지", "by Friday" 등 |
| FR-02.3 | 미응답 식별 | 48시간+ 미응답 메시지 |
| FR-02.4 | 우선순위 분류 | high/medium/low 자동 분류 |

#### FR-03: 자동화 액션

| ID | 액션 | 자동화 수준 |
|----|------|------------|
| FR-03.1 | Windows Toast 알림 | Full Auto |
| FR-03.2 | TODO 목록 생성 | Full Auto |
| FR-03.3 | Calendar 일정 추가 | 사용자 확인 필수 |
| FR-03.4 | 응답 초안 생성 | 사용자 승인 필수 (자동 전송 금지) |

### 4.2 Non-Functional Requirements

| ID | 요구사항 | Target |
|----|----------|--------|
| NFR-01 | 전체 분석 시간 | < 120초 |
| NFR-02 | 인증 방식 | Browser OAuth (API 키 금지) |
| NFR-03 | 플랫폼 | Windows PowerShell |
| NFR-04 | 토큰 저장 | 암호화 (DPAPI/keyring) |

---

## 5. Technical Design

### 5.1 시스템 아키텍처

![Architecture](../images/PRD-0001/architecture.png)
[HTML 원본](../mockups/PRD-0001/architecture.html)

### 5.2 데이터 흐름

![Data Flow](../images/PRD-0001/data-flow.png)
[HTML 원본](../mockups/PRD-0001/data-flow.html)

### 5.3 기술 스택

| 계층 | 기술 |
|------|------|
| **Language** | Python 3.12+ |
| **HTTP Client** | httpx |
| **CLI** | Click |
| **Slack SDK** | slack-sdk |
| **LLM** | Anthropic Claude API |
| **DB** | SQLite |
| **Notification** | winotify |

### 5.4 파일 구조

```
C:\claude\secretary\
├── scripts/
│   ├── daily_report.py        # 종합 오케스트레이터
│   ├── gmail_analyzer.py      # Gmail 분석
│   ├── calendar_analyzer.py   # Calendar 분석
│   ├── github_analyzer.py     # GitHub 분석
│   ├── slack_analyzer.py      # Slack 분석
│   ├── llm_analyzer.py        # LLM 세션 분석
│   ├── notification_receiver.py   # WebSocket 서버
│   ├── notification_analyzer.py   # 알림 분석
│   ├── parsers/               # LLM 파서
│   └── actions/               # 자동화 액션
├── android/                   # Android 앱 프로젝트
└── output/                    # TODO, 초안 출력
```

---

## 6. User Interface

### 6.1 CLI 인터페이스

![CLI Interface](../images/PRD-0001/cli-interface.png)
[HTML 원본](../mockups/PRD-0001/cli-interface.html)

**주요 명령어**:

```bash
# 전체 일일 리포트
python scripts/daily_report.py --all

# 개별 분석
python scripts/daily_report.py --gmail
python scripts/daily_report.py --slack
python scripts/daily_report.py --llm

# JSON 출력
python scripts/daily_report.py --all --json
```

### 6.2 출력 예시

```
========================================
📊 일일 업무 현황 (2026-02-02 (Sun))
========================================

📧 이메일 할일 (3건)
├── [긴급] 프로젝트 검토 요청 - 마감 2/3
│       발신: client@company.com
├── [보통] 주간 회의 안건 공유
│       발신: team@company.com

💬 Slack 멘션 (5건)
├── 🚨 [general] @you 긴급 확인 부탁드립니다 - 2시간 전
├── ⚠️ [dev] PR 리뷰 요청 - 24시간 전

📅 오늘 일정 (2건)
├── 14:00 팀 미팅 (온라인)
├── 16:00 1:1 미팅

========================================
📈 요약
├── 이메일 할일: 3건
├── Slack 멘션: 5건
├── 오늘 일정: 2건
└── GitHub 주의: 2건

⚡ 긴급 처리 필요: 4건
========================================
```

---

## 7. API Constraints

### 7.1 플랫폼별 제약

| 플랫폼 | API 상태 | 메시지 읽기 | 대안 |
|--------|----------|------------|------|
| Gmail | Full API | ✅ 가능 | - |
| Calendar | Full API | ✅ 가능 | - |
| GitHub | Full API | ✅ 가능 | - |
| Slack | Full API | ✅ 가능 | - |
| KakaoTalk | Send Only | ❌ 불가 | Android 알림 수집 |
| WhatsApp | Business Only | ❌ 불가 | Android 알림 수집 |

### 7.2 Android Notification 솔루션

카카오톡, WhatsApp 등 공식 API가 없는 서비스는 Android NotificationListenerService로 알림을 수집합니다.

```
Android Phone                    Desktop (Windows)
┌────────────────┐              ┌────────────────┐
│ Notification   │   WebSocket  │ notification_  │
│ Listener       │──────────────│ receiver.py    │
│ Service        │   (8800)     │                │
└────────────────┘              └────────────────┘
```

---

## 8. Security Considerations

### 8.1 인증

| 항목 | 정책 |
|------|------|
| Google OAuth | Browser Flow (API 키 금지) |
| Slack OAuth | User Token (xoxp-) |
| GitHub | Personal Access Token |
| 토큰 저장 | DPAPI 암호화 (Windows) |

### 8.2 안전 장치

| 액션 | 보호 수단 |
|------|----------|
| Calendar 일정 추가 | `--confirm` 플래그 필수 |
| 응답 초안 | 자동 전송 **절대 금지** |
| 민감 정보 | PII 마스킹 |

---

## 9. Implementation Status

### 9.1 완료된 Phase

| Phase | 상태 | 산출물 |
|:-----:|:----:|--------|
| **0** | ✅ 완료 | `slack_analyzer.py` |
| **1** | ✅ 완료 | `llm_analyzer.py`, 파서 |
| **2** | ✅ 완료 | `notification_receiver.py`, Android 앱 |
| **3** | ✅ 완료 | `actions/` (Toast, TODO, Calendar, Response) |

### 9.2 남은 작업

| 작업 | 우선순위 | 상태 |
|------|----------|------|
| Android 앱 빌드 | P2 | 대기 |
| Windows 방화벽 설정 | P2 | 대기 |
| Claude API 키 설정 | P1 | 대기 |

---

## 10. Risks & Mitigations

| 리스크 | 영향 | 대응 |
|--------|------|------|
| Slack Rate Limit (1 req/min) | 분석 지연 | 채널 캐싱, 배치 처리 |
| Android 권한 거부 | 알림 수집 불가 | 권한 요청 UX 가이드 |
| WebSocket 연결 불안정 | 데이터 손실 | Reconnect, 로컬 캐시 |
| Claude API 비용 | 운영 비용 증가 | Haiku 우선, 캐싱 |

---

## 11. Future Enhancements

| 기능 | 우선순위 | 설명 |
|------|----------|------|
| 웹 대시보드 | P3 | React 기반 시각화 |
| 모바일 앱 | P3 | React Native |
| 음성 인터페이스 | P3 | "오늘 할 일 알려줘" |
| 팀 협업 | P3 | 공유 리포트 |

---

## Appendix

### A. 관련 문서

| 문서 | 경로 |
|------|------|
| 전략 사양서 | `.omc/autopilot/spec.md` |
| 구현 계획 | `.omc/autopilot/implementation-plan.md` |
| CLAUDE.md | `CLAUDE.md` |

### B. Checklist

→ `docs/checklists/PRD-0001.md` 참조
