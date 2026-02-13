---
name: agent-teamworks
description: Multi-Agent Team Workflow - 4개 전문 팀 자율 협업 시스템
version: 1.0.0
triggers:
  keywords:
    - "/team"
    - "/teamwork"
    - "team dev"
    - "team quality"
    - "team ops"
    - "team research"
model_preference: sonnet
auto_trigger: true
omc_delegate: oh-my-claudecode:ultrawork
omc_agents:
  - executor
  - executor-high
  - architect
  - planner
---

# Agent Teamworks - Multi-Agent Team Workflow

> 4개 전문 팀(Dev, Quality, Ops, Research)이 자율적으로 협업하는 LangGraph 기반 시스템

## 아키텍처

```
/auto (복잡도 기반 라우팅)
  │
  ├─ score < 4 → 기존 경로
  └─ score >= 4 → Team Coordinator
                    │
        ┌───────────┼───────────┬───────────┐
        ▼           ▼           ▼           ▼
    Dev Team    Quality Team  Ops Team   Research Team
```

## 서브커맨드

| 커맨드 | 동작 |
|--------|------|
| `/team dev "작업"` | Dev Team 단독 실행 |
| `/team quality "작업"` | Quality Team 단독 실행 |
| `/team ops "작업"` | Ops Team 단독 실행 |
| `/team research "작업"` | Research Team 단독 실행 |
| `/teamwork "프로젝트"` | Coordinator → 4팀 오케스트레이션 |
| `/team status` | 현재 팀 실행 상태 조회 |

## 실행 지시

### `/team {팀명} "작업"` 실행 시

```python
from src.agents.teams import Coordinator

result = Coordinator.run_single_team("{팀명}", "작업 설명")
```

또는 OMC 에이전트로 위임:
```
Task(
  subagent_type="oh-my-claudecode:executor",
  model="sonnet",
  prompt="src/agents/teams/{팀명}_team.py의 {팀}Team을 실행하세요.
  태스크: {작업 설명}"
)
```

### `/teamwork "프로젝트"` 실행 시

```python
from src.agents.teams import Coordinator

coordinator = Coordinator()
result = coordinator.run("프로젝트 설명")
```

## 팀 구성

### Dev Team
TeamLead → [Architect, Frontend, Backend, Tester, Docs] → Integrator

### Quality Team (PDCA)
Planner → [Reviewer, Analyzer, GapDetector, SecurityChecker] → Iterator/Reporter
- gap < 90%: Iterator → 재검증 (최대 5회)
- gap >= 90%: Reporter → 보고서

### Ops Team
TeamLead → [CI_CD, Infra, Monitor, Security] → Integrator

### Research Team
TeamLead → [CodeAnalyst, WebResearcher, DataScientist, DocSearcher] → Synthesizer

## 복잡도 → 팀 배치

| 점수 | 투입 팀 |
|:----:|---------|
| 0-3 | 기존 경로 |
| 4-5 | Dev |
| 6-7 | Dev + Quality |
| 8-9 | Dev + Quality + Research |
| 10 | 4팀 전체 |

## 코드 위치

| 파일 | 역할 |
|------|------|
| `src/agents/teams/base_team.py` | 추상 기반 클래스 |
| `src/agents/teams/prompts.py` | 프롬프트 중앙 관리 |
| `src/agents/teams/dev_team.py` | Dev Team |
| `src/agents/teams/quality_team.py` | Quality Team |
| `src/agents/teams/ops_team.py` | Ops Team |
| `src/agents/teams/research_team.py` | Research Team |
| `src/agents/teams/coordinator.py` | Coordinator |
