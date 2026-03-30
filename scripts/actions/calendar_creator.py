#!/usr/bin/env python3
"""
Calendar Creator - Google Calendar 일정 생성

⚠️ 사용자 확인 필수: --confirm 플래그 없으면 dry-run만 수행

Usage:
    python calendar_creator.py --title "회의" --start "2026-02-02 14:00" --end "2026-02-02 15:00"
    python calendar_creator.py --title "회의" --start "2026-02-02 14:00" --end "2026-02-02 15:00" --confirm
    python calendar_creator.py --json  # stdin으로 JSON 입력

Examples:
    # Dry-run (실제 생성하지 않음)
    python calendar_creator.py --title "팀 미팅" --start "2026-02-03 10:00" --end "2026-02-03 11:00"

    # 실제 생성 (확인 필요)
    python calendar_creator.py --title "팀 미팅" --start "2026-02-03 10:00" --end "2026-02-03 11:00" --confirm

    # JSON 입력
    echo '{"title":"회의","start":"2026-02-03 14:00","end":"2026-02-03 15:00","confirm":true}' | python calendar_creator.py --json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Google API imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError:
    print("Error: Google API 라이브러리가 설치되지 않았습니다.")
    print(
        "설치: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
    )
    sys.exit(1)

# 인증 파일 경로
CREDENTIALS_DIR = Path(r"C:\claude\json")
CREDENTIALS_FILE = CREDENTIALS_DIR / "desktop_credentials.json"
TOKEN_FILE = CREDENTIALS_DIR / "token_calendar.json"

# OAuth Scopes (쓰기 권한 포함)
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
]


def get_credentials() -> Credentials:
    """Google OAuth 인증 처리"""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"Error: OAuth 자격증명 파일이 없습니다: {CREDENTIALS_FILE}")
                print(
                    "Google Cloud Console에서 OAuth 클라이언트 ID를 생성하고 다운로드하세요."
                )
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # 토큰 저장
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def parse_datetime(dt_str: str) -> datetime:
    """날짜/시간 문자열 파싱"""
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"날짜 형식 파싱 실패: {dt_str}")


def create_event(
    service,
    title: str,
    start_time: str,
    end_time: str,
    description: str = "",
    location: str = "",
    attendees: list | None = None,
    dry_run: bool = True,
) -> dict | None:
    """
    Google Calendar 일정 생성

    Args:
        service: Google Calendar API 서비스
        title: 일정 제목
        start_time: 시작 시간 (YYYY-MM-DD HH:MM)
        end_time: 종료 시간 (YYYY-MM-DD HH:MM)
        description: 설명
        location: 장소
        attendees: 참석자 이메일 리스트
        dry_run: True면 실제 생성하지 않음

    Returns:
        생성된 이벤트 정보 (dry_run이면 None)
    """
    try:
        # 날짜 파싱
        start_dt = parse_datetime(start_time)
        end_dt = parse_datetime(end_time)

        # 이벤트 구조
        event = {
            "summary": title,
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Seoul",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Seoul",
            },
        }

        if location:
            event["location"] = location

        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]

        # Dry-run 모드
        if dry_run:
            print("⚠️ DRY-RUN 모드: 실제 생성하지 않음")
            print(json.dumps(event, ensure_ascii=False, indent=2))
            return None

        # 실제 생성
        created_event = (
            service.events().insert(calendarId="primary", body=event).execute()
        )

        return created_event

    except Exception as e:
        print(f"Error: 일정 생성 실패 - {e}", file=sys.stderr)
        return None


def confirm_creation(event_data: dict) -> bool:
    """사용자 확인 프롬프트"""
    print("\n다음 일정을 생성하시겠습니까?")
    print(f"제목: {event_data['summary']}")
    print(f"시작: {event_data['start']['dateTime']}")
    print(f"종료: {event_data['end']['dateTime']}")
    if "location" in event_data:
        print(f"장소: {event_data['location']}")
    if "description" in event_data:
        print(f"설명: {event_data['description']}")

    response = input("\n생성하시겠습니까? (y/N): ").strip().lower()
    return response in ["y", "yes"]


def main():
    parser = argparse.ArgumentParser(description="Google Calendar 일정 생성")
    parser.add_argument("--title", help="일정 제목")
    parser.add_argument("--start", help="시작 시간 (YYYY-MM-DD HH:MM)")
    parser.add_argument("--end", help="종료 시간 (YYYY-MM-DD HH:MM)")
    parser.add_argument("--description", default="", help="설명")
    parser.add_argument("--location", default="", help="장소")
    parser.add_argument("--attendees", nargs="+", help="참석자 이메일 (공백 구분)")
    parser.add_argument(
        "--confirm", action="store_true", help="실제 생성 (없으면 dry-run)"
    )
    parser.add_argument("--json", action="store_true", help="stdin으로 JSON 입력")
    args = parser.parse_args()

    # JSON 입력 처리
    if args.json:
        try:
            data = json.load(sys.stdin)
            title = data.get("title", "")
            start_time = data.get("start", "")
            end_time = data.get("end", "")
            description = data.get("description", "")
            location = data.get("location", "")
            attendees = data.get("attendees", [])
            confirm = data.get("confirm", False)
        except json.JSONDecodeError as e:
            print(f"Error: JSON 파싱 실패 - {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # CLI 인자 처리
        if not args.title or not args.start or not args.end:
            print(
                "Error: --title, --start, --end는 필수입니다.", file=sys.stderr
            )
            sys.exit(1)

        title = args.title
        start_time = args.start
        end_time = args.end
        description = args.description
        location = args.location
        attendees = args.attendees
        confirm = args.confirm

    # 인증
    print("🔐 Google Calendar 인증 중...")
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    # Dry-run 모드 결정
    dry_run = not confirm

    # 일정 생성
    result = create_event(
        service,
        title,
        start_time,
        end_time,
        description,
        location,
        attendees,
        dry_run=dry_run,
    )

    if result:
        event_link = result.get("htmlLink", "")
        print(f"\n✅ 일정 생성 완료: {title}")
        print(f"링크: {event_link}")
        sys.exit(0)
    elif dry_run:
        print("\n실제 생성하려면 --confirm 플래그를 추가하세요.")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
