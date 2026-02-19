# Slack Channel Mastery Work Plan

**Version**: 1.0.0
**Created**: 2026-02-18
**Status**: PLANNED
**Complexity Score**: 4/5
**Target Channel**: `C0985UXQN6Q` (secretary project)

---

## 배경 (Background)

### 요청 내용

Slack 채널 `C0985UXQN6Q`의 **모든** 메시지 히스토리를 완전히 수집하고, 스레드·멤버·채널 메타데이터까지 Knowledge Store에 축적하여, 해당 채널의 AI 전문가 프로파일을 구축한다.

### 해결하려는 문제

현재 `KnowledgeBootstrap.learn_slack(limit=500)`은 다음 세 가지 근본적 한계를 갖는다:

| 한계 | 원인 | 결과 |
|------|------|------|
| **히스토리 단절** | `limit=500` 단건 호출, cursor 없음 | 최신 500건만 수집, 과거 전체 유실 |
| **스레드 미수집** | `thread_ts` 추출 후 replies 호출 없음 | 스레드 컨텍스트 100% 손실 |
| **채널 메타데이터 없음** | 멤버/토픽/핀 수집 로직 없음 | AI가 "누가 결정권자인지", "채널 목적이 무엇인지" 모름 |

"전문가" 수준을 달성하기 위해 필요한 데이터:

- 채널 전체 메시지 히스토리 (첫 메시지 ~ 현재)
- 모든 스레드의 replies
- 채널 멤버 목록 및 역할 정보
- 채널 토픽, 목적(purpose), 핀된 메시지
- 수집 완료 후 전문가 컨텍스트 요약 (주요 토픽, 의사결정, 멤버 역할)

### 현황 분석

```
scripts/knowledge/bootstrap.py (현재)
└── learn_slack(channel_id, limit=500)
    ├── subprocess: lib.slack history {channel_id} --limit 500 --json
    ├── ❌ cursor 없음 → 500건 초과 불가
    ├── ❌ thread replies 미수집
    └── ❌ 채널 메타데이터 미수집

scripts/intelligence/incremental/trackers/slack_tracker.py (참고)
└── _fetch_channel() — 증분 수집만, oldest 기준
    └── ✓ get_replies() 호출 있음 (Knowledge Store가 아닌 Intelligence Storage에 저장)
```

---

## 구현 범위 (Scope)

### 포함 항목

- `CM-K01`: cursor-based pagination으로 채널 전체 히스토리 수집
- `CM-K02`: 모든 parent 메시지의 thread replies 완전 수집
- `CM-K03`: 채널 메타데이터(멤버, 토픽, 핀) 수집 및 저장
- `CM-K04`: `ChannelMasteryAnalyzer` — 전문가 컨텍스트 생성 (TF-IDF 키워드, 의사결정, 멤버 역할)
- `CM-K05`: Intelligence Handler에 채널 전문가 컨텍스트 주입
- `CM-K06`: CLI 진입점 (`bootstrap.py mastery {channel_id}`)

### 제외 항목

- 파일/이미지 첨부 수집 (Slack files API — 별도 작업)
- 타 채널 지원 (현재 단일 채널 `C0985UXQN6Q` 전용)
- 실시간 스트리밍 보완 (Gateway SlackAdapter가 담당)
- Knowledge Store 스키마 변경 (`documents` 테이블 유지)

---

## 영향 파일 (Affected Files)

### 수정 예정 파일

| 파일 | 수정 내용 |
|------|----------|
| `C:\claude\secretary\scripts\knowledge\bootstrap.py` | `learn_slack_full()`, `_fetch_thread_replies()`, `_collect_channel_metadata()`, CLI `mastery` 서브커맨드 추가 |
| `C:\claude\secretary\scripts\knowledge\models.py` | `ChannelProfile` dataclass 추가 |
| `C:\claude\secretary\scripts\intelligence\response\handler.py` | `_build_context()` 및 RAG 검색에 채널 전문가 컨텍스트 주입 로직 추가 |

### 신규 생성 파일

| 파일 | 목적 |
|------|------|
| `C:\claude\secretary\scripts\knowledge\channel_profile.py` | `ChannelProfileStore` — 채널 메타데이터 SQLite 저장/조회 |
| `C:\claude\secretary\scripts\knowledge\mastery_analyzer.py` | `ChannelMasteryAnalyzer` — 전문가 컨텍스트 생성 |
| `C:\claude\secretary\tests\knowledge\test_channel_mastery.py` | 단위/통합 테스트 |

---

## 위험 요소 (Risks)

| 위험 | 영향 | 가능성 | 완화 방안 |
|------|------|--------|----------|
| **Slack API rate limit** | 수집 중단 | HIGH | Tier 3 (50 req/min) — 각 API 호출 간 `sleep(1.2s)` 삽입, 실패 시 exponential backoff (shared/retry.py 재활용) |
| **대용량 채널 처리 시간** | 수만 건 수집 시 수 시간 소요 | MEDIUM | checkpoint-based resume (cursor를 DB에 저장, 재실행 시 이어받기), 진행률 표시 |
| **기존 knowledge.db 중복** | 인덱스 낭비 | LOW | `INSERT OR REPLACE`(UPSERT) — ID `slack:{ts}` 기준, 기존 store.ingest()가 이미 처리 |
| **Thread replies 수집 실패** | 스레드 컨텍스트 손실 | MEDIUM | try/except로 개별 thread 실패 시 skip + 로그, 전체 중단 방지 |
| **lib.slack get_replies() 미구현** | replies 수집 불가 | MEDIUM | SlackTracker 코드를 참고하여 subprocess 대신 lib.slack 직접 import 방식 검토, fallback으로 subprocess 유지 |
| **`_subprocess` 30s timeout** | 대용량 응답 시 시간 초과 | HIGH | 페이지당 100건 단위 수집, 각 페이지 별도 subprocess 호출로 timeout 분산 |

---

## 태스크 목록 (Tasks)

### CM-K01: `learn_slack_full()` — cursor-based 전체 히스토리 수집

**파일**: `C:\claude\secretary\scripts\knowledge\bootstrap.py`

**구현 방법**:

기존 `learn_slack()` 옆에 `learn_slack_full()` 메서드 추가. Slack `conversations.history` API의 `cursor` 파라미터를 활용하여 첫 메시지부터 전체 수집.

```python
async def learn_slack_full(
    self,
    project_id: str,
    channel_id: str,
    page_size: int = 100,          # 페이지당 메시지 수 (Slack API max=200)
    rate_limit_sleep: float = 1.2, # API 호출 간 대기 (Tier 3: 50 req/min)
    resume_cursor: Optional[str] = None,  # checkpoint resume
) -> BootstrapResult:
    """
    cursor-based pagination으로 채널 전체 히스토리 수집.

    checkpoint_key = f"full:{channel_id}"
    cursor 위치를 ingestion_state에 저장 → 재실행 시 이어받기.
    """
```

subprocess 호출 패턴:
```
python -m lib.slack history {channel_id} --limit {page_size} --cursor {cursor} --json
```

응답의 `response_metadata.next_cursor`가 빈 문자열이면 수집 완료.

각 페이지 수집 후 cursor를 `ingestion_state` 테이블에 저장 (`checkpoint_value` 컬럼).

**Acceptance Criteria**:
- [ ] cursor가 None으로 시작해 마지막 페이지까지 반복 수집
- [ ] 중간 실패 시 checkpoint에서 재개 가능
- [ ] 각 페이지 호출 간 `rate_limit_sleep` 대기
- [ ] 수집된 전체 메시지 수가 기존 `learn_slack(limit=500)`보다 많음

---

### CM-K02: Thread Replies 완전 수집

**파일**: `C:\claude\secretary\scripts\knowledge\bootstrap.py`

**구현 방법**:

`learn_slack_full()` 내부에서 `thread_ts`를 가진 메시지(parent)를 수집 후, 별도 메서드 `_fetch_thread_replies()`로 replies 수집.

```python
async def _fetch_thread_replies(
    self,
    project_id: str,
    channel_id: str,
    thread_ts: str,
    rate_limit_sleep: float = 1.2,
) -> int:
    """
    thread_ts의 replies를 수집하여 Knowledge에 저장.

    subprocess: python -m lib.slack history {channel_id} --thread {thread_ts} --json

    content_type = "thread_reply"로 저장
    metadata에 parent_ts 포함
    """
```

`SlackTracker._fetch_channel()` 참고 (line 121-153): thread_ts != msg.ts일 때만 replies 수집.

**Acceptance Criteria**:
- [ ] thread_ts가 있는 parent 메시지마다 replies 수집 시도
- [ ] replies는 `content_type="thread_reply"`, `thread_id=thread_ts`로 저장
- [ ] reply 수집 실패 시 skip + 에러 로그 (전체 중단 없음)
- [ ] 중복 reply는 UPSERT 처리 (ID = `slack:{reply_ts}`)

---

### CM-K03: 채널 메타데이터 수집

**파일**: `C:\claude\secretary\scripts\knowledge\bootstrap.py`, `models.py`, `channel_profile.py` (신규)

**구현 방법**:

#### models.py 추가 dataclass

```python
@dataclass
class ChannelProfile:
    """Slack 채널 전문가 프로파일"""
    channel_id: str
    channel_name: str
    topic: str = ""
    purpose: str = ""
    created: Optional[datetime] = None
    members: list = field(default_factory=list)   # [{"id": "U...", "name": "...", "is_admin": bool}]
    pinned_messages: list = field(default_factory=list)  # [{"ts": "...", "text": "..."}]
    collected_at: Optional[datetime] = None
    total_messages: int = 0
    total_threads: int = 0
```

#### channel_profile.py (신규)

```python
class ChannelProfileStore:
    """ChannelProfile SQLite 저장/조회"""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS channel_profiles (
        channel_id TEXT PRIMARY KEY,
        channel_name TEXT,
        topic TEXT,
        purpose TEXT,
        created DATETIME,
        members_json TEXT,
        pinned_json TEXT,
        collected_at DATETIME,
        total_messages INTEGER DEFAULT 0,
        total_threads INTEGER DEFAULT 0
    );
    """

    async def save(self, profile: ChannelProfile) -> None: ...
    async def get(self, channel_id: str) -> Optional[ChannelProfile]: ...
```

DB 파일: 기존 `knowledge.db`에 테이블 추가 (신규 DB 생성 금지).

수집 subprocess:
```
python -m lib.slack info {channel_id} --json         → channel_name, topic, purpose, created
python -m lib.slack members {channel_id} --json      → members 목록
python -m lib.slack pins {channel_id} --json         → pinned_messages
```

**Acceptance Criteria**:
- [ ] `ChannelProfile` dataclass로 채널 정보 표현 가능
- [ ] `channel_profiles` 테이블이 `knowledge.db`에 생성됨
- [ ] 채널 이름, 토픽, 목적, 멤버 목록, 핀된 메시지 수집 완료
- [ ] lib.slack API 실패 시 빈 값으로 저장 (수집 중단 없음)

---

### CM-K04: `ChannelMasteryAnalyzer` — 전문가 컨텍스트 생성

**파일**: `C:\claude\secretary\scripts\knowledge\mastery_analyzer.py` (신규)

**구현 방법**:

Knowledge Store에 축적된 채널 메시지 전체를 분석하여 AI가 즉시 활용 가능한 전문가 요약을 생성.

```python
class ChannelMasteryAnalyzer:
    """채널 데이터 기반 전문가 컨텍스트 생성"""

    def __init__(self, store: KnowledgeStore, profile_store: ChannelProfileStore):
        self.store = store
        self.profile_store = profile_store

    async def build_mastery_context(
        self,
        project_id: str,
        channel_id: str,
        top_n_keywords: int = 20,
    ) -> dict:
        """
        Returns:
        {
            "channel_summary": "채널 목적 + 주요 활동 요약",
            "top_keywords": ["배포", "일정", "리뷰", ...],
            "key_decisions": ["2026-02-10: A 방식으로 구현 결정", ...],
            "member_roles": {"U040EUZ6JRY": "주요 의사결정권자", ...},
            "active_topics": ["gateway 개발", "intelligence 개선", ...],
        }
        """
```

분석 로직:

1. **상위 키워드 추출 (TF-IDF 간이 구현)**:
   - `store.get_recent(project_id, limit=5000)` 로 전체 메시지 로드
   - 한국어 + 영어 단어 토큰화 (공백/구두점 분리)
   - 불용어 제거 (조사, 접속사, 1음절 한자어 등)
   - 단어 빈도(TF) 계산, 역문서빈도(IDF)는 메시지 단위로 계산
   - 상위 N개 반환

2. **의사결정 추출**:
   - 정규식 패턴: `결정|확정|채택|진행|완료|승인|반려` 포함 문장 추출
   - 날짜 패턴과 함께 출현 시 key_decisions에 추가

3. **멤버 역할 파악**:
   - 발언량 기준 상위 3인: "주요 발언자"
   - action_keywords(`배포`, `릴리즈`, `머지`) 발언 비율 높은 멤버: "실행 담당"
   - 질문/지시 패턴(`?`, `부탁`, `해주세요`) 높은 멤버: "요청자"

4. **활성 토픽 추출**:
   - 최근 30일 메시지에서 상위 키워드 클러스터링 (단순 공출현 기반)

**Acceptance Criteria**:
- [ ] `build_mastery_context()` 실행 후 dict 반환
- [ ] `top_keywords` 최소 5개 이상 (메시지 충분 시)
- [ ] `key_decisions` — action 패턴 포함 메시지에서 추출
- [ ] `member_roles` — 멤버별 역할 분류 (발언량 기준)
- [ ] 빈 채널(메시지 0건)에서 빈 dict 반환 (예외 없음)

---

### CM-K05: Intelligence Handler 채널 전문가 컨텍스트 주입

**파일**: `C:\claude\secretary\scripts\intelligence\response\handler.py`

**구현 방법**:

`ProjectIntelligenceHandler.__init__()` 에 `mastery_analyzer` 파라미터 추가. `_build_context()` 메서드에서 채널 전문가 요약 주입.

```python
# __init__ 파라미터 추가
def __init__(
    self,
    ...
    mastery_analyzer=None,  # Optional[ChannelMasteryAnalyzer]
):
    self._mastery_analyzer = mastery_analyzer

# _build_context() 수정 — 기존 로직 유지, 추가만
async def _build_context(self, project_id: str, query_text: str = "") -> str:
    parts = []
    ...
    # 기존 코드 유지

    # 채널 전문가 컨텍스트 (CM-K05 신규)
    if self._mastery_analyzer:
        try:
            from scripts.knowledge.channel_profile import ChannelProfileStore
            profile_store = ChannelProfileStore(self._mastery_analyzer.store.db_path)
            await profile_store.init_db()
            mastery = await self._mastery_analyzer.build_mastery_context(
                project_id=project_id,
                channel_id="C0985UXQN6Q",  # projects.json에서 조회로 개선 가능
            )
            if mastery:
                parts.append("\n## 채널 전문가 컨텍스트")
                if mastery.get("channel_summary"):
                    parts.append(f"채널 요약: {mastery['channel_summary']}")
                if mastery.get("top_keywords"):
                    parts.append(f"주요 키워드: {', '.join(mastery['top_keywords'][:10])}")
                if mastery.get("key_decisions"):
                    parts.append(f"주요 의사결정:\n" + "\n".join(f"  - {d}" for d in mastery["key_decisions"][:5]))
                if mastery.get("member_roles"):
                    roles_str = ", ".join(f"{k}: {v}" for k, v in mastery["member_roles"].items())
                    parts.append(f"멤버 역할: {roles_str}")
        except Exception as e:
            logger.warning(f"채널 전문가 컨텍스트 주입 실패: {e}")

    return "\n".join(parts)
```

**Acceptance Criteria**:
- [ ] `_build_context()` 반환값에 "채널 전문가 컨텍스트" 섹션 포함
- [ ] mastery_analyzer 없으면 기존 동작 그대로 (backward-compatible)
- [ ] 주입 실패 시 로그 경고만 출력 (파이프라인 중단 없음)

---

### CM-K06: CLI 진입점

**파일**: `C:\claude\secretary\scripts\knowledge\bootstrap.py`

**구현 방법**:

기존 `__main__` 블록에 `mastery` 서브커맨드 추가. `argparse` 사용.

```
python scripts/knowledge/bootstrap.py mastery {channel_id} [--project secretary] [--page-size 100]
```

실행 순서:
1. `learn_slack_full()` — 전체 히스토리 수집 (진행률: "Page N: +M 건, total: X 건")
2. `_fetch_thread_replies()` — 모든 parent의 threads 수집 (진행률: "Thread N/M: +K replies")
3. `_collect_channel_metadata()` — 채널 메타데이터 수집
4. `ChannelMasteryAnalyzer.build_mastery_context()` — 전문가 프로파일 생성
5. 결과 요약 출력:

```
=== Channel Mastery 완료 ===
채널: #secretary-dev (C0985UXQN6Q)
총 메시지: 12,847건
스레드 replies: 3,421건
멤버: 8명
소요 시간: 23분 14초

상위 키워드: gateway, intelligence, 배포, 일정, 리뷰, ...
주요 의사결정: 5건
```

**Acceptance Criteria**:
- [ ] `python scripts/knowledge/bootstrap.py mastery C0985UXQN6Q` 실행 시 에러 없이 완료
- [ ] 진행률이 실시간 출력됨 (각 페이지/스레드 처리 후 즉시 출력)
- [ ] 결과 요약에 총 메시지 수, 스레드 수, 멤버 수, 소요 시간 포함
- [ ] `--project` 미지정 시 "secretary" 기본값 사용

---

## 구현 순서 (의존성 그래프)

```
CM-K01 (전체 히스토리 수집)
  │
  ├──▶ CM-K02 (Thread Replies 수집)    ← CM-K01과 병렬 구현 가능 (동일 파일)
  │
CM-K03 (채널 메타데이터)               ← CM-K01과 독립, 병렬 구현 가능
  │         │
  │         ▼
  │   channel_profile.py (신규)
  │   models.py (ChannelProfile 추가)
  │
  ▼
CM-K04 (MasteryAnalyzer)               ← CM-K01, K02, K03 완료 후
  │
  ▼
CM-K05 (Intelligence Handler 주입)     ← CM-K04 완료 후
  │
  ▼
CM-K06 (CLI 진입점)                    ← CM-K01~K05 모두 완료 후
```

**병렬 구현 가능 그룹**:
- Group A: CM-K01 + CM-K02 (bootstrap.py 동일 파일)
- Group B: CM-K03 (models.py + channel_profile.py)
- Group C: CM-K04 후 CM-K05, CM-K06 순차 진행

---

## 커밋 전략 (Commit Strategy)

| 순서 | Conventional Commit 메시지 | 포함 파일 |
|------|--------------------------|----------|
| 1 | `feat(knowledge): add ChannelProfile model and ChannelProfileStore` | `models.py`, `channel_profile.py` |
| 2 | `feat(knowledge): implement learn_slack_full with cursor-based pagination` | `bootstrap.py` (CM-K01, K02) |
| 3 | `feat(knowledge): collect channel metadata (members, topic, pins)` | `bootstrap.py` (CM-K03 로직) |
| 4 | `feat(knowledge): add ChannelMasteryAnalyzer for expert context generation` | `mastery_analyzer.py` |
| 5 | `feat(intelligence): inject channel mastery context into handler` | `handler.py` |
| 6 | `feat(knowledge): add mastery CLI entrypoint with progress output` | `bootstrap.py` (CM-K06) |
| 7 | `test(knowledge): add channel mastery unit and integration tests` | `tests/knowledge/test_channel_mastery.py` |

---

## 참고 문서

- **현재 learn_slack() 구현**: `C:\claude\secretary\scripts\knowledge\bootstrap.py` (line 190-301)
- **SlackTracker thread 수집 패턴**: `C:\claude\secretary\scripts\intelligence\incremental\trackers\slack_tracker.py` (line 121-153)
- **KnowledgeStore 스키마**: `C:\claude\secretary\scripts\knowledge\store.py` (line 33-97)
- **Intelligence Handler RAG 주입**: `C:\claude\secretary\scripts\intelligence\response\handler.py` (line 155-173, 281-297)
- **projects.json secretary 채널**: `C:\claude\secretary\config\projects.json` (slack_channels: `C0985UXQN6Q`)
- **Knowledge Ingestion Plan** (실시간 축적 설계): `C:\claude\secretary\docs\01-plan\knowledge-ingestion.plan.md`
