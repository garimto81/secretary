---
name: debug
description: 가설-검증 기반 디버깅
version: 2.0.0
omc_delegate: oh-my-claudecode:analyze
triggers:
  keywords:
    - "debug"
    - "/debug"
    - "디버깅"
---

# /debug - 체계적 디버깅

## OMC Integration

이 스킬은 OMC `analyze` 스킬에 위임합니다.

### 실행 방법

```python
Skill(skill="oh-my-claudecode:analyze", args="문제 분석")

# 또는 architect 직접 호출
Task(subagent_type="oh-my-claudecode:architect", model="opus",
     prompt="문제 원인 분석: [에러 내용]")
```

## 디버깅 Phase

1. D0: 문제 정의
2. D1: 가설 수립
3. D2: 검증
4. D3: 해결
5. D4: 회고
