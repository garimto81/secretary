#!/usr/bin/env python3
"""
Toast Notifier - Windows Toast 알림 전송

Usage:
    python toast_notifier.py --title "제목" --message "내용"
    python toast_notifier.py --json  # stdin으로 JSON 입력

Examples:
    python toast_notifier.py --title "긴급" --message "이메일 확인 필요"
    echo '{"title":"할일","message":"리뷰 3건 대기"}' | python toast_notifier.py --json
"""

import argparse
import json
import sys
from typing import Optional

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Windows Toast 라이브러리
try:
    from winotify import Notification, audio
except ImportError:
    print("Error: winotify 라이브러리가 설치되지 않았습니다.")
    print("설치: pip install winotify")
    sys.exit(1)


def send_notification(
    title: str,
    message: str,
    app_name: str = "Secretary AI",
    duration: str = "short",
    icon_path: Optional[str] = None,
) -> bool:
    """
    Windows Toast 알림 전송

    Args:
        title: 알림 제목
        message: 알림 내용
        app_name: 앱 이름 (기본: Secretary AI)
        duration: 지속 시간 (short|long, 기본: short)
        icon_path: 아이콘 경로 (선택)

    Returns:
        성공 여부
    """
    try:
        toast = Notification(
            app_id=app_name,
            title=title,
            msg=message,
            duration=duration,
        )

        if icon_path:
            toast.set_icon(icon_path)

        # 알림음 설정
        toast.set_audio(audio.Default, loop=False)

        toast.show()
        return True

    except Exception as e:
        print(f"Error: 알림 전송 실패 - {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Windows Toast 알림 전송")
    parser.add_argument("--title", help="알림 제목")
    parser.add_argument("--message", help="알림 내용")
    parser.add_argument("--app-name", default="Secretary AI", help="앱 이름")
    parser.add_argument(
        "--duration", choices=["short", "long"], default="short", help="지속 시간"
    )
    parser.add_argument("--icon", help="아이콘 경로")
    parser.add_argument("--json", action="store_true", help="stdin으로 JSON 입력")
    args = parser.parse_args()

    # JSON 입력 처리
    if args.json:
        try:
            data = json.load(sys.stdin)
            title = data.get("title", "알림")
            message = data.get("message", "")
            app_name = data.get("app_name", args.app_name)
            duration = data.get("duration", args.duration)
            icon_path = data.get("icon_path")
        except json.JSONDecodeError as e:
            print(f"Error: JSON 파싱 실패 - {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # CLI 인자 처리
        if not args.title or not args.message:
            print("Error: --title과 --message는 필수입니다.", file=sys.stderr)
            sys.exit(1)

        title = args.title
        message = args.message
        app_name = args.app_name
        duration = args.duration
        icon_path = args.icon

    # 알림 전송
    success = send_notification(title, message, app_name, duration, icon_path)

    if success:
        print(f"✅ 알림 전송 성공: {title}")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
