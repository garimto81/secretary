# Gateway Multi-Label Gmail Scan + Slack Interactive Channel Registration - Design

**Version**: 1.0.0
**Created**: 2026-02-12
**Status**: DRAFT
**Plan Reference**: `C:\claude\secretary\docs\01-plan\gateway-multi-label.plan.md`

---

## 1. Overview

| Feature | 요약 |
|---------|------|
| **F1** | GmailAdapter의 INBOX 단일 라벨 제한을 제거하고 전체 라벨을 스캔하되, SPAM/TRASH를 필터링 |
| **F2** | SlackAdapter의 빈 채널 자동 수집을 제거하고, 서버 시작 시 대화형 채널 선택 UI 제공 |

---

## 2. Feature 1: Gmail 전체 라벨 스캔

### 2.1 클래스 상수

```python
EXCLUDED_LABELS: set[str] = {"SPAM", "TRASH"}
SYSTEM_LABELS: set[str] = {
    "UNREAD", "IMPORTANT", "STARRED",
    "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_UPDATES",
    "CATEGORY_PROMOTIONS", "CATEGORY_FORUMS",
}
```

### 2.2 변경 요약

| 위치 | Before | After |
|------|--------|-------|
| `__init__` | `self._label_filter = config.get("label_filter", "INBOX")` | 필드 제거, deprecated 경고 |
| `_poll_new_messages` | `list_history(..., self._label_filter)` | `list_history(..., None)` + SPAM/TRASH 필터 |
| `_fallback_poll` | `list_emails("is:unread", 5, [self._label_filter])` | `list_emails("is:unread", 5, None, False)` |
| `channel_id` | `"inbox"` 하드코딩 | `_extract_primary_label()` 또는 `"all"` |

### 2.3 `_extract_primary_label()` 신규 메서드

사용자 정의 라벨 > INBOX/SENT/DRAFT > unknown 우선순위로 channel_id 결정.

### 2.4 데이터 흐름

```
History API 경로                    Fallback 경로
list_history(..., None)             list_emails("is:unread", 5, None, False)
      │                                   │
      ▼                                   │
SPAM/TRASH 필터 (어댑터)            Gmail API 자동 제외
      │                                   │
      ▼                                   ▼
_extract_primary_label()            channel_id = "all"
      │                                   │
      └───────────┬───────────────────────┘
                  ▼
          NormalizedMessage → Pipeline
```

### 2.5 에러 처리

- `labelIds` 필드 없음 → 빈 set, 필터 skip
- History 404 → 기존 fallback 호출
- Volume 급증 → `_seen_ids` 중복 방지

---

## 3. Feature 2: Slack 대화형 채널 등록

### 3.1 함수 시그니처

```python
def interactive_slack_channel_select(config_path: Path) -> list[str]:
    """대화형 채널 선택. 결과를 gateway.json에 저장."""

def _save_slack_channels(config_path: Path, channel_ids: list[str]) -> None:
    """선택된 채널 ID를 gateway.json에 영구 저장."""
```

### 3.2 `cmd_start()` 흐름

```
cmd_start()
  │
  ├─ load_config()
  ├─ slack.enabled && !slack.channels?
  │   ├─ isatty() → interactive_slack_channel_select()
  │   └─ !isatty() → 경고 출력
  ├─ SecretaryGateway(config_path)
  ├─ gateway.config에 변경분 반영
  └─ gateway.start()
```

### 3.3 SlackAdapter.connect() 변경

빈 채널 시 자동 수집 제거 → 경고 후 `return False`.

### 3.4 에러 처리

- 토큰 실패 → 안내 메시지, 빈 리스트
- EOF/KeyboardInterrupt → 안전 종료, 빈 리스트
- 비대화형 환경 → `isatty()` 체크 후 skip
- 전체를 try/except 감싸 서버 시작 보장

---

## 4. gateway.json 변경

`gmail.label_filter` 필드 제거 (deprecated).

---

## 5. 파일별 변경 요약

| 파일 | 변경 |
|------|------|
| `adapters/gmail.py` | 상수 추가, `__init__` 수정, `_poll_new_messages` 수정, `_extract_primary_label` 신규, `_fallback_poll` 수정 |
| `server.py` | `interactive_slack_channel_select()` 신규, `_save_slack_channels()` 신규, `cmd_start()` 수정 |
| `adapters/slack.py` | `connect()` 수정 (자동 수집 제거) |
| `config/gateway.json` | `label_filter` 제거 |

---

## 변경 이력

| 버전 | 날짜 | 변경 |
|------|------|------|
| 1.0.0 | 2026-02-12 | 초안 |
