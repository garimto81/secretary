# Android Notification Collector - Desktop 측 시스템

**Version**: 1.0.0
**Status**: Phase 2 구현 완료

Android NotificationListenerService와 통신하는 Desktop 측 WebSocket 서버 및 분석 스크립트

## 파일 구조

```
C:\claude\secretary\scripts\
├── notification_receiver.py   # WebSocket 서버 (포트 8800)
├── notification_analyzer.py   # 알림 분석 스크립트
└── test_notification_system.py # 시스템 테스트
```

## WebSocket 프로토콜

### 수신 메시지 형식

```json
{
  "type": "notification",
  "app": "com.kakao.talk",
  "title": "발신자 이름",
  "text": "메시지 내용",
  "timestamp": "2026-02-02T10:30:00Z",
  "extras": {
    "conversation_id": "123",
    "is_group": false
  }
}
```

### 응답 메시지 형식

```json
{
  "status": "ok",
  "timestamp": "2026-02-02T10:30:05Z"
}
```

## notification_receiver.py

WebSocket 서버로 Android 알림을 수신하고 SQLite에 저장합니다.

### 기능

1. **WebSocket 서버 (asyncio + websockets)**
   - 포트: 8800 (기본값)
   - 프로토콜: ws://0.0.0.0:8800

2. **SQLite 저장**
   - 경로: `C:\claude\json\notifications.db`
   - 테이블: `notifications`

3. **테이블 스키마**

```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app TEXT NOT NULL,
    title TEXT,
    text TEXT,
    timestamp DATETIME,
    conversation_id TEXT,
    is_group BOOLEAN,
    received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    raw_json TEXT
);

CREATE INDEX idx_app ON notifications(app);
CREATE INDEX idx_timestamp ON notifications(timestamp DESC);
CREATE INDEX idx_conversation ON notifications(conversation_id);
```

### CLI 명령어

| 명령어 | 용도 |
|--------|------|
| `--start` | 서버 시작 |
| `--status` | 서버 상태 확인 |
| `--stop` | 서버 중지 |
| `--port N` | WebSocket 포트 (기본: 8800) |
| `--db PATH` | SQLite DB 경로 |

### 사용 예시

```powershell
# 서버 시작
python scripts/notification_receiver.py --start

# 커스텀 포트/DB
python scripts/notification_receiver.py --start --port 9000 --db custom.db

# 서버 상태 확인
python scripts/notification_receiver.py --status

# 서버 중지
python scripts/notification_receiver.py --stop
# 또는 Ctrl+C
```

### 로그 출력 예시

```
🚀 Notification Receiver 시작
├── Port: 8800
└── Database: C:\claude\json\notifications.db
✅ Database 초기화 완료: C:\claude\json\notifications.db
✅ 서버 실행 중 (ws://0.0.0.0:8800)
Press Ctrl+C to stop...

🔗 Client 연결: ('192.168.1.100', 54321)
📬 [com.kakao.talk] 김개발: 긴급 회의 요청드립니다... (2026-02-02T10:30:00Z)
🔌 Client 연결 종료: ('192.168.1.100', 54321)
```

## notification_analyzer.py

SQLite에서 알림을 조회하고 긴급/미응답 메시지를 분석합니다.

### 기능

1. **앱별 필터링**
   - `--app kakao`, `whatsapp`, `line`, `telegram`, `sms` 등

2. **메시지 분석**
   - 긴급 키워드 감지: "긴급", "urgent", "asap", "오늘까지" 등
   - 질문/응답 필요 감지: "?", "확인해", "알려", "회신" 등
   - 미응답 확인: 12시간 이상 미응답 시 경고

3. **daily_report.py 통합용 JSON 출력**

### CLI 옵션

| 옵션 | 설명 |
|------|------|
| `--days N` | 최근 N일 알림 분석 (기본: 3) |
| `--app APP` | 특정 앱만 분석 (kakao, whatsapp, line, telegram, sms) |
| `--json` | JSON 형식 출력 |
| `--db PATH` | SQLite DB 경로 |

### 사용 예시

```powershell
# 최근 3일 전체 앱 분석
python scripts/notification_analyzer.py --days 3

# 카카오톡만 분석
python scripts/notification_analyzer.py --app kakao

# JSON 출력
python scripts/notification_analyzer.py --json

# 커스텀 DB
python scripts/notification_analyzer.py --db custom.db --days 7
```

### 출력 예시

```
📱 Android 알림 분석 (총 45건)

🚨 긴급 알림 (3건)
├── [KAKAO] 김개발
│   긴급 회의 요청드립니다. 오늘 3시 가능...

⚠️ 미응답 알림 (2건)
├── [WHATSAPP] Project Team - 15시간 경과

📊 앱별 통계
├── KAKAO: 25건 (긴급 2, 미응답 1)
├── WHATSAPP: 15건 (긴급 1, 미응답 1)
└── LINE: 5건 (긴급 0, 미응답 0)
```

### JSON 출력 예시

```json
{
  "urgent": [
    {
      "id": 123,
      "app": "com.kakao.talk",
      "app_name": "kakao",
      "title": "김개발",
      "text": "긴급 회의 요청드립니다. 오늘 3시 가능하신가요?",
      "timestamp": "2026-02-02T10:30:00Z",
      "conversation_id": "chat_123",
      "is_group": false,
      "received_at": "2026-02-02T10:30:05",
      "priority": "high",
      "reason": "긴급 키워드 포함"
    }
  ],
  "unanswered": [
    {
      "id": 456,
      "app": "com.whatsapp",
      "app_name": "whatsapp",
      "title": "Project Team",
      "text": "Please review the latest PR when you have time.",
      "timestamp": "2026-02-01T19:30:00Z",
      "hours_since": 15,
      "priority": "medium",
      "reason": "미응답 15시간"
    }
  ],
  "app_stats": {
    "kakao": {"count": 25, "urgent": 2, "unanswered": 1},
    "whatsapp": {"count": 15, "urgent": 1, "unanswered": 1},
    "line": {"count": 5, "urgent": 0, "unanswered": 0}
  },
  "total_count": 45
}
```

## test_notification_system.py

WebSocket 서버 동작을 확인하는 테스트 스크립트입니다.

### 사용법

```powershell
# 1. 서버 시작 (별도 터미널)
python scripts/notification_receiver.py --start

# 2. 테스트 실행
python scripts/test_notification_system.py
```

### 테스트 시나리오

1. 카카오톡 알림 (긴급 키워드)
2. WhatsApp 알림 (그룹 메시지)
3. LINE 알림 (일반 메시지)

## 앱 패키지명 매핑

| 앱 이름 | 패키지명 |
|---------|----------|
| `kakao` | `com.kakao.talk` |
| `whatsapp` | `com.whatsapp` |
| `line` | `jp.naver.line.android` |
| `telegram` | `org.telegram.messenger` |
| `sms` | `com.google.android.apps.messaging` |

## daily_report.py 통합

`notification_analyzer.py --json` 출력을 `daily_report.py`에서 활용:

```python
def analyze_notifications() -> dict:
    """Android 알림 분석"""
    print("📱 Android 알림 분석 중...")
    data = run_script(NOTIFICATION_SCRIPT, ["--days", "3", "--json"])

    if not data:
        return {"urgent": [], "unanswered": [], "app_stats": {}}

    return data
```

## 주의 사항

1. **서버 실행 필수**
   - Android 앱에서 알림을 전송하기 전에 `notification_receiver.py --start` 실행

2. **포트 충돌**
   - 기본 포트 8800이 사용 중이면 `--port` 옵션으로 변경

3. **방화벽**
   - Windows 방화벽에서 포트 8800 인바운드 허용 필요

4. **타임존**
   - 모든 타임스탬프는 UTC 기준 (`2026-02-02T10:30:00Z`)

## 다음 단계 (Phase 3 - Android 앱)

1. Android NotificationListenerService 구현
2. WebSocket 클라이언트 (ws://desktop-ip:8800)
3. 알림 필터링 (특정 앱만)
4. 백그라운드 전송

## 참조 패턴

- `gmail_analyzer.py`: 인증, 분석 로직, CLI 옵션
- `daily_report.py`: subprocess 실행, JSON 파싱, 통합 리포트

## 의존성

```
websockets>=12.0
```

설치:

```powershell
pip install -r requirements.txt
```
