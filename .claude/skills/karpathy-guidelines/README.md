# Karpathy Guidelines

![GitHub stars](https://img.shields.io/github/stars/forrestchang/andrej-karpathy-skills)

## 소개

Andrej Karpathy의 관찰에서 도출된 개발 원칙을 Claude Code 스킬로 구현한 패키지.

원본 레포(`forrestchang/andrej-karpathy-skills`)의 4원칙을 기반으로, 이번 확장에서 2개 원칙을 추가했다:

- **원칙 5 (신규)**: Documents over Documentation — 단일 문서, 단일 진실. 메타 문서 금지.
- **원칙 6 (신규)**: Context Awareness — 아는 것과 모르는 것을 구분한다.

## 설치 방법

### 방법 1: 직접 복사 (Windows)

```bash
# Windows 명령 프롬프트
xcopy /E /I "karpathy-guidelines" "%USERPROFILE%\.claude\skills\karpathy-guidelines\"

# 또는 PowerShell
Copy-Item -Recurse "karpathy-guidelines" "$env:USERPROFILE\.claude\skills\karpathy-guidelines"
```

### 방법 2: 심볼릭 링크 (관리자 권한 필요)

```bash
# Windows (관리자 권한 명령 프롬프트)
mklink /D "%USERPROFILE%\.claude\skills\karpathy-guidelines" "C:\claude\.claude\skills\karpathy-guidelines"
```

### 방법 3: macOS / Linux

```bash
cp -r karpathy-guidelines ~/.claude/skills/
# 또는 심볼릭 링크
ln -s "$(pwd)/karpathy-guidelines" ~/.claude/skills/karpathy-guidelines
```

## 사용 방법

### 자동 트리거

코드 리뷰, 리팩토링 요청 시 자동으로 원칙이 적용된다.

### 수동 호출

```
"karpathy 원칙 적용해서 이 코드 리뷰해줘"
"개발 원칙 기준으로 이 함수를 개선해줘"
```

## 원칙 요약

| 번호 | 원칙 | 한 줄 요약 |
|------|------|-----------|
| 1 | Read before you write | 코드를 수정하기 전에 반드시 먼저 읽는다 |
| 2 | Fail loud | 오류를 숨기지 않는다 |
| 3 | Minimal footprint | 필요한 것만 변경한다 |
| 4 | Prefer reversibility | 되돌릴 수 있는 변경을 선호한다 |
| 5 | Documents over Documentation | 단일 문서, 단일 진실. 메타 문서 금지 |
| 6 | Context Awareness | 아는 것과 모르는 것을 구분한다 |

## 상세 예시

각 원칙의 Bad/Good 실전 예시: `EXAMPLES.md` 참조

원칙 정의 전체: `CLAUDE.md` 참조
