# 구현 완료 보고서: 최초 채널 수집 전체 메시지/파일 수집

**날짜**: 2026-02-19
**PRD**: `docs/00-prd/initial-full-collection.prd.md`

---

## 변경 요약

### 근본 원인

| 구성요소 | 버그 | 영향 |
|----------|------|------|
| `SlackTracker._fetch_channel()` | 최초 수집 시에도 500건 캡 + 페이지네이션 로직 오류 (oldest 파라미터 재사용) | 채널 전체 히스토리 미수집 |
| `GmailTracker._fetch_via_list()` | 최초 수집 시에도 7일 날짜 필터 + 20건 제한 | 전체 Gmail 히스토리 미수집 |
| Slack 파일 | `files` 필드 미처리 | 파일 첨부 내용 Knowledge 반영 불가 |

---

## 구현 내역

### 1. `lib/slack/models.py`
- `SlackMessage`에 `files: list[dict] = Field(default_factory=list)` 추가

### 2. `lib/slack/client.py`
- `get_history_with_cursor(channel, limit, oldest, cursor)` 메서드 추가
  - Slack API `response_metadata.next_cursor` 반환
  - `files` 필드 포함 `SlackMessage` 생성

### 3. `scripts/intelligence/incremental/trackers/slack_tracker.py`
- `_fetch_channel()` 초기/증분 분기:
  - **최초 수집** (`last_ts is None`): cursor 기반 무제한 페이지네이션 + 파일 수집
  - **증분 수집**: 기존 500건 캡 유지
- `_save_file_entries()` 신규 메서드 추가

### 4. `scripts/intelligence/incremental/trackers/gmail_tracker.py`
- `_fetch_via_list(initial=False)` 파라미터 추가
  - `initial=True`: 날짜 필터 제거, limit=500
  - `initial=False`: 7일 필터, limit=20 (기존 동작)
- `fetch_new()`: 최초 수집 감지 → `initial=True` 전달

---

## 테스트 결과

```
tests/intelligence/test_incremental_trackers.py  7/7 PASSED
tests/intelligence/ (전체)                      165/165 PASSED
```

---

## 동작 변화

```
Before:
  채널 첫 수집 → 500건 제한 (중복 수집 버그 포함)
  Gmail 첫 수집 → 최근 7일 20건만

After:
  채널 첫 수집 → 전체 메시지 cursor 페이지네이션
                + 파일 첨부 별도 entry 저장
  Gmail 첫 수집 → 날짜 필터 없이 최대 500건
```
