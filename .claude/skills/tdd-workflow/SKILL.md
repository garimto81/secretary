---
name: tdd-workflow
description: "[DEPRECATED] /tdd로 리다이렉트됨"
version: 2.0.0
deprecated: true
redirect: tdd
deprecation_message: "/tdd-workflow는 /tdd로 통합되었습니다. /tdd를 사용하세요."
triggers:
  keywords: []
auto_trigger: false
---

# /tdd-workflow → /tdd (Deprecated)

⚠️ **이 스킬은 deprecated 되었습니다.**

## 리다이렉트

`/tdd-workflow`는 `/tdd`로 통합되었습니다.

```bash
# 대신 사용하세요
/tdd <feature-name>
```

## 마이그레이션 안내

| 기존 | 새로운 |
|------|--------|
| `/tdd-workflow` | `/tdd` |
| `python scripts/validate_red_phase.py` | `/tdd` 내부에서 자동 실행 |
| `python scripts/tdd_auto_cycle.py` | `/tdd` 내부에서 자동 실행 |

## Red-Green-Refactor

`/tdd`는 동일한 Red-Green-Refactor 워크플로우를 제공합니다:

1. 🔴 Red: 실패하는 테스트 작성
2. 🟢 Green: 최소 구현
3. ♻️ Refactor: 코드 개선

## 상세 문서

통합된 스킬: `.claude/skills/tdd/SKILL.md`
