---
name: check
description: 코드 품질 및 보안 검사
version: 2.0.0
omc_delegate: oh-my-claudecode:ultraqa
triggers:
  keywords:
    - "check"
    - "/check"
    - "검사"
---

# /check - 코드 품질 검사

## OMC Integration

이 스킬은 OMC `ultraqa` 스킬에 위임합니다.

### 실행 방법

```python
Skill(skill="oh-my-claudecode:ultraqa", args="코드 품질 검사")
```

### QA 사이클
1. 테스트 실행
2. 실패 시 수정
3. 통과까지 반복

## 직접 실행 (옵션)

```bash
# 린트
ruff check src/ --fix

# 테스트
pytest tests/ -v
```
