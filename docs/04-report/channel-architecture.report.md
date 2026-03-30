# Channel Architecture 리팩토링 완료 보고서

> Slack 채널 ID `C0985UXQN6Q`가 3개 설정 파일에 분산 하드코딩되던 구조적 문제를 `config/channels.json` 단일 레지스트리로 통합하여, 새 채널 추가 시 1개 파일만 수정하면 되는 구조로 전환했습니다.
>
> **Status**: Completed — Architect APPROVED (x2), Code Review APPROVED
> **복잡도**: STANDARD (3/5)
> **완료일**: 2026-02-19

---

## 1. PDCA 사이클 요약

### 1.1 Plan 단계

**문서**: `docs/01-plan/channel-architecture.plan.md`

**배경**:
- Slack 채널 ID `C0985UXQN6Q`가 `config/gateway.json` 2곳 + `config/projects.json` 1곳에 독립적으로 하드코딩됨
- 새 채널 추가 또는 역할 변경 시 3개 파일을 동시에 수정해야 하는 구조적 결함
- 채널 ID 누락·불일치로 인한 Silent Failure(채널 감시 단절, 잘못된 프로젝트 매핑) 위험

**분산 참조 현황 (Before)**:

```
config/gateway.json
├── channels.slack.channels: ["C0985UXQN6Q"]      ← Gateway 수신 감시
└── intelligence.chatbot_channels: ["C0985UXQN6Q"] ← Chatbot 분기 판단

config/projects.json
└── projects[secretary].slack_channels: ["C0985UXQN6Q"] ← 채널→프로젝트 매핑
```

### 1.2 Design 단계

**문서**: `docs/02-design/channel-architecture.design.md`

**핵심 설계 결정**:
1. `config/channels.json`을 단일 진실의 원천(Single Source of Truth)으로 정의
2. `ChannelRegistry` 클래스가 파일 로드 + 역할 기반 조회 + 프로젝트 매핑을 담당
3. `server.py`와 `project_context.py`는 레지스트리 우선 조회 후 기존 config로 폴백
4. 3중 import fallback 패턴으로 프로젝트 루트/scripts 내부/패키지 내부 실행 모두 지원
5. 기존 `gateway.json`, `projects.json` 값 유지(하위 호환) — 단계적 마이그레이션

**목표 구조 (After)**:

```
config/channels.json (단일 진실의 원천)
    ↓ ChannelRegistry.load()
ChannelRegistry (메모리 캐시)
    ├── server.py._connect_adapters()          → SlackAdapter 채널 목록 주입
    ├── server.py._register_intelligence_handler() → chatbot_channels 주입
    └── project_context.py.resolve()           → 채널→프로젝트 우선 매핑
```

### 1.3 Do 단계 (구현)

아래 "구현 완료 항목" 섹션 참조.

### 1.4 Check 단계

```
45 passed, 0 failed (전체 회귀 테스트)
lint: ruff check — PASS (0 violations)
Architect APPROVED (x2 — Phase 3.2, Phase 4.2)
Code Review APPROVED
```

---

## 2. 구현 완료 항목

### Phase A — 채널 레지스트리 설정 파일 정의

#### A1. `config/channels.json` 신규 생성

채널 ID, 유형, 역할, 프로젝트 연결을 한 곳에서 관리하는 마스터 설정 파일.

```json
{
  "channels": [
    {
      "id": "C0985UXQN6Q",
      "name": "general",
      "type": "slack",
      "roles": ["monitor", "chatbot", "project-bound"],
      "project_id": "secretary",
      "enabled": true
    }
  ]
}
```

**역할(role) 정의**:

| 역할 | 대체 대상 | 동작 |
|------|----------|------|
| `monitor` | `gateway.json channels.slack.channels` | Gateway 어댑터가 이 채널의 메시지 수신 감시 |
| `chatbot` | `gateway.json intelligence.chatbot_channels` | Intelligence handler가 Chatbot 경로로 직접 처리 |
| `project-bound` | `projects.json slack_channels` | `project_id` 필드로 채널→프로젝트 자동 매핑 |

#### A2. `config/gateway.json` 마이그레이션 마킹

`channels.slack` 섹션에 `_channel_source` 메타 필드 추가. 기존 값(`channels`, `chatbot_channels`)은 폴백용으로 유지.

```json
"slack": {
  "enabled": true,
  "channels": ["C0985UXQN6Q"],
  "_channel_source": "channels.json",
  ...
}
```

---

### Phase B — ChannelRegistry 클래스 + 코드 연동

#### B1. `scripts/gateway/channel_registry.py` 신규 생성

```
ChannelRegistry 클래스
  - load(path)              → channels.json 로드. 실패 시 빈 목록, 예외 미발생
  - get_by_role(role, type) → 역할 + 유형 필터링, enabled=true 채널 ID 목록 반환
  - get_project_id(id)      → 채널 ID → project_id 반환 (project-bound 역할 필수)
  - is_enabled(id)          → 채널 활성화 여부
  - all_channel_ids(type)   → 전체 enabled 채널 ID 목록
```

**폴백 설계**: `load()` 실패(파일 없음, JSON 오류, OS 오류) 시 `self._channels = []`로 초기화. 호출부에서 `get_by_role()`이 빈 목록을 반환하면 기존 `gateway.json` 값으로 폴백.

#### B2. `scripts/gateway/server.py` 수정

`_connect_adapters()`:
- 서버 시작 시 `ChannelRegistry` 로드 시도
- 로드 성공 시 `get_by_role("monitor", "slack")` 결과를 `SlackAdapter` config에 주입
- 로드 실패 또는 빈 결과 시 `gateway.json channels.slack.channels` 원본 사용

`_register_intelligence_handler()`:
- 레지스트리 있으면 `get_by_role("chatbot", "slack")` 결과를 `chatbot_channels`로 사용
- 레지스트리 없거나 빈 결과 시 `intel_config["chatbot_channels"]` 폴백

#### B3. `scripts/gateway/project_context.py` 수정

`ProjectContextResolver.__init__()`:
- `registry: ChannelRegistry | None = None` 파라미터 추가
- `self._registry`로 저장 (주입 없으면 None)

`resolve()` 우선순위 변경:
```
0. ChannelRegistry.get_project_id() (주입된 경우 최우선)
   ↓ 미매칭 시
1. projects.json slack_channels (기존 동작)
   ↓ 미매칭 시
2. Gmail 패턴 매칭
   ↓ 미매칭 시
3. 키워드 매칭
```

---

### Phase C — 설정 정합성 보장

#### C1. `config/projects.json` Deprecation 마킹

`secretary` 프로젝트의 `slack_channels` 배열에 deprecation 안내 필드 추가.
기존 값은 폴백 호환성을 위해 유지.

```json
"slack_channels": ["C0985UXQN6Q"],
"_deprecated_slack_channels_note": "Use config/channels.json for channel-project mapping instead"
```

---

## 3. 파일 변경 요약

| 파일 | 유형 | 변경 내용 |
|------|------|---------|
| `config/channels.json` | **신규** | 채널 레지스트리 마스터 설정 |
| `scripts/gateway/channel_registry.py` | **신규** | ChannelRegistry 클래스 (load, get_by_role, get_project_id, is_enabled, all_channel_ids) |
| `tests/gateway/test_channel_registry.py` | **신규** | ChannelRegistry 단위 테스트 6개 |
| `config/gateway.json` | 수정 | `_channel_source: "channels.json"` 마킹 추가 |
| `config/projects.json` | 수정 | `_deprecated_slack_channels_note` 필드 추가 |
| `scripts/gateway/server.py` | 수정 | `_connect_adapters`, `_register_intelligence_handler` 레지스트리 연동 |
| `scripts/gateway/project_context.py` | 수정 | `__init__` registry 파라미터, `resolve()` 레지스트리 우선 적용 |

**변경 없는 파일**:

| 파일 | 이유 |
|------|------|
| `scripts/gateway/pipeline.py` | 채널 ID 직접 참조 없음 |
| `scripts/intelligence/response/handler.py` | `chatbot_channels` 목록을 server.py에서 주입받으므로 내부 로직 무변경 |
| `scripts/gateway/models.py` | 데이터 모델, 채널 설정 무관 |
| `scripts/gateway/adapters/base.py` | 추상 인터페이스, 채널 설정 무관 |

---

## 4. 테스트 결과

### 신규 테스트 (`tests/gateway/test_channel_registry.py`)

| 테스트 케이스 | 검증 내용 | 결과 |
|-------------|---------|------|
| `test_load_channels_json` | 파일 로드 후 enabled 채널 수(2개) 확인 | PASS |
| `test_get_by_role_monitor` | monitor 역할 조회 + disabled 채널 제외 확인 | PASS |
| `test_get_by_role_chatbot` | chatbot 역할 조회 + monitor-only 채널 제외 확인 | PASS |
| `test_get_project_id` | project-bound 역할 채널 → project_id 반환 확인 | PASS |
| `test_is_enabled` | enabled/disabled/미등록 채널 상태 확인 | PASS |
| `test_fallback_when_no_registry` | 미로드 상태에서 빈 목록 반환 확인 | PASS |

### 전체 회귀 테스트

```
pytest tests/ -v
45 passed, 0 failed
```

```
ruff check scripts/gateway/channel_registry.py
0 violations
```

---

## 5. 폴백 전략

채널 레지스트리 도입으로 새로운 장애 지점이 생기지 않도록 4단계 폴백을 설계했습니다.

| 실패 시나리오 | 폴백 동작 | 로그 수준 |
|-------------|----------|---------|
| `channels.json` 미존재 | `gateway.json` 원본 채널 목록 사용 | WARNING |
| JSON 파싱 오류 | `gateway.json` 원본 채널 목록 사용 | WARNING |
| 레지스트리 로드 성공 + 역할 없음 | `gateway.json` 원본 채널 목록 사용 | DEBUG |
| `ChannelRegistry` import 실패 | `registry=None`, 기존 동작 그대로 | WARNING |

**결론**: `channels.json`을 삭제하거나 문법 오류가 생겨도 Gateway 서버는 기존 동작을 유지합니다.

---

## 6. 해결된 문제

### Before

새 Slack 채널을 추가하려면 3개 파일을 동시에 수정해야 했으며, 하나라도 누락하면 채널 감시 단절, chatbot 미응답, 프로젝트 매핑 실패 중 하나가 silent failure로 발생했습니다.

```
새 채널 추가 시 수정 필요 파일:
  gateway.json → channels.slack.channels 배열 추가
  gateway.json → intelligence.chatbot_channels 배열 추가
  projects.json → projects[N].slack_channels 배열 추가
```

### After

`config/channels.json` 1곳에 채널 항목을 추가하면 monitor, chatbot, 프로젝트 매핑이 모두 자동으로 반영됩니다.

```
새 채널 추가 시 수정 파일:
  channels.json → 채널 항목 1개 추가 (id, roles, project_id 포함)
```

---

## 7. 다음 액션

| 항목 | 내용 | 시점 |
|------|------|------|
| C2 구현 | `interactive_slack_channel_select()` → `channels.json` 자동 저장 (atomic write) | 운영 안정화 후 |
| `gateway.json` 정리 | `channels.slack.channels`, `intelligence.chatbot_channels` 하드코딩 제거 | C2 완료 후 |
| `projects.json` 정리 | `slack_channels` 배열 항목 실제 제거 | gateway.json 정리 후 |
