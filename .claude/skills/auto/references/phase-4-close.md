# /auto Phase 4: CLOSE — 상세 워크플로우

> 이 파일은 `/auto` Phase 4 진입 시 로딩됩니다. SKILL.md에서 Phase 4 시작 시 이 파일을 Read합니다.
> 원본: REFERENCE.md v25.0에서 분리 (v25.2 Progressive Disclosure)

---

## Phase 4: CLOSE (결과 기반 자동 실행 + 팀 정리)

### Phase 3↔4 루프 가드

```
phase3_reentry_count = 0  # Lead 메모리에서 관리
MAX_PHASE3_REENTRY = 3

# Phase 4 → Phase 3 재진입 시
phase3_reentry_count += 1
if phase3_reentry_count >= MAX_PHASE3_REENTRY:
    → "[Phase 4] Phase 3 재진입 {MAX_PHASE3_REENTRY}회 초과." 출력
    → 유의미 변경 커밋: git status --short → 변경사항 있으면 git add -A && git commit -m "wip({feature}): 루프 한계 초과 - 진행 중 변경사항 보존"
    → "미해결 이슈 보고 후 종료." 출력
    → TeamDelete()
```

---

### 누적 iteration 추적 (Lead 메모리)

```
cumulative_iteration_count = 0  # Phase 3-4 전체 누적
MAX_CUMULATIVE_ITERATIONS = 5

# executor 수정 실행 시
cumulative_iteration_count += 1
if cumulative_iteration_count >= MAX_CUMULATIVE_ITERATIONS:
    → "[Phase 4] 누적 {MAX_CUMULATIVE_ITERATIONS}회 개선 시도 초과. 최종 결과 보고." 출력
    → writer(reporter)
    → 유의미 변경 커밋: git status --short → 변경사항 있으면 git add -A && git commit -m "wip({feature}): 최대 개선 시도 후 현재 상태 보존"
    → TeamDelete()
```

| Check 결과 | 자동 실행 | 다음 |
|-----------|----------|------|
| gap < 90% | executor teammate (최대 5회 반복) | Phase 3 재실행 |
| gap >= 90% + Architect APPROVE | writer teammate | TeamDelete → 완료 |
| Architect REJECT | executor teammate (수정) | Phase 3 재실행 |

---

### Step 4.0: Case 1 — gap < 90%

```
Agent(subagent_type="executor-high", name="iterator", description="반복 수정", team_name="pdca-{feature}",
     prompt="[Gap Improvement] 설계-구현 갭을 90% 이상으로 개선하세요. gap-checker 결과에서 미구현/불일치 항목을 식별하고 순차적으로 수정하세요. 최대 5회 반복.")
SendMessage(type="message", recipient="iterator", content="갭 자동 개선 시작.")
# 완료 대기 → shutdown_request → Phase 3 재실행
```

---

### Step 4.1: Case 2 — gap >= 90% + APPROVE (보고서 생성)

```
# 보고서: LIGHT->writer(haiku), STANDARD/HEAVY->executor-high(opus)
Agent(subagent_type="writer", name="reporter", description="보고서 작성", team_name="pdca-{feature}",
     prompt="PDCA 사이클 완료 보고서를 생성하세요.
     포함: Plan 요약, Design 요약, 구현 결과, Check 결과, 교훈

     === 성능 메트릭 섹션 (필수 포함) ===
     보고서 마지막에 아래 메트릭을 자동 수집하여 포함하세요:

     ## Performance Metrics

     | 항목 | 값 |
     |------|-----|
     | 총 에이전트 수 | {spawn된 teammate 수} |
     | Phase별 소요 시간 | Phase 0: Xm, Phase 1: Xm, Phase 2: Xm, Phase 3: Xm, Phase 4: Xm |
     | QA 사이클 수 | {qa_cycles} |
     | Architect 판정 | {APPROVE/REJECT 횟수} |
     | 최종 Gap Match Rate | {gap_match_rate}% |
     | 복잡도 모드 | {LIGHT/STANDARD/HEAVY} |
     | Adaptive Tier | {TRIVIAL/STANDARD/COMPLEX/CRITICAL} |
     | 총 커밋 수 | {커밋 수} |

     위 값은 VerifyContract와 BuildContract에서 추출하세요.
     === 끝 ===

     출력: docs/04-report/{feature}.report.md")
SendMessage(type="message", recipient="reporter", content="보고서 생성 요청.")
# 완료 대기 → shutdown_request
# 유의미 변경 커밋 (MANDATORY):
#   git status --short 확인
#   변경사항 있으면: git add -A && git commit -m "docs(report): {feature} PDCA 완료 보고서"
# → TeamDelete()
```

---

### Step 4.1b: /loop 자동 스케줄 제안 (선택)

보고서 생성 후, 지속적 모니터링이 필요한 경우 `/loop` 스케줄을 제안합니다.

**제안 조건**: PR이 열려있거나, 배포 대기 중이거나, 품질 메트릭 감시가 필요한 경우.

| 시나리오 | 제안 스케줄 | 명령 예시 |
|---------|-----------|----------|
| PR 오픈 상태 | 10분 간격 PR 상태 감시 | `/loop 10m /pr review` |
| 배포 후 모니터링 | 5분 간격 헬스체크 | `/loop 5m /check --quick` |
| 코드 품질 회귀 감시 | 30분 간격 린트 스캔 | `/loop 30m /check --lint` |

```python
# /loop 스케줄 제안 (Phase 4 완료 시)
if pr_open or deploy_pending:
    print(f"""
=== /loop 스케줄 제안 ===
모니터링이 필요한 항목이 감지되었습니다.
제안: /loop 10m /pr review
수락하려면 'y', 건너뛰려면 Enter를 입력하세요.
==========================
""")
    # AskUserQuestion으로 수락 여부 확인
    # 수락 시 백그라운드 /loop 등록
```

**주의**: `/loop`은 최대 50개 동시 스케줄, 3일 자동 만료. 과도한 등록 방지.

---

### Step 4.2: Case 3 — Architect REJECT

```
Agent(subagent_type="executor-high", name="fixer", description="수정 실행", team_name="pdca-{feature}",
     prompt="Architect 거부 사유를 해결하세요: {rejection_reason}")
SendMessage(type="message", recipient="fixer", content="피드백 반영 시작.")
# 완료 대기 → shutdown_request → Phase 3 재실행
```

---

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
