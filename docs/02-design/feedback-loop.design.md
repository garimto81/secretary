# Feedback Loop — Design Document

**Version**: 1.0.0
**Created**: 2026-02-18
**Plan**: `docs/01-plan/feedback-loop.plan.md`
**Status**: APPROVED (Ralplan 합의 기반)
**Scope**: T1 (FeedbackStore) + T2 (CLI 확장) — MVP only

---

## 1. 구현 범위 (MVP)

| Task | 파일 | 설명 |
|------|------|------|
| **T1** | `scripts/intelligence/feedback_store.py` | FeedbackStore 클래스 신규 |
| **T1** | `scripts/intelligence/context_store.py` | `_migrate_feedback_table()` + `cleanup_old_entries()` 순서 수정 |
| **T2** | `scripts/intelligence/cli.py` | approve/reject에 `--reason`, `--modification` 추가 |
| **Test** | `tests/intelligence/test_feedback_store.py` | FeedbackStore 단위 테스트 |
| **Test** | `tests/intelligence/test_feedback_cli.py` | CLI 통합 테스트 |

**T3-T7 보류**: feedback 50건 이상 수집 후 재착수

---

## 2. DB 스키마

### 2.1 feedback_responses 테이블 (신규)

```sql
CREATE TABLE IF NOT EXISTS feedback_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL UNIQUE,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason TEXT,
    modification_summary TEXT,
    feedback_quality_score INTEGER DEFAULT 5
        CHECK (feedback_quality_score IS NULL OR feedback_quality_score BETWEEN 1 AND 5),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (draft_id) REFERENCES draft_responses(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_feedback_draft ON feedback_responses(draft_id);
CREATE INDEX IF NOT EXISTS idx_feedback_decision ON feedback_responses(decision);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_responses(created_at DESC);
```

**설계 결정**:
- `ON DELETE CASCADE`: `cleanup_old_entries()`가 draft_responses를 삭제할 때 자동 연쇄 삭제
- `CHECK (decision IN (...))`: 잘못된 결정값 DB 레벨 거부
- `feedback_quality_score`: DEFAULT 5 고정, CLI 미노출 (초기 단계 단순화)

### 2.2 마이그레이션 방식

`IntelligenceStorage.connect()` 내부에서 `_migrate_feedback_table()` 호출 추가.
기존 `_migrate_draft_columns()` 패턴과 동일:

```python
async def _migrate_feedback_table(self):
    """feedback_responses 테이블 추가 (멱등)"""
    migrations = [
        """CREATE TABLE IF NOT EXISTS feedback_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER NOT NULL UNIQUE,
            decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
            reason TEXT,
            modification_summary TEXT,
            feedback_quality_score INTEGER DEFAULT 5
                CHECK (feedback_quality_score IS NULL OR feedback_quality_score BETWEEN 1 AND 5),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (draft_id) REFERENCES draft_responses(id) ON DELETE CASCADE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_feedback_draft ON feedback_responses(draft_id)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_decision ON feedback_responses(decision)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_responses(created_at DESC)",
    ]
    for sql in migrations:
        try:
            await self._connection.execute(sql)
            await self._connection.commit()
        except Exception as e:
            if "already exists" in str(e).lower():
                pass
            else:
                raise
```

---

## 3. FeedbackStore 클래스 설계

### 3.1 위치 및 생성

```
scripts/intelligence/feedback_store.py
```

### 3.2 클래스 인터페이스

```python
class FeedbackStore:
    """
    피드백 데이터 저장소.

    IntelligenceStorage의 connection을 공유하여 write lock 경합 방지.
    독립 DB 연결 절대 금지.
    """

    REASON_CHOICES = ["부정확함", "어조부적절", "누락정보", "반복", "기타"]

    def __init__(self, storage: IntelligenceStorage):
        """
        Args:
            storage: 연결된 IntelligenceStorage 인스턴스
        """
        self._storage = storage

    @property
    def _conn(self):
        return self._storage._connection

    async def save_feedback(
        self,
        draft_id: int,
        decision: str,
        reason: Optional[str] = None,
        modification_summary: Optional[str] = None,
    ) -> int:
        """
        피드백 저장 (approve 또는 reject 시 호출).

        Args:
            draft_id: draft_responses.id
            decision: 'approved' | 'rejected'
            reason: 거부 사유 (REASON_CHOICES 중 하나, 선택형)
            modification_summary: 수정 내용 요약 (선택형)

        Returns:
            생성된 feedback_responses.id

        Raises:
            ValueError: 이미 피드백이 존재하는 경우 (UNIQUE 위반)
        """

    async def get_feedback_by_draft(self, draft_id: int) -> Optional[Dict[str, Any]]:
        """draft_id로 피드백 조회"""

    async def list_feedback(
        self,
        decision: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """피드백 목록 조회 (created_at DESC)"""
```

### 3.3 FeedbackStore import 패턴

3중 fallback 적용:
```python
try:
    from scripts.intelligence.feedback_store import FeedbackStore
except ImportError:
    try:
        from intelligence.feedback_store import FeedbackStore
    except ImportError:
        from .feedback_store import FeedbackStore
```

---

## 4. CLI 변경 설계 (T2)

### 4.1 `cmd_drafts_approve` 확장

**Before**:
```python
async def cmd_drafts_approve(args):
    storage = await get_storage()
    try:
        success = await storage.update_draft_status(
            draft_id=int(args.id),
            status="approved",
            reviewer_note=args.note,
        )
        if success:
            print(f"초안 #{args.id} 승인 완료")
        ...
```

**After**:
```python
REASON_CHOICES = ["부정확함", "어조부적절", "누락정보", "반복", "기타"]

async def cmd_drafts_approve(args):
    storage = await get_storage()
    try:
        success = await storage.update_draft_status(
            draft_id=int(args.id),
            status="approved",
            reviewer_note=args.note,
        )
        if success:
            # FeedbackStore에 피드백 저장
            from scripts.intelligence.feedback_store import FeedbackStore
            fb_store = FeedbackStore(storage)
            await fb_store.save_feedback(
                draft_id=int(args.id),
                decision="approved",
                reason=args.reason,
                modification_summary=args.modification,
            )
            print(f"초안 #{args.id} 승인 완료")
            if args.reason:
                print(f"  사유: {args.reason}")
        ...
```

**`cmd_drafts_reject`도 동일 패턴** (`decision="rejected"`).

### 4.2 argparse 변경

```python
# drafts approve
approve_parser.add_argument("--note", default="", help="리뷰 노트 (기존 호환)")
approve_parser.add_argument(
    "--reason",
    choices=REASON_CHOICES,
    default=None,
    help=f"승인 사유 ({', '.join(REASON_CHOICES)})",
)
approve_parser.add_argument("--modification", default=None, help="수정 내용 요약")

# drafts reject
reject_parser.add_argument("--note", default="", help="리뷰 노트 (기존 호환)")
reject_parser.add_argument(
    "--reason",
    choices=REASON_CHOICES,
    default=None,
    help=f"거부 사유 ({', '.join(REASON_CHOICES)})",
)
reject_parser.add_argument("--modification", default=None, help="수정 내용 요약")
```

**하위 호환성**: 기존 `--note` 유지, `--reason`/`--modification` 선택형(required=False)

### 4.3 사용 예시

```bash
# 기존 방식 (여전히 작동)
python cli.py drafts approve 42

# 신규 방식
python cli.py drafts approve 42 --reason 부정확함 --modification "내용을 더 정확하게 수정 필요"
python cli.py drafts reject 43 --reason 어조부적절 --modification "존댓말로 수정"
```

---

## 5. cleanup_old_entries 순서 (수정 불필요)

`ON DELETE CASCADE` 적용으로 `draft_responses` 삭제 시 `feedback_responses` 자동 삭제.
`cleanup_old_entries()`에 별도 삭제 쿼리 불필요.

---

## 6. 테스트 설계

### 6.1 tests/intelligence/test_feedback_store.py

| 테스트 | 검증 내용 |
|--------|---------|
| `test_save_feedback_approved` | 승인 피드백 저장 및 조회 |
| `test_save_feedback_rejected_with_reason` | 거부+사유+수정내용 저장 |
| `test_invalid_decision_raises` | CHECK constraint 위반 시 예외 |
| `test_duplicate_draft_id_raises` | UNIQUE constraint 위반 시 예외 |
| `test_cascade_delete` | draft 삭제 시 feedback 자동 삭제 확인 |
| `test_list_feedback_filter` | decision 필터 조회 |
| `test_get_feedback_by_draft_not_found` | 없는 draft_id → None 반환 |

### 6.2 tests/intelligence/test_feedback_cli.py

| 테스트 | 검증 내용 |
|--------|---------|
| `test_approve_stores_feedback` | approve 명령 실행 시 DB에 feedback 생성 |
| `test_reject_with_reason_stores_feedback` | reject --reason 실행 시 reason 저장 |
| `test_approve_without_reason_allowed` | reason 없이 approve 허용 |
| `test_invalid_reason_rejected` | choices 외 reason → argparse error |

---

## 7. 파일 변경 요약

| 파일 | 변경 유형 | 주요 변경 내용 |
|------|---------|--------------|
| `scripts/intelligence/context_store.py` | 수정 | `connect()`에 `_migrate_feedback_table()` 추가 |
| `scripts/intelligence/feedback_store.py` | **신규** | FeedbackStore 클래스 |
| `scripts/intelligence/cli.py` | 수정 | approve/reject에 --reason, --modification 추가 + FeedbackStore 연동 |
| `tests/intelligence/test_feedback_store.py` | **신규** | FeedbackStore 단위 테스트 |
| `tests/intelligence/test_feedback_cli.py` | **신규** | CLI 통합 테스트 |

**수정/신규 합계**: 3개 수정, 2개 신규 (총 5개 파일)

---

## 8. 승인자

**Ralplan 합의**: Architect + Planner + Critic — 2026-02-18
**다음 단계**: TDD 기반 구현 (T1 → T2 순차)
