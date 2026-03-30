# Channel Mastery PRD

**문서 버전**: 2.0
**작성일**: 2026-02-18
**상태**: Draft

---

## 1. 한 줄 요약

Gateway가 조용히 죽거나 GitHub을 모르는 채로 운영되는 문제를 재연결 자동화, GitHub 어댑터 구현, 플러그인 아키텍처로 해결한다.

---

## 2. 배경: 무엇이 불편한가

**연결 실패 무음 종료**: Gateway가 죽었는데 나는 모른다.

채널 연결이 끊기면 수신 루프가 조용히 종료된다. Slack이 끊겼는지, Gmail이 멈췄는지 직접 확인하기 전까지는 알 방법이 없다.

**GitHub 채널 공백**: Intelligence가 GitHub을 아예 학습하지 못한다.

GitHub 채널 타입은 정의되어 있지만 실제 어댑터가 없다. GitHub Issues, PR 댓글, 멘션 이벤트가 파이프라인에 한 건도 들어오지 않는다.

**채널 추가 장벽**: 설정 파일 수정으로 끝날 일이 코드 수정 작업이 된다.

현재 어댑터 생성 로직이 채널 이름을 하드코딩으로 분기한다. 새 채널을 붙이려면 소스코드를 직접 고쳐야 한다.

---

## 3. 이 도구를 쓰는 사람

이 도구의 유일한 사용자는 도구 제작자 본인이다. 개인 AI 비서를 상시 운영하는 개발자이며 동시에 구현자다.

---

## 4. 목표와 제외 범위

### Goals

| 목표 | 우선순위 |
|------|:--------:|
| GitHub 어댑터 구현 | P0 |
| Slack/Gmail 재연결 로직 | P0 |
| seen_ids 메모리 누수 방지 | P0 |
| 플러그인 아키텍처 | P1 |
| Health Monitoring API | P1 |
| 어댑터 E2E 테스트 | P1 |
| Slack Socket Mode | P2 |
| Gmail Push | P2 |

### Non-Goals

1. Slack Socket Mode를 기본값으로 전환 — 실시간성이 매력적이나 polling으로 충분
2. 재연결 실패 시 Slack DM 알림 — Reporter 연동은 Gateway 안정화 이후 단계
3. Health 데이터 DB 영구 저장 — 모니터링 시스템화 유혹이 있으나 메모리 기반으로 충분
4. GitHub webhook 방식 — Push가 이상적이나 로컬 환경에서 ngrok 의존성 발생

---

## 5. 기능 요구사항

### P0: Must-Have

#### FR-01: GitHub 어댑터 구현

GitHub REST API polling으로 Issues/PR/멘션 이벤트를 `NormalizedMessage`로 변환한다.

**Acceptance Criteria**:
- GitHub Issues, PR, 멘션 이벤트가 NormalizedMessage로 변환되어 파이프라인에 도달한다
- 기존 인증 토큰을 자동 로드하고, gateway.json 설정으로 활성화한다
- 단위 테스트 통과

설계 상세: docs/02-design/channel-mastery.design.md 참조

#### FR-02: Slack/Gmail 어댑터 재연결 로직

`listen()` 루프 Exception 발생 시 exponential backoff(5~300초)로 최대 10회 재연결.

**Acceptance Criteria**:
- 재연결 간격: 5, 10, 20, 40, 80, 160, 300초. 초과 시 `[CRITICAL]` 로그 + 어댑터 비활성화
- `get_status()` 응답에 `reconnect_count`, `last_error` 포함

설계 상세: docs/02-design/channel-mastery.design.md 참조

#### FR-03: seen_ids 슬라이딩 윈도우

Gmail 중복 체크용 메시지 ID 캐시를 5000건에서 최근 1000건으로 축소. 장기 운영 시 메모리 누수를 방지한다.

---

### P1: Should-Have

#### FR-04: 플러그인 아키텍처

설정 파일만으로 새 어댑터를 등록할 수 있게 한다. 소스코드 수정 없이 채널 추가가 가능해야 한다.

**Acceptance Criteria**:
- 설정 파일에 어댑터 경로 지정 시 자동 로드, 미지정 시 기존 방식으로 fallback
- 잘못된 설정 시 명확한 에러 메시지 출력 후 서버 시작 중단

설계 상세: docs/02-design/channel-mastery.design.md 참조

#### FR-05: Health Monitoring API

`ChannelAdapter.get_health()` 추상 메서드 추가. `messages_received`, `errors_count`, `reconnect_count`, `uptime_seconds` 수집. `python server.py status`에 채널별 요약 표시. 메모리 기반(재시작 시 초기화).

#### FR-06: 어댑터 E2E 테스트

각 어댑터 connect → listen → send를 mock 기반으로 검증. `pytest tests/gateway/ -v` 외부 서비스 의존 없이 즉시 실행 가능.

---

### P2: Nice-to-Have

#### FR-07: Slack Socket Mode

`gateway.json`에서 `mode: socket | polling` 선택. Socket Mode 연결 실패 시 polling으로 자동 fallback.

#### FR-08: Gmail Push

Cloud Pub/Sub 기반 Push 알림으로 60초 polling을 5초 이내로 단축. `aiohttp` 경량 서버(포트 8801)로 webhook 수신.

---

## 6. 성공 지표

### Primary (사용자 가치)

| 지표 | 현재 | 목표 | 측정 |
|------|:----:|:----:|------|
| 연결 실패 후 수동 재시작 횟수 | 측정 안 됨 | 0회/주 | 로그 `[RECONNECTED]` vs `[MANUAL_RESTART]` |
| 연결 실패 인지 지연 | 알 수 없음 | 즉시 확인 가능 | `server.py status` 출력 |
| GitHub → Intelligence 도달률 | 0% | 100% | intelligence.db source=github |
| 채널 추가에 코드 수정 필요 | 필요 | 불필요 | gateway.json만으로 등록 |

### Secondary (기술 지표)

| 지표 | 현재 | 목표 |
|------|:----:|:----:|
| 지원 채널 수 | 2 | 3 |
| 어댑터 테스트 커버리지 | 0% | 80% |
| 24시간 무중단 | 미검증 | 유지 |

---

## 7. 위험 요소

| 위험 | 심각도 | 가능성 | 완화 전략 |
|------|:------:|:------:|----------|
| GitHub API rate limit (5000req/hr) | 중 | 중 | polling 간격 60초, 증분 조회(etag/since 활용) |
| 동적 어댑터 로드 시 잘못된 경로로 서버 시작 실패 | 고 | 저 | 시작 시 어댑터 클래스 유효성 사전 검증, fallback 이름 매핑 유지 |
| 재연결 루프가 무한 재시도로 CPU 점유 | 중 | 중 | MAX_RETRIES=10 상한선, 재연결 실패 시 어댑터 disabled 상태로 전환 |
| Slack Socket Mode WebSocket 연결 불안정 (방화벽, 프록시) | 중 | 저 | polling fallback 자동 전환, 설정 기본값은 polling 유지 |
| Gmail Push webhook 공인 IP/도메인 필요 | 고 | 고 | P2 구현 전 인프라 요구사항 확인 필수 |
| GitHub 어댑터 토큰 만료로 무한 에러 루프 | 중 | 저 | 401 응답 시 즉시 재연결 중단, 토큰 갱신 안내 로그 출력 |

### Edge Cases

- **재연결 중 메시지 유실**: 재연결 성공 후 `oldest = last_ts`로 누락 메시지 소급 조회. 첫 연결 시는 재연결 시점 이후만 수신.
- **seen_ids 전환 직후 중복 처리**: 마이그레이션 시 48시간 이내 메시지 ID만 유지하여 중복 수신 방지.
- **Registry 중복 등록**: 동일 채널 이름 중복 시 후자 덮어쓰기, 경고 로그 출력.

---

## 8. 의존성

### 내부 의존성

| 모듈 | 역할 | 변경 영향 |
|------|------|-----------|
| `scripts/gateway/models.py` | `ChannelType.GITHUB` 기존 정의 | 변경 없음 |
| `scripts/gateway/pipeline.py` | `MessagePipeline.process()` | 변경 없음 (어댑터 독립적) |
| `scripts/gateway/storage.py` | `UnifiedStorage.save_message()` | 변경 없음 |
| `scripts/shared/retry.py` | Exponential backoff 유틸리티 | 재연결 컴포넌트에서 재활용 가능 |

### 외부 의존성

| 라이브러리 | 용도 | 현재 상태 |
|-----------|------|-----------|
| `lib.slack.SlackClient` | Slack polling, 메시지 전송 | 인증 완료 |
| `lib.gmail.GmailClient` | Gmail History API, Draft 생성 | 인증 완료 |
| `C:/claude/json/github_token.txt` | GitHub REST API 인증 | 인증 완료 |
| `requests` 또는 `httpx` | GitHub API HTTP 클라이언트 | requirements.txt 확인 필요 |
| `slack_sdk` (선택) | Slack Socket Mode | P2 구현 시 설치 필요 |
| `google-cloud-pubsub` (선택) | Gmail Push | P2 구현 시 설치 필요 |

### 운영 환경 전제

- Python 3.10+, Windows 11
- `C:/claude/secretary/data/` 디렉토리 쓰기 권한
- Ollama `http://localhost:11434` 상시 실행 (Intelligence 레이어)
- GitHub token: `C:/claude/json/github_token.txt` 존재
