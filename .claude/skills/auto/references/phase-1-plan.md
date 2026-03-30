# /auto Phase 1: PLAN — 상세 워크플로우

> 이 파일은 `/auto` Phase 1 진입 시 로딩됩니다. SKILL.md에서 Phase 1 시작 시 이 파일을 Read합니다.
> 원본: REFERENCE.md v25.0에서 분리 (v25.2 Progressive Disclosure)

---

## Phase 0, Step 0.2: Socratic Questioning (모호성 >= 0.5 시)

Ambiguity Score >= 0.5 감지 후, 구현 전 사용자 의도를 명확화하는 자동 질문 단계.

### Step 0.2a: Ambiguity Score 계산

```python
# Phase 0.2a — 사용자 요청의 모호성을 7개 팩터로 정량 측정
def calculate_ambiguity_score(user_request: str, current_phase: str) -> float:
    score = 0.0
    factors_triggered = []

    # F1: 파일 경로 미언급 (+0.15)
    if not contains_file_path(user_request):  # /, \, .ext 패턴 없음
        score += 0.15
        factors_triggered.append("no_file_path")

    # F2: 기술 용어 부재 (+0.10)
    if not contains_tech_terms(user_request):  # API, 함수명, 클래스명, 라이브러리명 없음
        score += 0.10
        factors_triggered.append("no_tech_terms")

    # F3: 특정 대상 미지정 (+0.15)
    if not contains_identifiers(user_request):  # PascalCase, snake_case, 따옴표 리터럴 없음
        score += 0.15
        factors_triggered.append("no_identifiers")

    # F4: 범위 미정의 (+0.10)
    if not contains_scope_qualifiers(user_request):  # only, all, specific, 단일, 전체 등 한정어 없음
        score += 0.10
        factors_triggered.append("no_scope")

    # F5: 다중 해석 가능 (+0.20) — 가장 높은 가중치
    if has_ambiguous_verbs(user_request) or pronoun_count(user_request) >= 2:
        # 모호 동사: fix, change, update, improve, handle, make, do
        score += 0.20
        factors_triggered.append("multi_interpretation")

    # F6: 컨텍스트 충돌 (+0.15)
    if phase_keyword_mismatch(user_request, current_phase):
        # 예: BUILD Phase에서 "설계 변경" 요청
        score += 0.15
        factors_triggered.append("context_conflict")

    # F7: 짧은 요청 (+0.15)
    if len(user_request) < 30:
        score += 0.15
        factors_triggered.append("short_request")

    return score, factors_triggered
    # 최대 합계: 1.00 (전 팩터 트리거 시)
```

**Magic Word Bypass**: `!quick`, `!just`, `!hotfix` 감지 시 score = 0 강제 (Socratic Questioning 전체 스킵).

### Step 0.2b: 팩터→차원 매핑 (질문 선별)

트리거된 팩터가 어떤 차원의 질문을 생성하는지 결정:

| 팩터 (Factor) | 가중치 | 매핑 차원 (Dimension) | 질문 생성 조건 |
|---------------|:------:|----------------------|---------------|
| F1: no_file_path | 0.15 | 범위 (Scope) | 파일/디렉토리 경로 없으면 범위 질문 |
| F2: no_tech_terms | 0.10 | 제약 (Constraints) | 기술 맥락 불명이면 제약 조건 질문 |
| F3: no_identifiers | 0.15 | 범위 (Scope) | 대상 불명이면 범위 재확인 |
| F4: no_scope | 0.10 | 수용 기준 (Acceptance) | 범위 미정이면 완료 기준 질문 |
| F5: multi_interpretation | 0.20 | 우선순위 (Priority) | 다중 해석이면 우선순위 질문 |
| F6: context_conflict | 0.15 | 목적 (Purpose) | Phase 불일치면 목적 재확인 |
| F7: short_request | 0.15 | 목적 (Purpose) | 정보 부족이면 목적 질문 |

**선별 알고리즘**:
1. 목적(Purpose)은 항상 포함 (가장 중요한 차원)
2. 나머지 4차원 중 트리거된 팩터 가중치 합산 → 상위 2개 차원 선택
3. 최종 3개 질문 (목적 1 + 상위 2)

```python
# Step 0.2b — 질문 선별
def select_questions(factors_triggered: list) -> list:
    # 목적은 항상 포함
    selected = ["purpose"]

    # 팩터→차원 가중치 집계
    dimension_scores = {
        "scope": 0, "constraints": 0, "priority": 0, "acceptance": 0
    }
    factor_to_dim = {
        "no_file_path": "scope", "no_tech_terms": "constraints",
        "no_identifiers": "scope", "no_scope": "acceptance",
        "multi_interpretation": "priority", "context_conflict": "purpose",
        "short_request": "purpose"
    }
    factor_weights = {
        "no_file_path": 0.15, "no_tech_terms": 0.10, "no_identifiers": 0.15,
        "no_scope": 0.10, "multi_interpretation": 0.20,
        "context_conflict": 0.15, "short_request": 0.15
    }
    for f in factors_triggered:
        dim = factor_to_dim[f]
        if dim != "purpose":  # purpose는 이미 선택됨
            dimension_scores[dim] += factor_weights[f]

    # 상위 2개 차원 선택
    top_2 = sorted(dimension_scores, key=dimension_scores.get, reverse=True)[:2]
    selected.extend(top_2)
    return selected  # 항상 3개
```

### Step 0.2c: 질문 생성 프롬프트

선별된 3개 차원에 대해 사용자 요청 컨텍스트를 반영한 구체적 질문을 생성:

```
# Lead가 AskUserQuestion으로 전달할 질문 생성 프롬프트
사용자 요청: "{user_request}"
트리거된 팩터: {factors_triggered}
선별된 차원: {selected_dimensions}

아래 차원별 템플릿을 사용자 요청에 맞게 구체화하세요.
각 질문은 1문장, 사용자가 바로 답할 수 있는 구체적 형태여야 합니다.
전문 용어 대신 평이한 한글을 사용하세요.

---
차원별 질문 템플릿:

[목적 Purpose]
- 기본: "이 작업으로 달성하려는 핵심 결과는 무엇인가요?"
- 구체화: "{user_request}의 최종 목표가 [A]인가요, [B]인가요?"
  (요청에서 추론 가능한 2개 선택지를 제시)

[범위 Scope]
- 기본: "변경 범위가 어디까지인가요?"
- 구체화 (F1 트리거): "어떤 파일/폴더를 수정해야 하나요?"
- 구체화 (F3 트리거): "구체적으로 어떤 함수/컴포넌트를 변경하나요?"

[제약 Constraints]
- 기본: "지켜야 할 기술적 제약이 있나요?"
- 구체화: "기존 {관련_시스템}과의 호환성을 유지해야 하나요?"
- 구체화: "성능/메모리/시간 제약이 있나요?"

[우선순위 Priority]
- 기본: "여러 변경 중 가장 먼저 해결할 것은?"
- 구체화: "요청에서 [A], [B], [C]가 감지되었는데, 우선순위는?"
  (요청에서 추출한 세부 항목을 나열)

[수용 기준 Acceptance]
- 기본: "완료로 판단할 구체적 기준은?"
- 구체화: "어떤 테스트/동작이 확인되면 완료인가요?"
- 구체화: "기존 동작이 변경되어도 괜찮나요?"
```

### Step 0.2d: 답변 처리 및 InitContract 반영

```python
# Step 0.2d — 답변을 InitContract에 구조화하여 반영
def process_socratic_answers(answers: list, init_contract: dict) -> dict:
    """
    사용자 답변을 InitContract.clarifications에 구조화.
    이후 Phase 1 (PRD, Plan)에서 참조.
    """
    clarifications = []
    for answer in answers:
        clarifications.append({
            "dimension": answer["dimension"],  # purpose/scope/constraints/priority/acceptance
            "question": answer["question"],
            "answer": answer["user_answer"],
        })

    init_contract["clarifications"] = clarifications

    # 답변 기반 복잡도 재조정 (선택적)
    # 범위 답변이 "시스템 전체"면 복잡도 +1
    for c in clarifications:
        if c["dimension"] == "scope" and "전체" in c["answer"]:
            init_contract["complexity_score"] = min(6, init_contract["complexity_score"] + 1)
        # 제약 답변이 구체적이면 STANDARD 이상 강제
        if c["dimension"] == "constraints" and len(c["answer"]) > 50:
            init_contract["complexity_score"] = max(2, init_contract["complexity_score"])

    return init_contract
```

### Step 0.2 전체 흐름 요약

```
사용자 요청 수신
  │
  ├─ Magic Word (!quick/!just/!hotfix) 감지? ──YES──→ score=0, 스킵
  │
  └─ Step 0.2a: Ambiguity Score 계산
       │
       ├─ score < 0.5 ──→ 질문 없이 Phase 0.3으로 진행
       │
       └─ score >= 0.5
            │
            ├─ Step 0.2b: 팩터→차원 매핑 → 3개 차원 선별
            ├─ Step 0.2c: 질문 생성 (차원별 템플릿 구체화)
            ├─ AskUserQuestion(3개 질문, 한 번에 전달)
            └─ Step 0.2d: 답변 → InitContract.clarifications 반영
                          + 복잡도 재조정 (scope/constraints 기반)
```

---

## Phase 0, Step 0.3: Adaptive Model Routing (Task 자동 분류)

Phase 0에서 Task 특성을 자동 분류하여 에이전트별 최적 모델을 선택합니다.

```
# Phase 0.3 — Task 복잡도 자동 감지
def classify_task(user_request, affected_files):
    file_count = len(affected_files)
    keywords = extract_keywords(user_request)

    if file_count <= 1 and any(k in keywords for k in ["format", "typo", "rename", "summary"]):
        return "TRIVIAL"    # → Haiku 항상
    elif file_count <= 5 and not any(k in keywords for k in ["refactor", "debug", "design", "architect"]):
        return "STANDARD"   # → Sonnet (기본)
    elif any(k in keywords for k in ["refactor", "debug", "design"]):
        return "COMPLEX"    # → Opus (기본)
    elif any(k in keywords for k in ["architect", "system", "migration", "breaking"]):
        return "CRITICAL"   # → Opus 항상
    else:
        return "STANDARD"   # 기본값

# --eco 옵션 결합
def apply_eco_override(classification, eco_level):
    if eco_level == "eco":
        # Opus → Sonnet
        return "STANDARD" if classification in ("COMPLEX", "CRITICAL") else classification
    elif eco_level == "eco-2":
        # + 비핵심 Sonnet → Haiku
        return "TRIVIAL" if classification == "STANDARD" else "STANDARD"
    elif eco_level == "eco-3":
        return "TRIVIAL"  # 전부 Haiku
    return classification
```

**InitContract 확장**: `"adaptive_tier": "TRIVIAL|STANDARD|COMPLEX|CRITICAL"` 필드 추가.

---

## Phase 1, Step 1.1: PRD (요구사항 문서화 — 구현 전 필수)

> **CRITICAL**: 요구사항 요청 시 반드시 PRD 문서를 먼저 생성/수정한 후 구현을 진행합니다.
> **목적**: 사용자 요구사항을 공식 문서화하여 구현 범위를 명확히 하고, 이후 Phase에서 PRD를 기준으로 검증합니다.
> **스킵 조건**: `--skip-prd` 옵션 명시 시 스킵 가능.

### Step 1.1.1: 기존 PRD 탐색

```
# docs/00-prd/ 디렉토리에서 기존 PRD 탐색
existing_prd = Glob("docs/00-prd/{feature}*.prd.md")

# 관련 PRD가 없으면 docs/00-prd/ 전체 탐색하여 연관 문서 확인
if not existing_prd:
    all_prds = Glob("docs/00-prd/*.prd.md")
    # 유사 이름이나 관련 주제의 PRD가 있으면 참조 대상으로 표시
```

### Step 1.1.2: PRD 생성 또는 수정

**신규 PRD 생성 (기존 PRD 없음):**
```
Agent(subagent_type="executor-high", name="prd-writer", description="PRD 문서 작성", team_name="pdca-{feature}",
     prompt="[Phase 1 PRD 생성] 사용자 요구사항을 PRD 문서로 작성하세요.

     === 사용자 요청 ===
     {user_request}

     === 기존 관련 PRD 요약 ===
     {existing_prds_summary}  (없으면 '없음')

     === PRD 템플릿 (필수 섹션) ===

     # {feature} PRD

     ## 0. Market Context (선택)
     - 시장 배경 / 고객 페인포인트
     - 비즈니스 Impact 범위
     - Target Segment / Volume
     - Appetite: {Small 2주 | Big 6주} (이 기능에 투자할 시간 예산)

     ## 1. 배경 및 목적
     - 왜 이 기능/변경이 필요한지
     - 해결하려는 문제

     ## 2. 요구사항
     ### 2.1 기능 요구사항 (Functional Requirements)
     - FR-001: {요구사항 1}
     - FR-002: {요구사항 2}
     (각 요구사항에 번호 부여, 검증 가능한 수준으로 구체적 기술)

     ### 2.2 비기능 요구사항 (Non-Functional Requirements)
     - NFR-001: 성능, 보안, 접근성 등 해당 사항

     ## 3. 기능 범위 (Scope)
     ### 3.1 포함 (In Scope)
     - 이번에 구현할 항목
     ### 3.2 제외 (Out of Scope)
     - 이번에 구현하지 않을 항목

     ## 4. 제약사항 (Constraints)
     - 기술적 제약, 일정 제약, 의존성

     ## 5. 우선순위 (Priority)
     | 요구사항 | 우선순위 | 근거 |
     |---------|---------|------|
     | FR-001  | P0 필수 | ... |
     | FR-002  | P1 권장 | ... |

     ## 6. 수용 기준 (Acceptance Criteria)
     - AC-001: {검증 가능한 수용 기준}
     - AC-002: ...

     ## Changelog
     | 날짜 | 변경 내용 | 작성자 |
     |------|---------|--------|
     | {오늘 날짜} | 초기 작성 | auto |

     === 출력 ===
     파일 경로: docs/00-prd/{feature}.prd.md
     디렉토리가 없으면 생성하세요.")
SendMessage(type="message", recipient="prd-writer", content="PRD 문서 작성 시작.")
# 완료 대기 → shutdown_request
```

**기존 PRD 수정 (PRD 존재 시):**
```
Agent(subagent_type="executor-high", name="prd-writer", description="PRD 문서 작성", team_name="pdca-{feature}",
     prompt="[Phase 1 PRD 수정] 기존 PRD를 새 요구사항에 맞게 수정하세요.

     === 기존 PRD 파일 ===
     docs/00-prd/{existing_prd_file}

     === 추가/변경 요구사항 ===
     {user_request}

     === 수정 규칙 ===
     1. 기존 요구사항(FR-xxx)은 보존하되, 변경된 항목은 명시적으로 표시
     2. 새 요구사항은 기존 번호 체계에 이어서 추가 (FR-003, FR-004 ...)
     3. 삭제된 요구사항은 ~~취소선~~ 처리 (이력 보존)
     4. ## Changelog 섹션에 변경 이력 추가
     5. 범위(Scope) 섹션도 요구사항 변경에 맞게 갱신
     6. 수용 기준(Acceptance Criteria)도 요구사항 변경에 맞게 갱신")
SendMessage(type="message", recipient="prd-writer", content="PRD 수정 시작.")
# 완료 대기 → shutdown_request
```

### Step 1.1.3: 사용자 승인 (MANDATORY)

```
# PRD 내용을 사용자에게 제시
prd_content = Read("docs/00-prd/{feature}.prd.md")

# 사용자에게 PRD 요약 출력
print("=== PRD 작성 완료 ===")
print("파일: docs/00-prd/{feature}.prd.md")
print("요구사항 {N}건, 수용 기준 {M}건")
print("========================")

# AskUserQuestion으로 승인 요청
AskUserQuestion:
  question: "PRD 문서를 확인해주세요. 진행 방식을 선택하세요."
  options:
    - "승인 (Phase 1 PLAN 진입)"
    - "수정 요청 (PRD 수정 후 재확인)"
    - "직접 수정 (사용자가 PRD 파일 직접 편집)"

# 승인 → Phase 1 진입
# 수정 요청 → 사용자 피드백 반영 후 Step 1.1.2 재실행 (max 3회)
# 직접 수정 → 사용자가 파일 편집 완료 후 Phase 1 진입
# 3회 수정 초과 → 현재 PRD로 Phase 1 진입 + 경고 출력
```

### PRD→Phase 1 Gate

PRD 승인 후 Phase 1 진입 전 최소 검증:

| # | 검증 항목 | 확인 방법 |
|:-:|----------|----------|
| 1 | PRD 파일 존재 | `docs/00-prd/{feature}.prd.md` 존재 |
| 2 | 요구사항 1건 이상 | `FR-` 패턴 1개 이상 존재 |
| 3 | 수용 기준 1건 이상 | `AC-` 패턴 1개 이상 존재 |

미충족 시: PRD 보완 후 재검증 (1회). 2회 실패 → Phase 1 진입 허용 (경고 포함).

### PRD와 이후 Phase 연계

| Phase | PRD 활용 |
|-------|---------|
| Phase 1 PLAN | Planner가 PRD 참조하여 계획 수립 |
| Phase 1 DESIGN | Design 문서에 PRD 요구사항 번호 매핑 |
| Phase 2 BUILD | impl-manager가 PRD 요구사항 기반 구현 |
| Phase 3 VERIFY | Architect가 PRD 수용 기준 기반 검증 |
| Phase 4 CLOSE | 보고서에 PRD 대비 달성률 포함 |

---

## Phase 1, Steps 1.2-1.3: PLAN (사전 분석 → 복잡도 판단 → 계획 수립)

### Step 1.0: 사전 분석 (병렬 Teammates)

```
# 병렬 spawn (독립 작업)
Agent(subagent_type="explore", name="doc-analyst", description="문서 탐색 분석", team_name="pdca-{feature}", prompt="docs/, .claude/ 내 관련 문서 탐색. 중복 범위 감지 필수. 결과를 5줄 이내로 요약.")

Agent(subagent_type="explore", name="issue-analyst", description="이슈 탐색 분석", team_name="pdca-{feature}", prompt="gh issue list 실행하여 유사 이슈 탐색. 연관 이슈 태깅 필요. 결과를 5줄 이내로 요약.")

# [Intent Inference] analyst(sonnet) — 사용자 의도 심층 분석
Agent(subagent_type="analyst", name="intent-analyst", description="사용자 의도 심층 분석", team_name="pdca-{feature}",
     prompt="[Phase 1 Intent Analysis] 사용자 요청의 의도를 심층 분석하세요.
             사용자 요청: {user_request}
             분석 항목:
             1. 명시적 요구사항 — 사용자가 직접 말한 것
             2. 암묵적 요구사항 — 당연히 기대하지만 말하지 않은 것
             3. 배경 맥락 — 왜 이 요청을 했는지 동기 추론
             4. 범위 경계 — 포함/제외 판단 (과잉 구현 방지)
             5. 위험 시나리오 2건+ — 잘못 해석하면 발생할 문제
             6. Planner 핵심 지시 (3줄 이내) — 계획 수립 시 반드시 반영할 사항
             코드베이스를 Glob/Grep으로 탐색하여 기술적 맥락을 파악한 뒤 분석하세요.")

# Mailbox로 결과 수신 후 모든 teammate shutdown_request
SendMessage(type="shutdown_request", recipient="doc-analyst")
SendMessage(type="shutdown_request", recipient="issue-analyst")
SendMessage(type="shutdown_request", recipient="intent-analyst")
```

**산출물**: 문서 중복 여부, 연관 이슈 번호, Intent Analysis (Phase 1.3에 사용)

### Step 1.1: 복잡도 점수 판단 (MANDATORY - 6점 만점)

| # | 조건 | 1점 기준 | 0점 기준 |
|:-:|------|---------|---------|
| 1 | **파일 범위** | 3개 이상 파일 수정 예상 | 1-2개 파일 |
| 2 | **아키텍처** | 새 패턴/구조 도입 | 기존 패턴 내 수정 |
| 3 | **의존성** | 새 라이브러리/서비스 추가 | 기존 의존성만 사용 |
| 4 | **모듈 영향** | 2개 이상 모듈/패키지 영향 | 단일 모듈 내 변경 |
| 5 | **사용자 명시** | `ralplan` 키워드 포함 | 키워드 없음 |
| 6 | **Appetite 선언** | "제대로/production-ready" 명시 | "빠르게/간단히/hotfix" 또는 미선언 |

**판단 로그 출력 (항상 필수):**
```
=== 복잡도 판단 ===
파일 범위: {0|1}점 ({근거})
아키텍처: {0|1}점 ({근거})
의존성:   {0|1}점 ({근거})
모듈 영향: {0|1}점 ({근거})
사용자 명시: {0|1}점
Appetite: {0|1}점 ({빠르게→0 | 제대로→1 | 미선언→0})
총점: {score}/6 -> {LIGHT|STANDARD|HEAVY}
===================
```

**복잡도 모드:**
- **0-1점**: LIGHT (간단, executor-high 단일)
- **2-3점**: STANDARD (보통, executor-high 루프)
- **4-6점**: HEAVY (복잡, Planner-Critic Loop)

### Step 1.1b: Plugin Activation Scan (Phase 0.4)

복잡도 판단 직후, 프로젝트 루트 파일 감지 + 복잡도 모드 기반으로 플러그인을 자동 활성화합니다.
상세 매핑 테이블: `references/plugin-fusion-rules.md`

```python
# Phase 0.4 — Lead가 직접 실행하는 플러그인 감지 로직
activated_plugins = []

# 1. Project Type Detection
if Glob("tsconfig.json"):
    activated_plugins.append("typescript-lsp")
if Glob("package.json"):
    pkg = Read("package.json")
    if '"react"' in pkg or '"next"' in pkg:
        activated_plugins.extend(["frontend-design", "code-review"])
    else:
        activated_plugins.append("code-review")
if Glob("next.config.*"):
    activated_plugins.append("frontend-design")
if Glob("pyproject.toml") or Glob("setup.py") or Glob("*.py"):
    activated_plugins.append("code-review")
if Glob(".claude/"):
    activated_plugins.extend(["claude-code-setup", "superpowers"])

# 2. Complexity-Tier Escalation
if mode in ["STANDARD", "HEAVY"]:
    activated_plugins.extend(["superpowers", "code-review"])
if mode == "HEAVY":
    activated_plugins.extend(["feature-dev", "claude-code-setup"])

# 3. Deduplicate
activated_plugins = list(set(activated_plugins))

# 4. Iron Laws 주입 (superpowers 활성 시)
iron_laws = ""
if "superpowers" in activated_plugins:
    iron_laws = Read("C:\\claude\\.claude\\references\\plugin-fusion-rules.md")
    # Section 8 Iron Laws를 impl-manager/QA/Gate prompt에 주입

# 5. 활성화 로그 출력 (항상 필수)
# === Plugin Activation ===
# 프로젝트 타입: {detected_types}
# 복잡도 모드: {mode}
# 활성 플러그인: {activated_plugins}
# Iron Laws: {TDD, Debugging, Verification}
# ===========================
```

**Iron Laws prompt 주입 (superpowers 흡수):**

impl-manager, QA Runner, Architect Gate prompt에 아래를 추가:

```
=== Iron Laws (MANDATORY) ===
1. TDD: 실패 테스트 없이 프로덕션 코드 작성 금지. 테스트 먼저 작성.
2. Debugging: Root cause 조사 없이 수정 금지. D0-D4 체계 준수.
3. Verification: 증거 없이 완료 선언 금지. 빌드/테스트/lint 결과 첨부 필수.
```

### Step 1.2: 계획 수립 (명시적 호출)

**LIGHT (0-1점): Planner sonnet teammate**
```
Agent(subagent_type="planner", name="planner", description="계획 수립", team_name="pdca-{feature}", prompt="... (복잡도: LIGHT {score}/6, 단일 파일 수정 예상).
     PRD 참조: docs/00-prd/{feature}.prd.md (있으면 반드시 기반으로 계획 수립).
     PRD의 요구사항 번호(FR-xxx)를 Plan 항목에 매핑하세요.
     사용자 확인/인터뷰 단계를 건너뛰세요. 바로 계획 문서를 작성하세요.
     === Intent Analysis (Step 1.0 산출물) ===
             {intent_analysis_result}
             위 분석의 암묵적 요구사항과 범위 경계를 계획에 반영하세요.
     === Mermaid 다이어그램 규칙 ===
             한 레벨 노드 최대 4개 (5개+ 시 subgraph 분할). 줄바꿈: <br/> 사용 (\n 금지). 노드 6개+ 시 단계적 빌드업.
     docs/01-plan/{feature}.plan.md 생성.")
SendMessage(type="message", recipient="planner", content="계획 수립 시작. 완료 후 TaskUpdate로 completed 처리.")
# 완료 대기 → shutdown_request
```

**STANDARD (2-3점): Planner opus teammate**
```
Agent(subagent_type="planner", name="planner", description="계획 수립", team_name="pdca-{feature}", prompt="... (복잡도: STANDARD {score}/6, 판단 근거 포함).
     PRD 참조: docs/00-prd/{feature}.prd.md (있으면 반드시 기반으로 계획 수립).
     PRD의 요구사항 번호(FR-xxx)를 Plan 항목에 매핑하세요.
     사용자 확인/인터뷰 단계를 건너뛰세요. 바로 계획 문서를 작성하세요.
     === Intent Analysis (Step 1.0 산출물) ===
             {intent_analysis_result}
             위 분석의 암묵적 요구사항과 범위 경계를 계획에 반영하세요.
     === Mermaid 다이어그램 규칙 ===
             한 레벨 노드 최대 4개 (5개+ 시 subgraph 분할). 줄바꿈: <br/> 사용 (\n 금지). 노드 6개+ 시 단계적 빌드업.
     docs/01-plan/{feature}.plan.md 생성.")
SendMessage(type="message", recipient="planner", content="계획 수립 시작. 완료 후 TaskUpdate로 completed 처리.")
# 완료 대기 → shutdown_request
```

**HEAVY (4-6점): Planner-Critic Loop (max 5 iterations)**

```
critic_feedback = ""      # Lead 메모리에서 관리
iteration_count = 0

Loop (max 5 iterations):
  iteration_count += 1

  # Step A: Planner Teammate
  Agent(subagent_type="planner", name="planner-{iteration_count}", description="계획 수립 반복",
       team_name="pdca-{feature}",
       prompt="[Phase 1 HEAVY] 계획 수립 (Iteration {iteration_count}/5).
               작업: {user_request}
               이전 Critic 피드백: {critic_feedback}
               계획 문서 작성 후 사용자 확인 단계를 건너뛰세요.
               Critic teammate가 reviewer 역할을 대신합니다.
               계획 완료 시 바로 '계획 작성 완료' 메시지를 전송하세요.
               필수 포함: 배경, 구현 범위, 영향 파일, 위험 요소.
               === Intent Analysis (Step 1.0 산출물) ===
               {intent_analysis_result}
               위 분석의 암묵적 요구사항과 범위 경계를 계획에 반영하세요.
               === Mermaid 다이어그램 규칙 ===
               한 레벨 노드 최대 4개 (5개+ 시 subgraph 분할). 줄바꿈: <br/> 사용 (\n 금지). 노드 6개+ 시 단계적 빌드업.
               출력: docs/01-plan/{feature}.plan.md")
  SendMessage(type="message", recipient="planner-{iteration_count}", content="계획 수립 시작.")
  # 결과 수신 대기 → shutdown_request

  # Step B: Architect Teammate
  Agent(subagent_type="architect", name="arch-{iteration_count}", description="기술적 타당성 검증",
       team_name="pdca-{feature}",
       prompt="[Phase 1 HEAVY] 기술적 타당성 검증.
               Plan 파일: docs/01-plan/{feature}.plan.md
               검증 항목: 1. 파일 경로 존재 여부 2. 의존성 충돌 3. 아키텍처 일관성 4. 성능/보안 우려
               소견을 5줄 이내로 요약하세요.")
  SendMessage(type="message", recipient="arch-{iteration_count}", content="타당성 검증 시작.")
  # 결과 수신 대기 → shutdown_request

  # Step C: Critic Teammate (Adversarial Weakness Analyzer)
  Agent(subagent_type="critic", name="critic-{iteration_count}", description="adversarial 약점 분석",
       team_name="pdca-{feature}",
       prompt="[Phase 1 HEAVY] Adversarial Plan 공격 (Iteration {iteration_count}/5).
               Plan 파일: docs/01-plan/{feature}.plan.md
               Architect 소견: {architect_feedback}
               이전 iteration 약점 수정 이력: {previous_weakness_fixes}
               당신은 adversarial 분석자입니다. 이 문서의 약점, 결함, 모순, 누락만 찾으세요.
               === 7가지 공격 벡터 ===
               A1 논리적 결함: 빠진 단계, 근거 없는 가정, 순환 논리
               A2 실패 시나리오: 외부 의존성 실패, 해피패스 붕괴, 미처리 엣지 케이스
               A3 모호성: '적절히','필요 시','가능하면','등' 등 모호어, 측정 불가 기준
               A4 내부 모순: 섹션 간 불일치, 기존 아키텍처 충돌, 목표-범위 불일치
               A5 누락 컨텍스트: 미존재 파일 참조, 미언급 의존성, 미고려 이해관계자
               A6 과잉 설계: 요구사항에 없는 기능/추상화, 조기 최적화, 범위 확장
               A7 OOP 설계 위반: 제어 결합도(3+), God Module(응집도 6-7), 순환 의존성, DIP 위반, 공통 결합도
               모든 벡터에서 공격하세요. 약점마다 문제-위치-영향을 명시하세요.
               이해할 수 없거나 도메인 지식이 부족한 부분은 QUESTION으로 표시하세요.
               반드시 첫 줄에 VERDICT: DESTROYED, VERDICT: QUESTION, 또는 VERDICT: SURVIVED를 출력하세요.
               SURVIVED는 Critical 0건 + Major 0건일 때만. 첫 iteration에서 SURVIVED는 거의 불가능합니다.")
  SendMessage(type="message", recipient="critic-{iteration_count}", content="Plan 공격 시작.")
  # 결과 수신 대기 → shutdown_request

  # Step D: Lead 판정
  critic_message = Mailbox에서 수신한 critic 메시지
  first_line = critic_message의 첫 줄

  if "VERDICT: SURVIVED" in first_line:
      → Loop 종료, Phase 2 진입
  elif "VERDICT: QUESTION" in first_line:
      → Loop 즉시 중단
      → critic_message에서 질문 목록 추출
      → AskUserQuestion으로 사용자에게 질문 전달
      → 사용자 답변을 다음 iteration의 previous_weakness_fixes에 주입
      → 다음 iteration 재개
  elif "VERDICT: DESTROYED" in first_line:
      → critic_feedback = critic_message에서 VERDICT: 줄 이후 전체 (약점 목록)
      → 누적 피드백이 1,500t 초과 시 최신 2회분만 유지
        (이전: "Iteration {N}: {핵심 요약 1줄}" 형태로 압축)
      → Planner에게 critic_feedback 전달하여 문서 재설계
      → 다음 iteration
  else:
      → DESTROYED로 간주 (안전 기본값)

  if iteration_count >= 5 and not SURVIVED:
      → # 설계 자체에 근본적 문제가 있음 — 강제 통과 금지
      → 미해결 약점 요약 보고서 작성 (남은 Critical/Major 약점 전체 목록)
      → AskUserQuestion으로 사용자에게 보고:
        "Critic 5회 반복 후에도 다음 약점이 해결되지 않았습니다: {남은 약점 요약}.
         설계 자체에 근본적 문제가 있을 수 있습니다."
        옵션:
        1. "요구사항 재정의" → Phase 1 처음부터 재시작 (PRD 재검토)
        2. "미해결 약점 수용 후 진행" → Plan에 WARNING 섹션 추가 + Phase 2 진입
        3. "작업 중단" → wip 커밋 + TeamDelete + 세션 종료
```

**Critic 판정 파싱 규칙:**
- 판정 추출: Critic 메시지 첫 줄에서 `VERDICT: DESTROYED`, `VERDICT: QUESTION`, 또는 `VERDICT: SURVIVED` 키워드 확인
- 키워드 불일치: 첫 줄에 VERDICT 없으면 DESTROYED로 간주
- DESTROYED 시: `VERDICT:` 줄 이후 전체 약점 목록을 critic_feedback에 저장 → Planner에게 전달하여 문서 재설계
- QUESTION 시: Loop 즉시 중단 → 질문 목록 추출 → AskUserQuestion으로 사용자에게 전달 → 답변 후 다음 iteration 재개
- 피드백 1,500t 이하: 전체 누적 유지 / 초과: 최신 2회분 전문 + 이전은 1줄 압축 / 5회 초과: 사용자 보고 + 판단 요청 (강제 통과 금지)

**산출물**: `docs/01-plan/{feature}.plan.md`

### Step 1.2 LIGHT: Lead Quality Gate (v22.1)

LIGHT(0-1점) 모드에서 Planner(sonnet) 완료 후 Lead가 직접 수행하는 최소 검증:

```
# Lead Quality Gate (에이전트 추가 비용: 0)
plan_content = Read("docs/01-plan/{feature}.plan.md")

# 조건 1: plan 파일 존재 + 내용 있음 (빈 파일 거부)
if not plan_content or len(plan_content.strip()) < 50:
    → Planner 1회 재요청 ("계획 내용이 부족합니다. 최소 배경, 구현 범위, 영향 파일을 포함하세요.")

# 조건 2: 파일 경로 1개 이상 언급
if no file path pattern (e.g., "src/", ".py", ".ts", ".md") found:
    → Planner 1회 재요청 ("구현 대상 파일 경로를 1개 이상 포함하세요.")

# 미충족 시 1회만 재요청. 2회째 실패 → 그대로 Phase 2 진입 (LIGHT이므로 과도한 차단 불필요)
```

### Step 1.2 STANDARD: Critic-Lite 단일 검토 (v22.1)

STANDARD(2-3점) 모드에서 Planner(opus) 완료 후 Critic-Lite 1회 검토:

```
Agent(subagent_type="critic", name="critic-lite", description="Critic-Lite 단일 약점 공격", team_name="pdca-{feature}",
     prompt="[Phase 1 STANDARD Critic-Lite] Adversarial Plan 공격 (1회).
             Plan 파일: docs/01-plan/{feature}.plan.md

             당신은 adversarial 분석자입니다. 이 문서의 약점만 찾으세요.
             === 7가지 공격 벡터 ===
             A1 논리적 결함: 빠진 단계, 근거 없는 가정, 순환 논리
             A2 실패 시나리오: 외부 의존성 실패, 해피패스 붕괴, 미처리 엣지 케이스
             A3 모호성: '적절히','필요 시','가능하면','등' 등 모호어, 측정 불가 기준
             A4 내부 모순: 섹션 간 불일치, 기존 아키텍처 충돌, 목표-범위 불일치
             A5 누락 컨텍스트: 미존재 파일 참조, 미언급 의존성
             A6 과잉 설계: 요구사항에 없는 기능/추상화
             A7 OOP 설계 위반: 제어 결합도(3+), God Module(응집도 6-7), 순환 의존성, DIP 위반, 공통 결합도

             반드시 첫 줄에 VERDICT: DESTROYED, VERDICT: QUESTION, 또는 VERDICT: SURVIVED를 출력하세요.
             약점마다 문제-위치-영향을 명시하세요. 이해 불가 시 QUESTION으로 표시.
             SURVIVED는 Critical 0건 + Major 0건일 때만.")
SendMessage(type="message", recipient="critic-lite", content="Plan 공격 시작.")
# 완료 대기 → shutdown_request

# VERDICT 파싱
critic_message = Mailbox에서 수신한 critic-lite 메시지
if "VERDICT: SURVIVED" in first_line:
    → Phase 2 진입
elif "VERDICT: QUESTION" in first_line:
    → 질문 추출 → AskUserQuestion으로 사용자에게 전달 → 답변과 함께 Planner 1회 수정
    → 수정본 수용 (추가 Critic 검토 없음, 무한 루프 방지)
elif "VERDICT: DESTROYED" in first_line:
    → Planner 1회 수정 (critic_feedback = 약점 목록 전달)
    → 수정본 수용 (추가 Critic 검토 없음, 무한 루프 방지)
else:
    → DESTROYED로 간주
```

### Step 1.3: 이슈 연동 (GitHub Issue)

**Step 1.0에서 연관 이슈 발견 시**: `gh issue comment <issue-number> "관련 Plan: docs/01-plan/{feature}.plan.md"`

**신규 이슈 생성 필요 시**: `gh issue create --title "{feature}" --body "Plan: docs/01-plan/{feature}.plan.md" --label "auto"`

---

## Plan→Build Gate: Plan 검증 (MANDATORY)

| # | 필수 섹션 | 확인 방법 |
|:-:|----------|----------|
| 1 | 배경/문제 정의 | `## 배경` 또는 `## 문제 정의` 헤딩 존재 |
| 2 | 구현 범위 | `## 구현 범위` 또는 `## 범위` 헤딩 존재 |
| 3 | 예상 영향 파일 | 파일 경로 목록 포함 |
| 4 | 위험 요소 | `## 위험` 또는 `위험 요소` 헤딩 존재 |

**누락 시**: Plan 문서를 먼저 보완한 후 Phase 2로 진행.

---

## 복잡도 분기 상세 (Phase 1-4 실행 차이)

### LIGHT 모드 (0-1점)

| Phase/Step | 실행 |
|------------|------|
| 1.1 PRD | PRD 생성/수정 + 사용자 승인 (`--skip-prd`로 스킵 가능) |
| 1.2-1.3 PLAN | Explore teammates (haiku) x2 + Planner (sonnet) + Lead Quality Gate |
| 1.4 DESIGN | **스킵** (설계 문서 생성 없음) |
| 2.1 BUILD | Executor teammate (opus) 단일 실행 |
| 2.2-2.3 | — (Code Review, Architect Gate 없음) |
| 3.1 VERIFY | QA Runner 1회 |
| 3.2-3.3 | Architect 최종 검증 (E2E 스킵) |
| 4 CLOSE | sonnet 보고서 |

### STANDARD 모드 (2-3점)

| Phase/Step | 실행 |
|------------|------|
| 1.1 PRD | PRD 생성/수정 + 사용자 승인 (`--skip-prd`로 스킵 가능) |
| 1.2-1.3 PLAN | Explore teammates (haiku) x2 + Planner (opus) + Critic-Lite |
| 1.4 DESIGN | Executor teammate (opus) — 설계 문서 생성 |
| 2.1 BUILD | impl-manager teammate (opus) — 4조건 자체 루프 |
| 2.2-2.3 | Code Review + Architect Gate (외부 검증, max 2회 rejection) |
| 3.1 VERIFY | QA Runner 3회 + Architect 진단 + Domain-Smart Fix |
| 3.2 E2E | E2E 백그라운드 + Architect 최종 검증 |
| 3.3 E2E | E2E 실패 처리 (진단 + Domain-Smart Fix, max 2회) |
| 4 CLOSE | gap < 90% → executor teammate (최대 5회) |

### HEAVY 모드 (4-6점)

| Phase | 실행 |
|-------|------|
| Phase 1.1 | PRD 생성/수정 + 사용자 승인 (`--skip-prd`로 스킵 가능) |
| Phase 1.2-1.3 | Explore teammates (haiku) x2 + Planner-Critic Loop (max 5 iter, A1-A7 adversarial 공격) |
| Phase 1.4 | Executor-high teammate (opus) — 설계 문서 생성 |
| Phase 2.1 | impl-manager teammate (opus) — 4조건 자체 루프 + 병렬 가능 |
| Phase 2.2-2.3 | Code Review + Architect Gate (외부 검증, max 2회 rejection) |
| Phase 3.1 | QA Runner 5회 + Architect 진단 + Domain-Smart Fix |
| Phase 3.2 | E2E 백그라운드 + Architect 최종 검증 |
| Phase 3.3 | E2E 실패 처리 (진단 + Domain-Smart Fix, max 2회) |
| Phase 4 | gap < 90% → executor teammate (최대 5회) |

### 자동 승격 규칙 (Phase 중 복잡도 상향 조정)

| 승격 조건 | 결과 |
|----------|------|
| 빌드 실패 2회 이상 | LIGHT → STANDARD |
| QA 3사이클 초과 (STANDARD→HEAVY만) | STANDARD → HEAVY |
| 영향 파일 5개 이상 | LIGHT/STANDARD → HEAVY |
| Architect REJECT 2회 | 현재 모드 유지, Phase 3 진입 허용 (사용자 알림) |

---

## Phase 1, Step 1.4: DESIGN (설계 통합 — STANDARD/HEAVY만)

> **CRITICAL**: `architect`는 READ-ONLY (Write/Edit 도구 없음). 설계 문서 **생성**에는 executor 계열 사용 필수.

**LIGHT 모드: 스킵** (설계 문서 생성 없음, Phase 2에서 직접 구현)

**STANDARD 모드: Executor opus teammate**
```
Agent(subagent_type="executor-high", name="design-writer", description="설계 문서 작성", team_name="pdca-{feature}",
     prompt="docs/01-plan/{feature}.plan.md를 참조하여 설계 문서를 작성하세요.
     필수 포함: 구현 대상 파일 목록, 인터페이스 설계, 데이터 흐름, 테스트 전략.
     출력: docs/02-design/{feature}.design.md")
SendMessage(type="message", recipient="design-writer", content="설계 문서 생성 요청. 완료 후 TaskUpdate로 completed 처리.")
# 완료 대기 → shutdown_request
```

**HEAVY 모드: Executor-high opus teammate**
```
Agent(subagent_type="executor-high", name="design-writer", description="설계 문서 작성", team_name="pdca-{feature}",
     prompt="docs/01-plan/{feature}.plan.md를 참조하여 설계 문서를 작성하세요.
     필수 포함: 구현 대상 파일 목록, 인터페이스 설계, 데이터 흐름, 테스트 전략, 예상 위험 요소.
     출력: docs/02-design/{feature}.design.md")
SendMessage(type="message", recipient="design-writer", content="설계 문서 생성 요청. 완료 후 TaskUpdate로 completed 처리.")
# 완료 대기 → shutdown_request
```

**산출물**: `docs/02-design/{feature}.design.md`

### Design→Build Gate: Design 검증

| # | 필수 항목 | 확인 방법 |
|:-:|----------|----------|
| 1 | 구현 대상 파일 목록 | 구체적 파일 경로 나열 존재 |
| 2 | 인터페이스/API 설계 | 함수/클래스 시그니처 정의 |
| 3 | 테스트 전략 | 테스트 범위/방법 언급 존재 |
| 4 | 데이터 흐름 | 입출력 흐름 기술 존재 |

---

### Step 1.6: Plan Approval Gate (HEAVY만)

HEAVY 모드에서는 Phase 2 BUILD 진입 전 사용자에게 계획을 명시적으로 승인받습니다.
토큰 낭비를 방지하고 팀메이트 스폰 전 방향성을 확인합니다.

**실행 조건**: `complexity_mode == "HEAVY"` 일 때만 실행. LIGHT/STANDARD는 스킵.

```python
# Plan Approval Gate (HEAVY만)
if mode == "HEAVY":
    # 1. 계획 요약 출력
    print(f"""
=== Plan Approval Gate (HEAVY) ===
PRD: {prd_path}
Plan: {plan_path}
Design: {design_path}
영향 파일: {len(affected_files)}개
예상 에이전트: {agent_count}개
복잡도: {complexity_score}/6
==================================
""")
    # 2. AskUserQuestion으로 승인 요청
    approval = AskUserQuestion("Phase 2 BUILD 진입을 승인하시겠습니까? (y/n/수정사항)")

    if approval.lower() in ["n", "no", "아니오"]:
        # 계획 수정 → Step 1.3 재실행
        print("[Plan Approval] 거부됨. Phase 1.3 계획 수립으로 복귀.")
    elif approval.lower() in ["y", "yes", "예", "ㅇ"]:
        # Phase 2 진입
        print("[Plan Approval] 승인됨. Phase 2 BUILD 진입.")
    else:
        # 수정사항 반영 후 재승인
        print(f"[Plan Approval] 수정 요청: {approval}")
        # planner에게 수정사항 전달 → 계획 업데이트 → 재승인 (max 2회)
```

**`--interactive` 모드와의 관계**: `--interactive`는 모든 Phase 전환 시 확인. Plan Approval Gate는 HEAVY 전용 심층 검토 (계획 내용까지 표시).
