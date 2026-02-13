#!/usr/bin/env python3
"""
Notification System Test - WebSocket 서버 테스트

테스트 알림을 전송하여 notification_receiver.py 동작 확인
"""

import asyncio
import json
import websockets
from datetime import datetime


async def send_test_notification():
    """테스트 알림 전송"""
    uri = "ws://localhost:8800"

    test_notifications = [
        {
            "type": "notification",
            "app": "com.kakao.talk",
            "title": "김개발",
            "text": "긴급 회의 요청드립니다. 오늘 3시 가능하신가요?",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "extras": {
                "conversation_id": "chat_123",
                "is_group": False
            }
        },
        {
            "type": "notification",
            "app": "com.whatsapp",
            "title": "Project Team",
            "text": "Please review the latest PR when you have time.",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "extras": {
                "conversation_id": "group_456",
                "is_group": True
            }
        },
        {
            "type": "notification",
            "app": "jp.naver.line.android",
            "title": "박매니저",
            "text": "보고서 확인해주세요",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "extras": {
                "conversation_id": "chat_789",
                "is_group": False
            }
        }
    ]

    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ WebSocket 연결 성공: {uri}")

            for i, notif in enumerate(test_notifications, 1):
                # 알림 전송
                await websocket.send(json.dumps(notif))
                print(f"📤 테스트 알림 전송 ({i}/{len(test_notifications)}): {notif['app']}")

                # 응답 수신
                response = await websocket.recv()
                resp_data = json.loads(response)
                print(f"📥 서버 응답: {resp_data['status']}")

                # 간격 두기
                await asyncio.sleep(0.5)

            print("\n✅ 모든 테스트 알림 전송 완료")

    except websockets.exceptions.WebSocketException as e:
        print(f"❌ WebSocket 연결 실패: {e}")
        print("서버가 실행 중인지 확인하세요: python notification_receiver.py --start")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")


if __name__ == "__main__":
    print("🧪 Notification System 테스트")
    print("=" * 50)
    asyncio.run(send_test_notification())
