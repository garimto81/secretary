# Feedback Loop MVP 완료 보고서

> Secretary 프로젝트 Intelligence 모듈에 사용자 피드백 수집 기능(FeedbackStore + CLI 확장)을 추가하여 향후 패턴 분석 및 프롬프트 개선의 기반을 마련했습니다.
>
> **Status**: Completed (356 passed, 0 failed)
> **Duration**: Plan → Ralplan → Design → Do → Check
> **Completion Date**: 2026-02-18

---

## 1. PDCA 사이클 요약

### 1.1 Plan 단계

**문서**: `docs/01-plan/feedback-loop.plan.md` (v1.1.0 — APPROVED)

**배경**:
- `cli.py drafts approve/reject` 결과가 DB에만 저장되고, 미래 판단 개선에 활용 미흡
- 피드백 데이터 수집 후 패턴 분석 → 프롬프트 자동 조정 파이프라인 구축 필요

**복잡도**: 7/10 (3개 신규 모듈 포함)

### 1.2 Ralplan 단계

**3자 합의**: Architect + Planner + Critic — 전원 APPROVED_WITH_CONDITIONS

| 리뷰어 | 핵심 조건 |
|--------|---------|
| **Architect** | FK `ON DELETE CASCADE`, `_migrate_feedback_table()` 패턴, 공유 connection |
| **Planner** | T2 코드 흐름 명시, 영향 파일 추가, T2→T3 데이터 수집 의존성 명시 |
| **Critic** | T1+T2만 즉시 구현, T3-T7은 50건 수집 후 재착수, rollback 임계값 재설계 |

**합의 결과**: 전체 7개 Task 중 T1+T2만 즉시 구현 (MVP 전략)

### 1.3 Design 단계

**문서**: `docs/02-design/feedback-loop.design.md`

**핵심 설계 결정**:
1. FeedbackStore는 IntelligenceStorage connection 공유 (독립 연결 금지)
2. `ON DELETE CASCADE` FK → cleanup_old_entries 연쇄 처리 자동화
3. `CHECK (decision IN ('approved', 'rejected'))` DB 레벨 검증
4. `_migrate_feedback_table()` 멱등 마이그레이션 패턴 (기존 `_migrate_draft_columns()` 동일)
5. `--reason`/`--modification` 선택형 (기존 `--note` 하위 호환 유지)

### 1.4 Do 단계 (구현)

**TDD 방식**: 테스트 먼저 작성(Red) → 구현(Green)

#### 신규 파일

**1. `scripts/intelligence/feedback_store.py`**
```
FeedbackStore 클래스
  - save_feedback(draft_id, decision, reason, modification_summary)
  - get_feedback_by_draft(draft_id)
  - list_feedback(decision, limit)
  - REASON_CHOICES = ["부정확함", "어조부적절", "누락정보", "반복", "기타"]
```

**2. `tests/intelligence/test_feedback_store.py`** (7개 테스트)
- save_feedback_approved, rejected_with_reason
- invalid_decision_raises, duplicate_raises
- cascade_delete, list_filter, not_found

**3. `tests/intelligence/test_feedback_cli.py`** (3개 테스트)
- approve_stores_feedback, reject_with_reason, approve_without_reason

#### 수정 파일

**4. `scripts/intelligence/context_store.py`**
- `PRAGMA foreign_keys=ON` 추가 (ON DELETE CASCADE 활성화 필수)
- `_migrate_feedback_table()` 메서드 추가
- `connect()`에서 호출 체인: `_migrate_draft_columns()` → `_migrate_feedback_table()`

**5. `scripts/intelligence/cli.py`**
- `REASON_CHOICES` 상수 추가
- `cmd_drafts_approve`: FeedbackStore.save_feedback() 통합 (`decision="approved"`)
- `cmd_drafts_reject`: FeedbackStore.save_feedback() 통합 (`decision="rejected"`)
- `argparse`: approve/reject 파서에 `--reason`(choices), `--modification` 추가

### 1.5 Check 단계

**테스트 결과**:
```
intelligence 모듈: 146 passed (3.05s)
전체 회귀: 356 passed, 0 failed (9.81s)
```

| 테스트 범주 | 결과 |
|------------|------|
| FeedbackStore 단위 (7개) | ✅ All PASSED |
| CLI 통합 (3개) | ✅ All PASSED |
| intelligence 전체 (146개) | ✅ All PASSED |
| 전체 회귀 (356개) | ✅ No regression |

---

## 2. 구현된 기능

### CLI 사용법

```bash
# 기존 방식 (하위 호환 유지)
python cli.py drafts approve 42
python cli.py drafts reject 43 --note "내용 확인"

# 신규 방식 — 사유/수정내용 입력
python cli.py drafts approve 42 --reason 부정확함 --modification "더 정확하게 수정"
python cli.py drafts reject 43 --reason 어조부적절 --modification "존댓말로 수정 필요"

# 사용 가능한 reason 목록
# 부정확함 | 어조부적절 | 누락정보 | 반복 | 기타
```

### DB 스키마 (feedback_responses)

```sql
CREATE TABLE feedback_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL UNIQUE,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    reason TEXT,
    modification_summary TEXT,
    feedback_quality_score INTEGER DEFAULT 5 CHECK (...),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (draft_id) REFERENCES draft_responses(id) ON DELETE CASCADE
);
```

---

## 3. T3-T7 조건부 착수 기준

| Task | 착수 조건 | 예상 시점 |
|------|---------|---------|
| T3 FeedbackAnalyzer | feedback 50건 이상 수집 | 2026-03월 이후 |
| T4 Dashboard CLI | T3 완료 후 | - |
| T5 PromptTuner | feedback 50건 + T6 설계 확정 후 | - |
| T6 버전 관리 | draft_writer.py 로드 메커니즘 설계 후 | - |
| T7 Impact Tracker | Before/After 기간 비교 방식으로 재설계 후 | - |

---

## 4. 다음 액션

1. **즉시**: `python cli.py drafts approve/reject` 시 `--reason` 입력 습관화
2. **2주 후**: feedback 건수 확인 (`SELECT count(*) FROM feedback_responses`)
3. **50건 달성 시**: T3 FeedbackAnalyzer 착수 결정

---

## 5. 파일 변경 요약

| 파일 | 유형 | 변경 내용 |
|------|------|---------|
| `scripts/intelligence/feedback_store.py` | **신규** | FeedbackStore 클래스 |
| `scripts/intelligence/context_store.py` | 수정 | `_migrate_feedback_table()`, `PRAGMA foreign_keys=ON` |
| `scripts/intelligence/cli.py` | 수정 | `--reason`, `--modification`, FeedbackStore 통합 |
| `tests/intelligence/test_feedback_store.py` | **신규** | 7개 단위 테스트 |
| `tests/intelligence/test_feedback_cli.py` | **신규** | 3개 통합 테스트 |
