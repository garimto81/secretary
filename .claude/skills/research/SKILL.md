---
name: research
description: RPI Phase 1 - 코드베이스 분석, 리서치, AI 리뷰
version: 2.0.0
omc_delegate: oh-my-claudecode:research
omc_agents:
  - researcher
  - researcher-low
  - scientist
  - explore
triggers:
  keywords:
    - "research"
    - "리서치"
    - "분석"
    - "조사"
---

# /research - 통합 리서치 커맨드

## OMC Integration

이 스킬은 OMC `research` 스킬에 위임합니다.

### 실행 방법

```python
Skill(skill="oh-my-claudecode:research", args="리서치 주제")

# 또는 직접 에이전트 호출
Task(subagent_type="oh-my-claudecode:researcher", model="sonnet",
     prompt="리서치: [주제]")
```

### OMC 에이전트

| 에이전트 | 모델 | 용도 |
|----------|------|------|
| `researcher` | sonnet | 문서/API 리서치 |
| `researcher-low` | haiku | 빠른 문서 조회 |
| `scientist` | sonnet | 데이터 분석 |
| `explore` | haiku | 코드베이스 탐색 |

## 인과관계 (CRITICAL - 절대 보존)

```
/work --loop Tier 3
    └── /research code (코드 분석 필요 시)
    └── /research web (오픈소스 탐색 필요 시)

/work Phase 1
    └── /research plan (구현 계획 수립)
```

**이 인과관계는 OMC 위임과 무관하게 그대로 유지됩니다.**

## 서브커맨드 (100% 보존)

| 서브커맨드 | 설명 |
|-----------|------|
| `/research code [path]` | 코드베이스 분석 |
| `/research web <keyword>` | 오픈소스/솔루션 검색 |
| `/research plan [target]` | 구현 계획 수립 |
| `/research review [scope]` | AI 코드 리뷰 |

## 서브커맨드 상세

### /research code - 코드베이스 분석 (기본값)

```bash
/research                    # 현재 디렉토리 분석
/research code               # 전체 코드베이스 분석
/research code src/api/      # 특정 경로 분석
/research code 123           # 이슈 #123 관련 코드
/research code --codebase    # 전체 구조 분석
/research code --deps        # 의존성 분석
```

### /research web - 오픈소스/솔루션 검색

```bash
/research web "React state management"
/research web "Python async HTTP client"
```

**수행 작업:**
1. 관련 오픈소스 라이브러리 검색
2. Make vs Buy 분석
3. 유사 구현 사례 조사

### /research plan - 구현 계획 수립

```bash
/research plan 123           # 이슈 #123 구현 계획
/research plan "user auth"   # 기능 구현 계획
/research plan --tdd         # TDD 기반 계획
/research plan --detailed    # 상세 계획
```

### /research review - AI 코드 리뷰

```bash
/research review             # staged 변경사항 리뷰
/research review --branch    # 브랜치 전체 변경사항
/research review --pr #42    # 특정 PR 리뷰
/research review --docs      # 문서 일관성 검사
```

## 옵션

| 옵션 | 설명 |
|------|------|
| `--save` | 결과를 `.claude/research/`에 저장 |
| `--quick` | 빠른 탐색 (5분 이내) |
| `--thorough` | 철저한 분석 (15-30분) |

## RPI 워크플로우

```
[R] Research → [P] Plan → [I] Implement
```

| Phase | 커맨드 | 목적 |
|-------|--------|------|
| **R** | `/research` | 정보 수집, 코드 분석 |
| **P** | `/research plan` | 구현 계획 수립 |
| **I** | 구현 | 코드 작성, 테스트 |

## 커맨드 파일 참조

상세 워크플로우: `.claude/commands/research.md`
