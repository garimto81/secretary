# /auto Phase 3: VERIFY — 상세 워크플로우

> 이 파일은 `/auto` Phase 3 진입 시 로딩됩니다. SKILL.md에서 Phase 3 시작 시 이 파일을 Read합니다.
> 원본: REFERENCE.md v25.0에서 분리 (v25.2 Progressive Disclosure)

---

## Phase 3: VERIFY (Quality Gate + QA Runner + Architect 진단 + 이중 검증 + E2E)

### Step 3.0: Quality Gate (자동 품질 검증)

QA 테스터 투입 전 기계적 품질 검증을 수행합니다.

```python
# Quality Gate 실행
quality_gate = Agent(
    subagent_type="quality-gate",
    name="quality-checker",
    team_name=team_name,
    description="자동 품질 검증 (lint+complexity+coverage+security)",
    prompt=f"""
프로젝트 루트: {project_dir}
변경 파일: {changed_files}

4가지 검증을 수행하고 Quality Gate Report를 출력하세요:
1. 정적 분석 (ruff check)
2. 코드 복잡도 (함수 50줄, CC 10)
3. 테스트 커버리지 (80% 기준)
4. 보안 스캔 (pip-audit/npm audit)
"""
)
# PASS/CONDITIONAL → Step 3.1로 진행
# FAIL → executor에게 수정 요청 후 재검증
```

---

### Step 3.1: QA 사이클 — QA Runner + Architect Root Cause 진단 + Domain-Smart Fix (v22.1)

> **v22.1 핵심 변경**: Lead 직접 QA 실행 → QA Runner teammate 위임 (Lead context 보호).
> 실패 시 Architect 진단 선행 (맹목적 수정 금지).

```
# LIGHT 모드: QA 1회 실행, 실패 시 보고만 (진단/수정 사이클 없음)
if mode == "LIGHT":
    Agent(subagent_type="qa-tester", name="qa-runner", description="QA 실행", team_name="pdca-{feature}", prompt="[Phase 3 QA Runner] 6종 QA 실행. (LIGHT 모드)")
    SendMessage(type="message", recipient="qa-runner", content="QA 실행 시작.")
    # 완료 대기 → shutdown_request
    if QA_PASSED → Step 3.2
    if QA_FAILED → 실패 보고 + STANDARD 자동 승격 조건 확인
    return  # LIGHT는 Architect 진단 + Domain Fix 사이클 진입하지 않음

# STANDARD/HEAVY 모드: 아래 QA 사이클 적용
failure_history = []  # 실패 기록 배열 (Lead 메모리에서 관리)
max_cycles = STANDARD:3 / HEAVY:5
cycle = 0

while cycle < max_cycles:
  cycle += 1

  # Step A: QA Runner Teammate (Lead context 보호)
  Agent(subagent_type="qa-tester", name="qa-runner-{cycle}", description="QA 실행 사이클",
       team_name="pdca-{feature}",
       prompt="[Phase 3 QA Runner] 6종 QA 실행.
               === 6종 QA Goal ===
               1. lint: ruff check src/ --fix (Python) / eslint (JS/TS)
               2. test: pytest tests/ -v (Python) / jest/vitest (JS/TS)
               3. build: npm run build / pip install -e . (해당 시)
               4. typecheck: mypy (Python, 설정 시) / tsc --noEmit (TS)
               5. custom: '{custom_pattern}' (--custom 옵션 시만)
               6. interactive: tmux 테스트 (--interactive 옵션 시만)

               각 goal에 대해 실행 → 결과 수집 → PASS/FAIL 판정.
               해당하지 않는 goal (예: Python 프로젝트의 eslint)은 SKIP 처리.

               모든 goal PASS 시 → QA_PASSED 메시지 전송
               1개라도 FAIL 시 → QA_FAILED 메시지 전송 (실패 goal, 에러 상세, 실패 시그니처 포함)

               메시지 형식:
               QA_PASSED: { 'goals': [{goal, status, output}] }
               QA_FAILED: { 'goals': [{goal, status, output, signature}], 'failed_count': N }")
  SendMessage(type="message", recipient="qa-runner-{cycle}", content="QA 실행 시작.")
  # 완료 대기 → shutdown_request

  # Lead: QA Runner 결과 판정
  if QA_PASSED:
      → Step 3.2 (이중 검증) 진입

  if QA_FAILED:
    # Step B: 실패 기록 + Exit Condition 검사
    for each failed_goal in qa_result.goals:
      failure_entry = {
        "cycle": cycle,
        "type": failed_goal.goal,
        "detail": failed_goal.output,
        "signature": failed_goal.signature
      }
      failure_history.append(failure_entry)

    # Exit Condition 1: Environment Error (PATH, 도구 미설치 등)
    if qa_result contains environment error pattern:
        → 즉시 중단 + "[Phase 3] 환경 오류 감지: {detail}. 환경 설정 필요." 출력
        → Phase 3 종료

    # Exit Condition 2: Same Failure 3x
    for each failure in failure_history:
      same_failures = [f for f in failure_history if f.signature == failure.signature]
      if len(same_failures) >= 3:
        → 조기 종료 + "[Phase 3] 동일 실패 3회: {signature}. Root cause 보고." 출력
        → Phase 3 종료

    # Step C: Systematic Debugging D0-D4 (Iron Law #2 — Root cause 없이 수정 금지)
    # superpowers systematic-debugging 흡수: Architect 단순 진단 → D0-D4 체계 강화
    Agent(subagent_type="architect", name="diagnostician-{cycle}", description="Systematic Debugging D0-D4 진단",
         team_name="pdca-{feature}",
         prompt="[Phase 3 Systematic Debugging] QA 실패 Root Cause 분석 — D0-D4 체계.
                 실패 내역: {qa_failed_details}
                 이전 실패 이력: {failure_history 요약}

                 === Systematic Debugging Protocol (Iron Law #2) ===
                 D0 SYMPTOM: 증상 수집 — 에러 메시지, 실패 테스트, 로그 패턴 정리
                 D1 HYPOTHESIS: 가설 수립 — 가능한 원인 2-3개 나열, 우선순위 부여
                 D2 VERIFY: 가설 검증 — Grep/Read로 코드 확인, 가설별 증거 수집
                 D3 ROOT_CAUSE: Root Cause 확정 — 검증된 가설 기반 원인 1개 확정

                 === D0-D4 책임 분리 (v25.0) ===
                 D0: qa-runner 소유 (증상 보고)
                 D1-D3: architect 소유 (READ-ONLY 진단)
                 D4: domain-fixer 소유 (수정 계획+실행)

                 D4 FIX_PLAN: 수정 계획 — 파일명:라인 수준 구체적 수정 지시 (domain-fixer에게 전달)

                 반드시 다음 형식으로 출력하세요:
                 D0_SYMPTOM: {증상 요약}
                 D1_HYPOTHESIS: {가설 목록}
                 D2_EVIDENCE: {검증 증거}
                 D3_ROOT_CAUSE: {확정된 원인 1줄}
                 DIAGNOSIS: {root cause 1줄 요약}
                 FIX_GUIDE: {구체적 수정 지시 — 파일명:라인 수준}
                 DOMAIN: {UI|build|test|security|logic|other}

                 진단 없이 '이것저것 시도해보세요' 식의 모호한 지시는 금지.
                 가설→검증→확정 순서를 반드시 따르세요.")
    SendMessage(type="message", recipient="diagnostician-{cycle}", content="Root cause 진단 시작.")
    # 완료 대기 → shutdown_request

    # Step D: Domain-Smart Fix (Architect 진단 기반)
    domain = diagnostician 메시지에서 DOMAIN 추출
    diagnosis = diagnostician 메시지에서 DIAGNOSIS 추출
    fix_guide = diagnostician 메시지에서 FIX_GUIDE 추출

    # Domain Routing
    domain_agent_map = {
        "UI": "designer", "component": "designer", "style": "designer",
        "build": "build-fixer", "compile": "build-fixer", "type": "build-fixer",
        "test": "executor", "coverage": "executor",
        "security": "security-reviewer",
        "logic": "executor", "other": "executor"
    }
    agent_type = domain_agent_map.get(domain, "executor")

    Agent(subagent_type=agent_type, name="fixer-{cycle}", description="수정 실행",
         team_name="pdca-{feature}",
         prompt="[Phase 3 Domain Fix] 진단 기반 QA 실패 수정.
                 DIAGNOSIS: {diagnosis}
                 FIX_GUIDE: {fix_guide}
                 DOMAIN: {domain}
                 이전 실패 이력: {failure_history 요약}
                 수정 후 해당 검사를 재실행하여 통과를 확인하세요.")
    SendMessage(type="message", recipient="fixer-{cycle}", content="진단 기반 수정 시작.")
    # 완료 대기 → shutdown_request

    → 다음 cycle로 (Step A 재실행)

# Exit Condition 3: Max Cycles 도달
→ "[Phase 3] QA {max_cycles}회 도달. 미해결: {remaining_issues}" 출력
→ 사용자에게 미해결 이슈 보고
```

---

### 4종 Exit Conditions 상세

| 우선순위 | 조건 | 감지 방법 | 처리 |
|:--------:|------|----------|------|
| 1 | Environment Error | QA Runner가 "command not found", "PATH", "not installed" 패턴 보고 | 즉시 중단 + 환경 문제 보고 |
| 2 | Same Failure 3x | failure_history 내 동일 signature 3회 누적 | 조기 종료 + root cause 보고 |
| 3 | Max Cycles 도달 | cycle >= max_cycles | 미해결 이슈 목록 보고 |
| 4 | Goal Met | QA_PASSED 수신 | Step 3.2 이중 검증 진입 |

---

### Interactive Testing (v22.1 신규, --interactive 옵션 시)

`--interactive` 옵션 시 QA Runner의 goal 6(interactive)이 활성화됩니다:

```
# QA Runner 내부에서 직접 실행 (goal 6)
# tmux new-session -d -s qa-test
# tmux send-keys -t qa-test '명령어' Enter
# tmux capture-pane -t qa-test -p
# 결과를 QA_PASSED/QA_FAILED 형식으로 보고
```

> **주의**: Interactive testing은 tmux가 설치된 환경에서만 작동합니다.

---

### Step 3.1b: UI Layout Verification (자동 — 조건 충족 시)

**트리거 조건**: 아래 모두 충족 시 자동 실행
1. `docs/mockups/*.html` 1개 이상 존재
2. 현재 Build에서 CSS/SCSS 파일 변경 발생 (`git diff --name-only | grep -E '\.(css|scss)$'`)

**실행 내용**:

```python
# Lead 직접 실행 (에이전트 위임 없음)
import subprocess, json
from pathlib import Path

# 1. 트리거 조건 확인
mockups = list(Path("docs/mockups").glob("*.html"))
css_changed = subprocess.run(
    ["git", "diff", "--name-only"],
    capture_output=True, text=True
).stdout
has_css_change = any(f.endswith(('.css', '.scss')) for f in css_changed.splitlines())

if mockups and has_css_change:
    # 2. 각 목업에 대해 밸런스 측정
    for mockup in mockups:
        result = subprocess.run(
            ["python", "C:/claude/lib/mockup_hybrid/balance_checker.py", str(mockup)],
            capture_output=True, text=True
        )
        metrics = json.loads(result.stdout)

        if metrics["verdict"] == "FAIL":
            # QA 리포트에 밸런스 경고 포함
            balance_warnings.append(f"⚠️ {mockup.name}: {metrics['failures']}")

    # 3. Before/After 비교 (git diff에 CSS 포함 시)
    for mockup in mockups:
        rel_path = mockup.relative_to(Path.cwd())
        # git show main 버전 → temp 파일 → Playwright 캡처 → before.png
        # 현재 버전 → after.png
        # Vision AI 비교 → 변경 요약 1줄
```

**밸런스 기준 판정** (기본값):
- 열 높이 편차 ≤ 50px
- 정보 밀도 편차 ≤ 20%
- 여백 비율 25-35%
- 스크롤 필요 열 ≤ 1개

**결과 처리**:
- PASS → 로그만 출력 (`[Phase 3.1b] UI Balance: PASS`)
- FAIL → QA 리포트에 밸런스 경고 포함 (QA 사이클 실패로 취급하지 않음, 경고만)

**목업 일괄 갱신** (추가 조건: `docs/mockups/*.html` 2개+ 존재 + 공유 CSS 변경):
- Phase 2 BUILD 완료 직후 영향받는 목업 자동 업데이트 + 캡처

---

### Step 3.2: E2E 검증 + Architect 최종 검증

**E2E 인덱스 체크 (Step 3.2 진입 시 1회 평가):**

```
# E2E 실행 조건 인덱싱 — 3개 조건 모두 충족 시만 e2e_enabled = true
e2e_enabled = (
    mode != "LIGHT"                               # LIGHT 모드 아님
    and not skip_e2e                              # --skip-e2e 옵션 아님
    and Glob("playwright.config.{ts,js}")         # Playwright 설정 파일 존재
)
# e2e_enabled == false → E2E 관련 모든 단계 스킵 (Step 3.2.1, 3.2.3, 3.3 전체)
```

**LIGHT 모드: Architect teammate만 (E2E 스킵)**
```
Agent(subagent_type="architect", name="verifier", description="검증 실행", team_name="pdca-{feature}",
     prompt="구현된 기능이 docs/01-plan/{feature}.plan.md 요구사항과 일치하는지 검증.")
SendMessage(type="message", recipient="verifier", content="검증 시작. APPROVE/REJECT 판정 후 TaskUpdate 처리.")
# verifier 완료 대기 → shutdown_request
# e2e_enabled == false → Step 3.3 스킵
```

**STANDARD/HEAVY 모드: E2E 백그라운드 + Architect 최종 검증**
```
# Step 3.2.1: E2E 백그라운드 spawn (e2e_enabled 시 — 포그라운드 검증과 병렬)
if e2e_enabled:
    Agent(subagent_type="qa-tester", name="e2e-runner", description="E2E 테스트 실행", team_name="pdca-{feature}",
         prompt="[Phase 3 E2E Background] E2E 테스트 백그라운드 실행.
         1. 프레임워크 감지:
            - playwright.config.* -> npx playwright test --reporter=list
            - cypress.config.* -> npx cypress run --reporter spec
            - vitest.config.* (browser) -> npx vitest run --reporter verbose
         2. 감지된 프레임워크로 실행 (첫 번째 매칭 우선)
         3. 결과 요약: 총 테스트 수, PASS 수, FAIL 수
         4. 실패 시: 실패 테스트명 + 에러 메시지 (첫 3줄)
         5. 출력 형식: E2E_PASSED 또는 E2E_FAILED + 실패 상세 목록
         --strict 모드: {strict_mode} (true 시 1회 실패 즉시 E2E_FAILED 보고)")
    SendMessage(type="message", recipient="e2e-runner", content="E2E 백그라운드 실행 시작.")
    # ※ 완료 대기하지 않음 — 아래 포그라운드 검증과 병렬 진행

# Step 3.2.2: Architect 최종 검증 (포그라운드)
Agent(subagent_type="architect", name="verifier", description="검증 실행", team_name="pdca-{feature}",
     prompt="구현된 기능이 docs/01-plan/{feature}.plan.md 요구사항과 일치하는지 최종 검증 (type=FINAL).

             === Unified Verification Protocol (v25.0) ===
             이것은 FINAL 검증입니다. Phase 2.3 이후 변경된 delta만 검증하세요.
             이전 검증에서 APPROVE된 항목은 재검증하지 마세요.

             === Iron Law #3: Verification (MANDATORY) ===
             증거 없이 APPROVE 금지. 아래 증거를 반드시 수집하고 판정에 포함:
             - 빌드 결과 (exit code)
             - 테스트 결과 (pass/fail 수)
             - lint/type-check 결과
             VERDICT: APPROVE 또는 VERDICT: REJECT 형식으로 판정.")
SendMessage(type="message", recipient="verifier", content="검증 시작. APPROVE/REJECT 판정 후 TaskUpdate 처리.")
# verifier 완료 대기 → shutdown_request

# Step 3.2.3: E2E 결과 수집 (포그라운드 검증 완료 후)
if e2e_enabled:
    # e2e-runner는 이미 백그라운드에서 병렬 실행 중
    # Mailbox에서 e2e-runner 메시지 수신 대기
    # 이미 완료된 경우 → 즉시 수신 / 아직 실행 중 → 대기
    e2e_result = wait_for_message(from="e2e-runner")
    SendMessage(type="shutdown_request", recipient="e2e-runner")
    if e2e_result == "E2E_PASSED":
        # 정상 진행 → Step 3.3 스킵
        pass
    elif e2e_result == "E2E_FAILED":
        e2e_failures = e2e_result.failures
        if strict_mode:
            # --strict: 즉시 중단 + 실패 보고 → Phase 4 미진입
            report_e2e_failure(e2e_failures)
            return
        # 비-strict → Step 3.3 E2E 실패 처리 진입
```

**HEAVY 모드: 동일 구조 (Architect + E2E 백그라운드)**

HEAVY 모드에서도 Architect는 `verifier`, e2e-runner는 `e2e-runner` 사용:
```
Agent(subagent_type="qa-tester", name="e2e-runner", description="E2E 테스트 실행", ..., ...)  # 백그라운드
Agent(subagent_type="architect", name="verifier", description="검증 실행", ..., ...)
```

- e2e-runner: E2E 테스트 (백그라운드 병렬 -- Playwright/Cypress/Vitest 자동 감지)
- Architect: Plan 대비 구현 일치 최종 검증 (APPROVE/REJECT)

> code-reviewer는 Phase 2 Step 2.2에서 이미 수행되었으므로 Phase 3에서는 생략합니다.

---

### Step 3.3: E2E 실패 처리 (e2e_enabled + E2E_FAILED 시만)

> **인덱싱**: `e2e_enabled == false` 또는 `E2E_PASSED`면 이 Step 전체를 스킵합니다.
> Step 3.2.3에서 E2E_FAILED를 수신한 경우에만 진입합니다.

**진입 조건 (모두 충족 시):**
- `e2e_enabled == true` (Step 3.2.0에서 평가)
- Step 3.2.3에서 `E2E_FAILED` 수신
- `strict_mode == false` (strict 시 Step 3.2.3에서 이미 중단)

**E2E 실패 수정 루프 (max 2회):**
```
e2e_fix_attempts = 0
max_e2e_fixes = 2

Loop (max_e2e_fixes):
    e2e_fix_attempts += 1

    # A. Architect E2E 실패 root cause 진단
    Agent(subagent_type="architect", name="e2e-diagnostician", description="E2E 진단", team_name="pdca-{feature}",
         prompt="[E2E Failure Diagnosis] Playwright E2E 테스트 실패 분석.
         실패 상세: {e2e_failures}
         1. 실패 root cause 식별 (UI 렌더링, 네트워크, 타이밍, 셀렉터 등)
         2. 수정 지침 (FIX_GUIDE) 작성
         3. DOMAIN 분류: UI/build/test/security/기타
         출력: DIAGNOSIS + FIX_GUIDE + DOMAIN")
    SendMessage(type="message", recipient="e2e-diagnostician", content="E2E 실패 진단 시작.")
    # 완료 대기 → shutdown_request

    # B. Domain-Smart Fix (Step 2.4 동일 라우팅)
    Agent(subagent_type="{domain-agent}", name="e2e-fixer", description="E2E 수정", team_name="pdca-{feature}",
         prompt="E2E 진단 기반 수정.
         DIAGNOSIS: {diagnosis}
         FIX_GUIDE: {fix_guide}
         수정 후 npx playwright test --reporter=list 로 검증.")
    SendMessage(type="message", recipient="e2e-fixer", content="E2E 수정 시작.")
    # 완료 대기 → shutdown_request

    # C. E2E 재실행
    Agent(subagent_type="qa-tester", name="e2e-rerun", description="E2E 재실행", team_name="pdca-{feature}",
         prompt="npx playwright test --reporter=list 재실행. E2E_PASSED 또는 E2E_FAILED 보고.")
    SendMessage(type="message", recipient="e2e-rerun", content="E2E 재실행 시작.")
    # 완료 대기 → shutdown_request

    if e2e_rerun_result == "E2E_PASSED":
        break  # 성공 → Phase 4 진입
    # E2E_FAILED → 다음 iteration

# 2회 초과: 미해결 E2E 실패 경고 포함하여 Phase 4 진입 허용
if e2e_fix_attempts >= max_e2e_fixes:
    warn("E2E 테스트 {len(e2e_failures)}건 미해결. Phase 4 보고서에 포함.")
```

**스킵 조건 (인덱싱 — Step 3.3 전체 비활성화):**
- `e2e_enabled == false` (LIGHT 모드, Playwright 미설치, `--skip-e2e`)
- Step 3.2.3에서 `E2E_PASSED` 수신
- `strict_mode == true` + `E2E_FAILED` (Step 3.2.3에서 이미 중단됨)

---

### Step 3.4: TDD 커버리지 보고 (있을 때만)

**Python 프로젝트:**
```bash
pytest --cov --cov-report=term-missing
```

**JavaScript/TypeScript 프로젝트:**
```bash
jest --coverage
```

**출력:** 커버리지 퍼센트, 미커버 라인 번호 (80% 미만 시 경고)

---

## Vercel BP 검증 규칙

Phase 2 Step 2.2에서 code-reviewer teammate prompt에 동적 주입하는 규칙:

> 상세: `.claude/references/vercel-bp-rules.md`
>
> 주입 시 해당 파일을 Read하여 code-reviewer prompt에 포함 (절대 경로: `C:\claude\.claude\references\vercel-bp-rules.md`)

**동적 주입 조건:**
- `Glob("next.config.*")` 결과 존재 또는 `package.json` 내 `"react"` dependency 존재 시 주입
- 웹 프로젝트가 아닌 경우 생략
