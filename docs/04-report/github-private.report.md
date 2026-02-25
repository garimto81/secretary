# GitHub 저장소 Private 전환 완료 보고서

**버전**: 1.0.0 | **완료일**: 2026-02-25 | **상태**: COMPLETED

---

## 요약

GitHub 공개 저장소를 프라이빗으로 일괄 전환하기 위한 자동화 도구를 구현했다.
토큰 scope 사전 검증 → dry-run 목록 조회 → 실제 전환(확인 필수) → 결과 검증까지 end-to-end 파이프라인을 완성했다.

**구현 범위**: FR-01 ~ FR-05 완료 (NFR-1, NFR-2 포함)
**커밋**: 1건 (`199609f`)
**테스트**: 9개 신규 (모두 통과, 회귀 테스트 44개 통과)
**Architect 검증**: APPROVE

---

## 구현 내용

### FR-01: 토큰 Scope 사전 확인

**파일**: `scripts/github_private_converter.py` (신규)

`--check-token` 플래그로 GitHub 토큰의 필요 scope를 확인한다.

**구현 로직**:
```python
def check_token(self) -> bool:
    # GitHub API: GET /user (사용자 정보)
    # 응답 headers의 X-OAuth-Scopes 분석
    # 필요 scope: "repo" 또는 "admin:repo_hook"
    # 있음: True 반환
    # 없음: 오류 메시지 + False 반환
```

**CLI 사용**:
```bash
python scripts/github_private_converter.py --check-token
# 출력:
# ✓ 토큰이 유효합니다.
# ✓ 필요 scope(repo)이 있습니다.
```

scope 없으면:
```bash
# 출력:
# ✗ 토큰 scope 부족: 'repo' 또는 'admin:repo_hook' 필요
# 현재 scope: public_repo
```

---

### FR-02: Public 저장소 목록 Dry-Run 조회

**파일**: `scripts/github_private_converter.py` (신규)

`--list` 플래그로 전환할 public 저장소 목록을 조회한다 (실제 변경 없음).

**구현 로직**:
```python
def list_public_repos(self) -> list[dict]:
    # GitHub API: GET /user/repos?type=owner&visibility=public
    # 페이지네이션: cursor 기반 (RFC 5988)
    # 각 저장소: {"name": str, "url": str, "is_fork": bool, "description": str}
    # 반환: 저장소 목록 (default 30개, --limit 옵션)
```

**CLI 사용**:
```bash
python scripts/github_private_converter.py --list
# 출력:
# [Dry-Run] 전환할 Public 저장소 3개:
# 1. my-repo1 (https://github.com/garimto81/my-repo1)
#    설명: 테스트 저장소
#    포크: 아니오
# 2. my-repo2
# ...
```

**NFR-1 (드라이런)**: `--list`는 항상 read-only. 저장소 변경 없음.

---

### FR-03: Private 저장소로 실제 전환

**파일**: `scripts/github_private_converter.py` (신규)

`--convert [--confirm]` 플래그로 public 저장소를 private으로 전환한다.
`--confirm` 없으면 dry-run만 수행한다.

**구현 로직**:
```python
def convert_to_private(self, confirm: bool = False) -> list[dict]:
    # Step 1: list_public_repos() 호출 (변경할 목록 확인)
    # Step 2: confirm=False면 dry-run 결과 반환
    # Step 3: confirm=True면:
    #   - check_token()로 scope 자동 사전 확인 (NFR-2)
    #   - scope 부족하면 오류 + 중단
    #   - GitHub API: PATCH /repos/{owner}/{repo}
    #     {"private": true}
    #   - 각 저장소별 결과 기록: {"name": str, "status": "success"|"error", "error": str|null}
    # Step 4: 결과 반환
```

**NFR-2 (자동 사전 확인)**: `--confirm` 시 check_token() 자동 호출

**CLI 사용**:

Dry-run (확인 전):
```bash
python scripts/github_private_converter.py --convert
# 출력:
# [Dry-Run] 다음 저장소를 Private으로 전환합니다:
# 1. my-repo1
# 2. my-repo2
# 3. my-repo3
#
# 실제 전환: python scripts/github_private_converter.py --convert --confirm
```

실제 전환 (확인 필수):
```bash
python scripts/github_private_converter.py --convert --confirm
# Step 1: 토큰 scope 확인...
# ✓ scope 확인됨
#
# Step 2: 저장소 전환 시작...
# [1/3] my-repo1 ... ✓ Private 전환 완료
# [2/3] my-repo2 ... ✓ Private 전환 완료
# [3/3] my-repo3 ... ✓ Private 전환 완료
#
# 완료: 3개 저장소 Private 전환됨
```

실패 예시:
```bash
# 출력:
# [2/3] my-repo2 ... ✗ 오류: 403 Forbidden (권한 없음)
#
# 부분 완료: 2개 성공, 1개 실패
```

---

### FR-04: 전환 결과 검증

**파일**: `scripts/github_private_converter.py` (신규)

`--verify` 플래그로 현재 public 저장소 상태를 확인한다 (private 전환 성공 여부).

**구현 로직**:
```python
def verify_conversion(self) -> dict:
    # GitHub API: GET /user/repos?type=owner&visibility=public
    # 결과가 비었으면: "모든 저장소가 Private입니다" → success
    # 결과가 있으면: "다음 저장소가 아직 Public입니다: ..." → partial/failure
```

**CLI 사용**:

성공:
```bash
python scripts/github_private_converter.py --verify
# ✓ 모든 저장소가 Private입니다.
```

미완료:
```bash
# ✗ 다음 저장소가 아직 Public입니다:
# - my-repo1 (https://github.com/garimto81/my-repo1)
# - my-repo2
```

---

### FR-05: Secretary 통합 확인

**파일**: 기존 `scripts/github_analyzer.py` 통합

`github_analyzer.py`가 GitHub API를 통해 저장소 메타데이터를 이미 수집 중.
private 저장소 전환 후 `github_analyzer.py --days 5` 재실행으로 변경사항 반영 여부 확인.

---

## 사용 방법

### 통합 워크플로우

```bash
# Step 1: 토큰 scope 확인 (필수)
python scripts/github_private_converter.py --check-token
# 출력: ✓ scope 확인됨 또는 ✗ scope 부족

# Step 2: 전환 대상 저장소 확인 (dry-run)
python scripts/github_private_converter.py --list
# 출력: [Dry-Run] 전환할 Public 저장소 N개 목록

# Step 3: 실제 전환 (--confirm 필수)
python scripts/github_private_converter.py --convert --confirm
# 출력: [1/N] repo1 ... ✓ Private 전환 완료

# Step 4: 결과 검증
python scripts/github_private_converter.py --verify
# 출력: ✓ 모든 저장소가 Private입니다.

# Step 5: Secretary 연동 확인
python scripts/github_analyzer.py --days 5
# 출력: GitHub 분석 결과 (private 저장소 제외/포함 여부 확인)
```

---

## 테스트 결과

**테스트 파일**: `tests/test_github_private_converter.py` (신규, 9개 케이스)

| 테스트 케이스 | 결과 |
|-------------|------|
| `test_check_token_valid_scope` | PASS |
| `test_check_token_missing_scope` | PASS |
| `test_check_token_network_error` | PASS |
| `test_list_public_repos` | PASS |
| `test_list_public_repos_empty` | PASS |
| `test_convert_to_private_dry_run` | PASS |
| `test_convert_to_private_confirm` | PASS |
| `test_convert_to_private_partial_failure` | PASS |
| `test_verify_conversion_all_private` | PASS |

```
신규 테스트: 9 passed
회귀 테스트: 44 passed (gateway, intelligence, knowledge, reporter 전체)
```

모든 테스트는 GitHub API mocking 기반으로 실행 (network 호출 없음).

**린트**:
```
ruff check scripts/github_private_converter.py --fix
# All checks passed
```

---

## 생성된 파일

| 파일 | 설명 |
|------|------|
| `scripts/github_private_converter.py` | GitHub 저장소 private 전환 도구 (메인 구현) |
| `tests/test_github_private_converter.py` | 단위 테스트 9개 |
| `docs/00-prd/github-private.prd.md` | 요구사항 문서 |
| `docs/01-plan/github-private.plan.md` | 구현 계획 문서 |

---

## 구현 상태

| 기능 | 상태 | 비고 |
|------|------|------|
| FR-01: `--check-token` | 완료 | GitHub API /user scope 검증 |
| FR-02: `--list` | 완료 | Dry-run public 저장소 목록 조회 |
| FR-03: `--convert [--confirm]` | 완료 | 실제 전환 (확인 필수) |
| FR-04: `--verify` | 완료 | 전환 결과 검증 |
| FR-05: Secretary 통합 | 완료 | github_analyzer.py 기존 통합 활용 |
| NFR-1: Dry-run 보호 | 완료 | `--list`는 read-only |
| NFR-2: 자동 scope 확인 | 완료 | `--confirm` 시 check_token() 자동 호출 |

---

## 해결된 문제

**기존 상황**: GitHub 공개 저장소를 프라이빗으로 전환할 자동화 도구 부재

| 문제 | 해결책 |
|------|--------|
| 수동으로 각 저장소 설정 변경 필요 | CLI 도구로 일괄 자동화 |
| 토큰 scope 부족 시 실패 | `--check-token`으로 사전 확인 |
| 실수로 저장소 변경 가능성 | `--list` dry-run + `--confirm` 필수 |
| 전환 성공 여부 불명확 | `--verify`로 검증 |
| Secretary와 데이터 불일치 | github_analyzer.py 재실행으로 동기화 |

---

## 아키텍처 영향

신규 module 추가:

```
scripts/
├── github_analyzer.py          (기존 — 저장소 메타 수집)
└── github_private_converter.py (신규 — Private 전환 도구)

tests/
└── test_github_private_converter.py (신규 — 단위 테스트 9개)

docs/
├── 00-prd/
│   └── github-private.prd.md      (신규 — 요구사항)
└── 01-plan/
    └── github-private.plan.md     (신규 — 계획)
```

Secretary 기존 아키텍처와 독립적으로 동작.
필요 시 `github_analyzer.py --days N` 재실행으로 메타데이터 동기화 가능.

---

## 향후 개선 사항

| 항목 | 내용 |
|------|------|
| 페이지네이션 테스트 확충 | `test_list_public_repos_pagination` 구현 (100개+ 저장소 처리) |
| 스케줄링 | 월 1회 자동 실행 cron job 또는 GitHub Actions 추가 |
| 대량 작업 시간 절감 | API 병렬 호출로 속도 개선 (현재 순차 처리) |
| 이력 저장 | 전환 일시, 변경 이전/이후 상태 JSON 기록 |
| Rollback 지원 | Private → Public 일괄 복구 옵션 추가 |

---

## Changelog

| 날짜 | 버전 | 커밋 | 내용 |
|------|------|------|------|
| 2026-02-25 | 1.0.0 | `199609f` | feat(github): GitHub 저장소 private 전환 스크립트 (FR-01~05, NFR-1~2) |
