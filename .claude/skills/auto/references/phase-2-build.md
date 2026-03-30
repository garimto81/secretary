# /auto Phase 2: BUILD — 상세 워크플로우

> 이 파일은 `/auto` Phase 2 진입 시 로딩됩니다. SKILL.md에서 Phase 2 시작 시 이 파일을 Read합니다.
> 원본: REFERENCE.md v25.0에서 분리 (v25.2 Progressive Disclosure)

---

## Phase 2: BUILD (옵션 처리 + 구현 + 코드 리뷰 + Architect Gate)

### Step 2.0.5: Task Clustering (접두사 규칙)

Phase 2 진입 시 TaskCreate로 생성하는 모든 Task에 Phase-Letter 접두사를 적용합니다:

```
# 접두사 규칙: [P{phase}-{letter}] {task_subject}
# 예시:
TaskCreate(subject="[P2-A] API 엔드포인트 구현", description="...", metadata={"blockedBy": []})
TaskCreate(subject="[P2-B] DB 스키마 마이그레이션", description="...", metadata={"blockedBy": []})
TaskCreate(subject="[P2-C] 프론트엔드 통합", description="...", metadata={"blockedBy": ["P2-A"]})
TaskCreate(subject="[P3-A] QA 사이클 실행", description="...", metadata={"blockedBy": ["P2-A", "P2-B", "P2-C"]})
```

| 규칙 | 설명 |
|------|------|
| Phase 번호 | `P0`=INIT, `P1`=PLAN, `P2`=BUILD, `P3`=VERIFY, `P4`=CLOSE |
| Letter 순서 | A, B, C... (동일 Phase 내 순서) |
| blockedBy | 선행 Task ID 배열 (의존성 명시) |
| 병렬 판단 | blockedBy가 비어있는 Task들은 동시 실행 가능 |

### Step 2.0: 옵션 처리 (있을 경우)

옵션이 있으면 구현 진입 전에 처리. 실패 시 에러 출력 후 중단 (조용한 스킵 금지).

> 옵션 핸들러 상세 (`--mockup`, `--anno`, `--gdocs`, `--critic`, `--debate`, `--research`, `--daily`, `--jira`, `--figma` 등): `options-handlers.md` 참조.

#### Phase 0 옵션 파싱 — 스킵 플래그

```python
# --skip-prd: Phase 1 Step 1.1 PRD 스킵
if "--skip-prd" in options:
    # Step 1.1 건너뛰기 → Step 1.2 사전 분석부터 시작
    # 이유 기록 필수 (규칙 13-requirements-prd 준수)

# --skip-analysis: Phase 1 Step 1.2 사전 분석 스킵
if "--skip-analysis" in options:
    # Step 1.2 건너뛰기 → Step 1.3 계획 수립부터 시작

# --no-issue: Phase 1 Step 1.5 이슈 연동 스킵
if "--no-issue" in options:
    # Step 1.5 건너뛰기 (GitHub 이슈 생성/코멘트 안 함)

# --dry-run: 범용 판단만 출력 (실제 변경 없음)
if "--dry-run" in options:
    # Phase 0 복잡도 판단 + Phase 1 계획까지만 실행
    # 구현(Phase 2), 검증(Phase 3), 마감(Phase 4) 스킵

# --strict: Phase 3 E2E strict 모드
if "--strict" in options:
    # E2E 1회 실패 즉시 중단 (기본: max 2회 재시도)

# --eco 세분화 (v25.0): 3단계 비용 절감
eco_level = 0
if "--eco-3" in options:
    eco_level = 3
elif "--eco-2" in options:
    eco_level = 2
elif "--eco" in options:
    eco_level = 1

if eco_level >= 1:
    # Level 1: Opus → Sonnet (architect, planner, critic, executor-high, scientist-high)

if eco_level >= 2:
    # Level 2: 비핵심 Sonnet → Haiku (추가 다운그레이드)
    # 대상: gap-detector, explore-medium, analyst, vision, catalog-engineer, claude-expert, researcher
    # 유지: code-reviewer, executor, designer, qa-tester, build-fixer, security-reviewer, tdd-guide

if eco_level >= 3:
    # Level 3: 전체 Sonnet → Haiku (프로토타이핑 전용)
    # WARNING: 프로덕션 워크플로우 금지

# --worktree: feature worktree 격리
if "--worktree" in options:
    # Phase 0에서 git worktree add + .claude junction 생성
    # 모든 teammate prompt에 worktree 경로 prefix 주입
    # Phase 4 완료 후 worktree 정리 (사용자 확인)
```

---

### Step 2.0.3: Pre-Build Context Check (HEAVY만)

HEAVY 모드에서 Agent Teams 스폰 전 컨텍스트 사용량을 사전 점검합니다.

| 조건 | 조치 |
|------|------|
| 컨텍스트 < 60% | 정상 진행 |
| 컨텍스트 60-80% | 에이전트 수 축소 경고 (병렬 2개 → 1개) |
| 컨텍스트 > 80% | 단일 executor 모드 강제 전환 + 사용자 알림 |

Lead가 현재 대화 길이를 기준으로 판단합니다. 명시적 `/context` 명령이 가능한 경우 실행하여 정확한 사용량을 확인합니다.

---

### Step 2.1: 모드별 구현 (명시적 호출)

**LIGHT 모드: Executor teammate (opus) 단일 실행**
```
Agent(subagent_type="executor-high", name="executor", description="구현 실행", team_name="pdca-{feature}",
     prompt="docs/01-plan/{feature}.plan.md 기반 구현 (설계 문서 없음). TDD 필수.")
SendMessage(type="message", recipient="executor", content="구현 시작. 완료 후 TaskUpdate로 completed 처리.")
# 완료 대기 → shutdown_request
```
- 4조건 검증 없음 (단일 실행)
- 빌드 실패 시 즉시 STANDARD 모드로 승격

**STANDARD 모드: impl-manager teammate (opus) — 4조건 자체 루프**
```
Agent(subagent_type="executor-high", name="impl-manager", description="4조건 자체 루프 구현 관리", team_name="pdca-{feature}",
     prompt="{impl-manager prompt 전문 — 아래 'impl-manager Prompt 전문' 섹션 참조}")
SendMessage(type="message", recipient="impl-manager", content="4조건 구현 루프 시작.")
# Lead는 IMPLEMENTATION_COMPLETED 또는 IMPLEMENTATION_FAILED 메시지만 수신
```

**HEAVY 모드: impl-manager teammate (opus) — 4조건 자체 루프 + 병렬 가능**
```
Agent(subagent_type="executor-high", name="impl-manager", description="4조건 자체 루프 구현 관리", team_name="pdca-{feature}",
     prompt="{impl-manager prompt 전문 — 아래 'impl-manager Prompt 전문' 섹션 참조}")
SendMessage(type="message", recipient="impl-manager", content="4조건 구현 루프 시작.")
# Lead는 IMPLEMENTATION_COMPLETED 또는 IMPLEMENTATION_FAILED 메시지만 수신
```

**HEAVY 병렬 실행 (독립 작업 2개 이상 시):**
```
# Lead가 설계 문서 분석 → 독립 작업 분할
Agent(subagent_type="executor-high", name="impl-api", description="API 구현 담당",
     team_name="pdca-{feature}", isolation="worktree",
     prompt="[Phase 2 HEAVY 병렬] API 구현 담당. {impl-manager 전체 prompt}.
             담당 범위: src/api/ 하위 파일만. 다른 경로 수정 금지.")
Agent(subagent_type="executor-high", name="impl-ui", description="UI 구현 담당",
     team_name="pdca-{feature}", isolation="worktree",
     prompt="[Phase 2 HEAVY 병렬] UI 구현 담당. {impl-manager 전체 prompt}.
             담당 범위: src/components/ 하위 파일만. 다른 경로 수정 금지.")

SendMessage(type="message", recipient="impl-api", content="API 구현 시작.")
SendMessage(type="message", recipient="impl-ui", content="UI 구현 시작.")
# 두 impl-manager 모두에서 IMPLEMENTATION_COMPLETED 수신 대기
# 하나라도 FAILED → Lead가 사용자에게 알림

# Worktree Merge: 두 impl 모두 완료 후 Lead가 worktree 변경사항 merge
# git merge 충돌 시 → 사용자에게 알림 + 수동 해결 요청
```

### Step 2.1b: Builder-Validator 쌍 (HEAVY만)

HEAVY 모드에서 executor와 qa-tester를 쌍으로 스폰하여 실시간 피드백 루프를 형성합니다.

| 역할 | 에이전트 | 책임 |
|------|---------|------|
| Builder | impl-manager (executor-high) | 구현 + TDD |
| Validator | live-qa (qa-tester) | 실시간 품질 검증 |

impl-manager 완료 메시지 수신 즉시 live-qa가 검증 시작. live-qa FAIL 시 impl-manager에 피드백 전달.
Architect는 최종 Gate만 담당 (Step 2.3 유지).

```python
# Builder-Validator 쌍 (HEAVY만)
Agent(subagent_type="executor-high", name="impl-manager", description="4조건 자체 루프 구현 관리",
     team_name="pdca-{feature}",
     prompt="{impl-manager prompt 전문}")
Agent(subagent_type="qa-tester", name="live-qa", description="실시간 품질 검증",
     team_name="pdca-{feature}",
     prompt="[Phase 2 Live QA] impl-manager 구현 결과를 실시간 검증.
             테스트 실행, lint 체크, 빌드 확인을 수행하고
             문제 발견 시 impl-manager에게 SendMessage로 피드백.
             최종 PASS/FAIL 판정을 Lead에게 보고.")
SendMessage(type="message", recipient="impl-manager", content="4조건 구현 루프 시작.")
SendMessage(type="message", recipient="live-qa", content="impl-manager 완료 대기 후 검증 시작.")
```

---

### Build→Verify Gate: impl-manager 완료 판정 + Architect Gate (v22.1)

- LIGHT: 빌드 통과만 확인 (Architect Gate 없음, Phase 3 직행)
- STANDARD/HEAVY: impl-manager `IMPLEMENTATION_COMPLETED` → **Step 2.2 Code Review → Step 2.3 Architect Gate 필수** → Phase 3
- impl-manager가 `IMPLEMENTATION_FAILED` 메시지 전송 시 Lead가 사용자에게 알림 + 수동 개입 요청
- --interactive 모드: 사용자 확인 요청

---

### Step 2.2: Code Review (STANDARD/HEAVY 필수)

구현 완료 후 **즉시** code-reviewer (sonnet) 실행. LIGHT 모드는 스킵.

```
# Code Review — 코드 품질 + Vercel BP 동적 주입
# Lead가 직접 프로젝트 유형 감지 후 Vercel BP 규칙 동적 주입

# === Vercel BP 동적 주입 메커니즘 (Lead 직접 실행) ===
has_nextjs = len(Glob("next.config.*")) > 0
has_react = False
pkg_files = Glob("package.json")
if pkg_files:
    has_react = '"react"' in Read("package.json")

if has_nextjs or has_react:
    vercel_bp_rules = Read("C:\claude\.claude\references\vercel-bp-rules.md")
    reviewer_prompt = f"구현 코드의 품질, 보안, 성능 이슈 분석.\n\n=== Vercel Best Practices ===\n{vercel_bp_rules}"
else:
    reviewer_prompt = "구현 코드의 품질, 보안, 성능 이슈 분석."

Agent(subagent_type="code-reviewer", name="code-reviewer", description="코드 리뷰", team_name="pdca-{feature}",
     prompt=reviewer_prompt)
SendMessage(type="message", recipient="code-reviewer", content="코드 품질 리뷰 시작. APPROVE 또는 REVISE + 수정 목록 제공.")
# code-reviewer 완료 대기 → shutdown_request

# === Hybrid Review (code-review 플러그인 활성 시, STANDARD/HEAVY) ===
# 내부 code-reviewer 결과 + 플러그인 5-agent 병렬 결과 병합
if "code-review" in activated_plugins and mode in ["STANDARD", "HEAVY"]:
    # code-review 플러그인 5개 병렬 에이전트:
    # 1. CLAUDE.md Compliance — CLAUDE.md 규칙 준수 검사
    # 2. Shallow Bug Scan — 표면 버그 탐지
    # 3. Git Blame Context — 변경 이력 기반 분석
    # 4. PR Comment Patterns — PR 코멘트 패턴 분석
    # 5. Code Comment Compliance — 코드 주석 품질 검사
    #
    # 플러그인 에이전트 결과를 내부 code-reviewer 결과와 병합:
    # - 내부 APPROVE + 플러그인 이슈 0건 → 최종 APPROVE
    # - 내부 APPROVE + 플러그인 이슈 있음 → 이슈 통합 후 REVISE
    # - 내부 REVISE → 플러그인 이슈도 수정 목록에 병합

# APPROVE → Step 2.3 Architect Gate 진입
# REVISE + 수정 목록 → executor로 수정 → code-reviewer 재검토 (max 2회)
```

---

### Step 2.3: Architect Verification Gate (STANDARD/HEAVY 필수)

impl-manager가 IMPLEMENTATION_COMPLETED를 보고한 후, 독립 Architect가 구현을 외부 검증합니다.

```
rejection_count = 0  # Lead 메모리에서 관리

# Architect 외부 검증
Agent(subagent_type="architect", name="impl-verifier", description="구현 검증", team_name="pdca-{feature}",
     prompt="[Phase 2 Architect Gate] 구현 외부 검증.
             Plan: docs/01-plan/{feature}.plan.md
             Design: docs/02-design/{feature}.design.md (있으면)

             구현된 코드가 Plan/Design 요구사항을 충족하는지 검증하세요.

             검증 항목:
             1. Plan의 모든 구현 항목이 실제 구현되었는지
             2. 설계 문서의 인터페이스/API가 구현과 일치하는지
             3. TDD 규칙 준수 (테스트 존재 여부)
             4. 빌드/lint 에러가 없는지 (ruff check, tsc --noEmit 등)
             5. 보안 취약점 (OWASP Top 10) 여부
             6. OOP 결합도/응집도 수준 (모듈 간 결합도 2단계 이하, 응집도 2단계 이하 목표)

             === OOP Score 평가 (v25.0) ===
             출력에 아래 OOP Score를 반드시 포함하세요:
             - avg_coupling: 모듈 간 평균 결합도 (1-6)
             - max_coupling: 최악 결합도
             - avg_cohesion: 모듈 내 평균 응집도 (1-7)
             - worst_cohesion: 최악 응집도
             - srp_violations: SRP 위반 모듈 수
             - dip_violations: DIP 위반 수
             - circular_deps: 순환 의존성 수

             OOP Gate 기준:
             - avg_coupling > 2.0 → REJECT
             - worst_cohesion > 4 → REJECT
             - circular_deps > 0 → REJECT
             - srp_violations > 0 → REJECT (STANDARD/HEAVY)

             === Iron Law #3: Verification (MANDATORY) ===
             증거 없이 APPROVE 금지. 아래 증거를 반드시 수집하고 판정에 포함하세요:
             - 빌드 결과 (exit code)
             - 테스트 결과 (pass/fail 수)
             - lint/type-check 결과

             반드시 첫 줄에 다음 형식으로 출력하세요:
             VERDICT: APPROVE 또는 VERDICT: REJECT
             DOMAIN: {UI|build|test|security|logic|other}

             REJECT 시 구체적 거부 사유와 수정 지침을 포함하세요.")
SendMessage(type="message", recipient="impl-verifier", content="구현 외부 검증 시작.")
# 완료 대기 → shutdown_request

# VERDICT 파싱
verifier_message = Mailbox에서 수신한 impl-verifier 메시지
if "VERDICT: APPROVE" in first_line:
    → Step 2.3b Gap Analysis (STANDARD/HEAVY만)
elif "VERDICT: REJECT" in first_line:
    rejection_count += 1
    domain = DOMAIN 값 추출
    rejection_reason = VERDICT 줄 이후 전체 내용

    if rejection_count >= 2:
        → "[Phase 2] Architect 2회 거부. 사용자 판단 필요." 출력
        → 사용자에게 알림 후 Phase 3 진입 허용 (완전 차단은 아님)
    else:
        → Step 2.4 Domain-Smart Fix 실행 → Architect 재검증
```

---

### Step 2.3b: Gap Analysis (STANDARD/HEAVY — Architect APPROVE 후)

Architect 정성 검증 통과 후, gap-detector로 설계-구현 정량 비교. LIGHT는 스킵.

```
# Gap Analysis — 7개 항목 정량 비교
Agent(subagent_type="gap-detector", name="gap-checker", description="설계-구현 정량 비교",
     team_name="pdca-{feature}",
     prompt="[Phase 2 Gap Analysis] 설계-구현 정량 비교.
             Plan: docs/01-plan/{feature}.plan.md
             Design: docs/02-design/{feature}.design.md (있으면)
             7개 항목 매칭 비교 → Match Rate(%) 산출.
             docs/03-analysis/{feature}.gap-analysis.md 출력.
             Match Rate >= 90%: APPROVE
             Match Rate < 90%: GAP_FOUND + 미구현 목록")
SendMessage(type="message", recipient="gap-checker", content="Gap 분석 시작.")
# 완료 대기 → shutdown_request

# 결과 파싱
if GAP_FOUND and match_rate < 90%:
    → executor로 갭 수정 → gap-detector 재검증 (max 1회)
if APPROVE or match_rate >= 90%:
    → 커밋 → Phase 3 진입
```

---

### Step 2.4: Domain-Smart Fix Routing

Architect REJECT 시 DOMAIN 값에 따라 전문 에이전트에게 수정 위임:

| Architect DOMAIN 값 | 에이전트 | subagent_type |
|---------------------|---------|---------------|
| UI, component, style | designer | `designer` |
| build, compile, type | build-fixer | `build-fixer` |
| test, coverage | executor | `executor` |
| security | security-reviewer | `security-reviewer` |
| logic, other | executor | `executor` |

```
# Domain-Smart Fix
Agent(subagent_type="{domain_agent}", name="domain-fixer", description="도메인별 수정",
     team_name="pdca-{feature}",
     prompt="[Phase 2 Domain Fix] Architect 거부 사유 해결.
             거부 사유: {rejection_reason}
             DOMAIN: {domain}
             수정 후 해당 검사를 재실행하여 통과를 확인하세요.")
SendMessage(type="message", recipient="domain-fixer", content="Architect 피드백 반영 시작.")
# 완료 대기 → shutdown_request → Step 2.3 Architect 재검증
```

---

## impl-manager Prompt 전문

Phase 2에서 impl-manager teammate에 전달하는 complete prompt:

```
[Phase 2 BUILD] Implementation Manager - 4조건 자체 루프

설계 문서: docs/02-design/{feature}.design.md
계획 문서: docs/01-plan/{feature}.plan.md

당신은 Implementation Manager입니다. 설계 문서를 기반으로 코드를 구현하고,
5가지 완료 조건을 모두 충족할 때까지 자동으로 수정/재검증을 반복합니다.

=== 4가지 완료 조건 (ALL 충족 필수) ===

1. TODO == 0: 설계 문서의 모든 구현 항목 완료. 부분 완료 금지.
2. 빌드 성공: 프로젝트 빌드 명령 실행 결과 에러 0개.
   - Python: ruff check src/ --fix (lint 통과)
   - Node.js: npm run build (빌드 통과)
   - 해당 빌드 명령이 없으면 이 조건은 자동 충족.
3. 테스트 통과: 모든 테스트 green.
   - Python: pytest tests/ -v (관련 테스트만 실행 가능)
   - Node.js: npm test 또는 jest
   - 테스트가 없으면 TDD 규칙에 따라 테스트 먼저 작성.
4. 에러 == 0: lint, type check 에러 0개.
   - Python: ruff check + mypy (설정 있을 때)
   - Node.js: tsc --noEmit (TypeScript일 때)

> 코드 품질 리뷰 책임은 code-reviewer 단독 담당 (v25.0 SRP 적용).

=== Delegation 강제 규칙 (v25.1) ===

10줄 초과 코드 변경은 반드시 에이전트에 위임하세요:
  - 10줄 이하: 직접 Edit/Write 허용
  - 11줄 이상: Agent(subagent_type="executor", ...) 또는 별도 teammate로 위임
  - 다중 파일 변경: 항상 위임 (파일 수 무관)
  - 위반 시: code-reviewer가 REVISE 판정에서 delegation violation 지적

=== 자체 Iteration 루프 ===

최대 10회까지 반복합니다:
  1. 4조건 검증 실행
  2. 미충족 조건 발견 시 → 해당 문제 수정
  3. 수정 후 → 1번으로 (재검증)
  4. ALL 충족 시 → IMPLEMENTATION_COMPLETED 메시지 전송
  5. 10회 도달 시 → IMPLEMENTATION_FAILED 메시지 전송

=== Iron Law Evidence Chain ===

IMPLEMENTATION_COMPLETED 전송 전 반드시 다음 4단계 증거를 확보하세요:
  1. 모든 테스트 통과 (pytest/jest 실행 결과 캡처)
  2. 빌드 성공 (build command 실행 결과 캡처)
  3. Lint/Type 에러 0개 (ruff/tsc 실행 결과 캡처)
  4. 위 3개 결과를 IMPLEMENTATION_COMPLETED 메시지에 포함

증거 없는 완료 주장은 절대 금지합니다.

=== Completion Promise 경고 (v22.1) ===

IMPLEMENTATION_COMPLETED 선언은 독립 Architect가 외부 검증합니다.
거짓 완료 신호 전송 시 REJECTED 판정을 받게 됩니다.
자기 채점만으로 COMPLETED를 선언하지 마세요. 4조건을 실제로 검증한 증거를 포함하세요.

=== Zero Tolerance 규칙 ===

다음 행위는 절대 금지합니다:
  - 범위 축소: 설계 문서의 구현 항목을 임의로 제외
  - 부분 완료: "나머지는 나중에" 식의 미완성 제출
  - 테스트 삭제: 실패하는 테스트를 삭제하여 green 만들기
  - 조기 중단: 4조건 미충족 상태에서 COMPLETED 전송
  - 불확실 언어: "should work", "probably fine", "seems to pass" 등 사용 시
    → 해당 항목에 대해 구체적 검증을 추가로 실행

=== Red Flags 자체 감지 ===

다음 패턴을 자체 감지하고 경고하세요:
  - "should", "probably", "seems to" 등 불확실 언어 사용
  - TODO/FIXME/HACK 주석 추가
  - 테스트 커버리지 80% 미만
  - 하드코딩된 값 (매직 넘버, 매직 스트링)
  - 에러 핸들링 누락 (bare except, empty catch)

감지 시 처리: Red Flag 발견 → 해당 항목을 즉시 수정 후 다음 iteration으로 진행.
수정 불가 시 IMPLEMENTATION_FAILED 메시지에 Red Flag 목록을 포함하여 Lead에게 보고.

=== OOP Implementation Guard ===

구현 중 아래 패턴을 적극 적용하세요:

1. 의존성 주입 (DI):
   - 구체 클래스를 직접 생성하지 말 것 (new ConcreteClass() 금지)
   - 생성자/팩토리를 통해 외부에서 주입
   - 테스트 시 Mock 교체 가능한 구조

2. 단일 책임 원칙 (SRP):
   - 한 클래스/모듈 = 한 가지 이유로만 변경
   - 파일 크기 > 300줄 → 분리 검토
   - 메서드 > 5개 독립 관심사 → 분리 필수

3. 인터페이스 분리 원칙 (ISP):
   - 클라이언트가 사용하지 않는 메서드에 의존하지 않도록
   - Fat Interface 감지 시 → 역할별 작은 인터페이스로 분리

4. 금지 패턴:
   - 전역 변수로 모듈 간 상태 공유 (공통 결합도)
   - boolean 파라미터로 다른 모듈 동작 제어 (제어 결합도)
   - 다른 모듈의 private 멤버 직접 접근 (내용 결합도)
   - 상속 깊이 3단계 이상 (Composition 우선)

이 가이드라인을 어기면 code-reviewer에서 HIGH/CRITICAL 이슈로 판정됩니다.

=== 메시지 형식 ===

[성공 시]
IMPLEMENTATION_COMPLETED: {
  "iterations": {실행 횟수},
  "files_changed": [{변경 파일 목록}],
  "test_results": "{pytest/jest 결과 요약}",
  "build_results": "{빌드 결과 요약}",
  "lint_results": "{lint 결과 요약}"
}

[실패 시]
IMPLEMENTATION_FAILED: {
  "iterations": 10,
  "remaining_issues": [{미해결 문제 목록}],
  "last_attempt": "{마지막 시도 요약}",
  "recommendation": "{권장 조치}"
}

=== Background Operations ===

install, build, test 등 장시간 명령은 background로 실행하세요:
  - npm install → background
  - pip install → background
  - 전체 테스트 suite → foreground (결과 확인 필요)

=== Delegation ===

직접 코드를 작성하세요. 추가 teammate를 spawn하지 마세요.
이 teammate 내부에서의 에이전트 호출은 금지됩니다.
```

---

## 자동 재시도/승격/실패 로직

| 조건 | 처리 |
|------|------|
| impl-manager 4조건 루프 내 빌드 실패 | impl-manager 자체 재시도 (10회 한도 내) |
| impl-manager 10회 초과 (FAILED 반환) | Lead가 사용자에게 알림 + 수동 개입 요청 |
| LIGHT에서 빌드 실패 2회 | STANDARD 자동 승격 (impl-manager 재spawn) |
| QA 3사이클 초과 | STANDARD → HEAVY 자동 승격 |
| 영향 파일 5개 이상 감지 | LIGHT/STANDARD → HEAVY 자동 승격 |
| 진행 상태 추적 | `pdca-status.json`의 `implManagerIteration` 필드 |
| 세션 중단 후 resume | `pdca-status.json` 기반 Phase/iteration 복원 |

---

## Step 2.9: Preview Branch + Architect Gate

### Preview Branch 자동 생성

BUILD 완료 시 프리뷰 브랜치를 자동 생성하여 변경사항을 격리합니다.

| 조건 | 동작 |
|------|------|
| Architect APPROVE | `preview/{feature-name}` 브랜치 자동 생성 |
| Architect REJECT | 프리뷰 브랜치 생성하지 않음, BUILD로 회귀 |
| 브랜치 네이밍 | `preview/{SKILL.md에서 추출한 feature명}` |

```python
# Preview Branch 생성 (Architect APPROVE 후)
preview_branch = f"preview/{feature_name}"
# git checkout -b {preview_branch}
# git push -u origin {preview_branch}
```

### Architect Gate 통과 조건 (명시적)

Architect는 아래 4가지 조건을 모두 충족해야 APPROVE합니다:

| # | 조건 | 검증 방법 |
|---|------|----------|
| 1 | 코드 품질 | code-reviewer 리뷰 통과 (critical 0건) |
| 2 | 테스트 통과 | 전체 테스트 PASS (신규 테스트 포함) |
| 3 | 설계 일치 | Plan Phase 설계 문서와 구현 일치 |
| 4 | Iron Laws 준수 | TDD + Debugging + Verification 3개 충족 |

REJECT 시 구체적 사유를 executor에게 전달합니다.
