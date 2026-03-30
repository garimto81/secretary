# Karpathy Guidelines — 실전 예시

각 원칙의 Bad/Good 대비 예시.

---

## 원칙 1: Read before you write

### Bad

```
사용자: "auth.py의 login 함수에 rate limiting 추가해줘"

Claude: (파일을 읽지 않고)
def login(username, password):
    if rate_limit_exceeded(username):
        raise RateLimitError()
    ...
→ 문제: 실제 login 함수 시그니처가 다를 수 있고,
        기존 코드와 충돌하는 로직을 삽입할 가능성이 높음
```

### Good

```
사용자: "auth.py의 login 함수에 rate limiting 추가해줘"

Claude: Read("C:\claude\src\auth.py")
"auth.py:34에서 login(email, password, session) 시그니처를 확인했습니다.
기존 코드에 rate_limiter 모듈이 이미 import되어 있으므로
다음과 같이 추가합니다..."
→ 올바른 시그니처와 기존 패턴을 기반으로 수정
```

---

## 원칙 2: Fail loud

### Bad

```python
# Bad: 오류를 숨기는 코드
def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}  # 조용히 빈 dict 반환 — 오류 숨김
```

### Good

```python
# Good: 오류를 명시적으로 노출
def load_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"설정 파일 파싱 실패 ({path}): {e}")
```

---

## 원칙 3: Minimal footprint

### Bad

```
사용자: "이 함수의 버그를 고쳐줘 (특정 버그 설명)"

Claude: 버그 수정 + 추가로:
- 변수명 전체 리팩토링
- 불필요하다고 판단한 주석 삭제
- 새 helper 함수 3개 추가
- 파일 상단 import 정리
→ 문제: 요청 범위 외 변경으로 예상치 못한 부작용 발생 가능
```

### Good

```
사용자: "이 함수의 버그를 고쳐줘 (특정 버그 설명)"

Claude: 해당 버그 원인 코드 1줄만 수정
"요청하신 버그만 수정했습니다.
주변 코드 개선이 필요해 보이는 부분이 있지만,
별도 요청이 있을 때 진행하겠습니다."
```

---

## 원칙 4: Prefer reversibility

### Bad

```
사용자: "이 디렉토리 정리해줘"

Claude: rm -rf old_files/
→ 문제: 삭제된 파일은 복구 불가.
        중요한 파일이 포함되어 있을 수 있음
```

### Good

```
사용자: "이 디렉토리 정리해줘"

Claude: "삭제 전에 확인이 필요합니다.
다음 파일/디렉토리를 삭제하려고 합니다:
  - old_files/temp_2025/ (최종 수정: 30일 전)
  - old_files/backup_v1/ (최종 수정: 60일 전)
진행할까요? (삭제 전 git에 커밋하거나 백업을 권장합니다)"
```

---

## 원칙 5: Documents over Documentation

### Bad

```
사용자: "이 README가 너무 복잡해서 이해하기 어려워"

Claude: README_GUIDE.md 신규 생성
  # README를 읽는 방법
  이 README는 3개 섹션으로 구성되어 있습니다...
→ 문제: README.md 자체를 개선하면 되는데,
        README를 설명하는 또 다른 문서를 만들어 혼란 가중
```

### Good

```
사용자: "이 README가 너무 복잡해서 이해하기 어려워"

Claude: README.md 상단에 "## TL;DR (5분 설치)" 섹션 추가
  ## TL;DR (5분 설치)
  1. npm install
  2. cp .env.example .env
  3. npm start
  나머지 세부 사항은 아래 섹션에서 확인.
→ 원본 문서를 직접 개선하여 단일 문서 원칙 유지
```

### Bad (임시 문서)

```
Claude: 작업 완료 후 IMPLEMENTATION_NOTES.md를 남겨둠
  # 구현 메모
  - 오늘 구현한 것들...
  - 나중에 정리할 TODO들...
→ 문제: "나중에 정리"는 없다. 이런 문서는 영원히 남아 혼란 야기
```

### Good (임시 문서)

```
Claude: 작업 완료 시 임시 메모는 즉시 삭제하거나
        관련 문서(CHANGELOG, TODO, README)에 병합 후 삭제
```

---

## 원칙 6: Context Awareness

### Bad

```
사용자: "UserService의 createUser 메서드를 수정해줘"

Claude: (파일을 읽지 않고)
"createUser 메서드는 보통 다음과 같이 구현됩니다:
async createUser(data: CreateUserDto) {
  return this.userRepository.save(data);
}"
→ 문제: 실제 메서드 시그니처, 기존 로직, 의존성을
        확인하지 않은 추정 코드 제시
```

### Good

```
사용자: "UserService의 createUser 메서드를 수정해줘"

Claude: "먼저 UserService를 읽겠습니다."
Read("C:\claude\src\services\user.service.ts")
"user.service.ts:45에서 확인했습니다.
현재 createUser는 email, password, role 3개 파라미터를 받고
hashService.hash()를 호출하고 있습니다.
이 구조를 기반으로 수정하겠습니다..."
```

### Bad (불확실한 정보를 단언)

```
Claude: "이 API는 rate limit이 분당 100건입니다."
→ 문제: 실제로 확인하지 않은 정보를 사실처럼 제시
```

### Good (지식 경계 인정)

```
Claude: "API 문서를 확인하지 않았으므로 rate limit은 직접 확인이 필요합니다.
일반적으로 분당 60-100건이 일반적이지만,
이 서비스의 실제 제한은 공식 문서에서 확인하세요."
```
