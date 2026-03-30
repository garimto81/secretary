# /auto 공통 참조 — Contracts, Fallback, Agent Teams, Session

> 이 파일은 Agent 미인식, 팀 운영 이슈, Contract 스키마 확인 등 필요 시 로딩됩니다.
> 원본: REFERENCE.md v25.0에서 분리 (v25.2 Progressive Disclosure)

---

## Contract Definitions (v25.0)

Phase 간 자료 결합도(1단계)를 보장하기 위한 표준 Contract JSON 스키마.

### InitContract (Phase 0 → Phase 1)
```json
{
  "feature": "string",
  "mode": "LIGHT | STANDARD | HEAVY",
  "complexity_score": "number (0-6)",
  "plugins": ["string[]"],
  "iron_laws": ["TDD", "Debugging", "Verification"],
  "options": { "skip_prd": false, "skip_analysis": false, "eco": null },
  "adaptive_tier": "TRIVIAL | STANDARD | COMPLEX | CRITICAL",
  "clarifications": ["string[] (Socratic Q 답변, 있을 경우)"],
  "team_name": "string"
}
```

### PlanContract (Phase 1 → Phase 2)
```json
{
  "prd_path": "string",
  "plan_path": "string",
  "requirements": [{ "id": "R1", "description": "string", "priority": "MUST|SHOULD|COULD" }],
  "affected_files": ["string[]"],
  "acceptance_criteria": ["string[]"],
  "oop_scorecard": {
    "coupling_pass": true,
    "cohesion_pass": true,
    "srp_pass": true,
    "dip_pass": true,
    "isp_pass": true
  }
}
```

### BuildContract (Phase 2 → Phase 3)
```json
{
  "changed_files": ["string[]"],
  "test_results": "PASS | FAIL",
  "build_status": "PASS | FAIL",
  "lint_status": "PASS | FAIL",
  "gap_match_rate": "number (0-100)",
  "review_verdict": "APPROVE | REVISE",
  "oop_score": {
    "avg_coupling": "number",
    "max_coupling": "number",
    "avg_cohesion": "number",
    "worst_cohesion": "number",
    "srp_violations": "number",
    "dip_violations": "number",
    "circular_deps": "number"
  }
}
```

### VerifyContract (Phase 3 → Phase 4)
```json
{
  "qa_cycles": "number",
  "qa_final_status": "PASS | FAIL",
  "e2e_status": "PASS | FAIL | SKIPPED",
  "architect_final_verdict": "APPROVE | REJECT",
  "unresolved_issues": ["string[]"]
}
```

### ContextProvider 패턴 (의존성 주입)

Lead가 Plugin/Iron Laws를 에이전트 prompt에 직접 삽입하는 대신, `{context_injection}` 플레이스홀더를 사용합니다:

```
# 에이전트 prompt 템플릿에서:
prompt="... {context_injection} ..."

# Lead가 주입 시:
context_injection = build_context(mode, plugins, iron_laws)
# → Iron Laws + Plugin rules + Vercel BP 등을 일괄 생성
```

에이전트 prompt 템플릿 변경 없이, ContextProvider 빌드 로직만 수정하면 주입 내용 변경 가능.

---

## 출력 토큰 초과 방지 프로토콜 (v22.4)

> 상세 규칙: `.claude/rules/12-large-document-protocol.md`

### PRD/Plan 문서 작성 시 청킹 강제 규칙

**prd-writer, design-writer, reporter** 에이전트 호출 시 prompt에 반드시 포함:

```
대형 문서 작성 프로토콜 (MANDATORY):
1. 문서 규모 예측 후 300줄+ → 스켈레톤-퍼스트 패턴 사용
2. Write(헤더/목차만) → Edit(섹션별 순차 추가)
3. 단일 Write로 전체 문서 생성 금지
4. 토큰 초과 시 → Continuation Loop (max 3회, 중단점부터 재개)
5. 타임아웃 발생 시 → 전체 재생성 금지, 미완료 섹션만 재시도
```

### Mermaid 다이어그램 작성 규칙

**prd-writer, planner, reporter** 에이전트가 저장 파일(.md)에 Mermaid 다이어그램을 포함할 때 prompt에 반드시 포함:

```
Mermaid 다이어그램 규칙 (MANDATORY):
1. 한 레벨(같은 깊이) 노드 최대 4개. 5개+ 시 subgraph 또는 2단 재배치로 분할
2. 리프 노드 총합 ≤ 6. 7~8개 → 분할 또는 LR 전환 필수. 9개+ → Overview+Detail 분할 필수
3. 노드 레이블: 한글 8자/영문 15자 이내. 초과 시 <br/>로 2줄 분할 (3줄 금지)
4. 노드 레이블 줄바꿈: \n 금지 → <br/> 사용 필수
5. 노드 6개+ 또는 subgraph 포함 시 단계적 빌드업 (Stage별 1~2개 추가)
6. %%{init}%% 설정은 GitHub에서 무시됨 — 가독성 문제는 분할로 해결
7. 상세: .claude/rules/11-ascii-diagram.md 참조
```

### 에이전트 타임아웃 처리 (Phase 1, 2, 4)

문서 생성 에이전트(prd-writer, design-writer, reporter)가 5분+ 무응답 시:

```
[금지] Lead가 직접 전체 문서 생성 시도 → 동일한 토큰 초과 유발
[금지] 전체 문서 재생성 Fallback

[올바른 처리]
1. 완료된 파일 부분 확인 (Read 도구)
2. 미완료 섹션 목록 파악
3. 새 에이전트를 미완료 섹션만 담당하도록 spawn
4. Circuit Breaker: 동일 실패 3회 → 사용자 알림 + 수동 판단 요청
```

---

## 에이전트 Fallback 매핑 (커스텀 에이전트 미인식 시)

`.claude/agents/` 커스텀 에이전트가 로드되지 않을 때 빌트인 에이전트로 대체한다.
`Agent type '{name}' not found` 에러 발생 시 아래 매핑으로 즉시 재시도 **(HARD RULE — 사용자 질문 없이 자동 적용)**:

### Fallback 적용 (HARD RULE)

"Agent type not found" 에러 발생 시:
1. 즉시 아래 매핑으로 재호출 (사용자 질문 없이 자동)
2. Tier 1 → 플러그인 빌트인 대체 시도
3. Tier 1 실패 → Tier 2 general-purpose + model 오버라이드
4. Tier 2도 실패 시 에러 보고 후 중단

```
Agent(subagent_type="executor-high", ...) → 에러 발생
  └─ "Agent type not found" 감지
  └─ 아래 매핑에서 대체 에이전트 선택
  └─ Agent(subagent_type="general-purpose", model="opus", ...) 재호출
  └─ prompt 첫 줄에 역할 명시 추가
```

### Tier 1: 플러그인 빌트인 대체 (모델 제어 가능)

| 커스텀 에이전트 | Fallback | model 오버라이드 | 비고 |
|----------------|----------|:----------------:|------|
| architect | feature-dev:code-architect | — | READ-ONLY prompt 명시 |
| critic | feature-dev:code-reviewer | — | Adversarial 검토 |
| code-reviewer | superpowers:code-reviewer | — | 코드 리뷰 |
| explore | Explore | — | 코드 탐색 |
| planner | Plan | — | 계획 수립 |

### Tier 2: general-purpose 대체 (model 파라미터 필수)

| 커스텀 에이전트 | model 오버라이드 | prompt 첫 줄 역할 명시 |
|----------------|:----------------:|----------------------|
| executor-high | `model="opus"` | `역할: Complex multi-file task executor. 모든 도구 사용 가능.` |
| executor | `model="sonnet"` | `역할: Focused task executor for implementation work.` |
| executor-low | `model="haiku"` | `역할: Simple single-file task executor.` |
| designer-high | `model="sonnet"` | `역할: Complex UI architecture and design systems.` |
| designer | `model="sonnet"` | `역할: UI/UX Designer-Developer. 스타일링 + 코드 생성.` |
| designer-low | `model="haiku"` | `역할: Simple styling and minor UI tweaks.` |
| qa-tester-high | `model="sonnet"` | `역할: Comprehensive production-ready QA testing.` |
| qa-tester | `model="sonnet"` | `역할: QA Runner. 6종 검증 (lint, type, unit, integration, build, security).` |
| writer | `model="haiku"` | `역할: Technical documentation writer.` |
| gap-detector | `model="haiku"` | `역할: 설계-구현 Gap 정량 분석기. Match Rate 계산.` |
| build-fixer | `model="sonnet"` | `역할: Build/TypeScript error fixer. 최소 diff로 빌드 수정.` |
| build-fixer-low | `model="haiku"` | `역할: Simple build error fixer. 단순 타입 에러 수정.` |
| researcher | `model="sonnet"` | `역할: External documentation & reference researcher.` |
| researcher-low | `model="haiku"` | `역할: Quick documentation lookups.` |
| analyst | `model="haiku"` | `역할: Pre-planning consultant for requirements analysis.` |
| architect-low | `model="haiku"` | `역할: Quick code questions & simple lookups.` |
| architect-medium | `model="sonnet"` | `역할: Architecture & Debugging Advisor - Medium complexity.` |
| code-reviewer-low | `model="haiku"` | `역할: Quick code quality checker.` |
| explore-high | `model="sonnet"` | `역할: Complex architectural search for deep system understanding.` |
| explore-medium | `model="haiku"` | `역할: Thorough codebase search with reasoning.` |
| scientist-high | `model="opus"` | `역할: Complex research, hypothesis testing, and ML specialist.` |
| scientist | `model="sonnet"` | `역할: Data analysis and research execution specialist.` |
| scientist-low | `model="haiku"` | `역할: Quick data inspection and simple statistics.` |
| security-reviewer | `model="sonnet"` | `역할: Security vulnerability detection specialist (OWASP Top 10).` |
| security-reviewer-low | `model="haiku"` | `역할: Quick security scan specialist.` |
| tdd-guide | `model="sonnet"` | `역할: TDD specialist enforcing Red-Green-Refactor methodology.` |
| tdd-guide-low | `model="haiku"` | `역할: Quick test suggestion specialist.` |
| vision | `model="haiku"` | `역할: Visual/media file analyzer for images, PDFs, and diagrams.` |
| frontend-dev | `model="sonnet"` | `역할: 프론트엔드 개발 및 UI/UX. React/Next.js 성능 최적화.` |
| ai-engineer | `model="sonnet"` | `역할: LLM 애플리케이션, RAG 시스템, 프롬프트 엔지니어링 전문가.` |
| catalog-engineer | `model="haiku"` | `역할: WSOPTV 카탈로그 및 제목 생성 전문가 (Block F/G).` |
| cloud-architect | `model="opus"` | `역할: 클라우드 인프라, 네트워크, 비용 최적화 전문가.` |
| claude-expert | `model="haiku"` | `역할: Claude Code, MCP, 에이전트, 프롬프트 엔지니어링 전문가.` |
| data-specialist | `model="sonnet"` | `역할: 데이터 분석, 엔지니어링, ML 파이프라인 전문가.` |
| database-specialist | `model="sonnet"` | `역할: DB 설계, 최적화, Supabase 전문가.` |
| devops-engineer | `model="sonnet"` | `역할: DevOps 전문가 (CI/CD, K8s, Terraform, 트러블슈팅).` |
| github-engineer | `model="sonnet"` | `역할: GitHub 및 Git 워크플로우 전문가.` |

### Fallback 사용 시 필수사항

1. **model 오버라이드 필수** (Tier 2): `Agent(subagent_type="general-purpose", model="opus", ...)` — 원래 에이전트의 모델 티어 유지
2. **prompt 역할 명시**: prompt 첫 줄에 `역할: {원래 에이전트 설명}` 추가
3. **READ-ONLY 에이전트**(architect): prompt에 `파일 수정 절대 금지. Read/Grep/Glob만 허용.` 명시
4. **Phase 4 보고서 기록**: Fallback 사용 에이전트와 원인을 보고서에 기록
5. **Lead 직접 실행 금지**: Fallback이 있더라도 Lead가 직접 구현하지 않음 (CLAUDE.md 규칙 3)

---

## Agent Teams 운영 규칙 (v21.0)

**모든 에이전트 호출은 Agent Teams in-process 방식을 사용합니다. Skill() 호출 0개.**

**모델 결정**: 에이전트 정의 파일(`.claude/agents/*.md`)의 `model:` 필드가 기본 모델을 결정합니다. Agent() 호출 시 선택적으로 `model` 파라미터(`"sonnet"`, `"opus"`, `"haiku"`)를 명시하여 오버라이드 가능합니다. Fallback(general-purpose) 시 `model` 명시 필수.
- Opus 티어: executor-high, architect, planner, critic, scientist-high (복잡한 구현/판단/계획/연구)
- Sonnet 티어: executor, code-reviewer, qa-tester, designer (반복 실행)
- Haiku 티어: explore, explore-medium, writer, analyst, vision, gap-detector, catalog-engineer, claude-expert (탐색/간단 문서/체크리스트)

### 팀 라이프사이클

1. **Phase 0**: `TeamCreate(team_name="pdca-{feature}")` — PDCA 시작 시 1회
2. **Phase 1-4**: `Agent(subagent_type="에이전트", name="역할", description="설명", team_name="pdca-{feature}")` → `SendMessage` → 완료 대기 → `shutdown_request`
3. **Phase 4**: 보고서 생성 후 Safe Cleanup (아래 절차)

### Phase 4 Safe Cleanup 절차 (v22.2)

**정상 종료 (5단계):**
1. writer teammate 완료 확인 (Mailbox 수신)
2. 모든 활성 teammate에 `SendMessage(type="shutdown_request")` 순차 전송
3. 각 teammate 응답 대기 (최대 5초). 무응답 시 다음 단계로 진행 (**차단 금지**)
4. `TeamDelete()` 실행
5. TeamDelete 실패 시 수동 fallback (⚠️ `rm -rf`는 tool_validator 차단 → Python 필수):
   ```bash
   python -c "import shutil,pathlib; [shutil.rmtree(pathlib.Path.home()/'.claude'/d/'pdca-{feature}', ignore_errors=True) for d in ['teams','tasks']]"
   ```

**세션 비정상 종료 후 복구:**
- 고아 팀 감지: `ls ~/.claude/teams/` — `pdca-*` 디렉토리가 남아있으면 고아 팀
- 복구 순서: `TeamDelete()` 시도 → 실패 시 Python 수동 정리
- 고아 task 정리 (UUID 형식만):
  ```bash
  python -c "import shutil,pathlib,re; [shutil.rmtree(p,ignore_errors=True) for p in pathlib.Path.home().joinpath('.claude','tasks').iterdir() if p.is_dir() and re.match(r'^[0-9a-f-]{36}$',p.name)]"
  ```
- stale todo 정리:
  ```bash
  python -c "import pathlib,time; [p.unlink() for p in pathlib.Path.home().joinpath('.claude','todos').glob('*.json') if time.time()-p.stat().st_mtime > 86400]"
  ```

**Context Compaction 후 팀 소실 시:**
- 증상: `TeamDelete()` 호출 시 "team not found" 에러
- 처리: 에러 무시하고 수동 정리 실행
- 원인: Issue #23620 — compaction 후 `~/.claude/teams/{name}/config.json` 미재주입

**VS Code 환경 (isTTY=false) 무한 대기 방지:**
- `settings.json`의 `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 확인 (in-process 모드)
- teammate 무응답 시 5초 후 강제 진행 (shutdown_request 응답 불필요)

### Teammate 운영 규칙

1. **Spawn 시 role name 명시**: `name="doc-analyst"`, `name="verifier"` 등 역할 명확히
2. **Task 할당**: `TaskCreate` → `SendMessage`로 teammate에게 작업 전달
3. **완료 대기**: Mailbox 자동 수신 (Lead가 polling 불필요)
4. **순차 작업**: 이전 teammate `shutdown_request` 완료 후 다음 teammate spawn
5. **병렬 작업**: 독립 작업은 동시 spawn 가능 (Phase 1.0 분석 등)

### Context 분리 장점 (vs 기존 단일 context)

| 기존 단일 context | Agent Teams |
|--------------|-------------|
| 결과가 Lead context에 합류 → overflow | Mailbox로 전달 → Lead context 보호 |
| foreground 3개 상한 필요 | 제한 없음 (독립 context) |
| "5줄 요약" 강제 | 불필요 |
| compact 실패 위험 | compact 실패 없음 |

---

## 세션 강제 종료 (`/auto stop`) + Lead 타임아웃 패턴

### Nuclear Option — Ctrl+C도 안 될 때 (외부 터미널 긴급 종료)

> **이 상황**: Claude Code 자체가 frozen. Ctrl+C 무효. `/auto stop` 입력 불가.
> **원인**: Node.js 이벤트 루프가 teammate IPC await 상태에서 블락.
> **해결**: **별도** PowerShell/CMD 창에서 외부 스크립트 실행.

```
Step 1: 새 PowerShell 창 열기 (Win+X → Terminal)
Step 2: python C:\claude\.claude\scripts\emergency_stop.py
        또는 즉시 전체 종료: python C:\claude\.claude\scripts\emergency_stop.py --force
Step 3: Claude Code 재시작 → claude
```

**emergency_stop.py 실행 순서:**
1. `~/.claude/teams/` + `~/.claude/tasks/` 고아 항목 전체 삭제
2. `~/.claude/todos/` stale TODO 초기화
3. `node.exe` (Claude Code) PID 탐색 → `taskkill /F /PID` 강제 종료

**수동 긴급 종료 (스크립트 없을 때):**
```powershell
# 1) Claude Code PID 확인
wmic process where "name='node.exe'" get processid,commandline

# 2) 해당 PID 강제 종료
taskkill /F /PID <확인된_PID>

# 3) 고아 팀 Python 정리
python -c "import shutil,pathlib; home=pathlib.Path.home(); [shutil.rmtree(p,ignore_errors=True) for d in ['teams','tasks'] for p in (home/'.claude'/d).iterdir() if p.is_dir()]"
```

### `/auto stop` — 즉시 실행 절차 (5단계)

Agent Teams hang 또는 강제 중단 필요 시 **순서대로** 실행:

**Step 1: Shutdown Request 전송**
```
SendMessage(type="shutdown_request", recipient="{teammate-name}", content="강제 중단")
# 모든 활성 teammate에 순차 전송 → 최대 5초 대기 → 무응답 시 Step 2 진행
```

**Step 2: TeamDelete 시도**
```
TeamDelete()
# 성공 → 종료
# "Cannot cleanup team with N active member(s)" 에러 → Step 3 진행
# "team not found" 에러 → 이미 삭제됨, 정상 종료
```

**Step 3: Python shutil.rmtree() 강제 삭제**
> ⚠️ `rm -rf ~/.claude/teams/...`는 `tool_validator.py`에 의해 **차단**됨. 반드시 Python 사용.

```bash
python -c "import shutil,pathlib; [shutil.rmtree(pathlib.Path.home()/'.claude'/d/'pdca-{feature}', ignore_errors=True) for d in ['teams','tasks']]"
```

**Step 4: TeamDelete 재시도**
```
TeamDelete()  # shutil 삭제 후 재시도. "team not found"도 정상.
```

**Step 5: 잔여 리소스 확인**
```bash
ls ~/.claude/teams/ | grep pdca
ls ~/.claude/tasks/ | grep pdca
```

### Lead 타임아웃 패턴 (Hang 방지)

```
# ❌ hang 위험 — description 누락
Agent(subagent_type="executor-high", name="impl-manager", team_name="pdca-{feature}", prompt="...")

# ✅ 올바른 패턴 (description 필수)
Agent(subagent_type="executor-high", name="impl-manager", description="4조건 자체 루프 구현 관리", team_name="pdca-{feature}", prompt="...")
```

**5분 Heartbeat Timeout:**
- Claude Code 내장 메커니즘 — teammate가 5분+ tool call 없으면 자동 비활성화

**Hang 발생 시 즉시 확인:**
```
1. ~/.claude/teams/ 에 pdca-* 디렉토리 잔존 여부
2. ~/.claude/tasks/ 에 관련 디렉토리 잔존 여부
3. Agent() 호출에 description 설정 여부
4. teammate에 완료 메시지 도달 여부
```

---

## Worktree 통합 (`--worktree` 옵션)

### Step 0.1: Worktree 설정 (Phase 0, TeamCreate 직후)

```bash
# 1. worktree 생성
git worktree add "C:/claude/wt/{feature}" -b "feat/{feature}" main

# 2. .claude junction 생성
cmd /c "mklink /J \"C:\\claude\\wt\\{feature}\\.claude\" \"C:\\claude\\.claude\""

# 3. 검증
git worktree list
ls "C:/claude/wt/{feature}/.claude/commands"
```

모든 Phase의 파일 경로에 worktree prefix 적용:
- `docs/01-plan/` → `C:\claude\wt\{feature}\docs\01-plan\`

### Teammate Prompt 패턴 (`--worktree` 시)

```
prompt="모든 파일은 C:\\claude\\wt\\{feature}\\ 하위에서 작업하세요.
       C:\\claude\\wt\\{feature}\\docs\\01-plan\\{feature}.plan.md를 참조하여 설계 문서를 작성하세요."
```

### Phase 4 Worktree Cleanup

```bash
# 1. junction 제거
cmd /c "rmdir \"C:\\claude\\wt\\{feature}\\.claude\""

# 2. worktree 제거
git worktree remove "C:/claude/wt/{feature}"

# 3. 정리
git worktree prune
```

### Agent Teams 병렬 격리 (HEAVY 모드)

```bash
git worktree add "C:/claude/wt/{feature}-impl" "feat/{feature}"
git worktree add "C:/claude/wt/{feature}-test" "feat/{feature}"
cmd /c "mklink /J \"C:\\claude\\wt\\{feature}-impl\\.claude\" \"C:\\claude\\.claude\""
cmd /c "mklink /J \"C:\\claude\\wt\\{feature}-test\\.claude\" \"C:\\claude\\.claude\""
```

```
Agent(subagent_type="executor-high", name="impl", description="구현 실행", team_name="pdca-{feature}", prompt="C:\\claude\\wt\\{feature}-impl\\ 경로에서 구현. 다른 경로 수정 금지.")
Agent(subagent_type="executor-high", name="tester", description="테스트 작성", team_name="pdca-{feature}", prompt="C:\\claude\\wt\\{feature}-test\\ 경로에서 테스트 작성. 다른 경로 수정 금지.")
```

---

## Resume (`/auto resume`) — Context Recovery

`/clear` 또는 새 세션 시작 후:
1. `docs/.pdca-status.json` 읽기 → `primaryFeature`와 `phaseNumber` 확인
2. 산출물 존재 검증: Plan 파일, Design 파일 유무로 실제 진행 Phase 교차 확인
3. Git 상태 확인: `git branch --show-current`, `git status --short`
4. Phase 2 중단 시: `implManagerIteration` 필드로 impl-manager 반복 위치 확인
5. `TeamCreate(team_name="pdca-{feature}")` 새로 생성 (이전 팀은 복원 불가)
6. 해당 Phase부터 재개 (완료된 Phase 재실행 금지)

### Resume 시 impl-manager 재개

`pdca-status.json`에 추가되는 필드:
```json
{
  "implManagerIteration": 5,
  "implManagerStatus": "in_progress",
  "implManagerRemainingIssues": ["test failure in X", "lint error in Y"]
}
```

Resume 시 impl-manager 재개 prompt:
```
"이전 시도에서 {N}회까지 진행됨. 남은 이슈: {remaining_issues}.
 이전 시도의 변경 사항은 이미 파일에 반영되어 있음. 이어서 진행."
```

---

## 자율 발견 모드 상세

| Tier | 이름 | 발견 대상 | 실행 |
|:----:|------|----------|------|
| 0 | CONTEXT | context limit 접근 | `/clear` + `/auto resume` 안내 |
| 1 | EXPLICIT | 사용자 지시 | 해당 작업 실행 |
| 2 | URGENT | 빌드/테스트 실패 | `/debug` 실행 |
| 3 | WORK | pending TODO, 이슈 | 작업 처리 |
| 4 | SUPPORT | staged 파일, 린트 에러 | `/commit`, `/check` |
| 5 | AUTONOMOUS | 코드 품질 개선 | 리팩토링 제안 |

---

## Execution Loop 코드 블록

```python
# --loop 옵션 파싱
loop_enabled = "--loop" in args
loop_max = 5  # 기본값
if loop_enabled:
    # --loop N 형태 파싱
    loop_idx = args.index("--loop")
    if loop_idx + 1 < len(args) and args[loop_idx + 1].isdigit():
        loop_max = int(args[loop_idx + 1])

# Execution Loop
loop_count = 0
consecutive_failures = 0
MAX_CONSECUTIVE_FAILURES = 3

while loop_enabled and loop_count < loop_max:
    loop_count += 1

    # Phase 0-4 실행
    result = execute_pdca_cycle(next_task)

    if result.success:
        consecutive_failures = 0
    else:
        consecutive_failures += 1
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            # Circuit Breaker 발동
            print(f"Circuit Breaker: 연속 {MAX_CONSECUTIVE_FAILURES}회 실패. 루프 중단.")
            break

    # 컨텍스트 관리
    # /session compact 실행

    # 다음 작업 탐지
    next_task = find_next_task(backlog=True, issues=True)
    if not next_task:
        print("다음 작업 없음. 루프 종료.")
        break

# 루프 종료 보고서
print_loop_summary(loop_count, loop_max, results)
```
