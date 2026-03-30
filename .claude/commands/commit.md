---
name: commit
description: Create git commits using conventional commit format with emojis
---

# /commit - Conventional Commit & Push

Create well-formatted git commits following Conventional Commits specification and push to remote.

## Usage

```
/commit              # Commit and push to current branch
/commit --no-push    # Commit only, skip push
/commit --rewrite N  # 최근 N개 커밋 메시지를 Conventional Commit으로 재작성
```

## Workflow

Claude Code will:
1. Check for staged changes (`git diff --cached`)
2. If no staged changes, show `git status` and ask what to stage
3. Analyze changes and determine commit type (feat, fix, docs, etc.)
4. Generate descriptive commit message with emoji
5. Execute `git commit`
6. **Push to remote** (`git push`)
7. Show final status

## Commit Format

```
<type>(<scope>): <subject> <emoji>

<body>

<footer>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

## Commit Types

| Type | Description | Emoji |
|------|-------------|-------|
| **feat** | New feature | ✨ |
| **fix** | Bug fix | 🐛 |
| **docs** | Documentation | 📝 |
| **style** | Formatting | 💄 |
| **refactor** | Code restructuring | ♻️ |
| **perf** | Performance | ⚡ |
| **test** | Tests | ✅ |
| **chore** | Maintenance | 🔧 |
| **ci** | CI/CD | 👷 |
| **build** | Build system | 📦 |

## Push Behavior

- **Default**: Push to current tracking branch
- **New branch**: Use `git push -u origin <branch>`
- **Diverged**: Warn user and ask before force push
- **--no-push**: Skip push step entirely

## Example

**Input**: `/commit`

**Output**:
```bash
# 1. Commit
git commit -m "feat(auth): Add OAuth2 authentication ✨

- Implement OAuth2 provider
- Add token validation
- Create auth middleware

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# 2. Push
git push origin main

# 3. Result
✅ Committed and pushed: feat(auth): Add OAuth2 authentication ✨
   Remote: https://github.com/user/repo/commit/abc1234
```

## Safety

- Never force push to main/master without explicit user confirmation
- Check for upstream changes before push
- Show diff summary before commit

## --rewrite N 모드 (커밋 메시지 재작성)

최근 N개 커밋의 메시지를 Conventional Commit 형식으로 AI 재작성합니다.

### 제약 사항

- Claude Code 환경에서 `git rebase -i` (interactive) 사용 불가
- `git commit --amend` 체인 방식으로 처리
- 원격 브랜치에 이미 push된 커밋은 --force-push 필요 → **사용자 확인 후 실행**

### 실행 워크플로우

```bash
# 1. 최근 N개 커밋 목록 확인
git log --oneline -N

# 2. 각 커밋별 diff 추출 및 AI 분석
git diff HEAD~i..HEAD~(i-1)

# 3. Conventional Commit 메시지 재작성 (AI 생성)
# type(scope): subject emoji
# - body
# 🤖 Generated with Claude Code

# 4. git commit --amend 체인 (non-interactive)
# ⚠️ 원격 브랜치 존재 시 force-push 필요 → 사용자 확인
```

### 예시

```bash
/commit --rewrite 3

# 처리 전:
# abc1234 fix stuff
# def5678 update code
# ghi9012 wip

# 처리 후:
# abc1234 fix(auth): OAuth 토큰 갱신 로직 수정 🐛
# def5678 refactor(api): 클라이언트 코드 구조 개선 ♻️
# ghi9012 feat(ui): 로그인 페이지 초기 구현 ✨
```

### 안전 장치

- main/master 브랜치에서 실행 시 경고 + 사용자 확인 필수
- 원격 브랜치 존재 시 force-push 경고 + 사용자 확인 필수
- 재작성 전 원본 메시지 백업 출력
- 품질 점수 60 미만 커밋만 대상 (이미 좋은 메시지는 스킵)

### 커밋 메시지 품질 점수 (post-commit hook)

커밋 후 자동으로 품질을 측정합니다:

| 점수 | 상태 | 조치 |
|------|------|------|
| 80+ | 우수 | - |
| 60-79 | 보통 | 경고만 |
| 60 미만 | 낮음 | `/commit --rewrite 1` 제안 |

점수 기준:
- Conventional Commit 형식 준수: +40점
- 이모지 포함: +10점
- 영어/한글 명확한 subject: +20점
- Body 설명 포함: +20점
- 50자 이내 subject: +10점 (50-72자: +5점)

## Related

- `/create pr` - Create pull request after commit
- `/session changelog` - Update changelog before commit
