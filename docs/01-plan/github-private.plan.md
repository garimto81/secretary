# GitHub 저장소 Private 전환 구현 계획

## 배경

현재 garimto81 GitHub 계정의 모든 public 저장소가 보안상 위험에 노출되어 있으며, private으로 전환하여 보안을 강화하고, secretary 프로젝트의 GitHub 연동이 정상 동작하는지 검증해야 합니다.

## 구현 범위

### 포함 항목
- GitHub API를 통한 public 저장소 목록 조회
- 토큰 scope 확인 및 검증
- 일괄 private 전환 기능 (확인 필수, `--confirm` 플래그)
- 전환 결과 검증
- secretary `github_analyzer.py` 정상 동작 확인

### 제외 항목
- Organization 저장소 대상 처리
- GitHub Actions, Workflows 설정 변경
- Git 로컬 저장소 수정

---

## 영향 파일

### 신규 생성 파일
- `C:\claude\secretary\scripts\github_private_converter.py` (약 250줄)

### 기존 확인 파일
- `C:\claude\secretary\config\projects.json` (확인만)
- `C:\claude\secretary\scripts\github_analyzer.py` (호출 검증만)

### 설정 파일
- `C:\claude\json\github_token.txt` (Bearer 토큰 읽음)

---

## 위험 요소

| 위험 요소 | 설명 | 완화 전략 |
|----------|------|----------|
| **되돌리기 불가** | private 전환 후 public 복구는 가능하지만 fork된 내용은 손실 가능 | `--list` 먼저 확인, `--confirm` 플래그 필수 |
| **토큰 권한 부족** | 현재 토큰이 `repo` scope 없으면 전환 불가 | `--check-token`으로 먼저 검증, 부족하면 중단 |
| **API Rate Limit** | 대량 저장소 전환 시 GitHub API rate limit (5,000/시간) 초과 가능 | 일반 계정 범위 내에서는 문제 없음, 필요시 재시도 로직 |
| **네트워크 오류** | API 호출 중 연결 끊김 시 일부 저장소만 전환될 수 있음 | 개별 저장소 실패 시 계속 진행, 최종 통계 및 재시도 가능하도록 설계 |
| **secretary 프로젝트 차단** | private 전환 후 `github_analyzer.py`가 접근 불가능할 수 있음 | 전환 후 `github_analyzer.py --days 5` 실행하여 즉시 검증 |

---

## 태스크 목록

### Task 1: `github_private_converter.py` 구현 — 토큰 검증 및 목록 조회

**설명**: GitHub API 기본 설정, 토큰 로드, scope 확인 기능 구현

**수행 방법**:
- 파일: `C:\claude\secretary\scripts\github_private_converter.py`
- 의존: httpx (이미 requirements.txt에 포함)

**구현 상세**:
```python
# 1. 모듈 임포트
import httpx, argparse, sys, json
from pathlib import Path

# 2. 상수 정의
GITHUB_API_BASE = "https://api.github.com"
TOKEN_PATH = Path("C:/claude/json/github_token.txt")

# 3. 헬퍼 함수 (전체 약 40줄)
def load_token() -> str:
    """토큰 파일에서 Bearer 토큰 읽기"""
    if not TOKEN_PATH.exists():
        print(f"❌ 토큰 파일 없음: {TOKEN_PATH}")
        sys.exit(1)
    token = TOKEN_PATH.read_text().strip()
    if not token:
        print("❌ 토큰이 비어있음")
        sys.exit(1)
    return token

def create_headers(token: str) -> dict:
    """GitHub API 헤더 생성"""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

# 4. Token scope 확인 함수 (약 20줄)
def check_token(token: str) -> dict:
    """
    GET /user 호출하여 X-OAuth-Scopes 헤더 파싱
    Returns: {"scopes": ["repo", "read:user", ...], "has_repo_scope": bool}
    """
    headers = create_headers(token)
    with httpx.Client() as client:
        response = client.get(f"{GITHUB_API_BASE}/user", headers=headers)
        if response.status_code != 200:
            print(f"❌ Token 검증 실패: {response.status_code}")
            print(response.text)
            sys.exit(1)

        scopes_header = response.headers.get("X-OAuth-Scopes", "")
        scopes = [s.strip() for s in scopes_header.split(",") if s.strip()]
        user_login = response.json().get("login", "unknown")

        return {
            "login": user_login,
            "scopes": scopes,
            "has_repo_scope": "repo" in scopes
        }

# 5. Public 저장소 조회 함수 (약 25줄)
def list_public_repos(token: str) -> list:
    """
    GET /user/repos?visibility=public&per_page=100
    여러 페이지 처리 (100개씩)
    Returns: [{"name": "claude", "owner": "garimto81", ...}, ...]
    """
    headers = create_headers(token)
    repos = []
    page = 1

    with httpx.Client() as client:
        while True:
            response = client.get(
                f"{GITHUB_API_BASE}/user/repos",
                headers=headers,
                params={"visibility": "public", "per_page": 100, "page": page}
            )
            if response.status_code != 200:
                print(f"❌ 저장소 목록 조회 실패: {response.status_code}")
                sys.exit(1)

            data = response.json()
            if not data:
                break

            for repo in data:
                repos.append({
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "private": repo["private"],
                    "url": repo["html_url"]
                })

            page += 1

    return repos
```

**Acceptance Criteria**:
- [x] 토큰 파일 존재 확인 후 읽기
- [x] GET /user 호출하여 scope 파싱 (X-OAuth-Scopes 헤더)
- [x] 페이지 처리로 모든 public 저장소 목록 반환
- [x] 오류 메시지 출력 및 sys.exit() 처리
- [x] 함수 단위 테스트 가능하게 설계

---

### Task 2: CLI 인터페이스 구현 — `--check-token`, `--list` 옵션

**설명**: argparse를 통한 커맨드라인 인터페이스 및 `check_token`, `list` 서브커맨드 구현

**수행 방법**:
- 함수: `main(args)` (약 60줄)
- argparse 구조:
  ```
  --check-token: Token scope 확인
  --list: Public 저장소 목록 조회 (dry-run)
  --convert [--confirm]: Private 전환 (--confirm 없으면 dry-run)
  --verify: 전환 검증
  ```

**구현 상세**:
```python
def main():
    parser = argparse.ArgumentParser(
        description="GitHub 저장소를 private으로 전환"
    )
    parser.add_argument("--check-token", action="store_true",
                        help="토큰 scope 확인")
    parser.add_argument("--list", action="store_true",
                        help="Public 저장소 목록 조회 (dry-run)")
    parser.add_argument("--convert", action="store_true",
                        help="Private 전환 실행")
    parser.add_argument("--confirm", action="store_true",
                        help="--convert 사용 시 실제 전환 실행 (없으면 dry-run)")
    parser.add_argument("--verify", action="store_true",
                        help="전환 결과 검증")

    args = parser.parse_args()

    # 최소 하나의 옵션 필요
    if not any([args.check_token, args.list, args.convert, args.verify]):
        parser.print_help()
        sys.exit(1)

    token = load_token()

    if args.check_token:
        result = check_token(token)
        print(f"[Token Scope Check]")
        print(f"Login: {result['login']}")
        print(f"Scopes: {', '.join(result['scopes'])}")
        print(f"repo scope: {'✓' if result['has_repo_scope'] else '✗'}")

        if not result['has_repo_scope']:
            print("\n❌ repo scope 없음. 토큰 재발급 필요")
            sys.exit(1)

    if args.list:
        repos = list_public_repos(token)
        print(f"\n[Public Repositories (dry-run)]")
        for i, repo in enumerate(repos, 1):
            print(f"{i}. {repo['full_name']} ({repo['url']})")
        print(f"\nTotal: {len(repos)} repository/repositories to convert")

    if args.convert:
        if not args.confirm:
            repos = list_public_repos(token)
            print(f"\n⚠️  WARNING: {len(repos)} 저장소를 private으로 전환합니다")
            print(f"실제 전환하려면 --confirm 플래그 추가:\n"
                  f"python scripts/github_private_converter.py --convert --confirm")
            sys.exit(0)

        convert_to_private(token)

    if args.verify:
        verify_conversion(token)

if __name__ == "__main__":
    main()
```

**Acceptance Criteria**:
- [x] argparse로 모든 옵션 정의
- [x] `--check-token` 실행 시 scope 출력
- [x] `--list` 실행 시 저장소 번호 및 URL 출력
- [x] `--convert` without `--confirm` → dry-run (경고 메시지)
- [x] `--convert --confirm` → 실제 전환 실행
- [x] 옵션 없이 실행 시 help 출력

---

### Task 3: Private 전환 함수 구현 — `--convert --confirm`

**설명**: PATCH /repos/{owner}/{repo} API 호출로 각 저장소를 private으로 전환

**수행 방법**:
- 함수: `convert_to_private(token: str)` (약 50줄)
- 각 저장소 PATCH 호출, 실패해도 계속 진행

**구현 상세**:
```python
def convert_to_private(token: str):
    """
    모든 public 저장소를 private으로 전환
    실패한 저장소도 기록하여 최종 통계 출력
    """
    print("⚠️  WARNING: Private 전환을 시작합니다. 이는 되돌리기 어려운 작업입니다.")
    confirm = input("계속하시겠습니까? (yes/no): ")
    if confirm.lower() != "yes":
        print("작업 취소됨")
        sys.exit(0)

    repos = list_public_repos(token)
    headers = create_headers(token)

    success_count = 0
    failed_repos = []

    print(f"\n[Converting {len(repos)} repositories to private]")

    with httpx.Client() as client:
        for i, repo in enumerate(repos, 1):
            print(f"[{i}/{len(repos)}] {repo['full_name']}...", end=" ", flush=True)

            try:
                response = client.patch(
                    f"{GITHUB_API_BASE}/repos/{repo['full_name']}",
                    headers=headers,
                    json={"private": True},
                    timeout=10.0
                )

                if response.status_code == 200:
                    print("✓")
                    success_count += 1
                else:
                    print(f"✗ ({response.status_code})")
                    failed_repos.append((repo['full_name'], response.status_code, response.text))

            except httpx.RequestError as e:
                print(f"✗ (error: {e})")
                failed_repos.append((repo['full_name'], "error", str(e)))

    print(f"\n[Conversion Summary]")
    print(f"Success: {success_count}/{len(repos)}")
    if failed_repos:
        print(f"Failed: {len(failed_repos)}")
        for name, code, msg in failed_repos:
            print(f"  - {name}: {code}")
```

**Acceptance Criteria**:
- [x] PATCH /repos/{owner}/{repo} {"private": true} 호출
- [x] 각 저장소 성공/실패 실시간 출력
- [x] 개별 실패 시에도 다음 저장소 계속 처리
- [x] 최종 통계 출력 (성공/실패 카운트)
- [x] 사용자 재확인 필수 (yes/no)

---

### Task 4: 검증 함수 구현 — `--verify`

**설명**: 전환 후 모든 저장소가 private 상태인지 확인

**수행 방법**:
- 함수: `verify_conversion(token: str)` (약 30줄)
- GET /user/repos?visibility=public 호출, 결과 0개 확인

**구현 상세**:
```python
def verify_conversion(token: str):
    """
    GET /user/repos?visibility=public 호출
    공개 저장소가 남아있으면 false, 없으면 true
    """
    print("[Verifying conversion...]")

    repos = list_public_repos(token)

    if len(repos) == 0:
        print("✓ 모든 저장소가 private으로 전환되었습니다")
        return True
    else:
        print(f"✗ 공개 저장소 {len(repos)}개가 남아있습니다:")
        for repo in repos:
            print(f"  - {repo['full_name']}")
        return False
```

**Acceptance Criteria**:
- [x] GET /user/repos?visibility=public 호출
- [x] 결과가 0개면 성공 메시지 출력
- [x] 1개 이상이면 남은 저장소 목록 출력

---

### Task 5: secretary 연동 검증

**설명**: 전환 후 `github_analyzer.py`가 정상 동작하는지 확인

**수행 방법**:
- 명령: `python scripts/github_analyzer.py --days 5`
- 예상 결과: 최근 5일 커밋 데이터 조회 성공

**Acceptance Criteria**:
- [x] `github_analyzer.py` 오류 없이 실행
- [x] private 저장소 접근 성공
- [x] 커밋 데이터 조회 완료

---

### Task 6: 테스트 작성 (선택)

**설명**: `github_private_converter.py` 주요 함수 단위 테스트

**수행 방법**:
- 파일: `C:\claude\secretary\tests\test_github_private_converter.py` (약 80줄)
- Mock httpx 클라이언트 사용

**구현 상세**:
```python
# pytest + unittest.mock 사용
def test_check_token_with_repo_scope():
    """토큰 scope 확인 — repo scope 있을 때"""
    # Mock httpx response
    # X-OAuth-Scopes: repo, read:user
    # Assertion: has_repo_scope = True

def test_check_token_without_repo_scope():
    """토큰 scope 확인 — repo scope 없을 때"""
    # Assertion: has_repo_scope = False

def test_list_public_repos():
    """Public 저장소 목록 조회"""
    # Mock /user/repos?visibility=public 응답
    # Assertion: 정확한 저장소 수 반환

def test_list_public_repos_pagination():
    """Public 저장소 목록 조회 — 페이지 처리"""
    # Mock 첫 번째 페이지 + 두 번째 페이지
    # Assertion: 모든 저장소 수집 (200개)
```

**Acceptance Criteria**:
- [x] Mock 기반 테스트 (외부 API 호출 없음)
- [x] 주요 함수 모두 포함
- [x] `pytest tests/test_github_private_converter.py -v` 실행 성공

---

## 커밋 전략

### Commit 1: 스크립트 구현
```
feat(github): GitHub 저장소 private 전환 스크립트

- github_private_converter.py 신규 작성
- --check-token: token scope 확인
- --list: public 저장소 목록 조회 (dry-run)
- --convert [--confirm]: private 전환 (확인 필수)
- --verify: 전환 결과 검증
```

### Commit 2: 테스트 추가
```
test(github): github_private_converter.py 단위 테스트

- test_check_token, test_list_public_repos, test_pagination 포함
```

### Commit 3: secretary 연동 검증 완료
```
docs(github): private 전환 검증 완료

- github_analyzer.py --days 5 정상 동작 확인
- config/projects.json github_repos 접근 검증
```

---

## 실행 순서 및 명령어

### Phase 1: 토큰 검증
```bash
python scripts/github_private_converter.py --check-token
# 출력: Login, Scopes, repo scope 확인 (✓ 또는 ✗)
```

### Phase 2: Public 저장소 목록 조회
```bash
python scripts/github_private_converter.py --list
# 출력: 1. garimto81/claude, 2. garimto81/..., Total: N
```

### Phase 3: Private 전환 (dry-run)
```bash
python scripts/github_private_converter.py --convert
# 출력: WARNING, --confirm 플래그 추가 안내
```

### Phase 4: Private 전환 실행
```bash
python scripts/github_private_converter.py --convert --confirm
# 출력: [1/N] garimto81/claude... ✓, [2/N] ... ✓, Success: N/N
```

### Phase 5: 검증
```bash
python scripts/github_private_converter.py --verify
# 출력: ✓ 모든 저장소가 private으로 전환되었습니다

python scripts/github_analyzer.py --days 5
# 출력: 최근 5일 커밋 데이터 정상 조회
```

---

## 테스트 방법

### 단위 테스트
```bash
pytest tests/test_github_private_converter.py -v
```

### 통합 테스트 (실제 GitHub API)
```bash
# 1. 토큰 검증
python scripts/github_private_converter.py --check-token

# 2. 목록 조회
python scripts/github_private_converter.py --list

# 3. dry-run 검증
python scripts/github_private_converter.py --convert
# → --confirm 플래그 없으면 실제 전환되지 않음

# 4. 실제 전환 (시뮬레이션만, 실제 환경에서 확인 필요)
python scripts/github_private_converter.py --convert --confirm

# 5. 결과 검증
python scripts/github_private_converter.py --verify

# 6. secretary 연동 확인
python scripts/github_analyzer.py --days 5
```

---

## 사용자 확인 안내문

⚠️ **WARNING: GitHub 저장소 Private 전환**

### 주의 사항
1. **되돌리기 제한**: Private 전환은 가능하지만 fork된 내용은 복구 불가능합니다.
2. **토큰 권한 필수**: 토큰의 `repo` scope가 필요합니다. (`--check-token`으로 먼저 확인)
3. **Rate Limit**: GitHub API 요청 제한은 5,000회/시간입니다. 저장소가 많으면 느릴 수 있습니다.

### 실행 전 확인 사항
```bash
# 1단계: 토큰 scope 확인 (필수)
python scripts/github_private_converter.py --check-token
# → repo scope ✓ 확인

# 2단계: 전환 대상 저장소 확인 (필수)
python scripts/github_private_converter.py --list
# → 목록을 출력하고 실제로 전환할지 재확인

# 3단계: 실제 전환 (--confirm 필수)
python scripts/github_private_converter.py --convert --confirm
# → 다시 한 번 확인 후 "yes" 입력
```

### 전환 후 검증
```bash
# 1단계: 저장소 상태 검증
python scripts/github_private_converter.py --verify
# → ✓ 모든 저장소가 private으로 전환되었습니다

# 2단계: secretary 연동 검증
python scripts/github_analyzer.py --days 5
# → 최근 5일 커밋 데이터 조회 성공
```

### 문제 발생 시
- **토큰 scope 부족**: GitHub 설정에서 Personal Access Token 재발급 (`repo` scope 포함)
- **API Rate Limit 초과**: 1시간 대기 후 재시도
- **secretary 연동 실패**: `config/projects.json` 설정 재확인, 토큰 권한 재검증

---

## 의존성

| 의존성 | 버전 | 용도 |
|--------|------|------|
| httpx | 0.24+ | GitHub API HTTP 요청 (이미 requirements.txt) |
| Python | 3.11+ | 프로젝트 표준 |

---

## 파일 크기 예상

| 파일 | 줄 수 | 설명 |
|------|------|------|
| `github_private_converter.py` | ~250 | 전체 스크립트 |
| `test_github_private_converter.py` | ~80 | 단위 테스트 |

