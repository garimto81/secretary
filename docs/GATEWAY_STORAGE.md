# Gateway Storage

통합 메시지 스토리지 (Phase 4)

## 개요

SQLite 기반 비동기 스토리지로 모든 채널의 메시지를 저장하고 조회합니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| **메시지 저장** | 모든 채널 메시지 통합 저장 |
| **빠른 조회** | 인덱싱을 통한 효율적 검색 |
| **비동기 지원** | aiosqlite 기반 비차단 I/O |
| **중복 방지** | ID 기반 REPLACE 동작 |

## 데이터베이스 스키마

```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    channel TEXT NOT NULL,              -- 'kakao', 'gmail', 'slack', 'sms'
    channel_id TEXT NOT NULL,           -- 채널 내부 ID (room, thread 등)
    sender_id TEXT NOT NULL,
    sender_name TEXT,
    text TEXT,
    message_type TEXT DEFAULT 'text',   -- 'text', 'image', 'file', 'sticker'
    timestamp DATETIME NOT NULL,
    is_group BOOLEAN DEFAULT FALSE,
    is_mention BOOLEAN DEFAULT FALSE,
    reply_to_id TEXT,
    media_urls TEXT,                    -- JSON array
    raw_json TEXT,                      -- JSON object
    priority TEXT,                      -- 'high', 'medium', 'low'
    has_action BOOLEAN DEFAULT FALSE,
    processed_at DATETIME,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_messages_channel ON messages(channel);
CREATE INDEX idx_messages_timestamp ON messages(timestamp DESC);
CREATE INDEX idx_messages_priority ON messages(priority);
CREATE INDEX idx_messages_processed ON messages(processed_at);
```

## 사용법

### 기본 사용

```python
from scripts.gateway.storage import UnifiedStorage, NormalizedMessage
from datetime import datetime

# Context manager 사용 (권장)
async with UnifiedStorage() as storage:
    # 메시지 저장
    msg = NormalizedMessage(
        id="msg_001",
        channel="kakao",
        channel_id="room_123",
        sender_id="user_456",
        sender_name="홍길동",
        text="안녕하세요",
        timestamp=datetime.now()
    )
    await storage.save_message(msg)

    # 메시지 조회
    retrieved = await storage.get_message("msg_001")
    print(retrieved.text)
```

### 최근 메시지 조회

```python
async with UnifiedStorage() as storage:
    # 전체 채널에서 최근 50개
    recent = await storage.get_recent_messages(limit=50)

    # 특정 채널에서만
    kakao_msgs = await storage.get_recent_messages(channel="kakao", limit=20)

    # 특정 시간 이후
    from datetime import datetime, timedelta
    since = datetime.now() - timedelta(hours=24)
    today_msgs = await storage.get_recent_messages(since=since)
```

### 미처리 메시지 처리

```python
async with UnifiedStorage() as storage:
    # 미처리 메시지 가져오기
    unprocessed = await storage.get_unprocessed_messages()

    for msg in unprocessed:
        # 메시지 처리 로직
        process_message(msg)

        # 처리 완료 표시
        await storage.mark_processed(msg.id)
```

### 통계 조회

```python
async with UnifiedStorage() as storage:
    stats = await storage.get_stats()

    print(f"총 메시지: {stats['total_messages']}")
    print(f"채널별 메시지: {stats['by_channel']}")
    print(f"미처리 메시지: {stats['unprocessed']}")

# 출력 예시:
# 총 메시지: 1523
# 채널별 메시지: {'kakao': 856, 'gmail': 432, 'slack': 235}
# 미처리 메시지: 12
```

### 미디어 메시지 저장

```python
msg = NormalizedMessage(
    id="img_001",
    channel="kakao",
    channel_id="room_123",
    sender_id="user_456",
    sender_name="홍길동",
    text="사진 보냅니다",
    message_type="image",
    timestamp=datetime.now(),
    media_urls=[
        "https://example.com/photo1.jpg",
        "https://example.com/photo2.jpg"
    ],
    raw_json={
        "extra_metadata": "some_value",
        "nested": {"key": "value"}
    }
)

async with UnifiedStorage() as storage:
    await storage.save_message(msg)
```

## API 레퍼런스

### UnifiedStorage

| 메서드 | 설명 |
|--------|------|
| `connect()` | DB 연결 및 스키마 초기화 |
| `close()` | DB 연결 종료 |
| `save_message(message)` | 메시지 저장 (REPLACE) |
| `get_message(message_id)` | ID로 메시지 조회 |
| `get_recent_messages(channel, limit, since)` | 최근 메시지 조회 |
| `get_unprocessed_messages()` | 미처리 메시지 조회 |
| `mark_processed(message_id)` | 메시지 처리 완료 표시 |
| `get_stats()` | 통계 조회 |

### NormalizedMessage

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `id` | str | ✅ | 메시지 고유 ID |
| `channel` | str | ✅ | 채널 종류 |
| `channel_id` | str | ✅ | 채널 내부 ID |
| `sender_id` | str | ✅ | 발신자 ID |
| `sender_name` | str | ❌ | 발신자 이름 |
| `text` | str | ❌ | 메시지 본문 |
| `message_type` | str | ❌ | 메시지 타입 (기본: 'text') |
| `timestamp` | datetime | ❌ | 메시지 시간 |
| `is_group` | bool | ❌ | 그룹 메시지 여부 |
| `is_mention` | bool | ❌ | 멘션 여부 |
| `reply_to_id` | str | ❌ | 답장 대상 ID |
| `media_urls` | List[str] | ❌ | 미디어 URL 목록 |
| `raw_json` | Dict | ❌ | 원본 JSON 데이터 |
| `priority` | str | ❌ | 우선순위 |
| `has_action` | bool | ❌ | 액션 필요 여부 |
| `processed_at` | datetime | ❌ | 처리 완료 시간 |
| `received_at` | datetime | ❌ | 수신 시간 (자동) |

## 데이터베이스 위치

- 기본 경로: `C:\claude\secretary\data\gateway.db`
- 커스텀 경로: `UnifiedStorage(db_path=Path("custom.db"))`

## 테스트

```powershell
# 전체 테스트
python -m pytest tests/test_gateway_storage.py -v

# 개별 테스트
python -m pytest tests/test_gateway_storage.py::test_save_and_get_message -v
```

## 성능 최적화

| 최적화 | 설명 |
|--------|------|
| **인덱싱** | channel, timestamp, priority, processed_at 인덱스 |
| **비동기 I/O** | aiosqlite로 비차단 데이터베이스 작업 |
| **Context manager** | 자동 연결/종료 관리 |
| **REPLACE** | ID 중복 시 자동 업데이트 |

## 다음 단계

- Phase 4-2: 채널 어댑터 구현 (Kakao, Slack 등)
- Phase 4-3: 액션 디스패처 (응답 초안 생성)
- Phase 4-4: 실시간 메시지 수신
