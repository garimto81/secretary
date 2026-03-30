# PRD: 최초 채널 수집 시 전체 메시지/파일 수집

## 배경/목적

현재 `SlackTracker._fetch_channel()`은 최초 실행 시에도 500건 제한이 적용되어 채널 전체 히스토리를 수집하지 못합니다.
`GmailTracker._fetch_via_list()`는 최초 실행 시 7일 날짜 필터 + 20건 제한으로 전체 메일을 수집하지 못합니다.
또한 Slack 메시지에 첨부된 파일 정보도 수집되지 않습니다.

## 요구사항

1. **SlackTracker 최초 수집 무제한**: `last_ts is None`일 때(채널 첫 수집) max_messages 캡 제거, cursor 기반 전체 페이지네이션
2. **GmailTracker 최초 수집 무제한**: `history_id is None`일 때 날짜 필터 제거, 500건으로 limit 상향
3. **Slack 파일 수집**: 메시지의 `files` 필드에서 파일 메타데이터(이름, 타입, URL, 제목) 추출하여 별도 context entry로 저장
4. **증분 수집은 기존 동작 유지**: `last_ts`가 존재하면 500건 캡, Gmail은 날짜 필터 유지

## 기능 범위

### 변경 파일
- `scripts/intelligence/incremental/trackers/slack_tracker.py`
  - `_fetch_channel()`: `is_initial = last_ts is None` 감지
  - 초기 수집 시: while True 무한 페이지네이션 (max_messages 캡 없음), next_cursor 기반
  - 초기 수집 시: 메시지 내 files 필드도 수집하여 저장
- `scripts/intelligence/incremental/trackers/gmail_tracker.py`
  - `fetch_new()`: initial 파라미터 추가
  - `_fetch_via_list()`: initial=True 시 날짜 필터 제거, limit=500

### 새 파일
- `tests/intelligence/test_incremental_trackers.py`
  - SlackTracker 최초 수집 시 무제한 페이지네이션 테스트
  - GmailTracker 최초 수집 시 날짜 필터 없는 테스트

## 비기능 요구사항
- Rate limiting: 페이지간 1초 대기 (Slack API rate limit 준수)
- 에러 처리: 각 페이지 실패 시 중단하지 않고 다음 페이지 시도
- 중복 방지: 기존 `save_context_entry` upsert 로직 그대로 사용

## 제약사항
- `lib.slack.SlackClient.get_history()` 시그니처 변경 없음 (cursor 파라미터 추가 필요 시 확인 필요)
- `lib.gmail.GmailClient.list_emails()` limit 파라미터 지원 가정

## 우선순위
1. SlackTracker 최초 수집 무제한 (P0 - 핵심 기능)
2. GmailTracker 최초 수집 무제한 (P0)
3. Slack 파일 수집 (P1)

## Changelog
- 2026-02-19: 최초 작성
