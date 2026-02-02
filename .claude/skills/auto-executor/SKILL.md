---
name: auto-executor
description: "[DEPRECATED] /auto로 리다이렉트됨"
version: 2.0.0
deprecated: true
redirect: auto
deprecation_message: "/auto-executor는 /auto로 통합되었습니다. /auto를 사용하세요."
triggers:
  keywords: []
auto_trigger: false
---

# /auto-executor → /auto (Deprecated)

⚠️ **이 스킬은 deprecated 되었습니다.**

## 리다이렉트

`/auto-executor`는 `/auto`로 통합되었습니다.

```bash
# 대신 사용하세요
/auto "작업 내용"
```

## 마이그레이션 안내

`/auto`는 자동으로 Task tool을 사용하여 서브에이전트에 작업을 위임합니다.
별도의 executor 스킬이 필요하지 않습니다.

## 상세 문서

통합된 스킬: `.claude/skills/auto/SKILL.md`
