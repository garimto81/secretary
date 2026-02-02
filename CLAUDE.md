# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

Gmail, Google Calendar, GitHub, Slack, LLM 세션(Claude Code, ChatGPT)을 통합 분석하여 일일 업무 현황 리포트를 자동 생성하고, 분석 결과를 기반으로 자동화 액션을 실행하는 AI 비서 도구입니다.

**Phase 3 추가**: 자동화 액션 (Toast 알림, TODO 생성, Calendar 일정 생성, 응답 초안)
**Phase 5 추가**: Life Management (MS To Do 연동, 명절/기념일 리마인더, 법인 세무 일정 자동화)

## 빌드 및 실행

```powershell
# 의존성 설치
pip install -r requirements.txt

# 전체 일일 리포트
python scripts/daily_report.py

# 개별 분석
python scripts/gmail_analyzer.py --unread --days 3
python scripts/calendar_analyzer.py --today
python scripts/github_analyzer.py --days 5
python scripts/slack_analyzer.py --days 3 --channels general,team
python scripts/llm_analyzer.py --days 7 --source claude_code

# Android 알림 수신 (Phase 2)
python scripts/notification_receiver.py --start --port 8800
python scripts/notification_analyzer.py --days 3 --app kakao

# Automation Actions (Phase 3)
python scripts/actions/toast_notifier.py --title "제목" --message "내용"
python scripts/actions/todo_generator.py --input report.json
python scripts/actions/calendar_creator.py --title "회의" --start "2026-02-10 14:00" --end "2026-02-10 15:00"
python scripts/actions/response_drafter.py --input unanswered_email.json

# JSON 출력
python scripts/daily_report.py --json
python scripts/llm_analyzer.py --json
```

## 아키텍처

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

`daily_report.py`가 각 분석 스크립트를 subprocess로 실행하고 JSON 결과를 수집하여 종합 리포트를 생성합니다.

`llm_analyzer.py`는 Claude Code 세션 로그(JSONL)와 ChatGPT Export(JSON)를 파싱하여 AI 사용 패턴을 분석합니다.

## 인증 설정

### Google OAuth (Gmail, Calendar)

인증 파일 경로:
- `C:\claude\json\desktop_credentials.json` - OAuth 클라이언트 ID
- `C:\claude\json\token_gmail.json` - Gmail 토큰 (자동 생성)
- `C:\claude\json\token_calendar.json` - Calendar 토큰 (자동 생성)

첫 실행 시 브라우저에서 OAuth 인증 진행됩니다.

### GitHub

- 환경 변수: `GITHUB_TOKEN`
- 또는 파일: `C:\claude\json\github_token.txt`
- 필요 권한: `repo`, `read:user`

### Slack

인증 파일 경로:
- `C:\claude\json\slack_credentials.json` - OAuth 클라이언트 또는 bot_token
- `C:\claude\json\slack_token.json` - Slack 토큰 (자동 생성)

인증 방법:
1. 직접 토큰 사용 (권장): `slack_credentials.json`에 `bot_token` 추가
2. OAuth 인증: `python -m lib.slack login`

필요 권한: `chat:write`, `channels:read`, `channels:history`, `groups:read`, `groups:history`, `users:read`

### LLM Sessions

Claude Code 세션 로그 경로:
- `C:\Users\AidenKim\.claude\projects\{hash}\*.jsonl`

ChatGPT Export 파일:
- 수동 제공 필요 (`--chatgpt-file PATH` 옵션)

## LLM 세션 분석 기능

| 기능 | 설명 |
|------|------|
| 세션 통계 | 일별/주별 AI 사용량 |
| 토픽 추출 | 언급된 파일, 브랜치, 키워드 |
| 도구 사용 패턴 | Read/Write/Bash/Task 빈도 |
| 프로젝트 활동 | 프로젝트별 세션 수 |

## 주의 필요 항목 기준

| 소스 | 조건 | 긴급도 |
|------|------|--------|
| Email | 마감일 D-1 | High |
| Email | 미응답 48시간+ | Medium |
| Email | 미응답 72시간+ | High |
| GitHub | PR 리뷰 대기 3일+ | 주의 |
| GitHub | 이슈 응답 없음 4일+ | 주의 |
| Slack | 긴급 키워드 포함 | High |
| Slack | 멘션 + 48시간+ | High |
| Slack | 멘션 + 24시간+ | Medium |

## CLI 옵션 요약

| 스크립트 | 주요 옵션 |
|----------|----------|
| `daily_report.py` | `--gmail`, `--calendar`, `--github`, `--slack`, `--llm`, `--life`, `--all`, `--json` |
| `gmail_analyzer.py` | `--unread`, `--days N`, `--max N`, `--json` |
| `calendar_analyzer.py` | `--today`, `--week`, `--days N`, `--json` |
| `github_analyzer.py` | `--days N`, `--repos`, `--json` |
| `slack_analyzer.py` | `--days N`, `--max N`, `--channels LIST`, `--json` |
| `llm_analyzer.py` | `--days N`, `--source SOURCE`, `--chatgpt-file PATH`, `--json` |
| `toast_notifier.py` | `--title`, `--message`, `--json` |
| `todo_generator.py` | `--input FILE`, `--print`, `--json` |
| `calendar_creator.py` | `--title`, `--start`, `--end`, `--confirm`, `--json` |
| `response_drafter.py` | `--email-id ID`, `--input FILE`, `--print`, `--json` |

## Automation Actions (Phase 3)

| 액션 | 설명 | 안전 장치 |
|------|------|----------|
| **Toast Notifier** | Windows Toast 알림 전송 | - |
| **TODO Generator** | 분석 결과에서 TODO 마크다운 생성 | - |
| **Calendar Creator** | Google Calendar 일정 생성 | `--confirm` 플래그 필수 (기본 dry-run) |
| **Response Drafter** | AI 응답 초안 생성 | 절대 자동 전송하지 않음 (파일 + 알림만) |

### 사용 예시

```powershell
# 1. 일일 리포트 분석 후 TODO 생성
python scripts/daily_report.py --json > report.json
python scripts/actions/todo_generator.py --input report.json

# 2. 미응답 이메일 초안 생성
python scripts/actions/response_drafter.py --input unanswered_email.json

# 3. Calendar 일정 추가 (dry-run)
python scripts/actions/calendar_creator.py --title "회의" --start "2026-02-10 14:00" --end "2026-02-10 15:00"

# 4. Calendar 일정 추가 (실제 생성)
python scripts/actions/calendar_creator.py --title "회의" --start "2026-02-10 14:00" --end "2026-02-10 15:00" --confirm

# 5. Toast 알림 전송
python scripts/actions/toast_notifier.py --title "긴급" --message "이메일 3건 확인 필요"
```

### 안전 규칙

| 규칙 | 내용 |
|------|------|
| **자동 전송 금지** | `response_drafter.py`는 절대 자동으로 이메일/메시지 전송하지 않음 |
| **확인 필수** | `calendar_creator.py`는 `--confirm` 없으면 dry-run만 수행 |
| **API 키 필요** | `response_drafter.py`는 `ANTHROPIC_API_KEY` 환경 변수 필요 |

## Life Management (Phase 5)

### MS To Do 연동

```powershell
# 인증 (최초 1회)
python scripts/integrations/mstodo_adapter.py login

# 리스트 조회
python scripts/integrations/mstodo_adapter.py lists

# TODO 추가 (Push-only)
python scripts/integrations/mstodo_adapter.py push --title "할일" --list personal
python scripts/integrations/mstodo_adapter.py push --title "세금 납부" --list business --importance high
```

인증 파일 경로:
- `C:\claude\json\token_mstodo.json` - MS Graph 토큰 (자동 생성)

### 생활 이벤트 관리

```powershell
# 앞으로 30일 이벤트
python scripts/life/event_manager.py upcoming --days 30

# 오늘의 리마인더
python scripts/life/event_manager.py reminders

# 이벤트 추가
python scripts/life/event_manager.py add --name "어머니 생신" --month 5 --day 15 --lunar --type birthday
```

설정 파일: `config/life_events.json`

### 세무 일정 자동화

```powershell
# 설정된 세무 일정 목록
python scripts/life/tax_calendar.py list

# 연간 일정 생성 (dry-run)
python scripts/life/tax_calendar.py generate --year 2026

# 실제 Calendar 등록
python scripts/life/tax_calendar.py generate --year 2026 --confirm
```

설정 파일: `config/tax_calendar.json`

### 기본 세무 일정 (한국 법인)

| 항목 | 빈도 | 기한 |
|------|------|------|
| 원천세 신고/납부 | 매월 | 10일 |
| 4대보험 납부 | 매월 | 10일 |
| 부가세 신고/납부 | 분기 | 1/4/7/10월 25일 |
| 법인세 신고/납부 | 연간 | 3월 31일 |
| 지방소득세 신고/납부 | 연간 | 4월 30일 |

### 프라이버시 설정

모든 데이터는 로컬에만 저장되며, Git에 민감 정보가 올라가지 않습니다:
- `.gitignore`에 `output/`, `config/`, `token_*.json` 제외됨
- MS To Do/Calendar는 비공개 리스트/캘린더 사용 권장
