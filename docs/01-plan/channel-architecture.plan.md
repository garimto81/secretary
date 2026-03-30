# Channel Architecture 계획

## 배경

### 작업 요청 요약
테스트용 Slack 채널 ID `C0985UXQN6Q`가 3개 독립 설정 파일/섹션에 하드코딩되어,
새 채널을 추가하거나 역할을 변경할 때 여러 파일을 동시에 수정해야 하는 구조적 문제가 있다.

### 현재 문제: 3곳 분산 참조

| 위치 | 키 경로 | 역할 |
|------|---------|------|
| `config/gateway.json` `.channels.slack.channels` | `["C0985UXQN6Q"]` | Gateway 수신 감시 대상 채널 목록 |
| `config/gateway.json` `.intelligence.chatbot_channels` | `["C0985UXQN6Q"]` | Chatbot 분기(direct reply) 판단 기준 |
| `config/projects.json` `.projects[].slack_channels` | `["C0985UXQN6Q"]` | 채널 → 프로젝트 매핑 |

### 이 3곳을 참조하는 코드

| 파일 | 라인 | 동작 |
|------|------|------|
| `scripts/gateway/server.py:256-266` | `_connect_adapters()` | `gateway.json channels` 읽어 SlackAdapter 생성 |
| `scripts/gateway/server.py:329-336` | `_register_intelligence_handler()` | `intelligence.chatbot_channels` 읽어 handler에 주입 |
| `scripts/gateway/project_context.py:83-111` | `ProjectContextResolver.resolve()` | `projects.json slack_channels`로 채널→프로젝트 매핑 |
| `scripts/intelligence/response/handler.py:137` | `_is_chatbot_channel()` | chatbot 채널 여부를 판단하여 별도 경로로 분기 |

### 기존 계획과의 차이
`channel-mastery.plan.md`는 어댑터 플러그인/재연결 안정화에 집중.
**채널 등록·라우팅 설계가 없으므로** 본 계획이 별도로 필요하다.

---

## 구현 범위

### 핵심 설계 원칙
채널을 **단일 레지스트리**에 등록하고, `role` 필드로 역할을 부여한다.
`gateway.json`의 `channels.slack.channels`와 `intelligence.chatbot_channels`는
채널 레지스트리에서 동적으로 조회하여 대체한다.
`projects.json`의 `slack_channels`는 채널 레지스트리의 `project_id` 필드와 연동한다.

### Phase A — 채널 레지스트리 스키마 설계 (config 변경)

**작업 ID: A1** — `config/channels.json` 신규 생성

```json
{
  "channels": [
    {
      "id": "C0985UXQN6Q",
      "name": "general",
      "type": "slack",
      "roles": ["monitor", "chatbot"],
      "project_id": "secretary",
      "enabled": true
    }
  ]
}
```

역할 정의:
- `monitor`: Gateway 어댑터가 수신 감시. `gateway.json channels.slack.channels` 대체.
- `chatbot`: Intelligence handler가 direct reply 수행. `intelligence.chatbot_channels` 대체.
- `project-bound`: `project_id` 필드가 유효한 경우. `projects.json slack_channels` 대체.

**Acceptance Criteria:**
- `config/channels.json` 파일이 존재하고 위 스키마를 따른다.
- 기존 `C0985UXQN6Q`가 `monitor + chatbot + project-bound` 역할로 등록된다.
- JSON 스키마 유효성 검증 통과 (필수 필드: `id`, `type`, `roles`, `enabled`).

---

**작업 ID: A2** — `config/gateway.json` 마이그레이션 준비

`channels.slack.channels` 키에 채널 레지스트리를 우선 참조하도록 **주석 형태 마킹**:
```json
"_channel_source": "channels.json"
```
기존 `channels: ["C0985UXQN6Q"]` 및 `chatbot_channels: ["C0985UXQN6Q"]` 값은
Phase B 완료 후 제거. Phase A에서는 유지하여 하위 호환성 보장.

**Acceptance Criteria:**
- `gateway.json` 구조가 깨지지 않는다.
- `_channel_source` 필드가 추가된다.

---

### Phase B — ChannelRegistry 클래스 구현

**작업 ID: B1** — `scripts/gateway/channel_registry.py` 신규 생성

```python
class ChannelRegistry:
    """
    config/channels.json 로드 및 역할 기반 조회를 제공하는 단일 채널 레지스트리.
    """
    def load(self, path: Path) -> None: ...
    def get_by_role(self, role: str, channel_type: str = "slack") -> List[str]:
        """특정 role이 부여된 채널 ID 목록 반환."""
    def get_project_id(self, channel_id: str) -> Optional[str]:
        """채널 ID → project_id 반환 (project-bound role인 경우)."""
    def is_enabled(self, channel_id: str) -> bool: ...
```

**Acceptance Criteria:**
- `get_by_role("monitor")` → `["C0985UXQN6Q"]` 반환 (channels.json 기준).
- `get_by_role("chatbot")` → `["C0985UXQN6Q"]` 반환.
- `get_project_id("C0985UXQN6Q")` → `"secretary"` 반환.
- 3중 import fallback 패턴 적용 (`scripts.gateway.channel_registry > gateway.channel_registry > .channel_registry`).

---

**작업 ID: B2** — `scripts/gateway/server.py` 수정 (레지스트리 주입)

`_connect_adapters()` (라인 254-282):
- `ChannelRegistry` 로드 후 `get_by_role("monitor", "slack")` 결과를 `SlackAdapter` config에 주입.
- `gateway.json channels.slack.channels` 값이 없으면 레지스트리에서 폴백.

`_register_intelligence_handler()` (라인 307-381):
- `intel_config.get("chatbot_channels", [])` 대신 레지스트리 `get_by_role("chatbot")` 결과 사용.
- 레지스트리 미로드 시 기존 `chatbot_channels` 필드로 폴백.

**Acceptance Criteria:**
- `server.py`가 레지스트리 없이도 구동 가능 (폴백 동작).
- `channels.json` 존재 시, 레지스트리 값이 우선 적용된다.
- 기존 테스트 (`tests/gateway/test_pipeline.py`) 통과.

---

**작업 ID: B3** — `scripts/gateway/project_context.py` 수정

`ProjectContextResolver.__init__()` + `resolve()`:
- `ChannelRegistry` 주입 옵션 추가 (생성자 파라미터).
- Slack 채널 매칭 시 `projects.json slack_channels` 외에 레지스트리 `get_project_id(channel_id)` 우선 조회.
- 레지스트리 매칭 성공 시 `projects.json` 조회 스킵.

**Acceptance Criteria:**
- 레지스트리 미주입 시 기존 `projects.json` 기반 매칭 동작 유지.
- 레지스트리 주입 시, 레지스트리 결과가 `projects.json`보다 우선 적용된다.
- 기존 테스트 `tests/gateway/test_project_context.py` 통과.

---

### Phase C — 설정 정합성 보장 (migration + docs)

**작업 ID: C1** — `config/projects.json` 채널 중복 제거 준비

`secretary.slack_channels`의 `C0985UXQN6Q`를 `channels.json`이 관리하게 되므로,
**deprecation 마킹**만 수행 (실제 제거는 운영 안정화 후).

**Acceptance Criteria:**
- `projects.json`에 `"_deprecated_slack_channels_note"` 필드 추가.
- 기존 `slack_channels` 배열 값 유지 (제거하지 않음).

---

**작업 ID: C2** — 채널 추가 CLI 검토

`server.py`의 `interactive_slack_channel_select()` (라인 483-543):
- 채널 선택 결과를 `gateway.json`뿐 아니라 `channels.json`에도 저장하도록 수정.
- `_save_slack_channels()` → `_save_to_registry()` 추가 (기존 함수 유지).

**Acceptance Criteria:**
- `python server.py start` 후 대화형 채널 선택 시 `channels.json`에 채널 항목 자동 추가.
- 기존 `gateway.json` 저장 동작은 유지.

---

## 영향 파일

### 신규 생성

| 파일 | 용도 |
|------|------|
| `config/channels.json` | 채널 레지스트리 마스터 설정 |
| `scripts/gateway/channel_registry.py` | ChannelRegistry 클래스 |

### 수정 대상

| 파일 | 수정 내용 | Phase |
|------|-----------|-------|
| `config/gateway.json` | `_channel_source` 마킹 추가 | A2 |
| `config/projects.json` | `_deprecated_slack_channels_note` 추가 | C1 |
| `scripts/gateway/server.py` | 레지스트리 로드 + `_connect_adapters`, `_register_intelligence_handler` 수정 | B2 |
| `scripts/gateway/project_context.py` | 레지스트리 주입 옵션 추가, `resolve()` 레지스트리 우선 적용 | B3 |

### 변경 없는 파일

| 파일 | 이유 |
|------|------|
| `scripts/gateway/pipeline.py` | 채널 ID 직접 참조 없음 |
| `scripts/gateway/adapters/base.py` | 추상 인터페이스, 채널 설정 무관 |
| `scripts/gateway/models.py` | 데이터 모델, 채널 설정 무관 |
| `scripts/intelligence/response/handler.py` | `_is_chatbot_channel()` 로직 자체는 변경 없음 (chatbot_channels 목록만 서버에서 주입) |
| `config/projects.json` `.projects[wsoptv]` | 별도 채널 ID 사용 (`_SLACK_CHANNEL_ID_wsoptv`), 영향 없음 |

---

## 위험 요소

### 기술적 위험

**위험 1: 폴백 동작 미작동으로 인한 채널 감시 단절**

`channels.json` 파싱 오류 또는 레지스트리 로드 실패 시,
폴백 없이 `gateway.json channels.slack.channels`도 빈 배열로 처리되면
어떤 Slack 채널도 수신되지 않는다.

완화 방법:
- `ChannelRegistry.load()` 실패 시 `None` 반환, 호출부에서 기존 config 배열로 폴백.
- `server.py`에서 레지스트리 로드 실패를 WARNING 로그로만 처리, 기존 동작 유지.

---

**위험 2: chatbot_channels 동기화 불일치**

Phase B 완료 전 과도기 상태에서 `channels.json`에 `chatbot` 역할을 부여했으나
`gateway.json intelligence.chatbot_channels` 목록에는 없는 채널이 생길 수 있다.

완화 방법:
- Phase B 완료까지 `channels.json`과 `gateway.json` 양쪽 모두 값을 유지.
- B2 완료 시점에 `gateway.json chatbot_channels` 값을 레지스트리로 완전 이전.

---

**Edge Case 1: 동일 채널에 `monitor`만 부여 (chatbot 역할 없음)**

`channels.json`에 채널이 `monitor` 역할만으로 등록되면,
`get_by_role("chatbot")`에 포함되지 않아 chatbot 응답이 비활성화된다.
이는 의도적 동작이므로 문서화로 명확히 한다.

---

**Edge Case 2: `project_id` 미설정 채널의 프로젝트 매핑 충돌**

레지스트리에 `project_id` 없이 등록된 채널이
`projects.json`의 `slack_channels`에도 없을 경우,
`ProjectContextResolver.resolve()`가 `None`을 반환하여
Intelligence 핸들러가 `pending_match`로 저장한다.
이는 기존 동작과 동일하며, 레지스트리 도입으로 새로운 장애를 만들지 않는다.

---

**Edge Case 3: `interactive_slack_channel_select` 중단 시 channels.json 부분 기록**

대화형 채널 선택 중 인터럽트 발생 시 `channels.json`에 불완전한 항목이 쓰일 수 있다.

완화 방법:
- `_save_to_registry()` 내에서 전체 항목 구성 후 atomic write (임시 파일 → rename).

---

### 위험 요소 요약

| 위험 | 심각도 | 완화 |
|------|--------|------|
| 레지스트리 로드 실패 → 채널 감시 단절 | 높음 | 폴백 로직 필수 |
| 과도기 이중 설정 불일치 | 중간 | Phase B까지 양쪽 유지 |
| 채널 역할 미설정 silent failure | 낮음 | 문서화 + 로그 |
| 부분 기록 | 낮음 | atomic write |

---

## 작업 순서

### Phase A — 설정 스키마 정의 (사전 조건 없음)

1. **A1**: `config/channels.json` 생성
   - 완료 기준: 파일 존재, `C0985UXQN6Q`가 `roles: ["monitor", "chatbot"]` + `project_id: "secretary"` 로 등록됨

2. **A2**: `config/gateway.json`에 `_channel_source` 마킹 추가
   - 완료 기준: JSON 파싱 오류 없음, Gateway 서버 정상 시작

### Phase B — 레지스트리 클래스 + 코드 연동 (A1 완료 후)

3. **B1**: `scripts/gateway/channel_registry.py` 구현
   - 완료 기준: `get_by_role("monitor")` 반환값 정확, 단위 테스트 통과

4. **B2**: `scripts/gateway/server.py` 수정
   - 완료 기준: 레지스트리 기반 채널 로드 동작, 기존 테스트 통과

5. **B3**: `scripts/gateway/project_context.py` 수정
   - 완료 기준: 레지스트리 우선 매칭 적용, 기존 테스트 통과

### Phase C — 정합성 정리 (B 전체 완료 후)

6. **C1**: `config/projects.json` deprecation 마킹
   - 완료 기준: `_deprecated_slack_channels_note` 필드 추가, JSON 유효

7. **C2**: `server.py interactive_slack_channel_select()` 레지스트리 저장 연동
   - 완료 기준: 대화형 채널 선택 시 `channels.json`에 항목 자동 추가, atomic write 적용

---

## 하위 호환 보장 체크리스트

- [ ] `channels.json` 미존재 시 기존 `gateway.json` 기반 동작 유지
- [ ] `ChannelRegistry` 주입 안 된 `ProjectContextResolver`는 `projects.json` 전용 동작
- [ ] `gateway.json intelligence.chatbot_channels` 값은 Phase B 완료 전까지 유효
- [ ] 기존 테스트 (`test_pipeline.py`, `test_project_context.py`) 무수정 통과
