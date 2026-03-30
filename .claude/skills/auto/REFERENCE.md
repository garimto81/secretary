# /auto REFERENCE — Phase별 분리 인덱스 (v25.2 Progressive Disclosure)

> **v25.2 변경**: 단일 3,088줄 REFERENCE.md → Phase별 6개 파일로 분리.
> SKILL.md는 오케스트레이터(218줄), 각 Phase 진입 시 해당 reference만 Read 로딩.
> **v25.0**: OOP Coupling/Cohesion. **v24.0**: Plugin Fusion. **v23.0**: Phase 0→4 재구성.

---

## Phase별 Reference 파일

| Phase | 파일 | 줄 수 | 로딩 시점 | 내용 |
|:-----:|------|:-----:|----------|------|
| 0 | `SKILL.md` (본체) | 218 | `/auto` 트리거 즉시 | 옵션, 팀 생성, 복잡도, 라우팅 |
| 1 | `references/phase-1-plan.md` | 830 | Phase 0 완료 후 | PRD, 사전 분석, 계획+설계, Socratic Q |
| 2 | `references/phase-2-build.md` | 474 | PlanContract 준비 후 | 구현, 코드 리뷰, Architect Gate, impl-manager |
| 3 | `references/phase-3-verify.md` | 416 | BuildContract 준비 후 | QA 사이클, E2E, 최종 검증, D0-D4 |
| 4 | `references/phase-4-close.md` | 141 | VerifyContract 준비 후 | 보고서, 메트릭, Safe Cleanup |

## 공통 Reference 파일

| 파일 | 줄 수 | 로딩 조건 | 내용 |
|------|:-----:|----------|------|
| `references/common.md` | 477 | Agent 미인식, 팀 운영 이슈 시 | Contracts 스키마, Fallback 매핑, Agent Teams, Session |
| `references/options-handlers.md` | 615 | `--mockup`, `--anno` 등 옵션 시 | 16개 옵션 핸들러 상세 워크플로우 |
| `guidelines/image-analysis.md` | — | 이미지 분석 시 | Vision AI 가이드라인 |

---

## Phase 매핑 (v22.4 → v25.2)

| v22.4 | v23.0 | v25.2 Reference |
|-------|-------|-----------------|
| Phase 0 (INIT) | Phase 0 (INIT) | `SKILL.md` |
| Phase 0.5 (PRD) | Phase 1, Step 1.1 | `references/phase-1-plan.md` |
| Phase 1 (PLAN) | Phase 1, Steps 1.2-1.3 | `references/phase-1-plan.md` |
| Phase 2 (DESIGN) | Phase 1, Step 1.4 | `references/phase-1-plan.md` |
| Phase 3 (DO) | Phase 2 (BUILD) | `references/phase-2-build.md` |
| Phase 4 (CHECK) | Phase 3 (VERIFY) | `references/phase-3-verify.md` |
| Phase 5 (ACT) | Phase 4 (CLOSE) | `references/phase-4-close.md` |

---

## 컨텍스트 절감 효과

| 시나리오 | v25.0 (단일 파일) | v25.2 (분리) | 절감률 |
|---------|:-----------------:|:------------:|:------:|
| `/auto` 트리거 | 504줄 로딩 | 218줄 로딩 | 57% |
| Phase 2 진입 | +3,088줄 참조 가능 | +474줄만 로딩 | 85% |
| Phase 3 진입 | +3,088줄 참조 가능 | +416줄만 로딩 | 87% |
| `--mockup` 사용 | +3,088줄 참조 가능 | +615줄만 로딩 | 80% |

---

## 사용 방법

```
# Phase 0 (SKILL.md에서 자동 처리)
# Phase 1 진입 시:
Read("C:/claude/.claude/skills/auto/references/phase-1-plan.md")

# Phase 2 진입 시:
Read("C:/claude/.claude/skills/auto/references/phase-2-build.md")

# 옵션 핸들러 필요 시:
Read("C:/claude/.claude/skills/auto/references/options-handlers.md")

# Agent 미인식/팀 이슈 시:
Read("C:/claude/.claude/skills/auto/references/common.md")
```

> **주의**: 기존 REFERENCE.md의 전체 내용은 위 6개 파일로 분리되었습니다.
> 이 파일은 인덱스 역할만 합니다. 상세 내용은 각 reference 파일을 참조하세요.
