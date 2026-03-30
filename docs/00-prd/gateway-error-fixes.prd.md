# Gateway 서버 오류 수정 PRD

**문서 버전**: 1.0.0
**작성일**: 2026-02-24
**상태**: Completed

---

## 배경/목적

Gateway 서버 실행 로그에서 3개의 독립적인 오류가 발견되었다.
운영 중 반복적으로 발생하여 Intelligence 초안 생성 실패 및 로그 오염을 초래하고 있었다.

각 오류는 서로 독립적이며, 4개 파일 수정으로 완전 해결 가능하다.

---

## 요구사항 목록

### 1. Gmail 404 오류 — 삭제된 메시지 반복 조회 방지

**파일**: `scripts/gateway/adapters/gmail.py`

**현황**:
- `_poll_new_messages()`에서 historyId 기반으로 메시지 ID를 수신 후 `get_email(msg_id)` 호출
- Gmail에서 이미 삭제된 메시지는 404를 반환하지만 `seen_ids`에 추가되지 않음
- 다음 polling 주기에서 동일 메시지 ID를 재조회하는 무한 반복 발생
- 삭제된 메시지(영구 오류)와 일시적 네트워크 오류가 동일하게 처리되어 구분 불가

**요구사항**:
- 404 또는 `notFound` 응답을 수신한 경우 해당 메시지 ID를 `seen_ids`에 즉시 추가한다
- 404 처리 시 ERROR가 아닌 WARNING 레벨로 로깅한다 (`"메시지 없음(삭제됨) - 건너뜀"`)
- 404 이외의 예외(일시적 네트워크 오류 등)는 `seen_ids`에 추가하지 않아 다음 polling에서 재시도 가능하게 한다
- `logging` 모듈을 import하고 `logger = logging.getLogger(__name__)`를 설정한다

**수락 기준**:
- 삭제된 메시지 ID는 이후 polling에서 재조회되지 않는다
- 404 로그가 ERROR가 아닌 WARNING으로 출력된다
- 일시적 네트워크 오류는 여전히 ERROR로 로깅되고 다음 polling에서 재시도된다

---

### 2. Claude CLI subprocess 60초 타임아웃 — 초안 생성 실패

**파일**: `config/gateway.json`

**현황**:
- `intelligence.claude_draft.timeout = 60` (초)
- Claude Sonnet subprocess(`claude -p`)가 복잡한 메시지 분석 시 60초를 초과함
- TimeoutError → RuntimeError → `retry_async(max_retries=1)` 총 2회 시도 후 최종 실패
- 최종 실패 시 메시지 상태가 `awaiting_draft`로 전환되어 초안 미생성

**요구사항**:
- `intelligence.claude_draft.timeout`을 60에서 180으로 증가한다
- Claude Sonnet의 실제 응답 시간(최대 2-3분)을 커버할 수 있는 여유를 확보한다
- retry 횟수는 1회 유지한다 (180초 × 3 = 540초 소요 방지)

**수락 기준**:
- 일반적인 메시지 초안 생성이 타임아웃 없이 완료된다
- `awaiting_draft` 전환 빈도가 감소한다

---

### 3. duckduckgo_search → ddgs 패키지 마이그레이션

**파일 1**: `requirements.txt`
**파일 2**: `scripts/intelligence/response/handler.py`

**현황**:
- `duckduckgo_search` 패키지가 `ddgs`로 이름 변경됨
- `requirements.txt`에 관련 패키지 미등록
- `handler.py`에서 구버전 `from duckduckgo_search import DDGS` import 사용
- 런타임 `RuntimeWarning` 반복 출력으로 로그 오염

**요구사항**:
- `requirements.txt`에 `ddgs>=6.0.0`을 추가한다
- `handler.py`의 import를 신버전 우선, 구버전 fallback 방식으로 수정한다:
  1. `from ddgs import DDGS` (신버전 우선)
  2. `from duckduckgo_search import DDGS` (구버전 fallback)
  3. 둘 다 없으면 `logger.warning` 출력 후 웹 검색 스킵
- 신구버전 모두 설치되지 않은 환경에서도 서버가 정상 기동되어야 한다

**수락 기준**:
- `RuntimeWarning: duckduckgo_search → ddgs` 경고가 출력되지 않는다
- `ddgs` 설치 환경에서 웹 검색이 정상 동작한다
- `ddgs` 미설치 환경에서도 Gateway 서버가 정상 기동된다

---

## 구현 범위

| # | 파일 | 변경 유형 |
|---|------|----------|
| 1 | `scripts/gateway/adapters/gmail.py` | 404 분기 처리 추가, logging 초기화 |
| 2 | `config/gateway.json` | timeout 60 → 180 |
| 3 | `requirements.txt` | ddgs 패키지 추가 |
| 4 | `scripts/intelligence/response/handler.py` | import 하위호환 처리 |

---

## 구현 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| Gmail 404 분기 처리 + logging 초기화 | 완료 | `seen_ids` 추가, WARNING 레벨 분리 |
| Claude CLI 타임아웃 60 → 180초 | 완료 | `config/gateway.json` 수정 |
| `requirements.txt` ddgs 추가 | 완료 | ddgs 9.10.0 설치 확인 |
| handler.py ddgs/duckduckgo fallback import | 완료 | 신구버전 모두 지원 |

---

## 검증 결과

```
ruff check scripts/gateway/adapters/gmail.py
                scripts/intelligence/response/handler.py
→ All checks passed

pytest tests/gateway/test_pipeline.py -v
→ 12 passed in 2.51s
```

ddgs 9.10.0 이미 설치 확인됨.

---

## Changelog

| 날짜 | 버전 | 변경 내용 | 결정 근거 |
|------|------|-----------|----------|
| 2026-02-24 | v1.0 | 최초 작성 — 3개 오류 요구사항 정의 | Gateway 서버 로그 오류 발견 |
| 2026-02-24 | v1.1 | 구현 완료 — 4개 파일 수정, 상태 Completed 전환 | 린트 통과 + 테스트 12/12 통과 |
