# Feedback Loop Integration Plan

**Version**: 1.1.0
**Created**: 2026-02-18
**Status**: APPROVED (Ralplan 합의 — Architect + Planner + Critic 3자 APPROVED_WITH_CONDITIONS)

**Ralplan 핵심 조건 (반영 완료)**:
1. FK `ON DELETE CASCADE` 추가 (Architect — cleanup 고아 레코드 방지)
2. `_migrate_feedback_table()` 패턴 사용 (Architect — private attribute 직접 접근 금지)
3. FeedbackStore는 IntelligenceStorage connection 공유 (Architect — write lock 경합 방지)
4. T2 코드 흐름 명시: `cmd_drafts_approve/reject` 내부에서 FeedbackStore.save_feedback() 호출 (Planner)
5. 영향 파일 추가: `analyzer.py`, `draft_writer.py` (T5/T6용, 현재 구현 범위 외) (Planner)
6. **즉시 구현 범위: T1(FeedbackStore) + T2(CLI 확장)만** (Critic — 데이터 50건 미만 시 T3-T7 불가)
7. `feedback_quality_score` = DEFAULT 5 고정 (초기 CLI 미노출) (Critic)
8. T7 A/B 테스트 → Before/After 기간 비교로 단순화 (Planner + Critic)

---

## 목표

사용자의 `drafts approve/reject` 피드백을 수집하여 Intelligence 모듈의 분석 정확도와 초안 품질을 점진적으로 향상시키는 자동화된 피드백 루프 시스템 구축.

현재 상태:
- Claude Opus로 생성된 응답 초안이 `cli.py drafts approve/reject`로 수동 리뷰됨
- 리뷰 결과(approve/reject)가 DB에만 저장되고 미래 판단 개선에 활용 안 됨

목표 상태:
- 피드백 데이터(approve/reject 사유, 수정 내용)로부터 패턴 학습
- 반복 거부 패턴 자동 식별 및 개선 제안
- 프롬프트 자동 조정으로 초안 품질 점진적 상향
- 품질 메트릭 대시보드로 진전도 추적

---

## 복잡도 점수: 7/10

| 평가 항목 | 점수 | 근거 |
|----------|:----:|------|
| **파일 범위** | 2 | 3개 신규 모듈 (feedback_store, feedback_analyzer, prompt_tuner), cli.py 확장 |
| **아키텍처** | 2 | 피드백 데이터 모델, 패턴 분석 엔진, 프롬프트 조정 로직 신규 |
| **의존성** | 1 | SQLite (기존 IntelligenceStorage 확장), 정규식, numpy/scipy (선택사항) |
| **모듈 영향** | 1 | intelligence/ 내부 강화 (gateway, core와 의존성 최소) |
| **데이터 복잡도** | 1 | 피드백 구조 단순, 패턴 분석 규칙 기반 (머신러닝 미포함) |

**위험도**: LOW (기존 Intelligence 아키텍처 하에서 순증분)

---

## 핵심 설계 결정사항

### 1. 피드백 데이터 수집 전략

**원칙**:
- 리뷰 시점(approve/reject)에 강제 피드백 정보 수집 (선택형)
- 최소 정보: `decision` (approve/reject), 선택 정보: `reason`, `modification`
- Reviewer Note와 별도로 구조화된 피드백 필드 유지

**DB 스키마** (feedback_responses 테이블):
```sql
CREATE TABLE feedback_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id INTEGER NOT NULL UNIQUE,
    decision TEXT NOT NULL,              -- 'approved' | 'rejected'
    reason TEXT,                         -- 거부 사유 (e.g., "부정확함", "어조 부적절", "누락")
    modification_summary TEXT,           -- 수정 내용 요약 (승인 전 수정한 경우)
    feedback_quality_score INTEGER,      -- 1-5 (피드백 신뢰도)
    created_at DATETIME,
    FOREIGN KEY (draft_id) REFERENCES draft_responses(id)
);

CREATE INDEX idx_feedback_draft ON feedback_responses(draft_id);
CREATE INDEX idx_feedback_decision ON feedback_responses(decision);
CREATE INDEX idx_feedback_created ON feedback_responses(created_at DESC);
```

### 2. 피드백 패턴 분석

**추적 차원**:
- **Sender별**: sender_id → approve_rate, top_rejection_reasons
- **Project별**: project_id → approve_rate, intent별 패턴
- **Intent별**: intent (질문/요청/정보공유/잡담) → approve_rate, 편향 분석
- **Channel별**: source_channel (slack/email/github) → approve_rate
- **시간별**: 일일/주간 추이, 개선 추세

**패턴 식별 규칙** (feedback_analyzer.py):
1. **Rejection Count Pattern**: 같은 sender + project 조합에서 거부 3회 이상
2. **Reason Frequency**: 특정 reason이 거부의 30% 이상 차지
3. **Confidence Mismatch**: Ollama confidence 높았으나 실제 reject 빈번
4. **Intent Skew**: 특정 intent에서만 approve_rate 급락 (< 50%)
5. **Channel Drift**: 채널별로 approve_rate 편차 > 30%

### 3. 프롬프트 자동 조정

**적용 수준** (보수적 접근):
- **Tier 1 (Ollama 프롬프트 조정)**: few-shot 예시 자동 주입
  - Tier 1a: 잘못된 분류 사례 → 명확한 반례 주입
  - Tier 1b: 신뢰도 보정 (confidence 과대평가 패턴 수정)

- **Tier 2 (Draft Writer 프롬프트 조정)**: context 강화 + 특수 지시
  - Tier 2a: 자주 거부되는 tone 패턴 → 명시적 tone 지시 추가
  - Tier 2b: 특정 sender 선호도 → sender profile 컨텍스트 주입

**제약사항**:
- 최소 데이터 수요: Tier 1 조정 시 거부 패턴 20건 이상 필요
- 오버피팅 방지: 특정 sender에 대한 과도한 맞춤화 금지 (가중치 상한선)
- 검증 기간: 조정 후 최소 50건 데이터 수집 후 효과 판정

### 4. 품질 메트릭 및 대시보드

**핵심 KPI**:
- **Approve Rate**: 전체, sender별, project별, intent별, channel별
- **Rejection Reasons Top 5**: 빈도순, 시간별 추이
- **Confidence Calibration**: Ollama confidence와 실제 approve_rate의 상관관계
- **Improvement Trend**: 월간 approve_rate 변화율

**리포트** (`cli.py feedback stats`):
```
=== Feedback Statistics ===
총 피드백: 152건
  - 승인: 128건 (84.2%)
  - 거부: 24건 (15.8%)

[Sender별 Approve Rate]
  sender_A: 92.3% (13/14)
  sender_B: 78.6% (11/14)
  sender_C: 60.0% (3/5)  ← 주의

[거부 사유 Top 5]
  1. 어조 부적절 (8회, 33.3%)
  2. 누락 정보 (6회, 25.0%)
  3. 부정확함 (4회, 16.7%)
  4. 반복 (3회, 12.5%)
  5. 기타 (3회, 12.5%)

[Intent별 Approve Rate]
  질문: 90.0% (18/20)
  요청: 82.5% (33/40)
  정보공유: 88.2% (15/17)
  잡담: 72.7% (8/11)

[월간 개선 추이]
  2026-01: 78.0% (50건)
  2026-02: 84.2% (102건)  ← 6.2% 개선

[프롬프트 조정 히스토리]
  - 2026-02-20: Ollama 프롬프트 + few-shot (어조 에러 대책)
  - 2026-02-25: Draft Writer 프롬프트 tone 명시화
```

---

## 구현 범위

### Phase 1: 피드백 데이터 계층 (T1-T2)

**T1: FeedbackStore 구현** (`intelligence/feedback_store.py`)
- DB 스키마 마이그레이션 (feedback_responses 테이블 추가)
- `save_feedback()`: approve/reject 시 사유/수정 내용 저장
- `get_feedback_by_draft()`, `list_feedback()`: 조회 메서드
- `update_feedback_quality_score()`: 피드백 신뢰도 평점

**T2: CLI 확장** (`cli.py`)
- `drafts approve <id> --reason <reason> [--modification <text>]`
- `drafts reject <id> --reason <reason> [--modification <text>]`
- Reason 선택지: `부정확함`, `어조부적절`, `누락정보`, `반복`, `기타`
- Modification (선택): 사용자가 수정한 내용 요약

### Phase 2: 패턴 분석 엔진 (T3-T4)

**T3: FeedbackAnalyzer 구현** (`intelligence/feedback_analyzer.py`)
- `analyze_rejection_patterns()`: 거부 패턴 식별 (5가지 규칙)
- `calculate_approve_rates()`: sender, project, intent, channel별 approve_rate
- `detect_confidence_mismatch()`: Ollama confidence vs 실제 결과 비교
- `generate_pattern_report()`: 패턴 분석 리포트 생성
- 시간 윈도우: 기본 30일, 조정 가능

**T4: 대시보드/CLI 통합** (`cli.py`)
- `feedback stats [--json] [--days N] [--format table|json]`
- `feedback patterns [--project ID] [--sender ID]`
- `feedback trend [--metric approve_rate|rejection_reasons] [--days 90]`

### Phase 3: 프롬프트 자동 조정 (T5-T6)

**T5: PromptTuner 구현** (`intelligence/prompt_tuner.py`)
- `generate_ollama_few_shots()`: 거부된 메시지를 반례로 변환 → few-shot 프롬프트 생성
- `generate_draft_tone_guidance()`: 거부 reason이 "어조부적절"인 경우 → 명시적 tone 지시 생성
- `apply_sender_profile()`: sender별 선호도 분석 → contextual hint 추가
- `suggest_prompt_adjustments()`: 조정 제안 (수동 승인 워크플로우)

**조정 보수성**:
- 조정은 suggestion 형태로 제시 (자동 적용 금지)
- 각 조정마다 `confidence_threshold` 설정 (거부된 경우만 적용)
- 최대 few-shot 5개 유지 (과도한 추가 금지)

**T6: 프롬프트 버전 관리**
- `config/prompts/analyze_prompt_v1.txt` (원본 baseline)
- `config/prompts/analyze_prompt_v2_tuned.txt` (Tier 1 조정)
- `config/prompts/draft_prompt_v1.txt` (원본)
- `config/prompts/draft_prompt_v2_tuned.txt` (Tier 2 조정)
- Ollama/ClaudeCodeDraftWriter에 버전 선택 파라미터

### Phase 4: 모니터링 및 효과 검증 (T7)

**T7: Feedback Impact Tracker** (`intelligence/feedback_tracker.py`)
- 프롬프트 변경 전후 approve_rate 비교
- A/B 테스트 설계 (변경 전후 50건씩 수집)
- 신뢰도 구간: 95% CI 포함

**추적 메트릭**:
```
Metric: Approve Rate
Before: 78.0% (n=50)
After:  84.2% (n=52)
Improvement: +6.2pp
Confidence: 95% CI [1.2pp, 11.2pp]
Significance: p=0.042 (유의미)
```

---

## 구현 순서 및 의존성

```
T1: FeedbackStore (기본 저장소)
├─ T2: CLI extend (피드백 입력)
├─ T3: FeedbackAnalyzer (패턴 분석)
│  └─ T4: Dashboard CLI (통계 출력)
└─ T5: PromptTuner (프롬프트 생성)
   └─ T6: Version Manager (버전 관리)
      └─ T7: Impact Tracker (효과 검증)
```

**순차 실행**: T1 → T2 → {T3, T5} 병렬 → T4 → T6 → T7

---

## 성공 지표

### 가용성 지표
- [ ] 피드백 DB 스키마 성공적 마이그레이션
- [ ] `drafts approve --reason` 및 `reject --reason` 명령 정상 작동
- [ ] `feedback stats`, `feedback patterns` 명령 정상 출력

### 정성적 지표
- [ ] 월간 approve_rate 추적 가능
- [ ] Reject 패턴 Top-5 자동 식별
- [ ] 프롬프트 개선 제안 자동 생성

### 정량적 지표 (3개월 목표)
- [ ] **Approve Rate 향상**: 초기값 대비 10%+ 개선
- [ ] **Feedback Coverage**: 전체 approve/reject의 70% 이상에 사유 입력
- [ ] **Confidence Calibration**: Ollama confidence와 approval 상관계수 r > 0.6
- [ ] **패턴 안정성**: 동일 패턴 반복 감소 (rejection reason 중복도 < 20%)

---

## 위험 요소 및 완화 전략

| 위험 | 영향도 | 완화 전략 |
|------|:------:|----------|
| **초기 데이터 부족** | HIGH | 최소 50건 feedback 수집 후 분석 시작; 초기 조정 threshold 높게 설정 |
| **오버피팅** | MEDIUM | sender 집중도 분석; 특정 sender > 30% 가중치 제한; 정기 리뷰 |
| **프롬프트 폭발** | LOW | few-shot 최대 5개, 버전 관리 strict, rollback 플랜 준비 |
| **피드백 편향** | MEDIUM | 피드백 quality_score 추적; 저신뢰도 feedback 가중치 감소 |
| **사용자 부담** | MEDIUM | feedback 입력 선택형 (강제 아님); CLI UX 최소화 |

### 실패 정의 및 롤백 전략
- **프롬프트 조정 후 approve_rate 5% 이상 하락** → 즉시 롤백
- **특정 sender approve_rate 급락 (> 20pp)** → sender-specific 조정 비활성화
- **false positive 패턴 20회 이상** → 패턴 detection 규칙 수정

---

## 참고 문서 및 의존성

| 문서 | 경로 | 연관성 |
|------|------|--------|
| Project Intelligence Plan | `docs/01-plan/project-intelligence.plan.md` | 기반 아키텍처 |
| Gateway Design | `docs/02-design/server-workflow.design.md` | Pipeline 참고 |
| Draft Writer Impl | `scripts/intelligence/response/draft_writer.py` | Prompt tuner 참고 |
| Ollama Analyzer | `scripts/intelligence/response/analyzer.py` | Confidence 활용 |
| IntelligenceStorage | `scripts/intelligence/context_store.py` | DB 확장 대상 |

---

## 초기 마일스톤 (4주)

### Week 1: 데이터 계층
- FeedbackStore 구현 및 테스트
- DB 마이그레이션 스크립트 작성

### Week 2: 입력 인터페이스
- CLI approve/reject 확장 (--reason, --modification)
- 첫 20건 사용자 피드백 수집

### Week 3: 패턴 분석
- FeedbackAnalyzer 구현
- Dashboard CLI 출력
- 패턴 리포트 검증

### Week 4: 프롬프트 조정 + 모니터링
- PromptTuner 구현 (제안 모드)
- Impact Tracker 설정
- A/B 테스트 설계

---

## 예상 리소스 및 일정

| 구성 | 예상 시간 | 담당 |
|------|:--------:|------|
| T1 (FeedbackStore) | 4h | executor |
| T2 (CLI extend) | 2h | executor |
| T3 (FeedbackAnalyzer) | 6h | architect |
| T4 (Dashboard) | 3h | executor |
| T5 (PromptTuner) | 8h | architect |
| T6 (Version Mgr) | 2h | executor |
| T7 (Impact Tracker) | 4h | architect |
| **합계** | **29h** | - |

**예상 일정**: 2-3주 (parallel execution)

---

## 다음 단계

1. **Ralplan 합의**: 이 계획을 architect, planner, critic과 검토
2. **설계 문서 작성**: `docs/02-design/feedback-loop.design.md`
3. **테스트 전략 수립**: 테스트 우선(TDD) 기반 구현
4. **초기 데이터 수집**: 피드백 threshold 낮춰 먼저 20건 수집
5. **주간 리뷰**: 매주 패턴 분석 결과 검토 및 조정

---

## 부록 A: 예시 피드백 입력 워크플로우

```bash
# 초안 조회
python cli.py drafts --status pending

# 초안 #42 승인 (이유 입력)
python cli.py drafts approve 42 --reason "정확하고 전문적" --modification "tone 조정함"

# 초안 #43 거부 (이유 필수)
python cli.py drafts reject 43 --reason "어조부적절" --modification "더 존중하는 톤으로 수정 필요"

# 피드백 통계 조회
python cli.py feedback stats --json

# 거부 패턴 분석
python cli.py feedback patterns --project secretary

# 월간 개선 추이
python cli.py feedback trend --metric approve_rate --days 90
```

---

## 부록 B: 데이터 마이그레이션 스크립트 개요

```python
# scripts/intelligence/migrations/001_add_feedback_responses.py

async def migrate():
    """feedback_responses 테이블 추가"""
    storage = IntelligenceStorage()
    await storage.connect()

    migrations = [
        """CREATE TABLE IF NOT EXISTS feedback_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            draft_id INTEGER NOT NULL UNIQUE,
            decision TEXT NOT NULL,
            reason TEXT,
            modification_summary TEXT,
            feedback_quality_score INTEGER DEFAULT 5,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (draft_id) REFERENCES draft_responses(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_feedback_draft ON feedback_responses(draft_id)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_decision ON feedback_responses(decision)",
        "CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback_responses(created_at DESC)",
    ]

    for sql in migrations:
        await storage._connection.execute(sql)
    await storage._connection.commit()
    await storage.close()
```

---

**승인자**: (Ralplan 진행 예정)
**최종 검토**: 2026-02-18
