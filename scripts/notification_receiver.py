#!/usr/bin/env python3
"""
Notification Receiver - Android 알림 수신 WebSocket 서버

Usage:
    python notification_receiver.py --start [--port 8800]
    python notification_receiver.py --status
    python notification_receiver.py --stop

Options:
    --start     WebSocket 서버 시작
    --status    서버 상태 확인
    --stop      서버 중지
    --port N    WebSocket 포트 (기본: 8800)
    --db PATH   SQLite DB 경로 (기본: C:/claude/json/notifications.db)

Server Protocol:
    수신 메시지 형식 (JSON):
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
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# WebSocket 라이브러리
try:
    import websockets
except ImportError:
    print("Error: websockets 라이브러리가 설치되지 않았습니다.")
    print("설치: pip install websockets")
    sys.exit(1)

# 기본 설정
DEFAULT_PORT = 8800
DEFAULT_DB = Path(r"C:\claude\json\notifications.db")
PID_FILE = Path(r"C:\claude\json\notification_receiver.pid")


def init_database(db_path: Path):
    """SQLite 데이터베이스 초기화"""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            app TEXT NOT NULL,
            title TEXT,
            text TEXT,
            timestamp DATETIME,
            conversation_id TEXT,
            is_group BOOLEAN,
            received_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            raw_json TEXT
        )
    """)

    # 인덱스 생성
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_app ON notifications(app)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp ON notifications(timestamp DESC)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation ON notifications(conversation_id)
    """)

    conn.commit()
    conn.close()

    print(f"✅ Database 초기화 완료: {db_path}")


def save_notification(db_path: Path, notification: dict):
    """알림 저장"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    extras = notification.get("extras", {})

    cursor.execute("""
        INSERT INTO notifications (
            app, title, text, timestamp, conversation_id, is_group, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        notification.get("app", ""),
        notification.get("title", ""),
        notification.get("text", ""),
        notification.get("timestamp", ""),
        extras.get("conversation_id", ""),
        extras.get("is_group", False),
        json.dumps(notification, ensure_ascii=False)
    ))

    conn.commit()
    conn.close()


async def handle_client(websocket, path, db_path: Path):
    """WebSocket 클라이언트 처리"""
    client_addr = websocket.remote_address
    print(f"🔗 Client 연결: {client_addr}")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)

                if data.get("type") != "notification":
                    print(f"⚠️ Unknown message type: {data.get('type')}")
                    continue

                # 알림 저장
                save_notification(db_path, data)

                # 로그 출력
                app = data.get("app", "unknown")
                title = data.get("title", "")
                text = data.get("text", "")[:50]
                timestamp = data.get("timestamp", "")

                print(f"📬 [{app}] {title}: {text}... ({timestamp})")

                # 응답 전송
                await websocket.send(json.dumps({
                    "status": "ok",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }))

            except json.JSONDecodeError as e:
                print(f"❌ JSON 파싱 실패: {e}")
                await websocket.send(json.dumps({
                    "status": "error",
                    "message": "Invalid JSON"
                }))
            except Exception as e:
                print(f"❌ 알림 처리 실패: {e}")

    except websockets.exceptions.ConnectionClosed:
        print(f"🔌 Client 연결 종료: {client_addr}")
    except Exception as e:
        print(f"❌ Client 처리 오류: {e}")


async def start_server(port: int, db_path: Path):
    """WebSocket 서버 시작"""
    print("🚀 Notification Receiver 시작")
    print(f"├── Port: {port}")
    print(f"└── Database: {db_path}")

    # DB 초기화
    init_database(db_path)

    # PID 저장
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PID_FILE, "w") as f:
        f.write(str(asyncio.current_task().get_coro().__self__))

    async with websockets.serve(
        lambda ws, path: handle_client(ws, path, db_path),
        "0.0.0.0",
        port
    ):
        print(f"✅ 서버 실행 중 (ws://0.0.0.0:{port})")
        print("Press Ctrl+C to stop...")
        await asyncio.Future()  # 무한 대기


def check_status():
    """서버 상태 확인"""
    if PID_FILE.exists():
        print(f"✅ 서버 실행 중 (PID: {PID_FILE.read_text()})")
        return True
    else:
        print("❌ 서버 중지 상태")
        return False


def stop_server():
    """서버 중지"""
    if not PID_FILE.exists():
        print("❌ 실행 중인 서버가 없습니다.")
        return

    # PID 파일 삭제
    PID_FILE.unlink()
    print("✅ 서버 중지 신호 전송")
    print("Note: 실제 프로세스는 수동으로 종료 필요 (Ctrl+C)")


def main():
    parser = argparse.ArgumentParser(description="Android 알림 수신 WebSocket 서버")
    parser.add_argument("--start", action="store_true", help="서버 시작")
    parser.add_argument("--status", action="store_true", help="서버 상태 확인")
    parser.add_argument("--stop", action="store_true", help="서버 중지")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="WebSocket 포트")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB 경로")
    args = parser.parse_args()

    if args.status:
        check_status()
    elif args.stop:
        stop_server()
    elif args.start:
        try:
            asyncio.run(start_server(args.port, args.db))
        except KeyboardInterrupt:
            print("\n🛑 서버 종료 중...")
            if PID_FILE.exists():
                PID_FILE.unlink()
            print("✅ 서버 종료 완료")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
