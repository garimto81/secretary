# Channel Architecture 기술 설계 문서

**연관 계획**: `docs/01-plan/channel-architecture.plan.md`
**작성일**: 2026-02-18
**상태**: 설계 완료

---

## 1. 아키텍처 다이어그램

### 1.1 현재 구조 (3곳 분산)

```
채널 ID "C0985UXQN6Q"가 3개 위치에 독립적으로 하드코딩됨

config/gateway.json
├── channels.slack.channels: ["C0985UXQN6Q"]      ← Gateway 수신 감시 대상
└── intelligence.chatbot_channels: ["C0985UXQN6Q"] ← Chatbot 분기 판단

config/projects.json
└── projects[secretary].slack_channels: ["C0985UXQN6Q"] ← 채널→프로젝트 매핑

┌─────────────────────────────────────────────────┐
│  server.py                                      │
│  _connect_adapters():                           │
│    channels_config["slack"]["channels"]  ──────►│ SlackAdapter 생성
│  _register_intelligence_handler():             │
│    intel_config["chatbot_channels"]  ──────────►│ handler에 주입
├─────────────────────────────────────────────────┤
│  project_context.py                             │
│  resolve():                                     │
│    project["slack_channels"]  ─────────────────►│ 채널→프로젝트 매핑
├─────────────────────────────────────────────────┤
│  response/handler.py                            │
│  _is_chatbot_channel():                         │
│    self._chatbot_channels  ────────────────────►│ Chatbot 여부 판단
└─────────────────────────────────────────────────┘

문제: 새 채널 추가 시 3개 파일을 동시에 수정해야 함
```

### 1.2 목표 구조 (ChannelRegistry 중심)

```
config/channels.json (단일 진실의 원천)
└── channels[]:
    ├── id, name, type
    ├── roles: [monitor, chatbot, project-bound]
    ├── project_id
    └── enabled

          ↓ load()

scripts/gateway/channel_registry.py
┌─────────────────────────────────┐
│       ChannelRegistry           │
│  get_by_role("monitor")  ──────►│ ["C0985UXQN6Q"]
│  get_by_role("chatbot")  ──────►│ ["C0985UXQN6Q"]
│  get_project_id(channel_id) ───►│ "secretary"
│  is_enabled(channel_id)  ──────►│ True
└─────────────────────────────────┘
          ↓ 주입

┌─────────────────────────────────────────────────┐
│  server.py                                      │
│  _connect_adapters():                           │
│    registry.get_by_role("monitor", "slack")  ──►│ SlackAdapter 생성
│    폴백: gateway.json channels.slack.channels   │
│  _register_intelligence_handler():             │
│    registry.get_by_role("chatbot")  ───────────►│ handler에 주입
│    폴백: intel_config["chatbot_channels"]       │
├─────────────────────────────────────────────────┤
│  project_context.py                             │
│  resolve() (레지스트리 주입 시):               │
│    registry.get_project_id(channel_id)  ───────►│ 채널→프로젝트 (우선)
│    폴백: project["slack_channels"]             │
├─────────────────────────────────────────────────┤
│  response/handler.py (변경 없음)               │
│  _is_chatbot_channel():                         │
│    self._chatbot_channels (server.py가 주입)   │
└─────────────────────────────────────────────────┘

장점: 새 채널 추가 시 channels.json만 수정
```

### 1.3 데이터 흐름 요약

```
channels.json
    ↓ ChannelRegistry.load()
ChannelRegistry (메모리 캐시)
    ├── server.py._connect_adapters() ──► SlackAdapter(config with channel_ids)
    ├── server.py._register_intelligence_handler() ──► ProjectIntelligenceHandler(chatbot_channels)
    └── project_context.py.resolve() ──► project_id (Slack 채널 우선 매칭)
```

---

## 2. channels.json 스키마 상세

### 2.1 파일 위치

```
C:\claude\secretary\config\channels.json
```

### 2.2 전체 스키마

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

### 2.3 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|:----:|------|
| `id` | string | O | 채널 고유 식별자. Slack의 경우 `C`로 시작하는 채널 ID |
| `name` | string | X | 사람이 읽기 쉬운 채널 이름 (예: "general") |
| `type` | string | O | 채널 유형. 현재 지원: `"slack"`, `"gmail"` |
| `roles` | string[] | O | 채널에 부여된 역할 목록. 하나 이상 필수 |
| `project_id` | string | X | 연관 프로젝트 ID. `project-bound` 역할에서 필수 |
| `enabled` | boolean | O | 채널 활성화 여부. `false`면 레지스트리 조회에서 제외 |

### 2.4 roles 값 정의

| 역할 | 대체 대상 | 설명 |
|------|----------|------|
| `monitor` | `gateway.json channels.slack.channels` | Gateway 어댑터가 이 채널의 메시지를 수신 감시. `get_by_role("monitor")`로 조회됨 |
| `chatbot` | `gateway.json intelligence.chatbot_channels` | Intelligence handler가 이 채널 메시지를 Chatbot 경로로 처리 (Ollama 직접 응답). `get_by_role("chatbot")`로 조회됨 |
| `project-bound` | `projects.json slack_channels` | 채널 ID → `project_id` 매핑을 레지스트리가 관리. `project_id` 필드가 유효한 경우에만 의미 있음 |

**역할 조합 규칙:**
- `monitor`만: 메시지 수신하되 Chatbot 응답 없음, 프로젝트 Intelligence 처리
- `monitor + chatbot`: 메시지 수신 + Chatbot 직접 응답 (Intelligence 분석 건너뜀)
- `monitor + project-bound`: 메시지 수신 + 특정 프로젝트로 자동 매핑
- `monitor + chatbot + project-bound`: 위 모두 (현재 `C0985UXQN6Q` 역할)

### 2.5 유효성 검증 규칙

`ChannelRegistry.load()` 내에서 각 채널 항목을 로드할 때 검증:

1. `id` 필드가 존재하고 비어있지 않아야 함 → 없으면 해당 항목 건너뜀, WARNING 로그
2. `type` 필드가 존재하고 `"slack"` 또는 `"gmail"` 중 하나여야 함 → 없으면 해당 항목 건너뜀
3. `roles` 필드가 존재하고 리스트여야 함 → 없거나 리스트가 아니면 해당 항목 건너뜀
4. `enabled` 필드가 `true`인 항목만 활성 레지스트리에 등록
5. `project-bound` 역할 부여 시 `project_id` 필드 존재 여부 확인 → 없으면 WARNING 로그 (등록은 허용)

---

## 3. ChannelRegistry 클래스 API 상세

### 3.1 파일 위치

```
C:\claude\secretary\scripts\gateway\channel_registry.py
```

### 3.2 3중 import fallback 패턴

```python
# 프로젝트 루트에서 실행 시
try:
    from scripts.gateway.channel_registry import ChannelRegistry
except ImportError:
    # scripts/ 내에서 실행 시
    try:
        from gateway.channel_registry import ChannelRegistry
    except ImportError:
        # 패키지 내부 import
        from .channel_registry import ChannelRegistry
```

### 3.3 전체 클래스 구조

```python
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import logging

logger = logging.getLogger(__name__)

_DEFAULT_CHANNELS_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "channels.json"
)


class ChannelRegistry:
    """
    config/channels.json 로드 및 역할 기반 조회를 제공하는 단일 채널 레지스트리.

    channels.json 미존재 또는 파싱 오류 시 빈 레지스트리로 초기화되며,
    호출부에서 기존 config로 폴백하도록 설계됨.
    """

    def __init__(self):
        self._channels: List[Dict[str, Any]] = []
        self._loaded: bool = False

    def load(self, path: Optional[Path] = None) -> bool:
        """
        channels.json 로드. 성공 시 True, 실패 시 False 반환.

        Args:
            path: channels.json 파일 경로. None이면 기본 경로 사용.

        Returns:
            bool: 로드 성공 여부

        동작:
            - 파일 미존재: WARNING 로그 + False 반환 (예외 발생하지 않음)
            - JSON 파싱 오류: WARNING 로그 + False 반환 (예외 발생하지 않음)
            - 유효하지 않은 항목: 개별 항목 건너뜀, 나머지는 로드
        """
        ...

    def get_by_role(self, role: str, channel_type: str = "slack") -> List[str]:
        """
        특정 role과 type이 부여된 활성화 채널 ID 목록 반환.

        Args:
            role: 조회할 역할 ("monitor", "chatbot", "project-bound")
            channel_type: 채널 유형 ("slack", "gmail"). 기본값: "slack"

        Returns:
            List[str]: 조건을 만족하는 채널 ID 목록 (enabled=true만 포함)

        예시:
            >>> registry.get_by_role("monitor")
            ["C0985UXQN6Q"]
            >>> registry.get_by_role("chatbot", "slack")
            ["C0985UXQN6Q"]
            >>> registry.get_by_role("monitor", "gmail")
            []
        """
        ...

    def get_project_id(self, channel_id: str) -> Optional[str]:
        """
        채널 ID에 매핑된 project_id 반환.
        project-bound 역할이 없거나 project_id 미설정 시 None 반환.

        Args:
            channel_id: 조회할 채널 ID

        Returns:
            Optional[str]: project_id 또는 None

        예시:
            >>> registry.get_project_id("C0985UXQN6Q")
            "secretary"
            >>> registry.get_project_id("C_UNKNOWN")
            None
        """
        ...

    def is_enabled(self, channel_id: str) -> bool:
        """
        채널 ID의 enabled 상태 반환.

        Args:
            channel_id: 조회할 채널 ID

        Returns:
            bool: 채널이 존재하고 enabled=true이면 True, 그 외 False

        예시:
            >>> registry.is_enabled("C0985UXQN6Q")
            True
            >>> registry.is_enabled("C_NOT_REGISTERED")
            False
        """
        ...

    def is_loaded(self) -> bool:
        """레지스트리가 성공적으로 로드되었는지 여부."""
        return self._loaded
```

### 3.4 load() 실패 시 폴백 동작

`load()` 반환값으로 성공/실패를 판단하여 호출부(server.py)에서 폴백:

```python
# server.py 내부 (Phase B2 적용 후)
registry = ChannelRegistry()
channels_json_path = Path(r"C:\claude\secretary\config\channels.json")

if registry.load(channels_json_path):
    # 레지스트리 기반 조회
    monitor_channels = registry.get_by_role("monitor", "slack")
else:
    # 폴백: gateway.json 원본 사용
    logger.warning("ChannelRegistry 로드 실패, gateway.json 채널 사용")
    monitor_channels = channels_config.get("slack", {}).get("channels", [])
```

---

## 4. 코드 변경 상세

### 4.1 server.py — `_connect_adapters()` 변경

**변경 위치**: `scripts/gateway/server.py` 라인 254-282

**Before:**
```python
async def _connect_adapters(self) -> None:
    """설정된 어댑터 연결"""
    channels_config = self.config.get("channels", {})

    # 자동 어댑터 생성 (Slack, Gmail)
    for channel_name, channel_config in channels_config.items():
        if not channel_config.get("enabled", False):
            continue

        if channel_name not in self.adapters:
            adapter = self._create_adapter(channel_name, channel_config)
            if adapter:
                self.adapters[channel_name] = adapter

    # 어댑터 연결
    for channel_name in list(self.adapters.keys()):
        channel_config = channels_config.get(channel_name, {})
        if not channel_config.get("enabled", False):
            continue

        adapter = self.adapters[channel_name]
        success = await adapter.connect()
        if success:
            print(f"  - {channel_name} 어댑터 연결 성공")
        else:
            print(f"  - {channel_name} 어댑터 연결 실패")

    # Intelligence 핸들러 등록
    await self._register_intelligence_handler()
```

**After:**
```python
async def _connect_adapters(self) -> None:
    """설정된 어댑터 연결"""
    channels_config = self.config.get("channels", {})

    # ChannelRegistry 로드 (channels.json 존재 시)
    self._channel_registry = None
    try:
        try:
            from scripts.gateway.channel_registry import ChannelRegistry
        except ImportError:
            try:
                from gateway.channel_registry import ChannelRegistry
            except ImportError:
                from .channel_registry import ChannelRegistry

        channels_json_path = Path(__file__).resolve().parent.parent.parent / "config" / "channels.json"
        registry = ChannelRegistry()
        if registry.load(channels_json_path):
            self._channel_registry = registry
            print(f"  - ChannelRegistry 로드 완료")
        else:
            print(f"  - ChannelRegistry 미적용 (channels.json 없음 또는 오류), gateway.json 사용")
    except ImportError:
        pass

    # 레지스트리가 있으면 monitor 채널 목록을 주입
    if self._channel_registry:
        slack_config = channels_config.get("slack", {})
        if slack_config.get("enabled", False):
            monitor_channels = self._channel_registry.get_by_role("monitor", "slack")
            if monitor_channels:
                slack_config = dict(slack_config)
                slack_config["channels"] = monitor_channels
                channels_config = dict(channels_config)
                channels_config["slack"] = slack_config

    # 자동 어댑터 생성 (Slack, Gmail)
    for channel_name, channel_config in channels_config.items():
        if not channel_config.get("enabled", False):
            continue

        if channel_name not in self.adapters:
            adapter = self._create_adapter(channel_name, channel_config)
            if adapter:
                self.adapters[channel_name] = adapter

    # 어댑터 연결
    for channel_name in list(self.adapters.keys()):
        channel_config = channels_config.get(channel_name, {})
        if not channel_config.get("enabled", False):
            continue

        adapter = self.adapters[channel_name]
        success = await adapter.connect()
        if success:
            print(f"  - {channel_name} 어댑터 연결 성공")
        else:
            print(f"  - {channel_name} 어댑터 연결 실패")

    # Intelligence 핸들러 등록
    await self._register_intelligence_handler()
```

### 4.2 server.py — `_register_intelligence_handler()` 변경

**변경 위치**: `scripts/gateway/server.py` 라인 307-381

**Before (핵심 부분):**
```python
async def _register_intelligence_handler(self) -> None:
    """Project Intelligence 핸들러를 파이프라인에 등록"""
    ...
    intel_config = self.config.get("intelligence", {})
    ...
    chatbot_channels = intel_config.get("chatbot_channels", [])

    handler = ProjectIntelligenceHandler(
        storage=intel_storage,
        registry=registry,
        ollama_config=ollama_config,
        claude_config=claude_config,
        chatbot_channels=chatbot_channels,
    )
    ...
```

**After (핵심 부분):**
```python
async def _register_intelligence_handler(self) -> None:
    """Project Intelligence 핸들러를 파이프라인에 등록"""
    ...
    intel_config = self.config.get("intelligence", {})
    ...
    # 레지스트리 우선 조회, 없으면 gateway.json 폴백
    if self._channel_registry is not None:
        chatbot_channels = self._channel_registry.get_by_role("chatbot", "slack")
        if not chatbot_channels:
            # 레지스트리에 chatbot 역할 없으면 기존 설정 폴백
            chatbot_channels = intel_config.get("chatbot_channels", [])
    else:
        chatbot_channels = intel_config.get("chatbot_channels", [])

    handler = ProjectIntelligenceHandler(
        storage=intel_storage,
        registry=registry,
        ollama_config=ollama_config,
        claude_config=claude_config,
        chatbot_channels=chatbot_channels,
    )
    ...
```

### 4.3 project_context.py — `__init__()` 변경

**변경 위치**: `scripts/gateway/project_context.py` 라인 51-55

**Before:**
```python
class ProjectContextResolver:
    """Stage 0.5: 메시지 → 프로젝트 매핑 및 컨텍스트 반환"""

    def __init__(self, projects_config_path: Optional[Path] = None):
        config_path = projects_config_path or _DEFAULT_CONFIG_PATH
        self._projects: List[Dict[str, Any]] = []
        self._contexts: Dict[str, ProjectContext] = {}
        self._load(config_path)
```

**After:**
```python
class ProjectContextResolver:
    """Stage 0.5: 메시지 → 프로젝트 매핑 및 컨텍스트 반환"""

    def __init__(
        self,
        projects_config_path: Optional[Path] = None,
        channel_registry=None,  # Optional[ChannelRegistry]
    ):
        config_path = projects_config_path or _DEFAULT_CONFIG_PATH
        self._projects: List[Dict[str, Any]] = []
        self._contexts: Dict[str, ProjectContext] = {}
        self._channel_registry = channel_registry  # ChannelRegistry 주입 (없으면 None)
        self._load(config_path)
```

### 4.4 project_context.py — `resolve()` 변경

**변경 위치**: `scripts/gateway/project_context.py` 라인 83-111

**Before:**
```python
def resolve(self, message: NormalizedMessage) -> Optional[str]:
    """메시지에서 project_id 결정. 순서: Slack 채널 → Email 패턴 → 키워드"""
    for project in self._projects:
        pid = project.get("id", "")
        if not pid:
            continue

        # 1. Slack 채널 매칭
        if message.channel == ChannelType.SLACK:
            slack_channels = project.get("slack_channels", [])
            if message.channel_id in slack_channels:
                logger.debug("Resolved project '%s' via Slack channel", pid)
                return pid

        # 2. Email sender/subject/text 패턴 매칭
        if message.channel == ChannelType.EMAIL:
            gmail_queries = project.get("gmail_queries", [])
            if gmail_queries and self._match_email(message, gmail_queries):
                logger.debug("Resolved project '%s' via email pattern", pid)
                return pid

        # 3. 키워드 매칭 (텍스트)
        keywords = project.get("keywords", [])
        if keywords and self._match_keywords(message.text or "", keywords):
            logger.debug("Resolved project '%s' via keyword match", pid)
            return pid

    logger.debug("No project resolved for message %s", message.id)
    return None
```

**After:**
```python
def resolve(self, message: NormalizedMessage) -> Optional[str]:
    """메시지에서 project_id 결정.
    순서: 레지스트리(Slack) → projects.json Slack 채널 → Email 패턴 → 키워드
    """
    # 0. 레지스트리 기반 Slack 채널 매핑 (주입된 경우 우선 적용)
    if (
        self._channel_registry is not None
        and message.channel == ChannelType.SLACK
        and message.channel_id
    ):
        pid = self._channel_registry.get_project_id(message.channel_id)
        if pid:
            logger.debug(
                "Resolved project '%s' via ChannelRegistry (channel_id=%s)",
                pid, message.channel_id,
            )
            return pid

    for project in self._projects:
        pid = project.get("id", "")
        if not pid:
            continue

        # 1. Slack 채널 매칭 (projects.json 기반)
        if message.channel == ChannelType.SLACK:
            slack_channels = project.get("slack_channels", [])
            if message.channel_id in slack_channels:
                logger.debug("Resolved project '%s' via Slack channel", pid)
                return pid

        # 2. Email sender/subject/text 패턴 매칭
        if message.channel == ChannelType.EMAIL:
            gmail_queries = project.get("gmail_queries", [])
            if gmail_queries and self._match_email(message, gmail_queries):
                logger.debug("Resolved project '%s' via email pattern", pid)
                return pid

        # 3. 키워드 매칭 (텍스트)
        keywords = project.get("keywords", [])
        if keywords and self._match_keywords(message.text or "", keywords):
            logger.debug("Resolved project '%s' via keyword match", pid)
            return pid

    logger.debug("No project resolved for message %s", message.id)
    return None
```

---

## 5. 폴백 전략 상세

### 5.1 channels.json 미존재

```
상황: config/channels.json 파일이 없음

ChannelRegistry.load() → False 반환 + WARNING 로그

server.py:
  self._channel_registry = None (레지스트리 미적용 상태 유지)
  _connect_adapters(): channels_config["slack"]["channels"] 원본 사용
  _register_intelligence_handler(): intel_config["chatbot_channels"] 원본 사용

project_context.py:
  resolve(): 레지스트리 단계 건너뜀, projects.json slack_channels 기반 매칭

결과: 기존 동작과 완전히 동일
```

### 5.2 JSON 파싱 오류

```
상황: channels.json이 존재하나 JSON 형식 오류

ChannelRegistry.load():
  except json.JSONDecodeError:
      logger.warning("channels.json 파싱 오류: %s", e)
      return False

이후 동작: 5.1과 동일 (gateway.json 원본 사용)
```

### 5.3 레지스트리 빈 결과

```
상황: channels.json은 유효하나 해당 역할의 채널이 없음

server.py._connect_adapters():
  monitor_channels = registry.get_by_role("monitor", "slack")
  if monitor_channels:      # 빈 리스트면 이 블록 건너뜀
      slack_config["channels"] = monitor_channels
  # 빈 결과 → slack_config 원본(channels.slack.channels) 그대로 사용

server.py._register_intelligence_handler():
  chatbot_channels = registry.get_by_role("chatbot", "slack")
  if not chatbot_channels:  # 빈 결과 → 폴백
      chatbot_channels = intel_config.get("chatbot_channels", [])
```

### 5.4 폴백 전략 요약

| 실패 시나리오 | 폴백 동작 | 로그 수준 |
|-------------|----------|---------|
| channels.json 미존재 | gateway.json 원본 사용 | WARNING |
| JSON 파싱 오류 | gateway.json 원본 사용 | WARNING |
| 레지스트리 로드 성공 + 빈 역할 결과 | gateway.json 원본 사용 | DEBUG |
| ChannelRegistry import 실패 | registry=None, 기존 동작 | WARNING |

---

## 6. 테스트 전략

### 6.1 신규 테스트: `tests/gateway/test_channel_registry.py`

```
위치: C:\claude\secretary\tests\gateway\test_channel_registry.py
```

필요한 테스트 케이스 목록:

#### ChannelRegistry.load() 테스트

| 케이스 ID | 설명 | 입력 | 기대 결과 |
|----------|------|------|---------|
| `test_load_valid_channels_json` | 정상 파일 로드 | 유효한 channels.json | True 반환, `_loaded=True` |
| `test_load_file_not_found` | 파일 미존재 | 존재하지 않는 경로 | False 반환, 예외 발생하지 않음 |
| `test_load_invalid_json` | JSON 파싱 오류 | 비정상 JSON 내용 | False 반환, 예외 발생하지 않음 |
| `test_load_missing_required_field` | 필수 필드 누락 항목 | id 없는 채널 포함 | False 아닌 True, 누락 항목만 건너뜀 |
| `test_load_disabled_channel_excluded` | enabled=false 채널 | enabled=false 항목 | 조회 결과에 포함되지 않음 |

#### ChannelRegistry.get_by_role() 테스트

| 케이스 ID | 설명 | 입력 | 기대 결과 |
|----------|------|------|---------|
| `test_get_by_role_monitor` | monitor 역할 조회 | role="monitor", type="slack" | `["C0985UXQN6Q"]` |
| `test_get_by_role_chatbot` | chatbot 역할 조회 | role="chatbot", type="slack" | `["C0985UXQN6Q"]` |
| `test_get_by_role_unknown` | 없는 역할 조회 | role="unknown" | `[]` |
| `test_get_by_role_type_filter` | 타입 필터 동작 | role="monitor", type="gmail" | `[]` (slack만 등록된 경우) |
| `test_get_by_role_empty_registry` | 빈 레지스트리 | 로드 전 상태 | `[]` |

#### ChannelRegistry.get_project_id() 테스트

| 케이스 ID | 설명 | 입력 | 기대 결과 |
|----------|------|------|---------|
| `test_get_project_id_known_channel` | 알려진 채널 조회 | `"C0985UXQN6Q"` | `"secretary"` |
| `test_get_project_id_unknown_channel` | 미등록 채널 조회 | `"C_UNKNOWN"` | `None` |
| `test_get_project_id_no_project_id_field` | project_id 미설정 채널 | project_id 없는 항목 | `None` |

#### ChannelRegistry.is_enabled() 테스트

| 케이스 ID | 설명 | 입력 | 기대 결과 |
|----------|------|------|---------|
| `test_is_enabled_registered_channel` | 등록된 활성 채널 | `"C0985UXQN6Q"` | `True` |
| `test_is_enabled_unregistered_channel` | 미등록 채널 | `"C_UNKNOWN"` | `False` |

#### 통합 테스트 (channels.json fixture 사용)

| 케이스 ID | 설명 |
|----------|------|
| `test_full_load_and_query` | tmp_path에 channels.json 생성 후 전체 API 검증 |
| `test_multiple_roles_per_channel` | 하나의 채널에 여러 역할 부여 시 각 역할 조회 정상 동작 |

### 6.2 기존 테스트 영향 분석

| 테스트 파일 | 영향 | 수정 필요 여부 |
|------------|------|:----------:|
| `tests/gateway/test_pipeline.py` | `_connect_adapters()` 변경 없음 (pipeline 테스트만). server.py 직접 테스트 없음 | X |
| `tests/gateway/test_project_context.py` | `ProjectContextResolver.__init__()`에 `channel_registry=None` 파라미터 추가됨. 기존 호출 `ProjectContextResolver()` 형태 유지되므로 무변경 통과 | X |
| `tests/gateway/test_models.py` | 모델 변경 없음 | X |
| `tests/test_action_dispatcher.py` | 채널 레지스트리 무관 | X |
| `tests/test_gateway_storage.py` | 스토리지 변경 없음 | X |

**결론**: 기존 테스트 파일 수정 없이 모두 통과 예상.

---

## 7. 구현 체크리스트

### Phase A — config 변경

- [ ] `config/channels.json` 생성 (`C0985UXQN6Q` monitor + chatbot + project-bound)
- [ ] `config/gateway.json`에 `_channel_source: "channels.json"` 마킹

### Phase B — 레지스트리 구현 + 연동

- [ ] `scripts/gateway/channel_registry.py` 구현 (load, get_by_role, get_project_id, is_enabled)
- [ ] `scripts/gateway/server.py` 수정 (`_connect_adapters` + `_register_intelligence_handler`)
- [ ] `scripts/gateway/project_context.py` 수정 (`__init__` registry 파라미터 + `resolve` 레지스트리 우선)
- [ ] `tests/gateway/test_channel_registry.py` 작성

### Phase C — 정합성 정리

- [ ] `config/projects.json`에 `_deprecated_slack_channels_note` 추가
- [ ] `interactive_slack_channel_select()` → `_save_to_registry()` 추가 (atomic write)

---

## 8. 참조 파일

| 파일 | 역할 |
|------|------|
| `docs/01-plan/channel-architecture.plan.md` | 원본 계획 |
| `config/gateway.json` | 현재 채널/Intelligence 설정 |
| `config/projects.json` | 현재 프로젝트-채널 매핑 |
| `scripts/gateway/server.py` | 변경 대상 (B2) |
| `scripts/gateway/project_context.py` | 변경 대상 (B3) |
| `scripts/intelligence/response/handler.py` | 변경 없음 (chatbot_channels 목록만 서버에서 주입) |
| `scripts/gateway/adapters/base.py` | 변경 없음 (추상 인터페이스) |
