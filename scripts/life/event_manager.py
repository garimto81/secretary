#!/usr/bin/env python3
"""
Life Event Manager - 생활 이벤트 관리 및 리마인더 시스템

명절(설날, 추석), 기념일, 생일 등의 이벤트를 관리하고
D-N 리마인더를 생성합니다.

Usage:
    python event_manager.py upcoming --days 30    # 앞으로 30일 내 이벤트
    python event_manager.py reminders             # 오늘의 리마인더
    python event_manager.py add --name "이벤트" --month 5 --day 15 --lunar

Examples:
    python event_manager.py upcoming --days 60
    python event_manager.py reminders --json
    python event_manager.py add --name "어머니 생신" --month 5 --day 15 --lunar --type birthday
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Optional

# Windows UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Use relative import to avoid runpy warning
try:
    from scripts.life.lunar_converter import lunar_to_solar
except ImportError:
    from lunar_converter import lunar_to_solar


class EventType(Enum):
    """이벤트 유형"""
    LUNAR_HOLIDAY = "lunar_holiday"  # 명절 (음력)
    ANNIVERSARY = "anniversary"       # 기념일 (양력)
    BIRTHDAY = "birthday"            # 생일 (양력/음력)


@dataclass
class LifeEvent:
    """생활 이벤트 데이터 모델"""
    name: str
    event_type: str  # lunar_holiday, anniversary, birthday
    month: int
    day: int
    is_lunar: bool = False
    reminder_days: List[int] = field(default_factory=lambda: [14, 7, 3])

    def to_dict(self) -> dict:
        """딕셔너리로 변환"""
        return {
            "name": self.name,
            "type": self.event_type,
            "month": self.month,
            "day": self.day,
            "is_lunar": self.is_lunar,
            "reminder_days": self.reminder_days,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LifeEvent":
        """딕셔너리에서 생성"""
        return cls(
            name=data["name"],
            event_type=data.get("type", "anniversary"),
            month=data["month"],
            day=data["day"],
            is_lunar=data.get("is_lunar", False),
            reminder_days=data.get("reminder_days", [14, 7, 3]),
        )


# 고정 명절 (음력)
KOREAN_HOLIDAYS = [
    LifeEvent("설날", "lunar_holiday", 1, 1, is_lunar=True),
    LifeEvent("추석", "lunar_holiday", 8, 15, is_lunar=True),
]

# 기본 설정 파일 경로
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "life_events.json"


class LifeEventManager:
    """
    생활 이벤트 관리자

    Features:
    - 음력/양력 변환 (korean_lunar_calendar)
    - 명절 자동 감지 (설날, 추석)
    - 기념일 설정 파일 로드
    - D-N 리마인더 생성
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        초기화

        Args:
            config_path: 설정 파일 경로 (기본: config/life_events.json)
        """
        self.config_path = config_path or CONFIG_FILE
        self.events: List[LifeEvent] = []
        self._load_events()

    def _load_events(self) -> None:
        """설정 파일에서 이벤트 로드"""
        # 고정 명절 추가
        self.events = list(KOREAN_HOLIDAYS)

        # 설정 파일에서 사용자 이벤트 로드
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                # 명절 설정 확인
                holidays_config = config.get("holidays", {})

                # 설날 비활성화 시 제거
                if not holidays_config.get("seollal", {}).get("enabled", True):
                    self.events = [e for e in self.events if e.name != "설날"]
                else:
                    # 설날 리마인더 설정 적용
                    seollal_reminder = holidays_config.get("seollal", {}).get("reminder_days")
                    if seollal_reminder:
                        for e in self.events:
                            if e.name == "설날":
                                e.reminder_days = seollal_reminder

                # 추석 비활성화 시 제거
                if not holidays_config.get("chuseok", {}).get("enabled", True):
                    self.events = [e for e in self.events if e.name != "추석"]
                else:
                    # 추석 리마인더 설정 적용
                    chuseok_reminder = holidays_config.get("chuseok", {}).get("reminder_days")
                    if chuseok_reminder:
                        for e in self.events:
                            if e.name == "추석":
                                e.reminder_days = chuseok_reminder

                # 사용자 이벤트 추가
                for event_data in config.get("events", []):
                    self.events.append(LifeEvent.from_dict(event_data))

            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: 설정 파일 파싱 오류 - {e}", file=sys.stderr)

    def _get_event_date(self, event: LifeEvent, year: int) -> Optional[date]:
        """
        이벤트의 해당 연도 날짜 계산

        Args:
            event: 이벤트
            year: 연도

        Returns:
            양력 날짜
        """
        if event.is_lunar:
            return lunar_to_solar(year, event.month, event.day)
        else:
            try:
                return date(year, event.month, event.day)
            except ValueError:
                return None

    def get_upcoming_events(self, days: int = 30) -> List[dict]:
        """
        앞으로 N일 내 이벤트 조회

        Args:
            days: 조회할 일수 (기본: 30일)

        Returns:
            이벤트 목록 (날짜순 정렬)
        """
        today = date.today()
        end_date = today + timedelta(days=days)
        current_year = today.year

        upcoming = []

        for event in self.events:
            # 올해 이벤트
            event_date = self._get_event_date(event, current_year)
            if event_date and today <= event_date <= end_date:
                days_until = (event_date - today).days
                upcoming.append({
                    "event": event.name,
                    "type": event.event_type,
                    "date": event_date.isoformat(),
                    "days_until": days_until,
                    "is_lunar": event.is_lunar,
                    "d_day": f"D-{days_until}" if days_until > 0 else "D-Day",
                })

            # 내년 이벤트 (올해 이벤트가 이미 지났을 경우)
            if event_date and event_date < today:
                next_year_date = self._get_event_date(event, current_year + 1)
                if next_year_date and next_year_date <= end_date:
                    days_until = (next_year_date - today).days
                    upcoming.append({
                        "event": event.name,
                        "type": event.event_type,
                        "date": next_year_date.isoformat(),
                        "days_until": days_until,
                        "is_lunar": event.is_lunar,
                        "d_day": f"D-{days_until}" if days_until > 0 else "D-Day",
                    })

        # 날짜순 정렬
        upcoming.sort(key=lambda x: x["days_until"])
        return upcoming

    def get_reminders_for_today(self) -> List[dict]:
        """
        오늘 발송해야 할 리마인더 목록 생성

        Logic:
        1. 모든 이벤트 로드 (설정 파일 + 명절)
        2. 각 이벤트의 올해 날짜 계산 (음력 변환 포함)
        3. 오늘과의 D-day 계산
        4. reminder_days에 포함되면 리마인더 생성

        Returns:
            리마인더 목록
        """
        reminders = []
        today = date.today()
        current_year = today.year

        for event in self.events:
            # 올해 이벤트 날짜
            event_date = self._get_event_date(event, current_year)

            # 올해 이벤트가 이미 지났으면 내년 이벤트 확인
            if event_date and event_date < today:
                event_date = self._get_event_date(event, current_year + 1)

            if not event_date:
                continue

            # D-day 계산
            days_until = (event_date - today).days

            # 리마인더 체크
            if days_until in event.reminder_days:
                reminders.append({
                    "event": event.name,
                    "type": event.event_type,
                    "date": event_date.isoformat(),
                    "days_until": days_until,
                    "message": f"{event.name} D-{days_until}",
                    "is_lunar": event.is_lunar,
                })

            # D-Day 당일
            if days_until == 0:
                reminders.append({
                    "event": event.name,
                    "type": event.event_type,
                    "date": event_date.isoformat(),
                    "days_until": 0,
                    "message": f"오늘은 {event.name}입니다!",
                    "is_lunar": event.is_lunar,
                })

        return reminders

    def add_event(
        self,
        name: str,
        month: int,
        day: int,
        event_type: str = "anniversary",
        is_lunar: bool = False,
        reminder_days: Optional[List[int]] = None,
    ) -> bool:
        """
        새 이벤트 추가

        Args:
            name: 이벤트 이름
            month: 월
            day: 일
            event_type: 이벤트 유형 (anniversary, birthday, lunar_holiday)
            is_lunar: 음력 여부
            reminder_days: 리마인더 일수 목록

        Returns:
            성공 여부
        """
        if reminder_days is None:
            reminder_days = [14, 7, 3]

        new_event = LifeEvent(
            name=name,
            event_type=event_type,
            month=month,
            day=day,
            is_lunar=is_lunar,
            reminder_days=reminder_days,
        )

        # 메모리에 추가
        self.events.append(new_event)

        # 설정 파일에 저장
        return self._save_event(new_event)

    def _save_event(self, event: LifeEvent) -> bool:
        """
        이벤트를 설정 파일에 저장

        Args:
            event: 저장할 이벤트

        Returns:
            성공 여부
        """
        try:
            # 기존 설정 로드
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            else:
                config = {
                    "events": [],
                    "holidays": {
                        "seollal": {"enabled": True, "reminder_days": [14, 7, 3]},
                        "chuseok": {"enabled": True, "reminder_days": [14, 7, 3]},
                    },
                    "default_reminder_days": [14, 7, 3],
                }

            # 이벤트 추가
            config["events"].append(event.to_dict())

            # 저장
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            return True

        except Exception as e:
            print(f"Error: 이벤트 저장 실패 - {e}", file=sys.stderr)
            return False

    def list_all_events(self) -> List[dict]:
        """
        모든 등록된 이벤트 목록 반환

        Returns:
            이벤트 목록
        """
        return [event.to_dict() for event in self.events]


def main():
    parser = argparse.ArgumentParser(
        description="Life Event Manager - 생활 이벤트 관리 및 리마인더"
    )
    subparsers = parser.add_subparsers(dest="command", help="명령어")

    # upcoming 명령
    upcoming_parser = subparsers.add_parser(
        "upcoming", help="앞으로 N일 내 이벤트 조회"
    )
    upcoming_parser.add_argument(
        "--days", type=int, default=30, help="조회할 일수 (기본: 30)"
    )
    upcoming_parser.add_argument(
        "--json", action="store_true", help="JSON 출력"
    )

    # reminders 명령
    reminders_parser = subparsers.add_parser(
        "reminders", help="오늘의 리마인더"
    )
    reminders_parser.add_argument(
        "--json", action="store_true", help="JSON 출력"
    )

    # add 명령
    add_parser = subparsers.add_parser("add", help="새 이벤트 추가")
    add_parser.add_argument("--name", required=True, help="이벤트 이름")
    add_parser.add_argument("--month", type=int, required=True, help="월 (1-12)")
    add_parser.add_argument("--day", type=int, required=True, help="일 (1-31)")
    add_parser.add_argument(
        "--type",
        choices=["anniversary", "birthday", "lunar_holiday"],
        default="anniversary",
        help="이벤트 유형",
    )
    add_parser.add_argument("--lunar", action="store_true", help="음력 날짜")
    add_parser.add_argument(
        "--reminder-days",
        type=int,
        nargs="+",
        default=[14, 7, 3],
        help="리마인더 일수 (기본: 14 7 3)",
    )
    add_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # list 명령
    list_parser = subparsers.add_parser("list", help="모든 이벤트 목록")
    list_parser.add_argument("--json", action="store_true", help="JSON 출력")

    args = parser.parse_args()

    # 명령어 없으면 도움말 출력
    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 매니저 초기화
    manager = LifeEventManager()

    if args.command == "upcoming":
        events = manager.get_upcoming_events(days=args.days)

        if args.json:
            print(json.dumps(events, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== 앞으로 {args.days}일 내 이벤트 ===\n")
            if not events:
                print("예정된 이벤트가 없습니다.")
            else:
                for event in events:
                    lunar_mark = " (음력)" if event["is_lunar"] else ""
                    print(f"  {event['d_day']:>6}  {event['event']}{lunar_mark}")
                    print(f"          {event['date']} ({event['type']})")
                    print()

    elif args.command == "reminders":
        reminders = manager.get_reminders_for_today()

        if args.json:
            print(json.dumps(reminders, ensure_ascii=False, indent=2))
        else:
            print("\n=== 오늘의 리마인더 ===\n")
            if not reminders:
                print("오늘 발송할 리마인더가 없습니다.")
            else:
                for reminder in reminders:
                    print(f"  [{reminder['type']}] {reminder['message']}")
                    print(f"          {reminder['date']}")
                    print()

    elif args.command == "add":
        success = manager.add_event(
            name=args.name,
            month=args.month,
            day=args.day,
            event_type=args.type,
            is_lunar=args.lunar,
            reminder_days=args.reminder_days,
        )

        if args.json:
            result = {
                "success": success,
                "event": {
                    "name": args.name,
                    "month": args.month,
                    "day": args.day,
                    "type": args.type,
                    "is_lunar": args.lunar,
                    "reminder_days": args.reminder_days,
                },
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            if success:
                lunar_mark = " (음력)" if args.lunar else ""
                print(f"\n이벤트 추가 완료: {args.name} ({args.month}/{args.day}{lunar_mark})")
            else:
                print("\n이벤트 추가 실패")
                sys.exit(1)

    elif args.command == "list":
        events = manager.list_all_events()

        if args.json:
            print(json.dumps(events, ensure_ascii=False, indent=2))
        else:
            print("\n=== 등록된 이벤트 목록 ===\n")
            for event in events:
                lunar_mark = " (음력)" if event["is_lunar"] else ""
                print(f"  {event['name']}: {event['month']}/{event['day']}{lunar_mark} ({event['type']})")
                print(f"          리마인더: D-{', D-'.join(map(str, event['reminder_days']))}")
                print()


if __name__ == "__main__":
    main()
