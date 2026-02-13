# Pipeline Completion Plan

> Gateway Pipeline의 미완성 기능 2개를 완성하여 메시지 수신부터 승인 후 전송까지 end-to-end 워크플로우를 구현한다.

## Context

### Original Request

Secretary Gateway의 6단계 MessagePipeline에서 미구현된 2개 기능을 완성:
1. **Stage 5 - Action Dispatch**: 감지된 액션(deadline, action_request)을 실제 TODO/Calendar로 디스패치
2. **승인 후 전송 경로**: `cli.py drafts approve` 이후 실제 Slack/Gmail 전송 메커니즘 구현

### Research Findings

코드베이스 탐색 결과:

**Stage 5 현황** (`pipeline.py:297-312`):
- `_dispatch_actions()` 메서드가 존재하지만 `pass`만 있음
- Stage 2 `_detect_actions()`가 3종 액션을 감지: `deadline:*`, `action_request:*`, `question`
- 연동 대상: `todo_generator.py` (JSON 입력 -> Markdown TODO 파일 생성), `calendar_creator.py` (dry-run/confirm 기반 Calendar 이벤트 생성)
- `todo_generator.py`는 동기 함수 (`extract_todos_from_*`, `generate_markdown`, `save_todo_file`)
- `calendar_creator.py`는 `--confirm` 없으면 dry-run만 수행 (안전장치 내장)

**승인 후 전송 현황**:
- `cli.py cmd_drafts_approve()`: DB status를 "approved"로 변경만 함, 전송 로직 없음
- `SlackAdapter.send()`: `confirmed=True`여도 강제로 draft 파일만 저장 (line 103-111)
- `GmailAdapter.send()`: 항상 draft 파일만 저장 (line 88-97)
- `ChannelAdapter.send()` 인터페이스: `confirmed=True`일 때 실제 전송하도록 설계되어 있으나 구현체가 무시
- `OutboundMessage.confirmed` 필드가 존재하지만 활용되지 않음
- `draft_responses` 테이블: `status` 컬럼으로 `pending/approved/rejected` 상태 관리

**안전장치 현황**:
- `config/gateway.json`: `safety.auto_send_disabled=true`, `safety.require_confirmation=true`
- Pipeline rate limit: 분당 10건
- Claude draft rate limit: 분당 5건
- 4계층: 설정(gateway.json) -> 어댑터(send 메서드) -> DB(status 컬럼) -> CLI(approve/reject)

### Existing Plans (비중복 확인)

| Plan | 범위 | 겹침 |
|------|------|------|
| `multichannel-integration.plan.md` | Gateway 아키텍처, 어댑터 설계, Pipeline 구조 | Pipeline 구조 정의만, dispatch 구현 없음 |
| `project-intelligence.plan.md` | 2-Tier LLM 분석 | Intelligence handler만, 액션 디스패치 없음 |
| `phase5-life-management.plan.md` | Life Management, MS To Do | 별도 도메인 |
| `poc-verification.plan.md` | PoC 검증 | 검증 범위만 |

-> Stage 5 dispatch와 승인 후 전송은 기존 Plan과 겹치지 않음

---

## Work Objectives

### Core Objective

Pipeline의 "감지 -> 저장" 흐름을 "감지 -> 저장 -> 디스패치 -> 승인 -> 전송"까지 완성하여, 메시지 수신부터 최종 액션까지 end-to-end 자동화 경로를 구축한다.

### Deliverables

1. **Stage 5 Action Dispatcher**: deadline/action_request 액션을 TODO 파일 생성 및 Calendar dry-run으로 디스패치
2. **`drafts send` CLI 커맨드**: 승인된 draft를 실제 Slack/Gmail로 전송하는 명시적 전송 경로
3. **어댑터 `send()` 실제 전송 구현**: SlackAdapter/GmailAdapter에서 `confirmed=True` 시 실제 전송
4. **안전장치**: 이중 확인, 전송 로그, dry-run 기본값 유지

### Definition of Done

- [ ] Stage 5에서 deadline 액션 감지 시 TODO 파일이 `output/todos/` 에 자동 생성됨
- [ ] Stage 5에서 deadline 액션 감지 시 Calendar dry-run 로그가 출력됨 (실제 생성은 하지 않음)
- [ ] `cli.py drafts send <id>` 실행 시 approved 상태 draft가 해당 채널로 실제 전송됨
- [ ] `cli.py drafts send <id> --dry-run` 실행 시 전송 내용만 표시하고 실제 전송하지 않음
- [ ] 전송 후 DB status가 "sent"로 업데이트됨
- [ ] approved 아닌 draft에 send 시도 시 거부됨
- [ ] 전송 실패 시 status가 "send_failed"로 업데이트되고 에러 메시지 기록됨
- [ ] 기존 4계층 안전장치가 유지됨 (자동 전송 절대 없음, 명시적 send만 가능)

---

## Must Have / Must NOT Have

### Must Have

| ID | 항목 |
|----|------|
| MH-1 | Stage 5에서 deadline/action_request 감지 시 TODO 파일 자동 생성 |
| MH-2 | `drafts send` CLI 커맨드 (approved draft만 전송 가능) |
| MH-3 | SlackAdapter에서 실제 Slack 메시지 전송 (lib.slack.SlackClient 사용) |
| MH-4 | GmailAdapter에서 실제 Gmail draft 생성 또는 전송 (lib.gmail.GmailClient 사용) |
| MH-5 | 전송 전 이중 확인 프롬프트 (`--force` 없으면 확인 필수) |
| MH-6 | 전송 결과 DB 기록 (status: sent/send_failed, sent_at 타임스탬프) |
| MH-7 | 전송 로그 파일 기록 (`data/send_log.jsonl`) |

### Must NOT Have

| ID | 항목 | 이유 |
|----|------|------|
| MN-1 | Pipeline Stage 5에서 자동 전송 | 자동 전송 금지 정책 위반 |
| MN-2 | approve와 동시에 자동 전송 | 명시적 send 단계 필수 |
| MN-3 | Calendar 이벤트 자동 생성 | dry-run만 허용, 실제 생성은 별도 CLI |
| MN-4 | question 액션의 자동 처리 | Intelligence handler가 이미 담당 |
| MN-5 | draft_responses 테이블 스키마 변경 | sent_at, send_error는 기존 컬럼 활용 또는 reviewer_note 필드 활용 |

---

## Task Flow and Dependencies

```
Task 1: ActionDispatcher 클래스 구현
    │
    ├── Task 2: Pipeline Stage 5 연동
    │
    └── Task 3: todo_generator async wrapper
         │
Task 4: draft_responses 테이블 확장 (sent_at, send_error 컬럼)
    │
    ├── Task 5: SlackAdapter.send() 실제 전송 구현
    │
    ├── Task 6: GmailAdapter.send() 실제 전송 구현
    │
    └── Task 7: CLI drafts send 커맨드 구현
         │
         └── Task 8: 전송 로그 및 안전장치

Task 9: 테스트 작성
```

---

## Detailed TODOs

### Task 1: ActionDispatcher 클래스 구현

**파일**: `C:\claude\secretary\scripts\gateway\action_dispatcher.py` (신규)

**목적**: 감지된 액션을 적절한 핸들러로 라우팅하는 디스패처 클래스

**구현 내용**:
```
ActionDispatcher
    ├── dispatch(message, actions) -> List[DispatchResult]
    ├── _handle_deadline(message, deadline_text) -> DispatchResult
    ├── _handle_action_request(message, keyword) -> DispatchResult
    └── _create_todo_entry(message, action_type, detail) -> dict
```

- `_handle_deadline`: deadline 텍스트에서 날짜 파싱 -> TODO 항목 생성 + Calendar dry-run 로그
- `_handle_action_request`: 요청 키워드 기반 TODO 항목 생성
- `_create_todo_entry`: NormalizedMessage에서 todo_generator 호환 dict 생성
- question 액션은 무시 (Intelligence handler에서 처리)

**Acceptance Criteria**:
- [ ] deadline 액션에서 TODO 파일 생성됨
- [ ] action_request 액션에서 TODO 파일 생성됨
- [ ] question 액션은 무시됨
- [ ] 3중 import fallback 패턴 준수

---

### Task 2: Pipeline Stage 5 연동

**파일**: `C:\claude\secretary\scripts\gateway\pipeline.py` (수정)

**수정 범위**: `_dispatch_actions()` 메서드 (lines 297-312)

**구현 내용**:
- MessagePipeline.__init__에서 ActionDispatcher 인스턴스 생성
- `_dispatch_actions()`에서 ActionDispatcher.dispatch() 호출
- dispatch 결과를 PipelineResult에 기록

**Acceptance Criteria**:
- [ ] ActionDispatcher가 pipeline 초기화 시 생성됨
- [ ] has_action=True인 메시지가 ActionDispatcher로 전달됨
- [ ] dispatch 실패 시 에러가 result.error에 기록되지만 pipeline은 계속 진행

---

### Task 3: todo_generator async wrapper

**파일**: `C:\claude\secretary\scripts\actions\todo_generator.py` (수정)

**수정 범위**: 기존 함수는 유지, async wrapper 함수 추가

**구현 내용**:
```python
async def append_todo_from_message(
    title: str,
    priority: str,
    sender: str,
    deadline: str = "",
    source_type: str = "gateway",
) -> Path:
    """Pipeline에서 호출하는 async wrapper - 오늘자 TODO 파일에 항목 추가"""
```

- 기존 `save_todo_file()`과 `generate_markdown()`을 재활용
- 오늘자 TODO 파일이 이미 존재하면 append, 없으면 새로 생성
- `asyncio.to_thread()`로 파일 I/O를 비동기로 실행

**Acceptance Criteria**:
- [ ] 기존 CLI 인터페이스 (`--input`, `--print`) 그대로 동작
- [ ] async wrapper가 Pipeline에서 호출 가능
- [ ] 오늘자 파일 존재 시 append 동작

---

### Task 4: draft_responses 테이블 확장

**파일**: `C:\claude\secretary\scripts\intelligence\context_store.py` (수정)

**수정 범위**: SCHEMA 상수 및 관련 메서드

**구현 내용**:
- `draft_responses` 테이블에 `sent_at DATETIME`, `send_error TEXT` 컬럼 추가
- 마이그레이션: ALTER TABLE 기반 (기존 데이터 유지)
- `update_draft_sent()` 메서드 추가
- `update_draft_send_failed()` 메서드 추가

**Acceptance Criteria**:
- [ ] 기존 DB에 새 컬럼이 안전하게 추가됨 (ALTER TABLE IF NOT EXISTS 패턴)
- [ ] 새 메서드가 sent_at, send_error를 업데이트함
- [ ] 기존 메서드들이 영향받지 않음

---

### Task 5: SlackAdapter.send() 실제 전송 구현

**파일**: `C:\claude\secretary\scripts\gateway\adapters\slack.py` (수정)

**수정 범위**: `send()` 메서드

**구현 내용**:
```python
async def send(self, message) -> SendResult:
    """메시지 전송

    confirmed=False: draft 파일만 저장 (기존 동작 유지)
    confirmed=True: lib.slack.SlackClient.send_message()로 실제 전송
    """
```

- `confirmed=False`: 기존 동작 유지 (draft 파일 저장)
- `confirmed=True`: `self._client.send_message(channel, text)` 호출
- 전송 성공 시 `SendResult(success=True, message_id=ts, sent_at=now)`
- 전송 실패 시 `SendResult(success=False, error=str(e))`
- `_client`가 None이면 connect 필요 에러 반환

**Acceptance Criteria**:
- [ ] confirmed=False 시 기존 draft 저장 동작 유지
- [ ] confirmed=True 시 실제 Slack 메시지 전송
- [ ] 전송 성공/실패 결과가 SendResult에 정확히 반영

---

### Task 6: GmailAdapter.send() 실제 전송 구현

**파일**: `C:\claude\secretary\scripts\gateway\adapters\gmail.py` (수정)

**수정 범위**: `send()` 메서드

**구현 내용**:
```python
async def send(self, message) -> SendResult:
    """이메일 전송

    confirmed=False: draft 파일만 저장 (기존 동작 유지)
    confirmed=True: lib.gmail.GmailClient로 Gmail draft 생성 (전송은 아님)
    """
```

- `confirmed=False`: 기존 동작 유지 (로컬 draft 파일)
- `confirmed=True`: `self._client.create_draft(to, subject, body)` 호출하여 Gmail Draft로 저장
- Gmail의 경우 실제 `send`가 아닌 `create_draft`로 Gmail UI에서 최종 확인 후 전송 가능하게 함
- 이유: 이메일은 Slack보다 되돌리기 어려우므로 추가 안전장치

**Acceptance Criteria**:
- [ ] confirmed=False 시 기존 로컬 draft 저장 동작 유지
- [ ] confirmed=True 시 Gmail Draft 생성 (Gmail UI에서 확인 가능)
- [ ] lib.gmail이 create_draft를 미지원 시 fallback으로 로컬 draft + 경고 메시지

---

### Task 7: CLI `drafts send` 커맨드 구현

**파일**: `C:\claude\secretary\scripts\intelligence\cli.py` (수정)

**수정 범위**: drafts 서브커맨드에 send 추가

**구현 내용**:
```
python cli.py drafts send <id> [--dry-run] [--force]
```

**워크플로우**:
1. DB에서 draft 조회
2. status가 "approved"인지 확인 (아니면 거부)
3. `--dry-run`이면 전송 내용만 표시하고 종료
4. `--force`가 없으면 전송 확인 프롬프트 표시
5. source_channel에 따라 적절한 어댑터 생성 및 connect
6. OutboundMessage 생성 (confirmed=True)
7. adapter.send() 호출
8. 성공 시 DB status를 "sent"로 업데이트, sent_at 기록
9. 실패 시 DB status를 "send_failed"로 업데이트, send_error 기록
10. 전송 로그 기록

**Acceptance Criteria**:
- [ ] approved 아닌 draft에 send 시 에러 메시지 출력
- [ ] --dry-run 시 전송 내용만 표시
- [ ] --force 없으면 확인 프롬프트 표시
- [ ] 전송 성공 시 DB 상태 업데이트
- [ ] 전송 실패 시 DB 에러 기록

---

### Task 8: 전송 로그 및 안전장치

**파일**: `C:\claude\secretary\scripts\intelligence\send_log.py` (신규)

**구현 내용**:
```python
class SendLogger:
    """전송 이력 JSONL 로그"""

    def __init__(self, log_path=None):
        self.log_path = log_path or Path(r"C:\claude\secretary\data\send_log.jsonl")

    def log_send(self, draft_id, channel, recipient, status, error=None):
        """전송 시도 기록"""

    def get_recent(self, limit=20) -> list:
        """최근 전송 이력 조회"""
```

- JSONL 형식 (한 줄에 하나의 JSON 객체)
- 기록 항목: timestamp, draft_id, channel, recipient, status, error, operator
- `cli.py drafts log` 커맨드로 조회 가능

**Acceptance Criteria**:
- [ ] 모든 전송 시도가 JSONL 파일에 기록됨
- [ ] `drafts log` 커맨드로 최근 전송 이력 조회 가능

---

### Task 9: 테스트 작성

**파일**: `C:\claude\secretary\tests\test_action_dispatcher.py` (신규), `C:\claude\secretary\tests\test_drafts_send.py` (신규)

**구현 내용**:

`test_action_dispatcher.py`:
- `test_dispatch_deadline_creates_todo`: deadline 액션 -> TODO 파일 생성 확인
- `test_dispatch_action_request_creates_todo`: action_request -> TODO 파일 생성 확인
- `test_dispatch_question_ignored`: question 액션 무시 확인
- `test_dispatch_empty_actions`: 빈 액션 리스트 처리

`test_drafts_send.py`:
- `test_send_approved_draft_success`: approved draft 전송 성공
- `test_send_pending_draft_rejected`: pending 상태 draft 전송 거부
- `test_send_dry_run_no_actual_send`: dry-run 시 전송 안 됨
- `test_send_failure_updates_status`: 전송 실패 시 send_failed 상태

**Acceptance Criteria**:
- [ ] 모든 테스트 통과
- [ ] mock을 사용하여 실제 Slack/Gmail API 호출 없이 테스트

---

## Commit Strategy

| 순서 | 커밋 메시지 | 포함 파일 |
|------|------------|----------|
| 1 | `feat(gateway): implement ActionDispatcher for Stage 5` | `action_dispatcher.py`, `pipeline.py`, `todo_generator.py` |
| 2 | `feat(intelligence): add sent_at/send_error columns to draft_responses` | `context_store.py` |
| 3 | `feat(gateway): implement actual send in SlackAdapter and GmailAdapter` | `adapters/slack.py`, `adapters/gmail.py` |
| 4 | `feat(intelligence): add drafts send CLI command with safety checks` | `cli.py`, `send_log.py` |
| 5 | `test: add tests for ActionDispatcher and drafts send` | `tests/test_action_dispatcher.py`, `tests/test_drafts_send.py` |

---

## Risk Assessment

| 위험 | 영향 | 가능성 | 완화 방안 |
|------|------|--------|----------|
| lib.slack에 `send_message()` 미구현 | HIGH | MEDIUM | lib.slack 코드 확인 필수, 미지원 시 Slack Web API 직접 호출 |
| lib.gmail에 `create_draft()` 미구현 | HIGH | MEDIUM | lib.gmail 코드 확인 필수, 미지원 시 Gmail API 직접 호출 또는 로컬 draft fallback |
| 기존 DB에 ALTER TABLE 실패 | MEDIUM | LOW | try/except로 이미 존재하는 컬럼이면 무시 |
| 안전장치 우회 경로 발생 | CRITICAL | LOW | Task 8에서 모든 전송 경로에 로그 기록, approved 상태 체크를 DB 레벨에서 강제 |
| Rate limit 미준수로 Slack/Gmail API 차단 | MEDIUM | LOW | 기존 rate limit 인프라 재활용, send에도 rate limit 적용 |

---

## Affected Files

### 신규 파일

| 파일 | 목적 |
|------|------|
| `C:\claude\secretary\scripts\gateway\action_dispatcher.py` | Stage 5 액션 디스패처 |
| `C:\claude\secretary\scripts\intelligence\send_log.py` | 전송 로그 |
| `C:\claude\secretary\tests\test_action_dispatcher.py` | 디스패처 테스트 |
| `C:\claude\secretary\tests\test_drafts_send.py` | 전송 워크플로우 테스트 |

### 수정 파일

| 파일 | 수정 범위 |
|------|----------|
| `C:\claude\secretary\scripts\gateway\pipeline.py` | `_dispatch_actions()` 구현 (lines 297-312) |
| `C:\claude\secretary\scripts\actions\todo_generator.py` | `append_todo_from_message()` async wrapper 추가 |
| `C:\claude\secretary\scripts\gateway\adapters\slack.py` | `send()` 실제 전송 구현 |
| `C:\claude\secretary\scripts\gateway\adapters\gmail.py` | `send()` Gmail Draft 생성 구현 |
| `C:\claude\secretary\scripts\intelligence\cli.py` | `drafts send`, `drafts log` 서브커맨드 추가 |
| `C:\claude\secretary\scripts\intelligence\context_store.py` | `sent_at`, `send_error` 컬럼 추가 및 관련 메서드 |

### 변경 없는 파일

| 파일 | 이유 |
|------|------|
| `C:\claude\secretary\scripts\gateway\models.py` | OutboundMessage 이미 confirmed 필드 보유 |
| `C:\claude\secretary\scripts\gateway\adapters\base.py` | ChannelAdapter.send() 인터페이스 이미 적절 |
| `C:\claude\secretary\scripts\gateway\server.py` | Pipeline 초기화 로직 변경 불필요 |
| `C:\claude\secretary\scripts\actions\calendar_creator.py` | 기존 인터페이스 그대로 사용 (subprocess 호출) |
| `C:\claude\secretary\scripts\intelligence\response\handler.py` | Intelligence 핸들러 변경 불필요 |
| `C:\claude\secretary\config\gateway.json` | 기존 safety 설정 유지 |

---

## Success Criteria

전체 완료 기준:

1. **Stage 5 Dispatch**: 마감일 포함 Slack 메시지 수신 -> Pipeline -> TODO 파일 자동 생성 (end-to-end)
2. **Draft 전송 워크플로우**: 메시지 수신 -> Intelligence 분석 -> 초안 생성 -> approve -> `drafts send` -> 실제 Slack 메시지 전송 (end-to-end)
3. **안전장치 유지**: 어떤 경로에서도 자동 전송이 발생하지 않음. 모든 전송은 `drafts send` CLI의 명시적 호출 필요
4. **전송 추적**: 모든 전송 시도가 DB + JSONL 로그에 기록됨
5. **기존 기능 무영향**: 기존 Pipeline, Intelligence, CLI 기능이 정상 동작
