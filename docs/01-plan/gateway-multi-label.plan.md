# Gateway Multi-Label Gmail Scan + Slack Interactive Channel Registration

**Version**: 1.0.0
**Created**: 2026-02-12
**Status**: DRAFT
**Complexity**: 3/5
**Related PRD**: N/A

---

## 1. Overview

### 1.1 Original Request

Secretary Gateway 서버의 두 가지 기능 개선:
1. GmailAdapter가 INBOX 라벨만 감시하는 제한을 제거하여 전체 라벨 스캔으로 확장
2. SlackAdapter의 빈 채널 배열 처리를 자동 수집에서 대화형 선택으로 변경

### 1.2 Complexity Score: 3/5

| 기준 | 점수 | 근거 |
|------|:----:|------|
| **파일 수** | 2/5 | 4개 파일 수정 (gmail.py, slack.py, server.py, gateway.json) |
| **로직 복잡도** | 3/5 | Gmail은 단순 파라미터 제거, Slack은 대화형 UI + 설정 파일 쓰기 로직 추가 |
| **위험도** | 3/5 | Gmail 전체 스캔 시 SPAM/TRASH 노출 위험, Slack 대화형 입력의 예외 처리 |
| **테스트 범위** | 3/5 | Gmail History API mock, Slack input() mock, gateway.json 쓰기 검증 |
| **의존성** | 2/5 | lib.gmail, lib.slack 기존 API만 사용, 새 의존성 없음 |

---

## 2. Scope

### 2.1 Must Have

| ID | 항목 | 설명 |
|----|------|------|
| M1 | Gmail 전체 라벨 스캔 | History API의 `label_id` 파라미터를 `None`으로 전달 |
| M2 | Gmail fallback 전체 스캔 | `list_emails` 호출 시 `label_ids=None`으로 변경 |
| M3 | SPAM/TRASH 필터링 | History API 결과에서 SPAM/TRASH 라벨 포함 메시지 제외 |
| M4 | Slack 대화형 채널 선택 | 서버 시작 시 `channels: []`이면 `input()`으로 대화형 질문 |
| M5 | 선택 결과 gateway.json 저장 | 사용자가 선택한 채널 ID 목록을 설정 파일에 영구 저장 |
| M6 | 세션 재질문 방지 | 한번 선택하면 해당 세션에서 재질문하지 않음 |

### 2.2 Must NOT Have

| ID | 항목 | 이유 |
|----|------|------|
| X1 | Gmail 라벨별 필터링 UI | 이번 scope 밖, 전체 스캔이 목표 |
| X2 | Slack WebSocket 전환 | 기존 polling 방식 유지 |
| X3 | gateway.json 스키마 변경 | 기존 필드 구조 최대한 유지 |
| X4 | Slack 채널 자동 join | bot이 이미 멤버인 채널만 대상 |

---

## 3. Affected Files

### 3.1 수정 대상

| 파일 | 변경 내용 | 영향도 |
|------|----------|--------|
| `C:\claude\secretary\scripts\gateway\adapters\gmail.py` | `_poll_new_messages()`: label_id 파라미터 제거, SPAM/TRASH 필터 추가. `_fallback_poll()`: label_ids 필터 제거, `include_spam_trash=False` 명시 | HIGH |
| `C:\claude\secretary\scripts\gateway\adapters\slack.py` | `connect()`: 빈 채널 시 대화형 선택 로직 추가 | HIGH |
| `C:\claude\secretary\scripts\gateway\server.py` | `_connect_adapters()` 또는 `cmd_start()`: Slack 대화형 선택을 어댑터 connect 전 동기 처리 | MEDIUM |
| `C:\claude\secretary\config\gateway.json` | `gmail.label_filter` 필드 제거 또는 deprecated 처리 | LOW |

### 3.2 참조 파일 (수정 없음)

| 파일 | 참조 이유 |
|------|----------|
| `C:\claude\lib\gmail\client.py` | `list_history(label_id=None)`, `list_emails(label_ids=None, include_spam_trash=False)` API 시그니처 확인 |
| `C:\claude\lib\slack\client.py` | `list_channels(include_private=True)` API 시그니처 확인 |
| `C:\claude\lib\slack\models.py` | `SlackChannel` 모델: id, name, is_member, topic, is_private 필드 확인 |
| `C:\claude\secretary\scripts\gateway\adapters\base.py` | `ChannelAdapter` 인터페이스 확인 |

---

## 4. Implementation Details

### 4.1 Feature 1: Gmail 전체 라벨 스캔

#### 4.1.1 `_poll_new_messages()` 변경

**Before** (line 155-160):
```python
history = await asyncio.to_thread(
    self._client.list_history,
    self._last_history_id,
    ["messageAdded"],
    self._label_filter,      # "INBOX"
)
```

**After**:
```python
history = await asyncio.to_thread(
    self._client.list_history,
    self._last_history_id,
    ["messageAdded"],
    None,                     # 전체 라벨 스캔
)
```

추가로, History API 결과에서 SPAM/TRASH 라벨 포함 메시지를 필터링해야 합니다:

```python
EXCLUDED_LABELS = {"SPAM", "TRASH"}

for record in history_records:
    for msg_added in record.get("messagesAdded", []):
        msg = msg_added.get("message", {})
        msg_id = msg.get("id")
        label_ids = set(msg.get("labelIds", []))

        # SPAM/TRASH 라벨 포함 메시지 제외
        if label_ids & EXCLUDED_LABELS:
            continue

        if msg_id and msg_id not in self._seen_ids:
            message_ids.add(msg_id)
```

**참고**: History API의 `messagesAdded[].message`에는 `labelIds` 필드가 포함됩니다. 이 필드가 없는 경우를 대비하여 빈 리스트를 기본값으로 사용합니다.

#### 4.1.2 `_fallback_poll()` 변경

**Before** (line 217-220):
```python
emails = await asyncio.to_thread(
    self._client.list_emails,
    "is:unread",
    5,
    [self._label_filter],     # ["INBOX"]
)
```

**After**:
```python
emails = await asyncio.to_thread(
    self._client.list_emails,
    "is:unread",
    5,
    None,                     # 전체 라벨 스캔
    False,                    # include_spam_trash=False (명시적)
)
```

`lib.gmail.GmailClient.list_emails`는 `include_spam_trash=False`가 기본값이므로, `label_ids=None` + `include_spam_trash=False` 조합으로 SPAM/TRASH를 자동 제외합니다.

#### 4.1.3 `channel_id` 정규화

현재 `NormalizedMessage`의 `channel_id`가 하드코딩된 `"inbox"`입니다. 전체 라벨 스캔 시 실제 라벨 정보를 반영하도록 변경합니다.

**Before**:
```python
channel_id="inbox",
```

**After** (History API 경로):
```python
# msg_added["message"]["labelIds"]에서 주요 라벨 추출
label_ids = msg_added.get("message", {}).get("labelIds", [])
primary_label = next(
    (l for l in label_ids if l not in ("UNREAD", "IMPORTANT", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_UPDATES", "CATEGORY_PROMOTIONS", "CATEGORY_FORUMS")),
    "unknown"
).lower()

# ...
channel_id=primary_label,
```

**After** (fallback 경로):
```python
# email 객체에서 라벨 정보가 없으므로 "all"로 표시
channel_id="all",
```

#### 4.1.4 `__init__` 및 설정 변경

- `self._label_filter` 필드를 제거하거나 무시 처리
- `gateway.json`의 `gmail.label_filter` 필드는 하위 호환을 위해 유지하되 사용하지 않음
- 향후 deprecated 경고 로그 출력 가능

### 4.2 Feature 2: Slack 대화형 채널 등록

#### 4.2.1 대화형 선택 함수

`server.py`에 동기 함수를 추가합니다 (서버 시작 전 실행):

```python
def interactive_slack_channel_select(config_path: Path) -> list[str]:
    """
    Slack 채널을 대화형으로 선택합니다.

    Returns:
        선택된 채널 ID 리스트
    """
    from lib.slack import SlackClient

    client = SlackClient()
    if not client.validate_token():
        print("[Slack] 토큰 검증 실패. 'python -m lib.slack login'을 실행하세요.")
        return []

    channels = client.list_channels(include_private=True)
    member_channels = [ch for ch in channels if ch.is_member]

    if not member_channels:
        print("[Slack] bot이 참여한 채널이 없습니다.")
        return []

    print("\n=== Slack 채널 선택 ===")
    print("bot이 참여한 채널 목록:\n")

    for i, ch in enumerate(member_channels, 1):
        private_tag = " [비공개]" if ch.is_private else ""
        topic_tag = f" - {ch.topic}" if ch.topic else ""
        print(f"  {i:3d}. #{ch.name}{private_tag}{topic_tag}")

    print(f"\n  0. 전체 선택 ({len(member_channels)}개)")
    print()

    while True:
        raw = input("감시할 채널 번호를 입력하세요 (쉼표 구분, 0=전체): ").strip()
        if not raw:
            continue

        if raw == "0":
            selected = member_channels
            break

        try:
            indices = [int(x.strip()) for x in raw.split(",")]
            selected = []
            for idx in indices:
                if 1 <= idx <= len(member_channels):
                    selected.append(member_channels[idx - 1])
                else:
                    print(f"  잘못된 번호: {idx}")
                    continue
            if selected:
                break
            print("  최소 1개 채널을 선택하세요.")
        except ValueError:
            print("  숫자만 입력하세요. (예: 1,3,5)")

    selected_ids = [ch.id for ch in selected]
    selected_names = [f"#{ch.name}" for ch in selected]
    print(f"\n선택됨: {', '.join(selected_names)}")

    # gateway.json에 저장
    _save_slack_channels(config_path, selected_ids)

    return selected_ids
```

#### 4.2.2 gateway.json 저장 함수

```python
def _save_slack_channels(config_path: Path, channel_ids: list[str]) -> None:
    """선택된 Slack 채널을 gateway.json에 저장"""
    config = load_config(config_path)
    config.setdefault("channels", {}).setdefault("slack", {})["channels"] = channel_ids

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"[Slack] {len(channel_ids)}개 채널이 gateway.json에 저장됨")
```

#### 4.2.3 서버 시작 흐름 변경

`cmd_start()` 또는 `SecretaryGateway.start()` 내에서 어댑터 연결 전에 대화형 선택을 실행합니다.

**위치**: `cmd_start()` 함수, `gateway.start()` 호출 전

```python
async def cmd_start(args):
    config_path = Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    config = load_config(config_path)

    # Slack 대화형 채널 선택 (서버 시작 전, 동기 처리)
    slack_config = config.get("channels", {}).get("slack", {})
    if slack_config.get("enabled", False) and not slack_config.get("channels"):
        selected = interactive_slack_channel_select(config_path)
        if selected:
            # 메모리 config에도 반영
            config["channels"]["slack"]["channels"] = selected

    gateway = SecretaryGateway(config_path)
    # ... (기존 로직)
```

#### 4.2.4 SlackAdapter 변경

`connect()` 메서드에서 빈 채널 시 자동 수집하는 기존 로직을 제거합니다.

**Before** (line 62-66):
```python
if not self._channels:
    channels = await asyncio.to_thread(
        self._client.list_channels, True
    )
    self._channels = [ch.id for ch in channels if ch.is_member]
```

**After**:
```python
if not self._channels:
    print("[SlackAdapter] 감시 채널이 설정되지 않았습니다.")
    print("[SlackAdapter] 'python server.py start'로 재시작하여 채널을 선택하세요.")
    self._connected = False
    return False
```

---

## 5. Task Breakdown

### Task 1: Gmail 전체 라벨 스캔 (executor, sonnet)

**파일**: `C:\claude\secretary\scripts\gateway\adapters\gmail.py`

| Step | 작업 | Acceptance Criteria |
|:----:|------|---------------------|
| 1-1 | `EXCLUDED_LABELS = {"SPAM", "TRASH"}` 클래스 상수 추가 | 상수 정의 확인 |
| 1-2 | `__init__`에서 `self._label_filter` 사용 중단 (제거 또는 무시) | `label_filter` 설정을 읽지 않음 |
| 1-3 | `_poll_new_messages()`: `list_history` 호출 시 3번째 인자를 `None`으로 변경 | History API가 전체 라벨 대상으로 호출됨 |
| 1-4 | `_poll_new_messages()`: history 결과에서 SPAM/TRASH labelIds 포함 메시지 필터링 | SPAM/TRASH 메시지가 normalized 결과에 포함되지 않음 |
| 1-5 | `_poll_new_messages()`: `channel_id` 값을 실제 라벨 기반으로 설정 | `channel_id`가 "inbox" 하드코딩이 아닌 실제 라벨 반영 |
| 1-6 | `_fallback_poll()`: `list_emails` 호출 시 `label_ids=None`, `include_spam_trash=False` | fallback도 전체 라벨 대상, SPAM/TRASH 제외 |
| 1-7 | `_fallback_poll()`: `channel_id`를 `"all"`로 변경 | fallback 경로 정상 동작 |

**blockedBy**: 없음

### Task 2: Slack 대화형 채널 등록 (executor, sonnet)

**파일**: `C:\claude\secretary\scripts\gateway\server.py`, `C:\claude\secretary\scripts\gateway\adapters\slack.py`

| Step | 작업 | Acceptance Criteria |
|:----:|------|---------------------|
| 2-1 | `server.py`에 `interactive_slack_channel_select()` 함수 추가 | 함수가 채널 목록 표시 + 사용자 입력 처리 |
| 2-2 | `server.py`에 `_save_slack_channels()` 함수 추가 | gateway.json에 선택 결과 저장, 기존 설정 보존 |
| 2-3 | `cmd_start()`에 대화형 선택 호출 로직 추가 | Slack enabled + channels 비어있을 때만 실행 |
| 2-4 | `slack.py`의 `connect()`에서 자동 수집 로직 제거 | 빈 채널 시 경고 출력 후 `return False` |
| 2-5 | 전체 선택(0) 및 부분 선택 모두 테스트 | 두 경로 모두 정상 동작 |

**blockedBy**: 없음

### Task 3: gateway.json 설정 정리 (executor-low, haiku)

**파일**: `C:\claude\secretary\config\gateway.json`

| Step | 작업 | Acceptance Criteria |
|:----:|------|---------------------|
| 3-1 | `gmail.label_filter` 필드에 대한 처리 결정 | 필드 유지 (하위 호환) 또는 제거 중 택 1 |

**blockedBy**: Task 1

### Task 4: 검증 (architect, opus)

| Step | 작업 | Acceptance Criteria |
|:----:|------|---------------------|
| 4-1 | Gmail: History API `label_id=None` 호출 시 전체 변경 이력 반환 확인 | INBOX 외 라벨 메시지도 감지 |
| 4-2 | Gmail: SPAM/TRASH 메시지가 파이프라인에 도달하지 않음 확인 | 필터링 로직 검증 |
| 4-3 | Slack: 대화형 선택 흐름 정상 동작 확인 | 번호 입력 → 채널 선택 → JSON 저장 |
| 4-4 | Slack: 저장 후 서버 재시작 시 재질문 없음 확인 | channels 배열이 비어있지 않으므로 skip |
| 4-5 | gateway.json 기존 설정이 보존되는지 확인 | 다른 필드가 손상되지 않음 |

**blockedBy**: Task 1, Task 2, Task 3

---

## 6. Execution Flow

```
Task 1 (Gmail 전체 라벨 스캔)  ──────┐
                                     ├──▶ Task 3 (설정 정리) ──▶ Task 4 (검증)
Task 2 (Slack 대화형 채널 등록) ─────┘
```

Task 1과 Task 2는 독립적이므로 병렬 실행 가능.

---

## 7. Risk Assessment

| Risk | 확률 | 영향 | 완화 방안 |
|------|:----:|:----:|----------|
| History API `messagesAdded[].message`에 `labelIds` 필드가 없는 경우 | LOW | MEDIUM | 빈 리스트 기본값 사용, 필드 없으면 필터링 skip (포함 허용) |
| 전체 라벨 스캔으로 메시지 volume 급증 | MEDIUM | MEDIUM | `_seen_ids` set으로 중복 방지, 기존 rate limiting 유지 |
| `input()` 호출이 비대화형 환경(daemon, CI)에서 hang | MEDIUM | HIGH | `--no-interactive` 플래그 추가 고려, 또는 stdin이 TTY인지 확인 후 비대화형이면 기존 자동 수집 fallback |
| gateway.json 쓰기 중 충돌 (동시 접근) | LOW | LOW | 서버 시작 전 동기 처리이므로 동시 접근 없음 |
| Slack 토큰 만료로 `list_channels` 실패 | MEDIUM | LOW | 예외 처리 후 안내 메시지 출력, 수동 설정 안내 |

---

## 8. Commit Strategy

| 순서 | Commit Message | 포함 파일 |
|:----:|----------------|----------|
| 1 | `feat(gateway): scan all Gmail labels instead of INBOX only` | `gmail.py` |
| 2 | `feat(gateway): add interactive Slack channel selection on startup` | `server.py`, `slack.py` |
| 3 | `chore(config): update gateway.json for multi-label support` | `gateway.json` |

---

## 9. Success Criteria

| ID | 기준 | 검증 방법 |
|----|------|----------|
| S1 | Gmail SENT, DRAFTS 등 INBOX 외 라벨의 메시지 변경이 감지됨 | History API 로그 확인 |
| S2 | SPAM/TRASH 라벨 메시지가 파이프라인에 진입하지 않음 | 필터링 로그 확인 |
| S3 | Slack 서버 시작 시 채널 목록이 표시되고 사용자가 선택 가능 | 수동 테스트 |
| S4 | 선택 결과가 gateway.json에 올바르게 저장됨 | JSON 파일 확인 |
| S5 | 재시작 시 이미 저장된 채널이 있으면 대화형 질문 없이 바로 시작 | 수동 테스트 |
| S6 | 기존 gateway.json의 다른 설정이 손상되지 않음 | JSON diff 확인 |
