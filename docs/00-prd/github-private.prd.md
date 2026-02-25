# GitHub 저장소 Private 전환 PRD

## 개요

- **목적**: garimto81 소유의 모든 GitHub 저장소를 private으로 전환하여 보안을 강화하고, secretary 프로젝트의 GitHub 연동이 정상 동작하도록 검증
- **배경**: 현재 public 저장소로 공개된 코드가 보안상 위험 요소가 될 수 있으며, private 전환 후 secretary의 `github_analyzer.py`가 정상적으로 private 저장소에 접근 가능한지 확인이 필요함
- **범위**: garimto81 계정 소유의 모든 public 저장소 대상. secretary 프로젝트의 GitHub 연동 검증 포함

---

## 요구사항

### 기능 요구사항

**FR-1: Public 저장소 목록 조회 및 Private 전환 스크립트**
- GitHub API `/user/repos?visibility=public` 를 사용하여 현재 public 저장소 목록 조회
- 각 저장소에 대해 `PATCH /repos/{owner}/{repo}` API로 `private: true` 설정
- 실행 전 조회 결과를 출력하여 사용자가 확인 후 전환 진행
- 전환 성공/실패 결과를 저장소별로 출력

**FR-2: GitHub 토큰 Scope 확인**
- 현재 토큰(`C:\claude\json\github_token.txt`)의 scope 확인
- Private 전환에 필요한 scope: `repo` (전체 저장소 접근)
- 토큰 scope 확인 방법: `GET /user` 응답 헤더의 `X-OAuth-Scopes` 필드 검사
- scope 부족 시 사용자에게 토큰 재발급 안내

**FR-3: secretary github_analyzer.py Private 저장소 접근 검증**
- 전환 완료 후 `scripts/github_analyzer.py`가 private 저장소에 정상 접근하는지 검증
- 기존 `/user/repos` API 호출이 private 저장소도 반환하는지 확인
- `--days 5` 옵션으로 최근 커밋 데이터 조회 검증

**FR-4: config/projects.json github_repos 설정 검토**
- `config/projects.json`의 `github_repos: ["garimto81/claude"]` 설정 확인
- Private 전환 후 해당 저장소 접근 가능 여부 검증
- 필요 시 추가 저장소 등록 또는 설정 수정

**FR-5: 전환 결과 검증 스크립트**
- 전환 후 모든 저장소가 private 상태인지 확인
- `GET /user/repos?visibility=public` 결과가 빈 목록인지 검증
- 전환 성공 저장소 수 / 전체 저장소 수 통계 출력

---

### 비기능 요구사항

- **NFR-1: 실행 전 확인 필수**: private 전환은 되돌리기 어려운 작업이므로, 실행 전 반드시 사용자에게 목록을 출력하고 `--confirm` 플래그 없이는 dry-run만 수행
- **NFR-2: 토큰 Scope 우선 확인**: 스크립트 실행 시 첫 단계로 토큰 scope를 확인하고, `repo` scope 없으면 즉시 중단 및 안내
- **NFR-3: 에러 처리**: 개별 저장소 전환 실패 시 다른 저장소 처리를 중단하지 않고 계속 진행, 실패 목록 별도 출력

---

## 제약사항

| 항목 | 내용 |
|------|------|
| **GitHub API Rate Limit** | 인증 요청 5,000회/시간. 저장소 수가 많을 경우 rate limit 초과 가능성 낮음 |
| **토큰 권한** | `repo` scope 필요. 현재 토큰이 해당 scope를 보유하지 않으면 전환 불가 |
| **되돌리기 제한** | private 전환 후 재공개는 가능하나 fork된 내용은 복구 불가 |
| **Organization 저장소** | 개인 계정(garimto81) 소유 저장소만 대상. Organization 저장소는 별도 권한 필요 |

---

## 우선순위

```
Phase A: 토큰 scope 확인 (선행 필수)
    ↓
Phase B: Public 저장소 목록 조회 (dry-run, 사용자 확인)
    ↓
Phase C: 일괄 Private 전환 실행 (--confirm 필요)
    ↓
Phase D: secretary 연동 검증 (github_analyzer.py + projects.json)
```

---

## 구현 계획

### Phase A: 현재 Public 저장소 목록 조회 (확인용)

**목표**: 전환 대상 저장소 목록 파악 및 토큰 권한 확인

구현 내용:
1. `scripts/github_private_converter.py` 스크립트 작성
2. `--list` 옵션: 현재 public 저장소 목록 출력 (dry-run)
3. `--check-token` 옵션: 토큰 scope 확인 및 출력
4. 토큰 파일: `C:\claude\json\github_token.txt` (Bearer 토큰)

출력 예시:
```
[Token Scope Check]
Current scopes: repo, read:user, ...
Required: repo ✓

[Public Repositories (dry-run)]
1. garimto81/claude (public)
2. garimto81/example-repo (public)
Total: N repositories to convert
```

### Phase B: 일괄 Private 전환 실행

**목표**: 모든 public 저장소를 private으로 전환

구현 내용:
1. `--convert` 옵션: 실제 전환 실행 (`--confirm` 필요)
2. 각 저장소 `PATCH /repos/{owner}/{repo}` 호출
3. 성공/실패 실시간 출력
4. 최종 통계 출력 (성공 N / 실패 M / 전체 K)

### Phase C: secretary 연동 검증

**목표**: 전환 후 secretary 프로젝트 GitHub 연동 정상 동작 확인

구현 내용:
1. `python scripts/github_analyzer.py --days 5` 실행하여 private 저장소 접근 검증
2. `config/projects.json` `github_repos` 설정의 저장소 접근 확인
3. 이상 없으면 검증 완료

---

## 구현 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| 토큰 scope 확인 로직 | 예정 | github_private_converter.py |
| Public 저장소 조회 | 예정 | `--list` 옵션 |
| Private 전환 스크립트 | 예정 | `--convert --confirm` 옵션 |
| 전환 결과 검증 | 예정 | `--verify` 옵션 |
| secretary 연동 검증 | 예정 | github_analyzer.py 실행 |

---

## Changelog

| 날짜 | 버전 | 변경 내용 | 결정 근거 |
|------|------|-----------|----------|
| 2026-02-25 | v1.0 | 최초 작성 | 보안 강화를 위한 저장소 private 전환 요구사항 정의 |
