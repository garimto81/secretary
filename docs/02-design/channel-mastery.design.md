# Channel Mastery 기술 설계

**PRD 참조**: docs/prd/channel-mastery.prd.md
**Plan 참조**: docs/01-plan/channel-mastery.plan.md
**작성일**: 2026-02-18
**상태**: Draft

---

## 1. 개선된 아키텍처 다이어그램

```
config/gateway.json
    │
    ├── channels.slack.adapter → importlib 동적 로드
    ├── channels.gmail.adapter → importlib 동적 로드
    └── channels.github.adapter → importlib 동적 로드

SecretaryGateway (server.py)
    ├── PluginAdapterRegistry (신규)
    │   ├── discover(channel_name, config) → ChannelAdapter
    │   └── 기존 이름 기반 매핑 fallback
    │
    ├── AdapterHealthMonitor (신규)
    │   ├── record_message(channel_name)
    │   ├── record_error(channel_name, error)
    │   └── get_health(channel_name) → HealthMetrics
    │
    ├── AdapterSupervisor (신규)
    │   ├── _listen_with_retry(adapter) → 재연결 루프
    │   └── backoff: 5, 10, 20, 40, 80, 160, 300초
    │
    └── MessagePipeline (기존)
        └── Stage 0.5~6 유지

어댑터 계층:
    ChannelAdapter (base.py)
    ├── get_health() 추상 메서드 추가
    ├── SlackAdapter (slack.py) → 재연결 로직 추가
    ├── GmailAdapter (gmail.py) → seen_ids 슬라이딩 윈도우
    └── GitHubAdapter (github.py) → 신규 구현
```

---

## 2. 파일 변경 요약

| 파일 | 변경 유형 | 내용 |
|------|:---------:|------|
| `scripts/gateway/adapters/base.py` | 수정 | `get_health()` 추상 메서드, `HealthMetrics` dataclass 추가 |
| `scripts/gateway/adapters/slack.py` | 수정 | 재연결 로직, health 지표 수집 |
| `scripts/gateway/adapters/gmail.py` | 수정 | 슬라이딩 윈도우 seen_ids, 재연결 로직, health 지표 |
| `scripts/gateway/adapters/github.py` | 신규 | `GitHubAdapter` 전체 구현 |
| `scripts/gateway/server.py` | 수정 | `PluginAdapterRegistry`, `AdapterSupervisor`, `AdapterHealthMonitor` |
| `config/gateway.json` | 수정 | `github` 채널 설정 섹션 추가, `adapter` 필드 예시 |
| `tests/gateway/test_slack_adapter.py` | 신규 | SlackAdapter E2E mock 테스트 |
| `tests/gateway/test_gmail_adapter.py` | 신규 | GmailAdapter E2E mock 테스트 |
| `tests/gateway/test_github_adapter.py` | 신규 | GitHubAdapter E2E mock 테스트 |

---

## 3. HealthMetrics dataclass

```python
@dataclass
class HealthMetrics:
    channel_name: str
    connected: bool
    messages_received: int = 0
    errors_count: int = 0
    last_message_at: Optional[datetime] = None
    last_error: Optional[str] = None
    reconnect_count: int = 0
    uptime_seconds: float = 0.0
    started_at: Optional[datetime] = None
```

저장 방식: 메모리 기반 (DB 저장 불필요, 재시작 시 초기화)

---

## 4. AdapterSupervisor 재연결 전략

```python
BACKOFF_SCHEDULE = [5, 10, 20, 40, 80, 160, 300]  # 초 단위
MAX_RETRIES = 10

async def _listen_with_retry(self, adapter: ChannelAdapter) -> None:
    retries = 0
    while self._running and retries < MAX_RETRIES:
        try:
            async for message in adapter.listen():
                ...
        except Exception as e:
            retries += 1
            wait = BACKOFF_SCHEDULE[min(retries - 1, len(BACKOFF_SCHEDULE) - 1)]
            # 재연결 시도
            await asyncio.sleep(wait)
            await adapter.connect()
```

MAX_RETRIES=10 초과 시 어댑터를 disabled 상태로 전환하고 `[CRITICAL]` 로그 기록.

---

## 5. FR-01: GitHubAdapter 인터페이스

```python
class GitHubAdapter(ChannelAdapter):
    def __init__(self, config: dict):
        super().__init__(config)
        self.channel_type = ChannelType.GITHUB
        self._token_path = Path(r"C:\claude\json\github_token.txt")
        self._polling_interval: int = config.get("polling_interval", 60)
        self._repos: list = config.get("repos", [])  # ["owner/repo", ...]
```

- `channel_id = "issues"` — Issues 이벤트
- `channel_id = "pulls"` — PR 이벤트, `is_mention = True` (리뷰 요청 시)
- polling 간격 기본값 60초, etag/since 기반 증분 조회
- 401 응답 시 즉시 재연결 중단, 토큰 갱신 안내 로그 출력

---

## 6. FR-04: gateway.json 플러그인 설정 예시

```json
{
  "channels": {
    "slack": {
      "enabled": true,
      "adapter": "scripts.gateway.adapters.slack.SlackAdapter"
    },
    "gmail": {
      "enabled": true,
      "adapter": "scripts.gateway.adapters.gmail.GmailAdapter"
    },
    "github": {
      "enabled": true,
      "adapter": "scripts.gateway.adapters.github.GitHubAdapter",
      "polling_interval": 60,
      "repos": ["owner/repo"]
    }
  }
}
```

`adapter` 필드 미지정 시 기존 이름 기반 매핑(`slack` → `SlackAdapter`)으로 fallback.

---

## 7. FR-04: importlib 동적 로드 패턴

```python
import importlib

def _load_adapter_class(self, class_path: str):
    """
    "scripts.gateway.adapters.github.GitHubAdapter" 형식의 경로를
    실제 클래스로 동적 로드한다.
    """
    module_path, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
```

잘못된 경로 지정 시 명확한 에러 메시지 출력 후 서버 시작 중단.
Registry 초기화 시 중복 채널 이름 감지 시 경고 로그 출력.
