# Pipeline Completion Design

> Plan Reference: docs/01-plan/pipeline-completion.plan.md

## 1. 전체 데이터 흐름도

### 1.1 현재 상태 (Before)

```
메시지 수신
    |
    v
Pipeline Stage 1-4 (Priority, Action Detection, Storage, Notification)
    |
    v
Stage 5: _dispatch_actions() ──── pass (미구현)
    |
    v
Stage 6: Custom Handlers (Intelligence 등)
    |
    v
Intelligence → Ollama 분석 → Claude Draft 생성 → DB 저장 (status=pending)
    |
    v
CLI: drafts approve → DB status="approved" ──── 종료 (전송 경로 없음)
```

### 1.2 목표 상태 (After)

```
메시지 수신
    |
    v
Pipeline Stage 1-4 (Priority, Action Detection, Storage, Notification)
    |
    v
Stage 5: _dispatch_actions()
    |
    +--[deadline:*]-------> ActionDispatcher._handle_deadline()
    |                           +-> todo_generator.append_todo_from_message() -> TODO 파일
    |                           +-> calendar_creator dry-run 로그 출력
    |
    +--[action_request:*]--> ActionDispatcher._handle_action_request()
    |                           +-> todo_generator.append_todo_from_message() -> TODO 파일
    |
    +--[question]----------> 무시 (Intelligence handler가 Stage 6에서 처리)
    |
    v
Stage 6: Custom Handlers (Intelligence 등)
    |
    v
Intelligence → Ollama → Claude Draft → DB (status=pending)
    |
    v
CLI: drafts approve → DB status="approved"
    |
    v
CLI: drafts send <id>
    +--[status != approved]---> 거부 메시지 출력, 종료
    +--[--dry-run]------------> 전송 내용 표시만, 종료
    +--[--force 없음]---------> 확인 프롬프트 → N이면 종료
    +--[전송 실행]
        |
        +--[source_channel=slack]
        |   +-> SlackAdapter.send(confirmed=True)
        |       +-> lib.slack.SlackClient.send_message()
        |       +-> SendResult(ok, ts, channel)
        |
        +--[source_channel=email]
        |   +-> GmailAdapter.send(confirmed=True)
        |       +-> self._client.service.users().drafts().create()
        |       +-> SendResult(success, draft_id)
        |
        +--[성공]--> DB: status="sent", sent_at=now
        +--[실패]--> DB: status="send_failed", send_error=message
        +--[항상]--> SendLogger.log_send() -> data/send_log.jsonl
```

### 1.3 컴포넌트 배치도

```
C:\claude\secretary\scripts\
    |
    +-- gateway/
    |   +-- pipeline.py .............. Stage 5에서 ActionDispatcher 호출 (수정)
    |   +-- action_dispatcher.py ..... ActionDispatcher 클래스 (신규)
    |   +-- models.py ................ OutboundMessage (변경 없음)
    |   +-- storage.py ............... UnifiedStorage (변경 없음)
    |   +-- adapters/
    |       +-- base.py .............. ChannelAdapter, SendResult (변경 없음)
    |       +-- slack.py ............. SlackAdapter.send() 실제 전송 (수정)
    |       +-- gmail.py ............. GmailAdapter.send() Draft 생성 (수정)
    |
    +-- intelligence/
    |   +-- cli.py ................... drafts send, drafts log 추가 (수정)
    |   +-- context_store.py ......... sent_at, send_error 컬럼 추가 (수정)
    |   +-- send_log.py .............. SendLogger JSONL 기록 (신규)
    |
    +-- actions/
        +-- todo_generator.py ........ append_todo_from_message() async wrapper (수정)
        +-- calendar_creator.py ...... subprocess 호출 대상 (변경 없음)
```

---

## 2. ActionDispatcher 상세 설계

### 2.1 클래스 다이어그램

```
ActionDispatcher
    |
    +-- __init__(config: Optional[Dict])
    |       config keys:
    |         todo_enabled: bool = True
    |         calendar_dry_run: bool = True
    |
    +-- async dispatch(message: NormalizedMessage, actions: List[str]) -> List[DispatchResult]
    |       1. actions 순회
    |       2. "deadline:" prefix -> _handle_deadline()
    |       3. "action_request:" prefix -> _handle_action_request()
    |       4. "question" -> skip (로그만)
    |       5. List[DispatchResult] 반환
    |
    +-- async _handle_deadline(message, deadline_text) -> DispatchResult
    |       1. _create_todo_entry(message, "deadline", deadline_text) -> dict
    |       2. todo_generator.append_todo_from_message() 호출
    |       3. calendar_creator subprocess dry-run 실행 (deadline 파싱 가능한 경우)
    |       4. DispatchResult(action="deadline", success=True, output_path=...)
    |
    +-- async _handle_action_request(message, keyword) -> DispatchResult
    |       1. _create_todo_entry(message, "action_request", keyword) -> dict
    |       2. todo_generator.append_todo_from_message() 호출
    |       3. DispatchResult(action="action_request", success=True, output_path=...)
    |
    +-- _create_todo_entry(message, action_type, detail) -> dict
            NormalizedMessage에서 todo_generator 호환 dict 생성:
            {
                "type": message.channel.value,
                "priority": _priority_from_message(message),
                "title": _title_from_action(action_type, detail, message),
                "sender": message.sender_name or message.sender_id,
                "deadline": detail (deadline인 경우),
                "source": f"{message.channel.value}:{message.channel_id}",
            }
```

### 2.2 DispatchResult 데이터 모델

```python
@dataclass
class DispatchResult:
    """단일 액션 디스패치 결과"""
    action: str              # "deadline", "action_request"
    success: bool
    output_path: Optional[str] = None   # 생성된 TODO 파일 경로
    calendar_dry_run: Optional[str] = None  # Calendar dry-run 출력
    error: Optional[str] = None
```

### 2.3 todo_generator 연동 방식

기존 동기 함수를 재활용하면서 async wrapper를 추가한다.

```python
async def append_todo_from_message(
    title: str,
    priority: str,         # "high" | "medium" | "low"
    sender: str,
    deadline: str = "",
    source_type: str = "gateway",
) -> Path:
    """Pipeline에서 호출하는 async wrapper - 오늘자 TODO 파일에 항목 추가"""
```

핵심 설계 결정:
- `asyncio.to_thread()`로 파일 I/O를 비동기 실행
- 기존 `generate_markdown()`, `save_todo_file()` 함수는 변경 없음
- 오늘자 파일 append 시 해당 우선순위 섹션을 찾아 삽입

### 2.4 Calendar dry-run 연동

```python
async def _run_calendar_dry_run(self, title: str, deadline_text: str) -> Optional[str]:
    """calendar_creator.py를 subprocess dry-run으로 호출"""
```

Calendar는 항상 dry-run만 실행 (MN-3). subprocess로 호출하므로 calendar_creator.py는 변경하지 않는다.

---

## 3. 어댑터 send() 개선 설계

### 3.1 SlackAdapter.send()

```
send(message: OutboundMessage) -> SendResult
    |
    +--[confirmed=False]
    |   기존 동작 유지:
    |   1. data/drafts/ 디렉토리에 .md 파일 저장
    |   2. SendResult(success=True, draft_path=path)
    |
    +--[confirmed=True]
        |
        +--[self._client is None]
        |   SendResult(success=False, error="SlackAdapter not connected")
        |
        +--[self._client exists]
            1. await asyncio.to_thread(
                   self._client.send_message,
                   channel=message.to,
                   text=message.text,
                   thread_ts=message.reply_to,
               )
            2. lib.slack.SendResult → gateway SendResult 변환
            3. SendResult(success=True, message_id=ts, sent_at=now)
```

핵심 설계 결정:
- `lib.slack.SlackClient.send_message()`는 동기 함수이므로 `asyncio.to_thread()`로 호출
- `lib.slack.SendResult`(ok, ts, channel)와 `gateway.base.SendResult`(success, message_id, error, sent_at, draft_path)는 다른 클래스 — 변환 필요

### 3.2 GmailAdapter.send()

```
send(message: OutboundMessage) -> SendResult
    |
    +--[confirmed=False]
    |   기존 동작 유지:
    |   1. data/drafts/ 디렉토리에 .md 파일 저장
    |   2. SendResult(success=True, draft_path=path)
    |
    +--[confirmed=True]
        |
        +--[self._client is None]
        |   SendResult(success=False, error="GmailAdapter not connected")
        |
        +--[self._client exists]
            Gmail Draft 생성 (전송이 아님):
            1. MIMEText로 메시지 구성
            2. base64 인코딩
            3. self._client.service.users().drafts().create() API 호출
            4. SendResult(success=True, message_id=draft_id, sent_at=now)
```

핵심 설계 결정:
- `lib.gmail.GmailClient`에는 `create_draft()` 메서드가 존재하지 않음
- `self._client.service`를 직접 접근하여 `users().drafts().create()` API 호출
- Gmail은 `confirmed=True`여도 직접 전송하지 않고 Gmail Draft로 생성 (이메일은 되돌리기 어려우므로 추가 안전장치)

---

## 4. CLI `drafts send` 설계

### 4.1 커맨드 인터페이스

```
python scripts/intelligence/cli.py drafts send <id> [--dry-run] [--force]
python scripts/intelligence/cli.py drafts log [--limit N] [--json]
```

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `<id>` | 필수 | Draft ID |
| `--dry-run` | False | 전송하지 않고 내용만 표시 |
| `--force` | False | 확인 프롬프트 생략 |

### 4.2 워크플로우

```
cmd_drafts_send(args)
    |
    1. storage.get_draft(id)
    |   +--[None]--> "초안을 찾을 수 없습니다" 출력, exit
    |
    2. draft["status"] 검증
    |   +--["approved" 아님]--> "approved 상태만 전송 가능 (현재: {status})" 출력, exit
    |
    3. --dry-run 체크
    |   +--[True]--> 전송 정보 표시, exit
    |
    4. --force 체크
    |   +--[False]--> 확인 프롬프트
    |       +--[N]--> "전송 취소" 출력, exit
    |
    5. 어댑터 생성 및 연결
    |   channel_type = _resolve_channel_type(draft["source_channel"])
    |   adapter = _create_adapter(channel_type)
    |   connected = await adapter.connect()
    |   +--[False]--> DB send_failed 기록, exit
    |
    6. OutboundMessage 생성 (confirmed=True)
    |
    7. adapter.send(outbound)
    |   +--[success]--> DB status="sent", JSONL 로그
    |   +--[failure]--> DB status="send_failed", JSONL 로그
    |
    8. adapter.disconnect()
```

### 4.3 채널 타입 해석

```python
def _resolve_channel_type(source_channel: str) -> ChannelType:
    mapping = {
        "slack": ChannelType.SLACK,
        "email": ChannelType.EMAIL,
        "gmail": ChannelType.EMAIL,
        "telegram": ChannelType.TELEGRAM,
    }
    return mapping.get(source_channel.lower(), ChannelType.UNKNOWN)
```

---

## 5. DB 스키마 변경

### 5.1 Plan 문서 모순 해결

Plan MN-5는 "스키마 변경 없음"을 명시하지만 Task 4는 컬럼 추가를 요구한다.
설계 결정: **컬럼을 추가한다.** `reviewer_note` 재사용은 리뷰 워크플로우 의미를 훼손.

### 5.2 ALTER TABLE 마이그레이션

```python
async def _migrate_draft_columns(self):
    """draft_responses에 전송 관련 컬럼 추가 (멱등)"""
    migrations = [
        ("sent_at", "ALTER TABLE draft_responses ADD COLUMN sent_at DATETIME"),
        ("send_error", "ALTER TABLE draft_responses ADD COLUMN send_error TEXT"),
    ]
    for col_name, sql in migrations:
        try:
            await self._connection.execute(sql)
            await self._connection.commit()
        except Exception as e:
            if "duplicate column" in str(e).lower():
                pass
            else:
                raise
```

### 5.3 새 메서드

```python
async def update_draft_sent(self, draft_id: int, message_id: Optional[str] = None) -> bool:
    """전송 성공 기록: status='sent', sent_at=now"""

async def update_draft_send_failed(self, draft_id: int, error_message: str) -> bool:
    """전송 실패 기록: status='send_failed', send_error=message"""
```

### 5.4 상태 전이 다이어그램

```
pending → approved (drafts approve)
pending → rejected (drafts reject)
approved → sent (drafts send 성공)
approved → send_failed (drafts send 실패)
send_failed → sent (drafts send 재시도 성공)
send_failed → send_failed (drafts send 재시도 실패)
```

---

## 6. SendLogger 설계

**파일**: `scripts/intelligence/send_log.py` (신규)

### JSONL 레코드 형식

```json
{
  "timestamp": "2026-02-12T14:30:05.123456",
  "draft_id": 42,
  "channel": "slack",
  "recipient": "U1234567",
  "status": "sent",
  "message_id": "1234567890.123456",
  "error": null,
  "operator": "cli"
}
```

- JSONL append-only (로그 로테이션은 범위 외)
- 파일 위치: `data/send_log.jsonl`

---

## 7. 안전장치 검증 매트릭스

| 전송 경로 | L1: 설정 | L2: 어댑터 | L3: DB | L4: CLI | L5: 로그 |
|-----------|----------|-----------|-------|---------|---------|
| Pipeline Stage 5 | auto_send_disabled | 전송 호출 없음 | - | - | - |
| Intelligence draft | auto_send_disabled | draft만 | pending | approve 필요 | - |
| `drafts send` | - | confirmed 분기 | approved 검증 | 확인 프롬프트 | JSONL |
| `drafts send --force` | - | confirmed 분기 | approved 검증 | 생략 | JSONL |
| `drafts send --dry-run` | - | 호출 안 됨 | 읽기만 | 표시만 | - |

### MN 준수 검증

| ID | 요구사항 | 보장 방식 |
|----|---------|-----------|
| MN-1 | Stage 5 자동 전송 없음 | ActionDispatcher는 TODO/Calendar만, send() 호출 없음 |
| MN-2 | approve 시 자동 전송 없음 | cmd_drafts_approve()는 DB update만 |
| MN-3 | Calendar 자동 생성 없음 | --confirm 없이 호출 = dry-run |
| MN-4 | question 자동 처리 없음 | ActionDispatcher가 question skip |

---

## 8. 파일 변경 목록

### 신규 파일

| 파일 | 목적 | LOC |
|------|------|-----|
| `scripts/gateway/action_dispatcher.py` | ActionDispatcher | ~150 |
| `scripts/intelligence/send_log.py` | SendLogger JSONL | ~60 |
| `tests/test_action_dispatcher.py` | ActionDispatcher 테스트 | ~120 |
| `tests/test_drafts_send.py` | drafts send 테스트 | ~150 |

### 수정 파일

| 파일 | 수정 범위 | 변경 |
|------|----------|------|
| `scripts/gateway/pipeline.py` | `__init__` + `_dispatch_actions()` | ~15줄 |
| `scripts/actions/todo_generator.py` | `append_todo_from_message()` 추가 | ~50줄 |
| `scripts/gateway/adapters/slack.py` | `send()` confirmed 분기 | ~25줄 |
| `scripts/gateway/adapters/gmail.py` | `send()` + `_create_gmail_draft()` | ~40줄 |
| `scripts/intelligence/cli.py` | `drafts send`, `drafts log` | ~100줄 |
| `scripts/intelligence/context_store.py` | 마이그레이션 + 새 메서드 | ~40줄 |

### Import 의존성 추가

| 파일 | 새 import |
|------|----------|
| pipeline.py | action_dispatcher.ActionDispatcher |
| action_dispatcher.py | actions.todo_generator.append_todo_from_message |
| cli.py | gateway.adapters, gateway.models, intelligence.send_log |

모든 import는 3중 fallback 패턴을 준수한다.
