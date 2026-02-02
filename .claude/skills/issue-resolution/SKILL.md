---
name: issue-resolution
description: "[DEPRECATED] /issue fix로 리다이렉트됨"
version: 2.0.0
deprecated: true
redirect: "issue fix"
deprecation_message: "/issue-resolution은 /issue fix로 통합되었습니다. /issue fix를 사용하세요."
triggers:
  keywords: []
auto_trigger: false
---

# /issue-resolution → /issue fix (Deprecated)

⚠️ **이 스킬은 deprecated 되었습니다.**

## 리다이렉트

`/issue-resolution`은 `/issue fix`로 통합되었습니다.

```bash
# 대신 사용하세요
/issue fix 123
/issue fix 123 --auto-fix
/issue fix 123 --create-pr
```

## 마이그레이션 안내

| 기존 | 새로운 |
|------|--------|
| `/issue-resolution 123` | `/issue fix 123` |
| `python scripts/analyze_issue.py 123` | `/issue fix 123 --analyze-only` |
| `python scripts/resolve_issue.py 123` | `/issue fix 123 --auto-fix` |
| `python scripts/handle_failed.py 123` | `/issue failed 123` |

## 워크플로우

`/issue fix`는 동일한 워크플로우를 제공합니다:

1. 분석: 이슈 타입 분류, 관련 파일 탐색
2. 계획: 수정 전략, 브랜치 생성
3. 구현: TDD 사이클
4. 검증: 테스트, 린트, PR 생성

## 인과관계 보존

```
/auto Tier 3 WORK
    └── /issue fix #N (열린 이슈 존재 시)

/issue fix → (confidence < 80%) → /debug
```

## 상세 문서

통합된 스킬: `.claude/skills/issue/SKILL.md`
