# Plan: 최초 채널 수집 시 전체 메시지/파일 수집 (initial-full-collection)

## 배경 (Background)

- **요청**: `last_ts is None`(Slack 최초 수집) 및 `history_id is None`(Gmail 최초 수집) 조건에서 제한 없이 전체 히스토리를 수집해야 한다.
- **해결 대상**:
  1. `SlackTracker._fetch_channel()`: 최초 수집 시에도 500건 캡이 적용되고, `oldest=messages[-1].ts` 방식으로 인해 같은 메시지가 반복 조회된 후 캡 도달로 종료됨.
  2. `GmailTracker._fetch_via_list()`: 최초 수집 시에도 `after:{7일전}` 날짜 필터 + 20건 제한이 그대로 적용됨.
  3. `SlackMessage` 모델에 `files` 필드 없음 → 첨부 파일 메타데이터가 유실됨.
- **현재 버그 재현 경로**:

```
  SlackTracker._fetch_channel()
    last_ts = None  (채널 최초 수집)
    while len(all_messages) < 500:
      messages = get_history(channel, 100, oldest=None)   # 첫 100건 조회
      all_messages.extend(messages)                       # 100건 추가
      current_last_ts = messages[-1].ts                  # ← 가장 오래된 ts 저장
      # oldest=가장_오래된_ts 로 재조회 → 동일 메시지 재수집 반복
    # 500건 캡 도달 → 종료 (전체 히스토리 미수집)
```

```
  GmailTracker._fetch_via_list()
    query = f"after:{7일전_epoch} {원본_쿼리}"   # 날짜 필터 강제 적용
    emails = list_emails(query, limit=20)         # 20건 제한 고정
    # 최초 수집이어도 최근 7일 20건만 반환
```

---

## 구현 범위 (Scope)

### 포함 항목

- `lib.slack.models.SlackMessage`에 `files` 필드 추가
- `lib.slack.SlackClient`에 `get_history_with_cursor()` 메서드 추가 (기존 `get_history()` 변경 없음)
- `SlackTracker._fetch_channel()` 최초 수집 경로 재작성 (cursor 기반 무제한 페이지네이션 + 파일 수집)
- `GmailTracker._fetch_via_list()` 최초 수집 시 날짜 필터 제거 + limit 500 상향
- 단위 테스트 파일 신규 작성 (`tests/intelligence/test_incremental_trackers.py`)

### 제외 항목

- Slack 증분 수집(`last_ts is not None`) 로직 — 기존 동작 그대로 유지
- Gmail History API 경로(`_fetch_via_history`) — 변경 없음
- `get_replies()` 스레드 수집 로직 — 변경 없음
- 파일 다운로드/콘텐츠 저장 — 메타데이터(이름, 타입, URL, 제목)만 저장

---

## 영향 파일 (Affected Files)

### 수정 파일

| 파일 | 수정 유형 |
|------|----------|
| `C:\claude\lib\slack\models.py` (line 55-71) | `SlackMessage`에 `files` 필드 추가 |
| `C:\claude\lib\slack\client.py` (line 225-271 이후) | `get_history_with_cursor()` 메서드 추가 |
| `C:\claude\secretary\scripts\intelligence\incremental\trackers\slack_tracker.py` (line 51-157) | `_fetch_channel()` 초기 수집 경로 분기, `_save_file_entry()` 추가 |
| `C:\claude\secretary\scripts\intelligence\incremental\trackers\gmail_tracker.py` (line 99-123) | `_fetch_via_list()` `initial` 파라미터 추가 |

### 신규 파일

| 파일 | 목적 |
|------|------|
| `C:\claude\secretary\tests\intelligence\test_incremental_trackers.py` | SlackTracker / GmailTracker 최초 수집 단위 테스트 |

---

## 위험 요소 (Risks)

| 위험 | 가능성 | 영향 | 완화 방법 |
|------|:------:|:----:|----------|
| 채널 히스토리가 수만 건인 경우 초기 수집 시간 과도 | 높음 | 중 | 페이지간 1초 rate limit 대기 유지; 채널당 시간 제한은 Slack API rate limit으로 자동 조절됨 |
| `get_history_with_cursor()`가 `files` 미포함 메시지를 처리할 때 KeyError | 낮음 | 높음 | `msg.get("files", [])` 방어 코드 적용 |
| `_fetch_via_list(initial=True)`에서 Gmail 쿼리가 빈 문자열인 경우 전체 수신함 조회 | 중간 | 중 | `queries`가 비어 있으면 `"is:inbox"` 유지 (기존 로직과 동일) |
| `GmailClient.list_emails(limit=500)` 파라미터 미지원 | 낮음 | 높음 | 실제 `list_emails()` 시그니처 확인 후 executor가 구현 시 검증 필요 |

### Edge Cases

1. **Slack `next_cursor`가 영구 순환하는 경우**: Slack API가 동일 cursor를 반복 반환하는 버그가 알려져 있음. `seen_cursors: set` 로 중복 cursor 감지 후 루프 종료 처리 필요.
2. **파일이 있는 메시지가 thread_ts를 가지는 경우**: `_save_file_entry()` 내 `metadata`에 `thread_ts` 포함하여 파일의 대화 맥락 보존.

---

## 태스크 목록 (Tasks)

### Task 1: `SlackMessage`에 `files` 필드 추가

**파일**: `C:\claude\lib\slack\models.py`
**위치**: `SlackMessage` 클래스 (line 55-71)

**수정 내용**:
```python
# 기존 SlackMessage (line 55-70)
class SlackMessage(BaseModel):
    ts: str
    text: str
    channel: str
    user: Optional[str] = None
    thread_ts: Optional[str] = None
    timestamp: Optional[datetime] = None

# 변경 후
class SlackMessage(BaseModel):
    ts: str
    text: str
    channel: str
    user: Optional[str] = None
    thread_ts: Optional[str] = None
    timestamp: Optional[datetime] = None
    files: list[dict] = Field(default_factory=list)  # 첨부 파일 메타데이터
```

**Acceptance Criteria**:
- `SlackMessage(ts="1", text="t", channel="C1")` 인스턴스 생성 시 `files == []` 확인
- `SlackMessage(ts="1", text="t", channel="C1", files=[{"name": "f.pdf"}])` 정상 파싱
- 기존 `SlackMessage` 생성 코드(`get_history()` 내부 포함)에서 TypeError 없음

---

### Task 2: `SlackClient.get_history_with_cursor()` 메서드 추가

**파일**: `C:\claude\lib\slack\client.py`
**위치**: `get_history()` 메서드(line 225-271) 다음에 추가

**구현 내용**:
```python
def get_history_with_cursor(
    self,
    channel: str,
    limit: int = 100,
    oldest: str | None = None,
    cursor: str | None = None,
) -> tuple[list[SlackMessage], str | None]:
    """
    cursor 기반 페이지네이션으로 채널 히스토리를 조회합니다.

    Returns:
        (messages, next_cursor) 튜플. 다음 페이지가 없으면 next_cursor=None.
    """
    self._rate_limiter.wait_if_needed("conversations.history")

    try:
        params = {"channel": channel, "limit": limit}
        if oldest is not None:
            params["oldest"] = oldest
        if cursor is not None:
            params["cursor"] = cursor

        response = self._client.conversations_history(**params)

        messages = []
        for msg in response.data.get("messages", []):
            messages.append(SlackMessage(
                ts=msg["ts"],
                text=msg.get("text", ""),
                channel=channel,
                user=msg.get("user"),
                thread_ts=msg.get("thread_ts"),
                timestamp=datetime.fromtimestamp(float(msg["ts"])) if msg.get("ts") else None,
                files=msg.get("files", []),
            ))

        next_cursor = (
            response.data
            .get("response_metadata", {})
            .get("next_cursor") or None
        )

        return messages, next_cursor

    except SlackApiError as e:
        self._handle_error(e)
```

**Acceptance Criteria**:
- `(messages, None)` 반환 시 `next_cursor is None` 확인
- `response_metadata.next_cursor`가 `""` 빈 문자열일 때도 `None` 반환 (falsy 처리)
- 응답 메시지에 `files` 키가 있을 때 `SlackMessage.files`에 매핑됨

---

### Task 3: `SlackTracker._fetch_channel()` 최초 수집 경로 재작성

**파일**: `C:\claude\secretary\scripts\intelligence\incremental\trackers\slack_tracker.py`
**위치**: `_fetch_channel()` 전체 (line 51-157)

**구현 로직**:

```
  _fetch_channel(project_id, channel_id)
    last_ts = get_slack_last_ts(project_id, channel_id)
    is_initial = (last_ts is None)

    if is_initial:
      # 초기 수집: cursor 기반 무제한 페이지네이션
      cursor = None
      seen_cursors = set()
      all_messages = []

      while True:
        (messages, next_cursor) = get_history_with_cursor(channel_id, 100, cursor=cursor)
        all_messages.extend(messages)

        for msg in messages:
          if msg.files:
            for f in msg.files:
              _save_file_entry(project_id, channel_id, msg.ts, f)

        if not next_cursor or next_cursor in seen_cursors:
          break
        seen_cursors.add(next_cursor)
        cursor = next_cursor
        sleep(1.0)   # rate limit

    else:
      # 증분 수집: 기존 로직 유지 (500건 캡)
      all_messages = [기존 while 루프]

    # 저장 + max_ts 갱신 (공통)
```

**`_save_file_entry()` 구현**:
```python
async def _save_file_entry(
    self, project_id: str, channel_id: str, msg_ts: str, file_info: dict
) -> None:
    file_id = file_info.get("id", msg_ts)
    entry_id = hashlib.sha256(
        f"slack:file:{channel_id}:{file_id}".encode()
    ).hexdigest()[:16]

    await self.storage.save_context_entry({
        "id": entry_id,
        "project_id": project_id,
        "source": "slack",
        "source_id": file_id,
        "entry_type": "file",
        "title": file_info.get("title") or file_info.get("name", "(파일)"),
        "content": file_info.get("name", ""),
        "metadata": {
            "channel_id": channel_id,
            "msg_ts": msg_ts,
            "filetype": file_info.get("filetype"),
            "url_private": file_info.get("url_private"),
            "size": file_info.get("size"),
        },
    })
```

**Acceptance Criteria**:
- `last_ts is None`이고 API가 2페이지(cursor 있음 → cursor 없음) 반환할 때 총 200건 수집
- `last_ts is not None`이면 기존 500건 캡 로직 경로 실행 (리그레션 없음)
- 메시지에 `files: [{"id": "F1", "name": "doc.pdf"}]` 포함 시 `entry_type="file"` 항목 저장
- cursor 순환 버그(동일 cursor 재반환) 발생 시 무한 루프 없이 종료

---

### Task 4: `GmailTracker._fetch_via_list()` 최초 수집 분기

**파일**: `C:\claude\secretary\scripts\intelligence\incremental\trackers\gmail_tracker.py`
**위치**: `_fetch_via_list()` (line 99-123), `fetch_new()` (line 29-56)

**수정 내용**:

`fetch_new()` 내 최초 수집 감지:
```python
async def fetch_new(self, project_id: str, gmail_queries: list[str]) -> int:
    ...
    last_history_id = await self.state_manager.get_gmail_history_id(project_id)

    if last_history_id:
        count = await self._fetch_via_history(project_id, last_history_id)
    else:
        # 최초 수집: initial=True 전달
        count = await self._fetch_via_list(project_id, gmail_queries, initial=True)

    return count
```

`_fetch_via_list()` 파라미터 추가:
```python
async def _fetch_via_list(
    self, project_id: str, queries: list[str], initial: bool = False
) -> int:
    query = " OR ".join(queries) if queries else "is:inbox"

    if not initial:
        # 증분 수집: 날짜 필터 + 20건 제한 유지
        seven_days_ago_epoch = int((datetime.now() - timedelta(days=7)).timestamp())
        query = f"after:{seven_days_ago_epoch} {query}"
        limit = 20
    else:
        # 최초 수집: 날짜 필터 없음, 500건
        limit = 500

    emails = await asyncio.to_thread(self._client.list_emails, query, limit)
    ...
```

**Acceptance Criteria**:
- `initial=True` 호출 시 query에 `"after:"` 문자열 미포함 확인
- `initial=True` 호출 시 `list_emails` limit 인자가 `500`임 확인
- `initial=False` (기본값) 호출 시 기존 동작 유지 (`after:{epoch}`, limit=20)
- `fetch_new()` 내에서 `last_history_id is None`일 때 `initial=True`로 호출됨

---

### Task 5: 단위 테스트 작성

**파일**: `C:\claude\secretary\tests\intelligence\test_incremental_trackers.py` (신규)

**테스트 구성**:

```
TestSlackTrackerInitial
  test_initial_fetch_uses_cursor_pagination
    - get_history_with_cursor mock: 2회 호출 (1회: next_cursor="C2", 2회: next_cursor=None)
    - 결과: save_context_entry 200회 호출 (page 1 100건 + page 2 100건)

  test_initial_fetch_saves_file_entries
    - 1회 호출에 messages 1건, files=[{"id":"F1","name":"doc.pdf"}] 포함
    - save_context_entry 2회 호출 (message 1 + file 1)
    - file entry의 entry_type == "file" 확인

  test_initial_fetch_stops_on_cursor_cycle
    - get_history_with_cursor가 항상 동일한 next_cursor="SAME" 반환
    - save_context_entry는 1페이지분만 호출 (무한 루프 없음)

  test_incremental_fetch_uses_existing_logic
    - last_ts = "1700000000.000000" (None 아님)
    - get_history가 호출되고 get_history_with_cursor는 호출되지 않음

TestGmailTrackerInitial
  test_initial_fetch_no_date_filter
    - last_history_id = None
    - list_emails mock 설정
    - list_emails 호출 시 query 인자에 "after:" 미포함 확인

  test_initial_fetch_limit_500
    - list_emails 호출 시 두 번째 인자(limit) == 500 확인

  test_incremental_fetch_has_date_filter
    - _fetch_via_list(initial=False) 호출
    - query에 "after:" 포함 확인, limit == 20 확인
```

**테스트 기반**: `unittest.mock.AsyncMock` + `pytest.mark.asyncio`
기존 `tests/intelligence/conftest.py`의 `mock_storage` fixture 재사용.

**Acceptance Criteria**:
- `pytest tests/intelligence/test_incremental_trackers.py -v` 전체 통과
- 외부 서비스(Slack API, Gmail API) 없이 즉시 실행 가능 (mock 기반)
- 테스트 실행 시간 < 5초

---

## 구현 순서 (Implementation Order)

```
  +-----------------------------------+
  | Task 1: SlackMessage.files 필드  |
  | lib/slack/models.py              |
  +------------------+---------------+
                     |
                     v
  +-----------------------------------+
  | Task 2: get_history_with_cursor() |
  | lib/slack/client.py              |
  | (Task 1 완료 후 files 매핑 가능) |
  +------------------+---------------+
                     |
          +----------+-----------+
          |                      |
          v                      v
  +-----------------+  +-------------------+
  | Task 3:         |  | Task 4:           |
  | slack_tracker   |  | gmail_tracker     |
  | (Task 2 의존)   |  | (독립 수정)       |
  +-----------------+  +-------------------+
          |                      |
          +----------+-----------+
                     |
                     v
  +-----------------------------------+
  | Task 5: 단위 테스트              |
  | test_incremental_trackers.py     |
  +-----------------------------------+
```

- Task 1 → Task 2 (순차, `files` 필드 필요)
- Task 2 → Task 3 (순차, `get_history_with_cursor()` 필요)
- Task 3 ‖ Task 4 (병렬 가능)
- Task 5 (Task 3, 4 완료 후)

---

## 커밋 전략 (Commit Strategy)

```
feat(lib/slack): SlackMessage에 files 필드 추가
feat(lib/slack): get_history_with_cursor() cursor 기반 페이지네이션 메서드 추가
fix(intelligence): SlackTracker 최초 수집 시 무제한 cursor 페이지네이션 및 파일 수집
fix(intelligence): GmailTracker 최초 수집 시 날짜 필터 제거 및 limit 500 상향
test(intelligence): SlackTracker/GmailTracker 최초 수집 단위 테스트 추가
```

---

## 복잡도 판단

- 파일 범위: 5개 파일 (lib 2 + secretary 2 + test 1)
- 아키텍처 변경: 없음 (기존 패턴 내 수정)
- 신규 의존성: 없음
- 증분 수집 리그레션 위험: 중간 (기존 경로 분기 보존)
- **복잡도: MEDIUM**
- **태스크 수: 5개**
