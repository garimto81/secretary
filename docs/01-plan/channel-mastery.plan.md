# Channel Mastery 구현 계획

**PRD 참조**: docs/prd/channel-mastery.prd.md
**생성일**: 2026-02-18
**복잡도**: STANDARD (3/5)
**상태**: Active

---

## 배경

Secretary Gateway는 Slack, Gmail 2개 채널만 실제로 동작하지만, `ChannelType.GITHUB`는 이미 enum에 정의되어 있어 구현 공백이 존재한다. 또한 신규 채널 추가 시마다 `server.py` 하드코딩 수정이 필요하고, 연결 실패 시 재연결 로직이 없어 장시간 운영이 불안정하다. Channel Mastery는 GitHub 어댑터 구현, 재연결 안정화, 플러그인 아키텍처 도입으로 Gateway의 안정성·확장성을 강화한다.

---

## 구현 범위

### Phase 1: 기반 안정화 (P0)

| 작업 ID | 작업 | 영향 파일 | 완료 기준 |
|---------|------|----------|----------|
| CM-01 | `GitHubAdapter` 구현 (polling 방식, Issues/PR/Mentions) | `C:\claude\secretary\scripts\gateway\adapters\github.py` (신규) | `pytest tests/gateway/test_github_adapter.py -v` 통과, Issues·PR 이벤트가 `NormalizedMessage`로 변환됨 |
| CM-02 | `AdapterSupervisor` 재연결 루프 구현 (exponential backoff) | `C:\claude\secretary\scripts\gateway\server.py` (수정) | 연결 실패 후 5·10·20·40·80·160·300초 backoff로 최대 10회 재연결, `[CRITICAL]` 로그 기록 확인 |
| CM-03 | `SlackAdapter` 재연결 로직 적용 및 `reconnect_count`/`last_error` 상태 노출 | `C:\claude\secretary\scripts\gateway\adapters\slack.py` (수정) | 연결 실패 시뮬레이션 테스트 통과, `get_status()` 응답에 `reconnect_count` 포함 |
| CM-04 | `GmailAdapter` `seen_ids` 슬라이딩 윈도우 교체 (5000→1000건) | `C:\claude\secretary\scripts\gateway\adapters\gmail.py` (수정) | 메모리 상한선 1000건 검증 테스트 통과, 원자적 set 교체 확인 |

### Phase 2: 플러그인 아키텍처 (P1)

| 작업 ID | 작업 | 영향 파일 | 완료 기준 |
|---------|------|----------|----------|
| CM-05 | `PluginAdapterRegistry` 구현 — `importlib` 동적 로드, 이름 기반 fallback | `C:\claude\secretary\scripts\gateway\server.py` (수정) | `gateway.json`에 `adapter` 클래스 경로 지정 시 동적 로드, 잘못된 경로에 명확한 에러 출력 |
| CM-06 | `HealthMetrics` dataclass + `AdapterHealthMonitor` 구현 | `C:\claude\secretary\scripts\gateway\server.py` (수정), `C:\claude\secretary\scripts\gateway\adapters\base.py` (수정) | `python server.py status` JSON 출력에 채널별 `messages_received`·`errors_count`·`uptime_seconds` 포함 |
| CM-07 | `ChannelAdapter.get_health()` 추상 메서드 추가 + 기존 어댑터 구현 | `C:\claude\secretary\scripts\gateway\adapters\base.py` (수정), `adapters/slack.py` (수정), `adapters/gmail.py` (수정), `adapters/github.py` (수정) | 모든 어댑터가 `get_health()` 구현, `HealthMetrics` 반환 |
| CM-08 | 어댑터 E2E mock 테스트 3종 추가 | `C:\claude\secretary\tests\gateway\test_slack_adapter.py` (신규), `tests\gateway\test_gmail_adapter.py` (신규), `tests\gateway\test_github_adapter.py` (신규) | `pytest tests/gateway/ -v` 전체 통과, 외부 서비스 의존 없음 |
| CM-09 | `gateway.json`에 `github` 채널 섹션 및 `adapter` 필드 예시 추가 | `C:\claude\secretary\config\gateway.json` (수정) | `"github": {"enabled": true, "adapter": "scripts.gateway.adapters.github.GitHubAdapter"}` 설정으로 활성화 확인 |

### Phase 3: 실시간 채널 (P2, 선택)

| 작업 ID | 작업 | 영향 파일 | 완료 기준 |
|---------|------|----------|----------|
| CM-10 | Slack Socket Mode 선택적 지원 (`gateway.json` `mode: socket\|polling`) | `C:\claude\secretary\scripts\gateway\adapters\slack.py` (수정) | `mode: socket` 설정 시 `slack_sdk.socket_mode` 사용, 연결 실패 시 polling fallback 자동 전환 |
| CM-11 | Gmail Cloud Pub/Sub Push 수신 서버 구현 (포트 8801, aiohttp) | `C:\claude\secretary\scripts\gateway\adapters\gmail.py` (수정), `C:\claude\secretary\scripts\gateway\server.py` (수정) | `mode: push` 설정 시 Pub/Sub webhook으로 5초 내 이메일 수신, 실패 시 다음 polling 사이클 재처리 |

---

## 영향 파일

### 신규 파일

| 파일 | 목적 |
|------|------|
| `C:\claude\secretary\scripts\gateway\adapters\github.py` | `GitHubAdapter` 전체 구현 (Issues, PR, Mentions polling) |
| `C:\claude\secretary\tests\gateway\test_slack_adapter.py` | SlackAdapter E2E mock 테스트 |
| `C:\claude\secretary\tests\gateway\test_gmail_adapter.py` | GmailAdapter E2E mock 테스트 |
| `C:\claude\secretary\tests\gateway\test_github_adapter.py` | GitHubAdapter E2E mock 테스트 |

### 수정 파일

| 파일 | 수정 내용 |
|------|----------|
| `C:\claude\secretary\scripts\gateway\server.py` | `PluginAdapterRegistry`, `AdapterSupervisor`, `AdapterHealthMonitor` 추가 |
| `C:\claude\secretary\scripts\gateway\adapters\base.py` | `get_health()` 추상 메서드, `HealthMetrics` dataclass 추가 |
| `C:\claude\secretary\scripts\gateway\adapters\slack.py` | 재연결 로직, health 지표 수집, (선택) Socket Mode |
| `C:\claude\secretary\scripts\gateway\adapters\gmail.py` | seen_ids 슬라이딩 윈도우, 재연결 로직, health 지표, (선택) Push |
| `C:\claude\secretary\config\gateway.json` | `github` 채널 섹션, `adapter` 필드 예시 추가 |

### 변경 없는 파일

| 파일 | 이유 |
|------|------|
| `C:\claude\secretary\scripts\gateway\models.py` | `ChannelType.GITHUB` 이미 정의됨 |
| `C:\claude\secretary\scripts\gateway\pipeline.py` | 어댑터와 독립적, 파이프라인 로직 변경 불필요 |
| `C:\claude\secretary\scripts\gateway\storage.py` | `save_message()` 인터페이스 변경 불필요 |
| `C:\claude\secretary\scripts\shared/retry.py` | `AdapterSupervisor`에서 재활용 (수정 불필요) |

---

## 위험 요소

| 위험 | 심각도 | 완화 전략 |
|------|:------:|----------|
| `importlib` 동적 로드 시 잘못된 클래스 경로로 서버 시작 실패 | 고 | 시작 시 어댑터 클래스 사전 검증, fallback 이름 매핑 유지 |
| GitHub API rate limit (5000req/hr) 초과 | 중 | polling 간격 60초, etag/since 기반 증분 조회 |
| `AdapterSupervisor` 재연결 루프 CPU 점유 | 중 | MAX_RETRIES=10 상한선, 초과 시 어댑터 disabled 전환 |

---

## 작업 순서

Phase 1 → Phase 2 순서 의존성:

```
CM-01 (GitHubAdapter 구현)
    │
    └── CM-07 (get_health() 추상 메서드 + GitHubAdapter 구현체) ← CM-06 (HealthMetrics)
            │
            └── CM-08 (E2E 테스트 3종)

CM-02 (AdapterSupervisor 재연결 루프)
    │
    ├── CM-03 (SlackAdapter 재연결 + health)
    └── CM-04 (GmailAdapter seen_ids 슬라이딩 윈도우 + health)

CM-05 (PluginAdapterRegistry)
    │
    └── CM-09 (gateway.json github 섹션 추가)

Phase 2 (CM-05~CM-09) 전체는 Phase 1 (CM-01~CM-04) 완료 후 착수

CM-10, CM-11 (Phase 3) — Phase 2 완료 후, 사용자 요청 시에만 진행
```

**권장 착수 순서**: CM-02 → CM-03 → CM-04 → CM-01 → CM-06 → CM-07 → CM-05 → CM-09 → CM-08
