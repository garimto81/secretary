#!/usr/bin/env python3
"""
Calendar Analyzer - Google Calendar 일정 분석

Usage:
    python calendar_analyzer.py [--today] [--week] [--days N]

Options:
    --today     오늘 일정만 조회
    --week      이번 주 일정 조회
    --days N    앞으로 N일 일정 조회 (기본: 7일)

Output:
    일정 목록 및 준비 필요 항목
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
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

# 인증 파일 경로 (google-workspace Skill과 동일)
CREDENTIALS_DIR = Path(r"C:\claude\json")
CREDENTIALS_FILE = CREDENTIALS_DIR / "desktop_credentials.json"
TOKEN_FILE = CREDENTIALS_DIR / "token_calendar.json"

# OAuth Scopes
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
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


def get_events(service, start_time: datetime, end_time: datetime) -> list:
    """일정 조회"""
    try:
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start_time.isoformat().replace("+00:00", "Z"),
                timeMax=end_time.isoformat().replace("+00:00", "Z"),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        return events_result.get("items", [])

    except Exception as e:
        print(f"Error: 일정 조회 실패 - {e}")
        return []


def parse_event(event: dict) -> dict:
    """이벤트 파싱"""
    start = event.get("start", {})
    end = event.get("end", {})

    # 시간 또는 종일 이벤트
    start_time = start.get("dateTime", start.get("date", ""))
    end_time = end.get("dateTime", end.get("date", ""))
    is_all_day = "date" in start and "dateTime" not in start

    # 시간 추출
    time_str = ""
    if not is_all_day and start_time:
        try:
            dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            time_str = dt.strftime("%H:%M")
        except:
            time_str = start_time

    # 장소/링크 추출
    location = event.get("location", "")
    conference_link = ""
    conference_data = event.get("conferenceData", {})
    if conference_data:
        entry_points = conference_data.get("entryPoints", [])
        for ep in entry_points:
            if ep.get("entryPointType") == "video":
                conference_link = ep.get("uri", "")
                break

    # 참석자 확인
    attendees = event.get("attendees", [])
    attendee_count = len(attendees)
    response_status = "unknown"
    for attendee in attendees:
        if attendee.get("self"):
            response_status = attendee.get("responseStatus", "unknown")
            break

    # 준비 필요 여부 판단
    needs_preparation = False
    summary = event.get("summary", "").lower()
    description = (
        event.get("description", "").lower() if event.get("description") else ""
    )

    prep_keywords = [
        "발표",
        "presentation",
        "review",
        "데모",
        "demo",
        "미팅",
        "meeting",
        "면접",
        "interview",
    ]
    if any(kw in summary or kw in description for kw in prep_keywords):
        needs_preparation = True

    return {
        "id": event.get("id", ""),
        "summary": event.get("summary", "(제목 없음)"),
        "start_time": start_time,
        "end_time": end_time,
        "time_str": time_str,
        "is_all_day": is_all_day,
        "location": location,
        "conference_link": conference_link,
        "attendee_count": attendee_count,
        "response_status": response_status,
        "needs_preparation": needs_preparation,
        "description": (
            event.get("description", "")[:200] if event.get("description") else ""
        ),
    }


def format_output(events: list, title: str = "일정") -> str:
    """결과 포맷팅"""
    if not events:
        return f"📅 {title}: 일정이 없습니다."

    output = [f"📅 {title} ({len(events)}건)"]

    # 날짜별 그룹화
    current_date = ""
    for event in events:
        start_time = event["start_time"]

        # 날짜 추출
        if "T" in start_time:
            event_date = start_time.split("T")[0]
        else:
            event_date = start_time

        # 날짜 변경 시 헤더 출력
        if event_date != current_date:
            current_date = event_date
            try:
                dt = datetime.fromisoformat(event_date)
                date_str = dt.strftime("%m/%d (%a)")
            except:
                date_str = event_date
            output.append(f"\n  [{date_str}]")

        # 이벤트 출력
        time_str = event["time_str"] if event["time_str"] else "종일"
        location_str = ""
        if event["conference_link"]:
            location_str = " (온라인)"
        elif event["location"]:
            location_str = f" ({event['location'][:20]})"

        prep_icon = " ⚠️" if event["needs_preparation"] else ""
        output.append(f"  ├── {time_str} {event['summary']}{location_str}{prep_icon}")

    # 준비 필요 항목 요약
    prep_events = [e for e in events if e["needs_preparation"]]
    if prep_events:
        output.append("")
        output.append(f"⚠️ 준비 필요 ({len(prep_events)}건)")
        for event in prep_events:
            output.append(f"  ├── {event['summary']}")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Google Calendar 일정 분석기")
    parser.add_argument("--today", action="store_true", help="오늘 일정만 조회")
    parser.add_argument("--week", action="store_true", help="이번 주 일정 조회")
    parser.add_argument("--days", type=int, default=7, help="앞으로 N일 일정 조회")
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    args = parser.parse_args()

    # 인증
    print("🔐 Google Calendar 인증 중...")
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    # 시간 범위 설정
    now = datetime.now(UTC)
    start_time = now

    if args.today:
        # 오늘만
        end_time = now.replace(hour=23, minute=59, second=59)
        title = "오늘 일정"
    elif args.week:
        # 이번 주 (일요일까지)
        days_until_sunday = 6 - now.weekday()
        end_time = now + timedelta(days=days_until_sunday)
        end_time = end_time.replace(hour=23, minute=59, second=59)
        title = "이번 주 일정"
    else:
        # N일 후까지
        end_time = now + timedelta(days=args.days)
        title = f"앞으로 {args.days}일 일정"

    # 일정 조회
    print(f"📅 {title} 조회 중...")
    events = get_events(service, start_time, end_time)

    if not events:
        print(f"📅 {title}: 일정이 없습니다.")
        return

    # 파싱
    parsed_events = [parse_event(event) for event in events]

    # 출력
    if args.json:
        print(json.dumps(parsed_events, ensure_ascii=False, indent=2))
    else:
        print("\n" + format_output(parsed_events, title))


if __name__ == "__main__":
    main()
