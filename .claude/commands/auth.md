---
name: auth
description: AI 인증 관리 (openai, google, status, logout)
---

# /auth - AI 인증

$ARGUMENTS를 파싱하여 **Bash tool로 즉시 실행**.

| 입력 | 동작 |
|------|------|
| `/auth` | 인증 상태 표시 |
| `/auth openai` | OpenAI 로그인 |
| `/auth google` | Google 로그인 |
| `/auth logout openai` | 토큰 삭제 |
| `/auth logout google` | 토큰 삭제 |

## 실행

```bash
uv run python -m ai_auth $ARGUMENTS
```

인수가 없으면 `uv run python -m ai_auth` (status 표시).
