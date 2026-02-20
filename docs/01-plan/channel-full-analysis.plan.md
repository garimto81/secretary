# 채널 완벽 분석 시스템 작업 계획

**버전**: 1.0.0 | **작성일**: 2026-02-20 | **기반 PRD**: `docs/00-prd/channel-full-analysis.prd.md`

---

## 배경 (Background)

### 요청 내용
채널의 전체 메시지를 JSON으로 덤프 → Sonnet으로 의미 분석 → 고품질 채널 지식 문서 생성 → Chatbot 답변 품질 향상.

### 해결하려는 문제

| 문제 | 원인 | 현재 코드 위치 |
|------|------|--------------|
| 채널 지식 문서 품질 불량 | TF-IDF가 URL 파편(`com`, `https`, `garimto`) 키워드 추출 | `mastery_analyzer.py:L191-L221` |
| Claude fallback 발동 → 오염 데이터 사용 | `_call_claude()` 실패 시 오염된 `mastery_context` 그대로 사용 | `channel_prd_writer.py:L50-L53` |
| 전체 메시지 미수집 | `KnowledgeStore`에 저장된 일부 메시지만 분석 (최대 5000건, 필터됨) | `mastery_analyzer.py:L117-L121` |
| Chatbot 답변 품질 저하 | `_load_channel_context()` JSON 로드만 사용, MD 문서 활용 안 함 | `handler.py:L414-L438` |

---

## 구현 범위 (Scope)

### 포함 항목
- `ChannelMessageDumper` 신규 클래스 (FR-01)
- `ChannelPRDWriter.write_from_dump()` 메서드 추가 (FR-02)
- `mastery_analyzer.py` URL 불용어 패턴 추가 (FR-02 선행)
- `handler._load_channel_doc()` 메서드 추가 + `_handle_chatbot_message()` 연동 (FR-03)
- `server.py` 시작 훅: 덤프 파일 없는 채널 자동 실행 (FR-04)
- 단위 테스트: `tests/knowledge/test_channel_message_dumper.py` 신규

### 제외 항목
- 기존 `write()` 메서드 삭제 금지 (호환성 유지)
- `channel_contexts/*.json` 제거 금지 (병행 사용)
- Telegram, Gmail 채널 (Slack만 대상)
- `KnowledgeStore` 데이터 마이그레이션

---

## 구현 순서 (Implementation Order)

```
  +---------------------------+
  | Task 1                    |
  | mastery_analyzer.py       |
  | URL 불용어 패턴 추가       |
  +------------+--------------+
               |
               v
  +------------+--------------+
  | Task 2                    |
  | channel_message_dumper.py |
  | 신규 클래스 (FR-01)       |
  +------------+--------------+
               |
               v
  +------------+--------------+
  | Task 3                    |
  | channel_prd_writer.py     |
  | write_from_dump() 추가    |
  | (FR-02)                   |
  +------------+--------------+
               |
               v
  +------------+--------------+
  | Task 4                    |
  | handler.py                |
  | _load_channel_doc() 추가  |
  | (FR-03)                   |
  +------------+--------------+
               |
               v
  +------------+--------------+
  | Task 5                    |
  | server.py                 |
  | 자동 덤프 훅 (FR-04)      |
  +------------+--------------+
               |
               v
  +------------+--------------+
  | Task 6                    |
  | 테스트 작성 및 검증       |
  +---------------------------+
```

---

## 영향 파일 (Affected Files)

### 수정 예정 파일
| 파일 | 변경 유형 | 변경 내용 |
|------|----------|----------|
| `C:\claude\secretary\scripts\knowledge\mastery_analyzer.py` | 수정 | URL 불용어 상수 추가 (L37-L48 ENGLISH_STOPWORDS 블록 이후) |
| `C:\claude\secretary\scripts\knowledge\channel_prd_writer.py` | 수정 | `write_from_dump()` 메서드 추가, `_build_dump_prompt()` 추가 |
| `C:\claude\secretary\scripts\intelligence\response\handler.py` | 수정 | `_load_channel_doc()` 메서드 추가, `_handle_chatbot_message()` 수정 |
| `C:\claude\secretary\scripts\gateway\server.py` | 수정 | `_run_initial_channel_dumps()` 메서드 추가, `start()` 내 호출 |
| `C:\claude\secretary\scripts\shared\paths.py` | 수정 | `CHANNEL_DUMPS_DIR` 상수 추가 |

### 신규 생성 파일
| 파일 | 설명 |
|------|------|
| `C:\claude\secretary\scripts\knowledge\channel_message_dumper.py` | FR-01 메인 구현 |
| `C:\claude\secretary\tests\knowledge\test_channel_message_dumper.py` | 단위 테스트 |
| `C:\claude\secretary\data\channel_dumps\` | 런타임 데이터 디렉토리 (파일은 런타임 생성) |

---

## 위험 요소 (Risks)

### R-01: Slack API Rate Limit 초과
- **상황**: 채널 메시지 전체 수집 중 `conversations.history` API를 연속 호출 시 `ratelimited` 오류
- **대응**: 요청 간 1.2초 슬립, 응답 `retry_after` 헤더 존중. 기존 `lib/slack/client.py`의 `get_history_with_cursor()`가 페이지네이션은 지원하지만 rate limit 자동 재시도는 없음 → `ChannelMessageDumper` 레벨에서 `asyncio.sleep(1.2)` 삽입 필수

### R-02: 덤프 JSON 50MB 초과
- **상황**: 메시지 수 10000건 이상인 채널에서 JSON 파일이 50MB 초과 가능
- **대응**: 저장 시 메시지 수 확인, 10000건 초과 시 최근 10000건만 유지 (PRD NFR 명시). `total_messages` 필드는 실제 전체 수 기록

### R-03: Map-Reduce 청킹 시 컨텍스트 손실
- **상황**: 2000개 초과 메시지를 청크별 요약 후 통합할 때 청크 경계에서 중요 대화 맥락 분리
- **대응**: 청크 오버랩 50개 메시지 포함 (앞 청크 마지막 50개를 다음 청크 앞에 추가). 통합 프롬프트에서 "중복 정보 제거" 명시

### R-04: Claude subprocess 타임아웃 (write_from_dump)
- **상황**: 2000개 메시지 텍스트를 프롬프트에 포함하면 입력 토큰 초과 → 타임아웃 또는 거부
- **대응**: 프롬프트 메시지 텍스트는 메시지당 최대 200자 절삭. 총 입력 토큰 추정: 2000개 × 200자 = 400000자 ≈ 100000 토큰 → Map-Reduce 필수 임계값을 500개로 설정 권장

### R-05: handler.py chatbot 응답 속도 저하
- **상황**: `_load_channel_doc()`이 대형 MD 파일(수백 KB)을 매 메시지마다 동기 파일 읽기
- **대응**: 클래스 인스턴스 변수에 MD 내용 캐싱 (`_channel_doc_cache: dict[str, str]`). 파일 mtime 변경 시 캐시 무효화

---

## 태스크 목록 (Tasks)

### Task 1: mastery_analyzer.py URL 불용어 추가

**파일**: `C:\claude\secretary\scripts\knowledge\mastery_analyzer.py`

**변경 위치**: `ENGLISH_STOPWORDS` 집합 (L37-L48) 이후에 새 상수 추가

**변경 내용**:
```python
# URL/GitHub 오염 불용어 (TF-IDF 키워드 오염 방지)
URL_STOPWORDS = {
    "http", "https", "www", "com", "org", "net", "io", "kr",
    "github", "garimto", "blob", "tree", "main", "master",
    "issues", "pulls", "commit", "raw", "releases", "tag",
    "report", "invalid", "closed", "open", "label",
    "html", "json", "xml", "yaml", "md",
}
```

**`_extract_keywords()` 수정**: `all_stopwords = KOREAN_STOPWORDS | ENGLISH_STOPWORDS` → `all_stopwords = KOREAN_STOPWORDS | ENGLISH_STOPWORDS | URL_STOPWORDS`

**`_extract_issue_patterns()` 수정**: 동일한 방식으로 `URL_STOPWORDS` 추가

**Acceptance Criteria**:
- `mastery_analyzer.py`를 import하면 `URL_STOPWORDS` 상수가 존재함
- `_extract_keywords()` 결과에 `"com"`, `"https"`, `"garimto"` 포함되지 않음
- 기존 테스트 `tests/knowledge/test_channel_mastery.py` 전체 통과

---

### Task 2: ChannelMessageDumper 신규 구현 (FR-01)

**파일**: `C:\claude\secretary\scripts\knowledge\channel_message_dumper.py` (신규)

**클래스 구조**:

```
  ChannelMessageDumper
  ├── __init__(slack_client, dump_dir)
  ├── dump(channel_id, force=False) -> Path
  │   ├── _load_existing(dump_path) -> dict | None
  │   ├── _collect_incremental(channel_id, oldest_ts) -> list[dict]
  │   ├── _collect_full(channel_id) -> list[dict]
  │   ├── _normalize_message(raw_msg) -> dict
  │   └── _save_dump(dump_path, data) -> None
  └── (CLI) main()
```

**덤프 JSON 구조**:
```json
{
  "channel_id": "C0985UXQN6Q",
  "channel_name": "general",
  "dump_date": "2026-02-20T15:30:00",
  "total_messages": 1523,
  "messages": [
    {
      "ts": "1708393200.000100",
      "user": "U040EUZ6JRY",
      "text": "메시지 내용",
      "thread_ts": null,
      "reactions": ["thumbsup:2"]
    }
  ]
}
```

**핵심 메서드 설계**:

`dump(channel_id, force=False) -> Path`:
1. `CHANNEL_DUMPS_DIR / f"{channel_id}.json"` 경로 설정
2. `force=False`면 기존 덤프 로드 → 마지막 `ts` 기반 증분 수집
3. `force=True`면 전체 수집
4. 메시지 수 10000건 초과 시 최근 10000건만 유지
5. JSON 저장 후 Path 반환

`_collect_incremental(channel_id, oldest_ts)`:
- `lib.slack.client.get_history_with_cursor(channel, limit=200, oldest=oldest_ts)` 반복 호출
- 각 페이지 수집 후 `asyncio.sleep(1.2)` (Rate Limit 보호)
- `has_more=False`일 때 종료

`_collect_full(channel_id)`:
- cursor 없이 최초 호출 시작
- 동일하게 `asyncio.sleep(1.2)` 삽입
- 전체 수집 완료 후 반환

`_normalize_message(raw_msg) -> dict`:
- `ts`, `user`, `text` 필드만 추출
- `thread_ts`: `raw_msg.get("thread_ts")`, parent와 같으면 None 처리
- `reactions`: `[f"{r['name']}:{r['count']}" for r in raw_msg.get("reactions", [])]`
- `text` 4000자 절삭 (NFR: 최대 50MB 제한)

**CLI 인터페이스**:
```
python scripts/knowledge/channel_message_dumper.py --channel C0985UXQN6Q [--force]
```

**Acceptance Criteria**:
- `dump(channel_id)` 호출 시 `data/channel_dumps/{channel_id}.json` 생성
- JSON에 `channel_id`, `dump_date`, `total_messages`, `messages` 필드 모두 포함
- 기존 덤프 있으면 `oldest_ts` 이후 메시지만 추가 (증분)
- `force=True` 시 기존 덤프 무시하고 전체 수집
- Rate limit 보호: 페이지 요청 사이 1.2초 슬립 포함

---

### Task 3: ChannelPRDWriter.write_from_dump() 추가 (FR-02)

**파일**: `C:\claude\secretary\scripts\knowledge\channel_prd_writer.py`

**추가 메서드**: `write_from_dump(channel_id, dump_path, force=False) -> Path`

**Map-Reduce 청킹 전략**:

```
  messages (전체)
       |
       v
  len(messages) <= 500?
       |
    Yes|        No
       |         |
       v         v
  [Direct]   [Map 단계]
  단일 프롬프트  청크 분할 (500개씩, 오버랩 50개)
  Sonnet 호출  각 청크 Sonnet 요약
       |         |
       |         v
       |    [Reduce 단계]
       |    청크 요약 통합 Sonnet 호출
       |         |
       +---------+
                 |
                 v
            채널 MD 저장
```

**추가 메서드 목록**:
- `write_from_dump(channel_id, dump_path, force=False) -> Path`: 메인 진입점
- `_load_dump(dump_path) -> list[dict]`: JSON 파일 로드, `messages` 필드 반환
- `_messages_to_text(messages, max_chars_per_msg=200) -> str`: 메시지 리스트 → 텍스트 변환
- `_build_dump_prompt(channel_id, messages_text) -> str`: 실제 대화 기반 Sonnet 프롬프트
- `_chunked_analysis(channel_id, messages, chunk_size=500, overlap=50) -> str`: Map-Reduce 실행

**`_build_dump_prompt()` 핵심 차이점**:
- 기존 `_build_prd_prompt()`는 TF-IDF 키워드 전달
- 신규는 **실제 대화 텍스트** 전달 (샘플 메시지 형태)
- 프롬프트 구조:
```
채널 {channel_id}의 실제 Slack 대화 내용을 분석하여 채널 지식 문서를 생성하세요.

[실제 대화 샘플]
{messages_text}

위 대화를 바탕으로 다음 항목을 정확히 파악하여 마크다운 문서를 생성하세요:
- 채널의 실제 목적 (추측 아님, 대화에서 파악)
- 반복 논의 주제 (실제 등장한 주제만)
- 실제 의사결정 사례
...
```

**`write_from_dump()` 흐름**:
1. 출력 경로 설정 (`CHANNEL_DOCS_DIR / f"{channel_id}.md"`)
2. `force=False`면 기존 파일 존재 시 스킵
3. `_load_dump(dump_path)` → messages 로드
4. `len(messages) <= 500`이면 직접 분석, 초과 시 Map-Reduce
5. Sonnet 호출 (`_call_claude()` 재사용)
6. `_validate_sections()` → 누락 섹션 보완 (`_merge_missing_sections()` 재사용)
7. 파일 저장

**Acceptance Criteria**:
- `write_from_dump(channel_id, dump_path)` 호출 시 `config/channel_docs/{channel_id}.md` 생성
- 500개 이하: 단일 Sonnet 호출
- 500개 초과: Map-Reduce (청크 요약 후 통합)
- 생성 문서에 `REQUIRED_SECTIONS` 9개 섹션 모두 포함
- `_call_claude()` 실패 시 기존 `write()` fallback 방식과 동일하게 fallback PRD 생성
- 기존 `write()` 메서드는 변경 없음

---

### Task 4: handler._load_channel_doc() 추가 (FR-03)

**파일**: `C:\claude\secretary\scripts\intelligence\response\handler.py`

**추가 메서드**: `_load_channel_doc(channel_id: str) -> str`

**설계**:
```python
def _load_channel_doc(self, channel_id: str) -> str:
    """config/channel_docs/{channel_id}.md 로드 (캐싱)"""
    # 캐시 확인 (mtime 기반 무효화)
    # 파일 없으면 빈 문자열 반환
    # 성공 시 MD 내용 반환
```

**캐싱 메커니즘**:
- `__init__()`에 `self._channel_doc_cache: dict[str, tuple[float, str]] = {}` 추가
  - key: `channel_id`, value: `(mtime, content)`
- `_load_channel_doc()` 호출 시:
  1. 파일 존재 확인 → 없으면 `""` 반환
  2. `mtime` 비교 → 캐시 유효하면 캐시 반환
  3. 파일 읽기 → 캐시 업데이트 → 반환

**`_handle_chatbot_message()` 수정 (L482-L483)**:

현재:
```python
ch_ctx_dict = self._load_channel_context(channel_id or "")
channel_context = self._channel_context_to_str(ch_ctx_dict)
```

변경 후:
```python
ch_ctx_dict = self._load_channel_context(channel_id or "")
channel_context = self._channel_context_to_str(ch_ctx_dict)

# MD 채널 지식 문서 우선 사용
channel_doc = self._load_channel_doc(channel_id or "")
if channel_doc:
    channel_context = f"## 채널 지식베이스\n{channel_doc}\n\n{channel_context}"
```

**`_build_context()` 수정 (L814-L836 channel_ctx_section 생성 블록)**:

MD 문서가 있으면 JSON 컨텍스트보다 먼저 삽입:
```python
if channel_id:
    channel_doc = self._load_channel_doc(channel_id)
    if channel_doc:
        channel_ctx_section = f"## 채널 지식베이스\n{channel_doc[:8000]}\n"
    else:
        # 기존 JSON 컨텍스트 로드 로직 유지
        ch_ctx = self._load_channel_context(channel_id)
        ...
```

**Acceptance Criteria**:
- `_load_channel_doc("C0985UXQN6Q")` 호출 시 `config/channel_docs/C0985UXQN6Q.md` 내용 반환
- 파일 없으면 빈 문자열 반환 (예외 없음)
- 동일 채널 두 번째 호출 시 파일 읽기 없이 캐시 반환
- `_handle_chatbot_message()`에서 MD 문서 있으면 프롬프트에 "채널 지식베이스" 섹션 주입
- 기존 `_load_channel_context()` JSON 로직은 fallback으로 유지

---

### Task 5: server.py 자동 덤프 훅 (FR-04)

**파일**: `C:\claude\secretary\scripts\gateway\server.py`

**추가 메서드**: `_run_initial_channel_dumps() -> None`

**호출 위치**: `start()` 내 `_start_channel_watcher()` 호출 이후 (L176), fire-and-forget

**설계**:
```python
async def _run_initial_channel_dumps(self) -> None:
    """등록된 Slack 채널 중 덤프 없는 채널 자동 덤프 실행"""
    # 1. channels.json에서 enabled=True Slack 채널 목록 조회
    # 2. data/channel_dumps/{channel_id}.json 없는 채널만 필터
    # 3. ChannelMessageDumper 초기화 (SlackClient 사용)
    # 4. 채널별 dump() 순차 실행 (병렬 금지 — Rate Limit)
    # 5. 덤프 완료 후 ChannelPRDWriter.write_from_dump() 호출
    # 6. 오류 시 로그만 출력 (서버 시작 차단 금지)
```

**`start()` 수정**:
```python
# L176 이후 추가
await self._start_channel_watcher()

# 초기 채널 덤프 (비동기 백그라운드, 서버 시작 차단 안 함)
asyncio.create_task(self._run_initial_channel_dumps())
```

**`paths.py` 수정**: `CHANNEL_DUMPS_DIR = DATA_DIR / "channel_dumps"` 추가

**Acceptance Criteria**:
- Gateway 서버 시작 시 `data/channel_dumps/` 없는 채널 자동 덤프 시작
- 덤프 실패 시 오류 로그 출력 후 다음 채널 진행 (서버 시작 중단 없음)
- 이미 덤프 파일 있는 채널은 건너뜀
- `config/channels.json`의 `enabled: false` 채널 제외

---

### Task 6: 단위 테스트 작성

**파일**: `C:\claude\secretary\tests\knowledge\test_channel_message_dumper.py` (신규)

**테스트 케이스**:

```python
class TestChannelMessageDumperDump:
    - test_dump_creates_json_file()
      # SlackClient mock, dump() 호출 → JSON 파일 생성 확인
    - test_dump_incremental_uses_oldest_ts()
      # 기존 덤프 있으면 oldest_ts 사용 확인
    - test_dump_force_ignores_existing()
      # force=True 시 기존 덤프 무시, 전체 수집

class TestChannelMessageDumperNormalize:
    - test_normalize_message_fields()
      # ts, user, text, thread_ts, reactions 필드 검증
    - test_normalize_truncates_long_text()
      # text 4000자 초과 시 절삭 확인
    - test_normalize_thread_ts_same_as_ts_becomes_none()
      # thread_ts == ts이면 None 처리

class TestChannelMessageDumperRateLimit:
    - test_dump_sleeps_between_pages()
      # asyncio.sleep(1.2) 호출 여부 확인 (mock)

class TestWriteFromDump:
    - test_write_from_dump_single_chunk()
      # 500개 이하 메시지 → 단일 Sonnet 호출
    - test_write_from_dump_map_reduce()
      # 501개 메시지 → chunked_analysis 호출 확인
    - test_write_from_dump_skips_existing()
      # 기존 MD 있으면 force=False 시 스킵

class TestLoadChannelDoc:
    - test_load_channel_doc_returns_content()
      # MD 파일 있으면 내용 반환
    - test_load_channel_doc_missing_returns_empty()
      # 파일 없으면 빈 문자열 반환
    - test_load_channel_doc_caches_result()
      # 두 번 호출 시 파일 읽기 1회만 (mock 확인)
```

**Acceptance Criteria**:
- `pytest tests/knowledge/test_channel_message_dumper.py -v` 전체 통과
- 외부 서비스(Slack API) 없이 실행 가능 (SlackClient mock)
- 기존 `tests/knowledge/test_channel_prd_writer.py` 회귀 없음

---

## 커밋 전략 (Commit Strategy)

각 Task 완료 후 독립 커밋. Conventional Commit 형식:

```
feat(knowledge): add URL stopwords to mastery_analyzer for clean TF-IDF

feat(knowledge): implement ChannelMessageDumper for full channel dump (FR-01)

feat(knowledge): add write_from_dump with Map-Reduce chunking to ChannelPRDWriter (FR-02)

feat(intelligence): add _load_channel_doc with caching to handler (FR-03)

feat(gateway): add initial channel dump hook on server start (FR-04)

test(knowledge): add test_channel_message_dumper unit tests
```

---

## 참고 사항

### lib.slack.client 기존 메서드 활용
- `get_history_with_cursor(channel, limit, oldest, cursor)` — `C:\claude\lib\slack\client.py`
- 반환값: `{"messages": [...], "has_more": bool, "response_metadata": {"next_cursor": "..."}}`
- `limit` 최대 200 (Slack API 제한)

### CHANNEL_DOCS_DIR 경로
- `C:\claude\secretary\config\channel_docs\` (기존 `paths.py:L48` 정의됨)

### CHANNEL_DUMPS_DIR 경로 (신규)
- `C:\claude\secretary\data\channel_dumps\` (`paths.py`에 추가 필요)

### Import 패턴 준수
모든 신규 모듈은 3중 import fallback 패턴 사용:
```python
try:
    from scripts.knowledge.xxx import Xxx
except ImportError:
    try:
        from knowledge.xxx import Xxx
    except ImportError:
        from .xxx import Xxx
```
