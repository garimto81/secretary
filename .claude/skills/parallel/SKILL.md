---
name: parallel
description: Multi-agent parallel execution (dev, test, review, research)
version: 2.0.0
omc_delegate: oh-my-claudecode:ultrawork
omc_agents:
  - executor
  - executor-high
  - qa-tester
  - architect
triggers:
  keywords:
    - "parallel"
    - "병렬"
    - "ulw"
    - "ultrawork"
---

# /parallel - 병렬 멀티에이전트 실행

## OMC Integration

이 스킬은 OMC `ultrawork` 스킬에 위임합니다.

### 실행 방법

```python
Skill(skill="oh-my-claudecode:ultrawork", args="작업 설명")

# 또는 직접 에이전트 호출 (병렬)
Task(subagent_type="oh-my-claudecode:executor", model="sonnet",
     prompt="작업 1", run_in_background=True)
Task(subagent_type="oh-my-claudecode:executor", model="sonnet",
     prompt="작업 2", run_in_background=True)
```

### OMC 에이전트

| 에이전트 | 모델 | 용도 |
|----------|------|------|
| `executor` | sonnet | 일반 구현 작업 |
| `executor-high` | opus | 복잡한 구현 |
| `qa-tester` | sonnet | 테스트 작업 |
| `architect` | opus | 아키텍처 분석 |

## 서브커맨드 (100% 보존)

| 서브커맨드 | 설명 | 에이전트 수 |
|-----------|------|:-----------:|
| `/parallel dev` | 병렬 개발 | 4 |
| `/parallel test` | 병렬 테스트 | 4 |
| `/parallel review` | 병렬 코드 리뷰 | 4 |
| `/parallel research` | 병렬 리서치 | 4 |
| `/parallel check` | 충돌 검사 | 1 |

## 서브커맨드 상세

### /parallel dev - 병렬 개발

```bash
/parallel dev "사용자 인증 기능"
/parallel dev --branch "API + UI 동시 개발"
```

**에이전트 역할:**
| 에이전트 | 역할 |
|----------|------|
| Architect | 설계, 인터페이스 정의 |
| Coder | 핵심 로직 구현 |
| Tester | 테스트 작성 |
| Docs | 문서화 |

### /parallel test - 병렬 테스트

```bash
/parallel test
/parallel test --module auth
/parallel test --strict
```

**테스터 역할:**
| 에이전트 | 범위 |
|----------|------|
| Unit | 함수, 클래스, 모듈 |
| Integration | API, DB 연동 |
| E2E | 전체 사용자 플로우 |
| Security | OWASP Top 10 |

### /parallel review - 병렬 코드 리뷰

```bash
/parallel review
/parallel review src/auth/
/parallel review --security-only
```

**리뷰어 역할:**
| 에이전트 | 검토 항목 |
|----------|----------|
| Security | SQL Injection, XSS |
| Logic | 알고리즘, 엣지 케이스 |
| Style | 명명 규칙, 가독성 |
| Performance | 복잡도, 캐싱 |

### /parallel research - 병렬 리서치

```bash
/parallel research "React vs Vue 비교"
/parallel research "AI 코딩 도구"
```

### /parallel check - 충돌 검사

```bash
/parallel check "Task A, Task B, Task C"
/parallel check --tasks tasks.md
```

**병렬 작업 전 파일 충돌 가능성 사전 분석:**
```
┌──────────────┬────┬────┬────┬─────────┐
│ 파일         │ A  │ B  │ C  │ 충돌    │
├──────────────┼────┼────┼────┼─────────┤
│ auth.ts      │ W  │ R  │ -  │ -       │
│ user.ts      │ W  │ W  │ -  │ ⚠️ A-B  │
└──────────────┴────┴────┴────┴─────────┘
```

## 커맨드 파일 참조

상세 워크플로우: `.claude/commands/parallel.md`
