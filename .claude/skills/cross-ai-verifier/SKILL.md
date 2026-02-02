---
name: cross-ai-verifier
description: "[DEPRECATED] /verify로 리다이렉트됨"
version: 2.0.0
deprecated: true
redirect: verify
deprecation_message: "/cross-ai-verifier는 /verify로 통합되었습니다. /verify를 사용하세요."
triggers:
  keywords: []
auto_trigger: false
---

# /cross-ai-verifier → /verify (Deprecated)

⚠️ **이 스킬은 deprecated 되었습니다.**

## 리다이렉트

`/cross-ai-verifier`는 `/verify`로 통합되었습니다.

```bash
# 대신 사용하세요
/verify src/auth.py --focus security
/verify --all src/ --parallel
```

## 마이그레이션 안내

| 기존 | 새로운 |
|------|--------|
| `/cross-ai-verifier` | `/verify` |
| `verify --provider openai` | `/verify --provider openai` |
| `verify --provider gemini` | `/verify --provider gemini` |

## 기능

`/verify`는 동일한 Cross-AI 검증 기능을 제공합니다:

- OpenAI GPT-4 검증
- Gemini Pro 검증
- 보안/버그/성능 분석

## 상세 문서

통합된 스킬: `.claude/skills/verify/SKILL.md`
