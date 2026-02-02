# Secretary Phase 4: Multi-Channel Messaging Integration Plan

**Version**: 1.0.0
**Created**: 2026-02-02
**Status**: DRAFT
**Reference**: OpenClaw Architecture Study

---

## 1. Vision and Goals

### 1.1 Project Vision

Secretary를 단순한 일일 리포트 도구에서 **실시간 멀티채널 AI 비서**로 진화시킨다. OpenClaw의 Gateway/WebSocket 아키텍처를 참고하되, Python 기반을 유지하면서 Secretary의 기존 강점(분석 + 자동화 액션)을 결합한다.

### 1.2 Core Goals

| Goal | Description | Success Metric |
|------|-------------|----------------|
| **Real-time Reception** | 5개 이상 메시징 채널 실시간 수신 | 메시지 지연 < 5초 |
| **Unified Pipeline** | 단일 메시지 처리 파이프라인 | 1개 코드 경로로 모든 채널 처리 |
| **Bidirectional** | 수신 + 응답 전송 (안전 장치 포함) | 응답 초안 생성 후 확인 필수 |
| **Preserve Safety** | 자동 전송 금지 규칙 유지 | 모든 전송에 명시적 확인 필요 |
| **Python Native** | TypeScript 전환 없이 Python 유지 | 100% Python 구현 |

### 1.3 Non-Goals (Phase 4에서 제외)

- Multi-agent 병렬 처리 (Phase 5 후보)
- 음성/영상 통화 지원
- End-to-end 암호화 구현 (채널 자체 암호화 의존)
- 대규모 그룹 관리 (1:1 및 소규모 그룹 우선)

---

## 2. Architecture Design

### 2.1 High-Level Architecture

```
                    ┌─────────────────────────────────────────────────────────────┐
                    │                     Secretary Gateway                        │
                    │                    (Python asyncio)                          │
                    └─────────────────────────────────────────────────────────────┘
                                              │
                ┌─────────────────────────────┼─────────────────────────────┐
                │                             │                             │
                ▼                             ▼                             ▼
    ┌───────────────────┐       ┌───────────────────┐       ┌───────────────────┐
    │  Channel Adapters │       │  Message Pipeline │       │  Action Handlers  │
    │   (Inbound/Out)   │       │   (Unified)       │       │   (Phase 3)       │
    └───────────────────┘       └───────────────────┘       └───────────────────┘
              │                           │                           │
    ┌─────────┴─────────┐       ┌─────────┴─────────┐       ┌─────────┴─────────┐
    │ WhatsApp Adapter  │       │ Message Normalizer│       │ Toast Notifier    │
    │ Telegram Adapter  │       │ Priority Analyzer │       │ TODO Generator    │
    │ Discord Adapter   │       │ Context Enricher  │       │ Calendar Creator  │
    │ Slack Adapter     │       │ Action Dispatcher │       │ Response Drafter  │
    │ KakaoTalk Adapter │       │ Response Router   │       │ [New] Message     │
    │ [Android Push]    │       └───────────────────┘       │       Sender      │
    └───────────────────┘                                   └───────────────────┘
              │
              ▼
    ┌───────────────────┐
    │   SQLite Storage  │
    │  (Unified Schema) │
    └───────────────────┘
```

### 2.2 Component Design

#### 2.2.1 Gateway Server (Core)

```python
# scripts/gateway/server.py
class SecretaryGateway:
    """
    Central WebSocket/HTTP server managing all channel connections.
    Based on asyncio for concurrent channel handling.
    """

    def __init__(self, config: GatewayConfig):
        self.adapters: Dict[str, ChannelAdapter] = {}
        self.pipeline: MessagePipeline = MessagePipeline()
        self.storage: UnifiedStorage = UnifiedStorage()
        self.action_handlers: ActionRegistry = ActionRegistry()

    async def start(self):
        """Start all channel adapters and HTTP server"""
        pass

    async def handle_message(self, message: NormalizedMessage):
        """Unified message processing"""
        pass
```

#### 2.2.2 Channel Adapter Interface

```python
# scripts/gateway/adapters/base.py
from abc import ABC, abstractmethod
from typing import AsyncIterator

class ChannelAdapter(ABC):
    """Base interface for all messaging channel adapters"""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the messaging platform"""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Clean disconnect from platform"""
        pass

    @abstractmethod
    async def listen(self) -> AsyncIterator[RawMessage]:
        """Async generator yielding incoming messages"""
        pass

    @abstractmethod
    async def send(self, message: OutboundMessage) -> SendResult:
        """Send a message (requires explicit confirmation)"""
        pass

    @abstractmethod
    def normalize(self, raw: RawMessage) -> NormalizedMessage:
        """Convert platform-specific message to unified format"""
        pass
```

#### 2.2.3 Normalized Message Schema

```python
# scripts/gateway/models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class ChannelType(Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    KAKAOTALK = "kakaotalk"
    ANDROID_PUSH = "android_push"
    EMAIL = "email"  # Gmail integration

class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    REACTION = "reaction"
    SYSTEM = "system"

@dataclass
class NormalizedMessage:
    """Platform-agnostic message format"""
    id: str
    channel: ChannelType
    channel_id: str  # Platform-specific chat/conversation ID
    sender_id: str
    sender_name: Optional[str]
    text: str
    message_type: MessageType
    timestamp: datetime
    is_group: bool
    is_mention: bool
    reply_to_id: Optional[str]
    media_urls: List[str]
    raw_data: Dict[str, Any]  # Original message for debugging

    # Analysis fields (populated by pipeline)
    priority: Optional[str] = None
    has_action: Optional[bool] = None
    urgency_keywords: Optional[List[str]] = None
```

### 2.3 Data Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                          MESSAGE FLOW                                   │
└────────────────────────────────────────────────────────────────────────┘

1. INBOUND FLOW (Reception)
   ┌──────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
   │ Platform │───▶│  Adapter  │───▶│ Normalizer│───▶│  Storage  │
   │ (WA/TG)  │    │ (Listen)  │    │           │    │ (SQLite)  │
   └──────────┘    └───────────┘    └───────────┘    └─────┬─────┘
                                                          │
                                                          ▼
                                                    ┌───────────┐
                                                    │  Pipeline │
                                                    │ (Analyze) │
                                                    └─────┬─────┘
                                                          │
                   ┌──────────────────────────────────────┼──────────┐
                   │                                      │          │
                   ▼                                      ▼          ▼
            ┌───────────┐                          ┌───────────┐ ┌───────────┐
            │   Toast   │                          │   TODO    │ │  Report   │
            │  Notifier │                          │ Generator │ │ Aggregator│
            └───────────┘                          └───────────┘ └───────────┘

2. OUTBOUND FLOW (Response - with Safety)
   ┌──────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
   │  Draft   │───▶│  Review   │───▶│  Confirm  │───▶│  Adapter  │
   │ Generator│    │  (Human)  │    │  (Y/N)    │    │  (Send)   │
   └──────────┘    └───────────┘    └───────────┘    └───────────┘
        │                │                                  │
        │                ▼                                  ▼
        │          ┌───────────┐                     ┌──────────┐
        └─────────▶│   File    │                     │ Platform │
                   │  (Draft)  │                     │ (WA/TG)  │
                   └───────────┘                     └──────────┘
```

---

## 3. Implementation Phases

### Phase 4.1: Gateway Foundation (Week 1-2)

**Goal**: Core Gateway 서버 및 통합 메시지 스토리지 구축

#### Tasks

| ID | Task | Complexity | Dependency |
|----|------|------------|------------|
| 4.1.1 | Gateway Server 기본 구조 (asyncio) | HIGH | - |
| 4.1.2 | ChannelAdapter 인터페이스 정의 | MEDIUM | - |
| 4.1.3 | NormalizedMessage 스키마 설계 | MEDIUM | - |
| 4.1.4 | Unified SQLite 스키마 확장 | MEDIUM | 4.1.3 |
| 4.1.5 | MessagePipeline 기본 구현 | HIGH | 4.1.3 |
| 4.1.6 | Config 시스템 (JSON5/YAML) | LOW | - |
| 4.1.7 | Logging/Monitoring 인프라 | LOW | 4.1.1 |

#### Deliverables

- `scripts/gateway/server.py` - Gateway 메인 서버
- `scripts/gateway/adapters/base.py` - Adapter 인터페이스
- `scripts/gateway/models.py` - 데이터 모델
- `scripts/gateway/storage.py` - 통합 스토리지
- `scripts/gateway/pipeline.py` - 메시지 파이프라인
- `config/gateway.json` - Gateway 설정

#### Database Schema Extension

```sql
-- Unified messages table (extends notifications.db)
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,  -- 'whatsapp', 'telegram', etc.
    channel_id TEXT NOT NULL,  -- Platform chat ID
    sender_id TEXT NOT NULL,
    sender_name TEXT,
    text TEXT,
    message_type TEXT DEFAULT 'text',
    timestamp DATETIME NOT NULL,
    is_group BOOLEAN DEFAULT FALSE,
    is_mention BOOLEAN DEFAULT FALSE,
    reply_to_id TEXT,
    media_urls TEXT,  -- JSON array
    raw_json TEXT,

    -- Analysis fields
    priority TEXT,
    has_action BOOLEAN,
    processed_at DATETIME,

    -- Indexes
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_channel ON messages(channel);
CREATE INDEX idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX idx_messages_priority ON messages(priority);
CREATE INDEX idx_messages_channel_id ON messages(channel_id);
```

---

### Phase 4.2: Telegram Integration (Week 3-4)

**Goal**: 첫 번째 메시징 채널 - Telegram Bot API 통합

**Why Telegram First?**
- Bot Token 기반 간단한 인증
- 공식 API 안정성
- Long-polling으로 WebSocket 없이 시작 가능
- OpenClaw에서도 "가장 빠른 설정"으로 추천

#### Tasks

| ID | Task | Complexity | Dependency |
|----|------|------------|------------|
| 4.2.1 | python-telegram-bot 라이브러리 통합 | MEDIUM | 4.1.* |
| 4.2.2 | TelegramAdapter 구현 (Long-polling) | HIGH | 4.2.1 |
| 4.2.3 | Message Normalization (Text/Media) | MEDIUM | 4.2.2 |
| 4.2.4 | DM Policy 구현 (allowlist/pairing) | MEDIUM | 4.2.2 |
| 4.2.5 | Group 메시지 처리 | MEDIUM | 4.2.2 |
| 4.2.6 | Outbound Send (with confirmation) | HIGH | 4.2.2 |
| 4.2.7 | 테스트 봇 설정 및 E2E 테스트 | MEDIUM | 4.2.* |

#### Deliverables

- `scripts/gateway/adapters/telegram.py` - Telegram Adapter
- `config/channels/telegram.json` - Telegram 설정
- `tests/test_telegram_adapter.py` - 단위 테스트

#### Configuration Example

```json
{
  "telegram": {
    "enabled": true,
    "botToken": "${TELEGRAM_BOT_TOKEN}",
    "dmPolicy": "allowlist",
    "allowFrom": ["123456789"],
    "groups": {
      "*": { "requireMention": true }
    },
    "textChunkLimit": 4000
  }
}
```

---

### Phase 4.3: WhatsApp Integration (Week 5-6)

**Goal**: WhatsApp Web 연동 (가장 널리 사용되는 메신저)

**Approach**: Baileys 대신 Python 대안 사용 또는 Node.js 브릿지

#### Options Analysis

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **yowsup** (Python) | Native Python | Deprecated, 불안정 | Not recommended |
| **whatsapp-web.js** (Node) | 안정적, 활발한 개발 | Node.js 필요 | Recommended |
| **Baileys** (Node) | OpenClaw 검증됨 | Node.js 필요 | Alternative |
| **Twilio WhatsApp** | 공식 API | 비용, 24시간 제한 | Business only |

**Selected Approach**: `whatsapp-web.js` + Python Bridge (subprocess 또는 WebSocket)

#### Tasks

| ID | Task | Complexity | Dependency |
|----|------|------------|------------|
| 4.3.1 | Node.js WhatsApp 브릿지 서버 설계 | HIGH | 4.1.* |
| 4.3.2 | Python-Node IPC 구현 | HIGH | 4.3.1 |
| 4.3.3 | WhatsAppAdapter 구현 | HIGH | 4.3.2 |
| 4.3.4 | QR 로그인 플로우 | MEDIUM | 4.3.3 |
| 4.3.5 | Session 관리 (creds.json) | MEDIUM | 4.3.3 |
| 4.3.6 | Media 처리 (Image/Audio) | MEDIUM | 4.3.3 |
| 4.3.7 | Outbound Send (Draft 확인) | HIGH | 4.3.3 |

#### Bridge Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Python Gateway                               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                   WhatsAppAdapter                          │  │
│  │  - send_to_bridge(message)                                 │  │
│  │  - receive_from_bridge() -> AsyncIterator                  │  │
│  └────────────────────────┬──────────────────────────────────┘  │
│                           │ WebSocket / Unix Socket              │
│                           ▼                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │
                            ▼
┌───────────────────────────┼──────────────────────────────────────┐
│                    Node.js Bridge                                 │
│  ┌────────────────────────┴──────────────────────────────────┐  │
│  │               whatsapp-web.js Client                       │  │
│  │  - Baileys/WWS connection                                  │  │
│  │  - QR code generation                                      │  │
│  │  - Message send/receive                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

#### Deliverables

- `scripts/gateway/adapters/whatsapp.py` - WhatsApp Adapter
- `bridge/whatsapp/index.js` - Node.js 브릿지
- `bridge/whatsapp/package.json` - Node 의존성
- `config/channels/whatsapp.json` - WhatsApp 설정

---

### Phase 4.4: Discord Integration (Week 7)

**Goal**: Discord Bot 통합

#### Tasks

| ID | Task | Complexity | Dependency |
|----|------|------------|------------|
| 4.4.1 | discord.py 라이브러리 통합 | LOW | 4.1.* |
| 4.4.2 | DiscordAdapter 구현 | MEDIUM | 4.4.1 |
| 4.4.3 | Server/Channel 메시지 처리 | MEDIUM | 4.4.2 |
| 4.4.4 | DM 처리 | LOW | 4.4.2 |
| 4.4.5 | Slash Command 지원 (Optional) | LOW | 4.4.2 |

#### Deliverables

- `scripts/gateway/adapters/discord.py`
- `config/channels/discord.json`

---

### Phase 4.5: Slack Enhancement (Week 8)

**Goal**: 기존 Slack 분석기를 Gateway 아키텍처로 통합

#### Tasks

| ID | Task | Complexity | Dependency |
|----|------|------------|------------|
| 4.5.1 | 기존 slack_analyzer.py 리팩토링 | MEDIUM | 4.1.* |
| 4.5.2 | SlackAdapter 구현 (Socket Mode) | HIGH | 4.5.1 |
| 4.5.3 | Real-time Event 처리 | MEDIUM | 4.5.2 |
| 4.5.4 | Thread 메시지 처리 | MEDIUM | 4.5.2 |

#### Deliverables

- `scripts/gateway/adapters/slack.py`
- 기존 `slack_analyzer.py` 마이그레이션

---

### Phase 4.6: KakaoTalk Integration (Week 9-10)

**Goal**: 한국 사용자를 위한 KakaoTalk 통합

**Challenge**: KakaoTalk은 공식 Bot API가 제한적

#### Options Analysis

| Option | Availability | Limitation |
|--------|--------------|------------|
| KakaoTalk Channel API | Business 계정 필요 | 1:1 메시지만 |
| Android Notification | 이미 구현됨 (Phase 2) | 수신만 가능 |
| PC 클라이언트 연동 | 비공식 | 불안정 |

**Selected Approach**: Android Notification 기반 + 응답은 Toast로 알림

#### Tasks

| ID | Task | Complexity | Dependency |
|----|------|------------|------------|
| 4.6.1 | 기존 notification_receiver.py 통합 | LOW | 4.1.* |
| 4.6.2 | KakaoTalkAdapter (Notification-based) | MEDIUM | 4.6.1 |
| 4.6.3 | 카카오톡 앱별 파싱 로직 | MEDIUM | 4.6.2 |
| 4.6.4 | 응답 초안 → PC 알림 플로우 | LOW | 4.6.2 |

---

### Phase 4.7: Unified CLI & Daily Report Integration (Week 11)

**Goal**: Gateway를 기존 시스템과 통합

#### Tasks

| ID | Task | Complexity | Dependency |
|----|------|------------|------------|
| 4.7.1 | Gateway CLI (start/stop/status) | MEDIUM | 4.1.* |
| 4.7.2 | daily_report.py 연동 | MEDIUM | 4.7.1 |
| 4.7.3 | Real-time 알림 → Daily Report 연결 | HIGH | 4.7.2 |
| 4.7.4 | 통합 Dashboard (Optional, Web UI) | HIGH | 4.7.* |

#### CLI Commands

```powershell
# Gateway 시작
python -m scripts.gateway start --port 8800

# Gateway 상태 확인
python -m scripts.gateway status

# Gateway 중지
python -m scripts.gateway stop

# 채널 로그인
python -m scripts.gateway login telegram
python -m scripts.gateway login whatsapp  # QR 표시

# 채널 상태
python -m scripts.gateway channels
```

---

### Phase 4.8: Safety & Outbound Controls (Week 12)

**Goal**: 자동 전송 금지 규칙 강화 및 확인 플로우 구현

#### Safety Rules (CRITICAL)

| Rule | Implementation |
|------|----------------|
| **자동 전송 금지** | 모든 send()는 `--confirm` 플래그 필수 |
| **Draft 저장** | 응답 초안은 항상 파일로 저장 |
| **알림 후 전송** | Toast로 초안 알림 → 사용자 확인 → 전송 |
| **전송 로그** | 모든 전송 이력 SQLite 기록 |
| **Rate Limiting** | 분당 전송 수 제한 (기본: 10) |

#### Outbound Flow

```python
class OutboundMessage:
    channel: ChannelType
    to: str
    text: str
    draft_file: Path  # 항상 저장됨
    confirmed: bool = False  # 명시적 확인 필요
    sent_at: Optional[datetime] = None

async def send_message(msg: OutboundMessage) -> SendResult:
    """
    SAFETY: 이 함수는 confirmed=True일 때만 실제 전송
    """
    if not msg.confirmed:
        # 1. 초안 파일 저장
        save_draft(msg)

        # 2. Toast 알림
        toast_notify(f"응답 초안 생성: {msg.draft_file}")

        # 3. 전송하지 않음
        return SendResult(status="draft_saved", draft_path=msg.draft_file)

    # confirmed=True인 경우만 실제 전송
    result = await adapter.send(msg)
    log_sent_message(msg, result)
    return result
```

---

## 4. Technical Stack Decision

### 4.1 Language: Python 유지

| Factor | Decision | Rationale |
|--------|----------|-----------|
| **Language** | Python 3.11+ | 기존 코드 자산 활용, asyncio 충분 |
| **Async Framework** | asyncio | 표준 라이브러리, 외부 의존성 최소화 |
| **HTTP Server** | aiohttp 또는 FastAPI | WebSocket 지원 |
| **WhatsApp** | Node.js Bridge | Python 대안 부재 |

### 4.2 Key Libraries

| Purpose | Library | Version |
|---------|---------|---------|
| Telegram | python-telegram-bot | 20.x |
| Discord | discord.py | 2.x |
| Slack | slack-sdk | 3.x |
| WebSocket Server | websockets | 12.x |
| HTTP Server | aiohttp | 3.9.x |
| Database | aiosqlite | 0.19.x |
| Config | pydantic-settings | 2.x |

### 4.3 WhatsApp Bridge Stack

| Component | Technology |
|-----------|------------|
| Runtime | Node.js 20 LTS |
| Library | whatsapp-web.js 1.x |
| IPC | WebSocket (localhost:8801) |
| Session | Local file (creds.json) |

---

## 5. Risks and Mitigation

### 5.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| WhatsApp 계정 밴 | HIGH | MEDIUM | 전용 번호 사용, Rate limiting |
| Node.js 브릿지 불안정 | MEDIUM | LOW | Watchdog + 자동 재시작 |
| 메시지 유실 | HIGH | LOW | SQLite WAL 모드, 트랜잭션 |
| 채널 API 변경 | MEDIUM | MEDIUM | 어댑터 격리, 빠른 업데이트 |

### 5.2 Security Risks

| Risk | Mitigation |
|------|------------|
| 토큰 노출 | 환경 변수 / 암호화된 config |
| 무단 전송 | confirmed 플래그 강제, Rate limiting |
| 세션 탈취 | 로컬 파일 권한 제한 (600) |

### 5.3 Dependency Risks

| Risk | Mitigation |
|------|------------|
| whatsapp-web.js 중단 | Baileys로 대체 준비 |
| Telegram API 제한 | Webhook 모드 대안 |
| Discord Rate Limit | 지수 백오프, 큐잉 |

---

## 6. Success Criteria

### 6.1 Phase 4 Complete Criteria

| Criterion | Measurement | Target |
|-----------|-------------|--------|
| 채널 수 | 지원 채널 수 | >= 4 (TG, WA, Discord, Slack) |
| 메시지 지연 | 수신 ~ 저장 시간 | < 5초 (p95) |
| 안정성 | Uptime | > 99% (30일) |
| 자동화 | 수동 개입 없이 동작 | 재시작 시 자동 복구 |
| 안전성 | 무단 전송 건수 | 0건 |

### 6.2 User Experience Metrics

| Metric | Target |
|--------|--------|
| 설정 시간 (Telegram) | < 5분 |
| 설정 시간 (WhatsApp) | < 10분 (QR 포함) |
| Daily Report 포함 | 모든 채널 메시지 통합 |
| 응답 초안 생성 시간 | < 30초 |

### 6.3 Code Quality Metrics

| Metric | Target |
|--------|--------|
| Test Coverage | >= 80% |
| Type Hints | 100% (public API) |
| Documentation | 모든 public 함수 docstring |
| Linting | ruff clean |

---

## 7. Timeline Summary

```
Week 1-2   │ Phase 4.1: Gateway Foundation
Week 3-4   │ Phase 4.2: Telegram Integration
Week 5-6   │ Phase 4.3: WhatsApp Integration
Week 7     │ Phase 4.4: Discord Integration
Week 8     │ Phase 4.5: Slack Enhancement
Week 9-10  │ Phase 4.6: KakaoTalk Integration
Week 11    │ Phase 4.7: CLI & Daily Report Integration
Week 12    │ Phase 4.8: Safety & Outbound Controls
```

**Total Duration**: 12 weeks
**Start Date**: TBD
**Target Completion**: TBD + 12 weeks

---

## 8. File Structure (Proposed)

```
C:\claude\secretary\
├── scripts/
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── server.py              # Gateway 메인
│   │   ├── models.py              # 데이터 모델
│   │   ├── pipeline.py            # 메시지 파이프라인
│   │   ├── storage.py             # 통합 스토리지
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # 어댑터 인터페이스
│   │   │   ├── telegram.py
│   │   │   ├── whatsapp.py
│   │   │   ├── discord.py
│   │   │   ├── slack.py
│   │   │   └── kakaotalk.py
│   │   └── cli.py                 # Gateway CLI
│   ├── actions/                   # Phase 3 (기존)
│   └── daily_report.py            # 기존 (Gateway 연동)
├── bridge/
│   └── whatsapp/
│       ├── index.js               # Node.js 브릿지
│       ├── package.json
│       └── package-lock.json
├── config/
│   ├── gateway.json               # Gateway 설정
│   └── channels/
│       ├── telegram.json
│       ├── whatsapp.json
│       ├── discord.json
│       └── slack.json
├── tests/
│   ├── test_gateway.py
│   ├── test_telegram_adapter.py
│   ├── test_whatsapp_adapter.py
│   └── test_pipeline.py
└── docs/
    └── 01-plan/
        └── multichannel-integration.plan.md  # This file
```

---

## 9. Next Steps

1. **Immediate**: 이 계획 문서 리뷰 및 피드백
2. **Phase 4.1 착수**: Gateway 기본 구조 구현 시작
3. **Telegram Bot 생성**: @BotFather에서 테스트 봇 생성
4. **WhatsApp 번호 준비**: 전용 번호 확보 (eSIM 권장)

---

## Appendix A: OpenClaw Reference Notes

### A.1 OpenClaw 채널 목록 (참고용)

- WhatsApp (Baileys)
- Telegram (grammY)
- Discord (Discord.js)
- Slack (Bolt SDK)
- Google Chat
- Signal (signal-cli)
- iMessage (BlueBubbles)
- Microsoft Teams
- Matrix, Nostr, LINE, etc.

### A.2 OpenClaw Gateway 특징

- 단일 WebSocket 서버로 모든 채널 통합
- TypeScript 기반
- Multi-agent 세션 격리
- SKILL.md 기반 확장 시스템

### A.3 Secretary vs OpenClaw 차이점

| Aspect | Secretary | OpenClaw |
|--------|-----------|----------|
| Language | Python | TypeScript |
| Focus | 분석 + 자동화 액션 | AI 채팅 비서 |
| Safety | 자동 전송 금지 | Pairing/Allowlist |
| Scale | 개인용 | Multi-agent |

---

**Document End**
