---
name: audit
version: 2.0.0
description: >
  Daily configuration audit and workflow optimization for Claude Code setup. Triggers on "audit", "점검", "health check", "trend". Use when verifying CLAUDE.md consistency, checking plugin health, reviewing GitHub issues, or running trend-based analysis.
triggers:
  keywords:
    - "audit"
    - "trend"
    - "워크플로우 개선"
    - "plugin health"
    - "skill audit"
---

# /audit (v24.0 Plugin Fusion)

이 스킬은 `.claude/commands/audit.md` 커맨드 파일의 내용을 실행합니다.

## 서브커맨드 라우팅

| 서브커맨드 | 동작 |
|-----------|------|
| (없음) | **통합 점검: 설정 9항목 + 트렌드 분석 + 자동 적용** |
| `config` | 설정 점검만 (CLAUDE.md, 커맨드, 에이전트, 스킬, 문서 동기화, 추적 이슈, Plugin Health, Skill TDD) |
| `issues` | GitHub 추적 이슈 상태 확인만 (`.claude/config/tracked-issues.json` 기반) |
| `quick` | 빠른 점검 (버전/개수만) |
| `deep` | 심층 점검 (내용 분석 + Setup Audit 포함) |
| `fix` | 발견된 문제 자동 수정 |
| `baseline` | 현재 상태를 기준으로 저장 |
| `suggest [영역]` | 솔루션 추천 |
| `trend` | 웹 리서치 기반 워크플로우 개선 분석 + /auto 갭 분석 + 결과 캐싱 |
| `trend --apply` | 트렌드 분석 + 자동 적용 + 커밋 + 결과 캐싱 |

## 통합 워크플로우 (기본 동작)

`/audit` 단독 실행 시 설정 점검(9항목)과 트렌드 분석을 한번에 수행합니다.

```
/audit 실행
    │
    ├─ [Phase 1] 설정 점검 (9항목)
    │       ├─ [1/9] CLAUDE.md 점검 (버전, 커맨드/에이전트/스킬 개수)
    │       ├─ [2/9] 커맨드 점검 (frontmatter, 필수 섹션)
    │       ├─ [3/9] 에이전트 점검 (역할, 전문분야, 도구)
    │       ├─ [4/9] 스킬 점검 (SKILL.md 존재, 트리거)
    │       ├─ [5/9] 문서 동기화 점검
    │       ├─ [6/9] GitHub 추적 이슈 상태 확인
    │       ├─ [7/9] Plugin Health Check (v24.0)
    │       ├─ [8/9] Skill TDD Audit (v24.0)
    │       └─ [9/9] Setup Audit (deep/HEAVY만)
    │
    ├─ [Phase 2] 웹 리서치 기반 트렌드 분석
    │       ├─ 현재 워크플로우 인벤토리 수집
    │       ├─ researcher 에이전트 웹 리서치 (3-tier 쿼리)
    │       ├─ analyst 에이전트 갭 분석
    │       ├─ 개선 아이디어 출력
    │       └─ 결과 캐싱 (.claude/research/)
    │
    └─ [Phase 3] 통합 결과 요약
```

**핵심 규칙:**
- Phase 1은 항상 실행 (9/9 중 Setup Audit는 deep/HEAVY 조건부)
- Phase 2는 항상 실행 (WebSearch 실패 시만 스킵)
- 24시간 이내 캐시 존재 시 재사용 옵션 제공
- Phase 3에서 설정 점검 + 트렌드 결과 통합 출력

## v24.0 신규 점검 항목

### Plugin Health Check [7/9]
`references/plugin-fusion-rules.md` 기반 플러그인 상태 검증:
- 5개 플러그인 존재 확인 (feature-dev, code-review, superpowers, claude-code-setup, typescript-lsp)
- Project Type Detection 정확성 (파일 존재 → 타입 감지)
- 복잡도-플러그인 매핑 일치 (LIGHT/STANDARD/HEAVY)
- Iron Laws 3개 주입 여부 (REFERENCE.md Gate 지점)

### Skill TDD Audit [8/9]
superpowers 17개 스킬 → /auto Phase 매핑 검증:
- 17개 스킬 전수 체크 (fusion-rules.md §3 기준)
- 주입 시점 일치 (SKILL.md/REFERENCE.md 교차 검증)
- Cross-cutting 3개 Iron Laws 전 Phase 적용 확인
- 미사용/미매핑 스킬 감지

### Setup Audit [9/9] (deep/HEAVY만)
claude-code-setup automation-recommender 활용:
- Hook/에이전트/스킬 최적화 제안
- MCP 서버 활용도 점검

## `trend` 서브커맨드 워크플로우

```
/audit trend 실행
    │
    ├─ [1/5] 현재 워크플로우 인벤토리 수집
    ├─ [2/5] 웹 리서치 (researcher 에이전트, 8개 쿼리)
    ├─ [3/5] 갭 분석 (analyst 에이전트)
    ├─ [4/5] 개선 아이디어 제안 출력
    └─ [5/5] 결과 캐싱
```

**핵심 규칙:**
- Phase 2는 항상 실행 (WebSearch 타임아웃 시만 스킵)
- 24시간 이내 캐시 존재 시 재사용 여부 질문
- `--refresh` 시 캐시 무시, 새로 검색
- `--apply` 시 Step 4.5(자동 적용 + 커밋) 추가 실행

## 커맨드 파일 참조

상세 워크플로우: `.claude/commands/audit.md`
