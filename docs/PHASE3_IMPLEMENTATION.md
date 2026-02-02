# Phase 3: Automation Actions Implementation

## 개요

분석 결과를 기반으로 자동화 액션을 실행하는 시스템 구현 완료.

## 구현된 액션

| 액션 | 파일 | 기능 | 안전 장치 |
|------|------|------|----------|
| **Toast Notifier** | `scripts/actions/toast_notifier.py` | Windows Toast 알림 전송 | - |
| **TODO Generator** | `scripts/actions/todo_generator.py` | 분석 결과에서 TODO 마크다운 생성 | - |
| **Calendar Creator** | `scripts/actions/calendar_creator.py` | Google Calendar 일정 생성 | `--confirm` 필수 (기본 dry-run) |
| **Response Drafter** | `scripts/actions/response_drafter.py` | AI 응답 초안 생성 | 절대 자동 전송 금지 (파일 + 알림만) |

## 파일 구조

```
C:\claude\secretary\scripts\
└── actions\
    ├── __init__.py                # 패키지 초기화
    ├── toast_notifier.py          # Windows Toast 알림 (winotify)
    ├── todo_generator.py          # TODO 마크다운 생성
    ├── calendar_creator.py        # Google Calendar API
    └── response_drafter.py        # Claude API 응답 초안
```

## 사용 예시

### 1. Toast 알림

```powershell
# CLI 방식
python scripts/actions/toast_notifier.py --title "긴급" --message "이메일 3건 확인 필요"

# JSON 방식
echo '{"title":"할일","message":"리뷰 대기"}' | python scripts/actions/toast_notifier.py --json
```

### 2. TODO 생성

```powershell
# 분석 결과에서 TODO 생성
python scripts/daily_report.py --json > report.json
python scripts/actions/todo_generator.py --input report.json

# 출력만 (파일 저장 안 함)
python scripts/actions/todo_generator.py --input report.json --print
```

**출력 경로**: `C:\claude\secretary\output\todos\YYYY-MM-DD.md`

**형식**:
```markdown
# TODO - 2026-02-02

## 긴급 (High)
- [ ] 프로젝트 리뷰 요청 (발신: manager@example.com, 마감: 2026-02-05)

## 보통 (Medium)
- [ ] 문서 확인 부탁 (발신: colleague@example.com)

## 낮음 (Low)
- [ ] 팀 미팅 준비 (시간: 14:00)
```

### 3. Calendar 일정 생성

```powershell
# Dry-run (실제 생성하지 않음)
python scripts/actions/calendar_creator.py `
  --title "팀 미팅" `
  --start "2026-02-10 14:00" `
  --end "2026-02-10 15:00" `
  --description "주간 팀 미팅"

# 실제 생성 (확인 필수)
python scripts/actions/calendar_creator.py `
  --title "팀 미팅" `
  --start "2026-02-10 14:00" `
  --end "2026-02-10 15:00" `
  --confirm
```

**인증**: `C:\claude\json\token_calendar.json` (기존 토큰 재사용)
**필요 권한**: `calendar.events` (쓰기 권한)

### 4. 응답 초안 생성

```powershell
# JSON 파일로 초안 생성
python scripts/actions/response_drafter.py --input unanswered_email.json

# 출력만 (파일 저장 안 함)
python scripts/actions/response_drafter.py --input unanswered_email.json --print
```

**출력 경로**: `C:\claude\secretary\output\drafts\{timestamp}_{id}.md`

**CRITICAL**:
- 절대 자동으로 이메일/메시지를 전송하지 않음
- 초안 파일 생성 + Toast 알림만 수행
- 사용자가 파일을 검토 후 수동으로 전송해야 함

## 의존성

```txt
winotify>=1.1.0           # Windows Toast notifications
anthropic>=0.18.0         # Claude API
```

**설치**:
```powershell
pip install -r requirements.txt
```

## 환경 변수

| 변수 | 필요 여부 | 용도 |
|------|----------|------|
| `ANTHROPIC_API_KEY` | `response_drafter.py`만 | Claude API 인증 |

## 안전 규칙

| 규칙 | 내용 |
|------|------|
| **자동 전송 금지** | `response_drafter.py`는 절대 자동으로 이메일 전송하지 않음 |
| **확인 필수** | `calendar_creator.py`는 `--confirm` 없으면 dry-run만 수행 |
| **파일 생성 위치** | `output/todos/`, `output/drafts/` 고정 |

## 테스트

```powershell
# 개별 액션 테스트
python tests/test_actions.py

# 데모 실행
python demo_actions.py
```

## 알려진 이슈

1. **Encoding 이슈**: Windows 콘솔에서 일부 유니코드 문자(이모지) 출력 시 `cp949` 인코딩 에러
   - 해결: 각 스크립트에 `sys.stdout.reconfigure(encoding="utf-8")` 추가됨
   - 여전히 subprocess 출력에서 발생 가능

2. **Calendar API Scope**: `calendar_creator.py`는 쓰기 권한(`calendar.events`) 필요
   - 기존 토큰이 read-only면 재인증 필요
   - 첫 실행 시 OAuth 브라우저 인증 진행

3. **Claude API 키**: `response_drafter.py`는 `ANTHROPIC_API_KEY` 환경 변수 필수
   - 없으면 에러 발생하고 종료

## 통합 워크플로우 예시

```powershell
# 1. 일일 리포트 분석
python scripts/daily_report.py --json > report.json

# 2. TODO 생성
python scripts/actions/todo_generator.py --input report.json

# 3. Toast 알림
python scripts/actions/toast_notifier.py `
  --title "일일 리포트 완료" `
  --message "TODO 3건 생성됨"
```

## 다음 단계 (Phase 4)

- 전체 워크플로우 자동화 스크립트
- 스케줄러 통합 (Windows Task Scheduler)
- 알림 설정 커스터마이징
- 응답 초안 템플릿 시스템

---

**구현 날짜**: 2026-02-02
**구현자**: Claude Code (Sisyphus-Junior)
