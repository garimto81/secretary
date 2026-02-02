---
name: auto-workflow
description: "[DEPRECATED] /auto로 리다이렉트됨"
version: 4.1.0
deprecated: true
redirect: auto
deprecation_message: "/auto-workflow는 /auto로 통합되었습니다. /auto를 사용하세요."
triggers:
  keywords: []
auto_trigger: false
---

# /auto-workflow → /auto (Deprecated)

⚠️ **이 스킬은 deprecated 되었습니다.**

## 리다이렉트

`/auto-workflow`는 `/auto`로 통합되었습니다.

```bash
# 대신 사용하세요
/auto "작업 내용"
```

## 마이그레이션 안내

| 기존 | 새로운 |
|------|--------|
| `/auto-workflow` | `/auto` |
| `/auto-workflow --gdocs` | `/auto --gdocs` |
| `/auto-workflow resume` | `/auto resume` |

## 상세 문서

통합된 스킬: `.claude/skills/auto/SKILL.md`
