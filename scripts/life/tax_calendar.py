#!/usr/bin/env python3
"""
Tax Calendar Manager - Korean Corporate Tax Event Automation

Generates Google Calendar recurring events for Korean corporate tax deadlines:
- Monthly: Withholding tax (10th), Social insurance (10th)
- Quarterly: VAT (25th of 1/4/7/10)
- Yearly: Corporate tax (Mar 31), Local income tax (Apr 30)

Usage:
    python tax_calendar.py generate --year 2026          # dry-run
    python tax_calendar.py generate --year 2026 --confirm  # create events
    python tax_calendar.py list                          # list configured events
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional

# Windows console UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Google API imports
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

# Paths
CREDENTIALS_DIR = Path(r"C:\claude\json")
CREDENTIALS_FILE = CREDENTIALS_DIR / "desktop_credentials.json"
TOKEN_FILE = CREDENTIALS_DIR / "token_calendar.json"
CONFIG_FILE = Path(r"C:\claude\secretary\config\tax_calendar.json")

# OAuth Scopes
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


class TaxEventFrequency(Enum):
    """Tax event frequency types"""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass
class TaxEvent:
    """Tax event data model"""

    name: str
    frequency: str  # monthly, quarterly, yearly
    day: int
    month: Optional[int] = None  # yearly events
    quarter_months: Optional[list[int]] = None  # quarterly events [1,4,7,10]
    reminder_days: list[int] = field(default_factory=lambda: [7, 3, 1])
    calendar_color: str = "#FF6B6B"
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate and set defaults"""
        if self.frequency == "quarterly" and self.quarter_months is None:
            self.quarter_months = [1, 4, 7, 10]

    def get_frequency_enum(self) -> TaxEventFrequency:
        """Get frequency as enum"""
        return TaxEventFrequency(self.frequency)


# Default corporate tax events (Korean)
CORPORATE_TAX_EVENTS: list[TaxEvent] = [
    TaxEvent("원천세 신고/납부", "monthly", 10),
    TaxEvent("4대보험 납부", "monthly", 10),
    TaxEvent(
        "부가세 신고/납부", "quarterly", 25, quarter_months=[1, 4, 7, 10]
    ),
    TaxEvent("법인세 신고/납부", "yearly", 31, month=3),
    TaxEvent("지방소득세 신고/납부", "yearly", 30, month=4),
]


class TaxCalendarManager:
    """
    Corporate tax calendar manager

    Features:
    - Load tax events from config or use defaults
    - Generate RRULE for recurring events
    - Create Google Calendar events with reminders
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        """
        Initialize manager

        Args:
            config_path: Path to config file (default: CONFIG_FILE)
        """
        self.config_path = config_path or CONFIG_FILE
        self.config = self._load_config()
        self.events = self._load_events()

    def _load_config(self) -> dict:
        """Load configuration from file"""
        if self.config_path.exists():
            with open(self.config_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_events(self) -> list[TaxEvent]:
        """Load tax events from config or use defaults"""
        if not self.config.get("enabled", True):
            return []

        events_config = self.config.get("events", {})
        if not events_config:
            return CORPORATE_TAX_EVENTS

        events: list[TaxEvent] = []
        for key, cfg in events_config.items():
            if cfg.get("enabled", True):
                events.append(
                    TaxEvent(
                        name=cfg.get("name", key),
                        frequency=cfg.get("frequency", "monthly"),
                        day=cfg.get("day", 10),
                        month=cfg.get("month"),
                        quarter_months=cfg.get("quarter_months"),
                        reminder_days=cfg.get("reminder_days", [7, 3, 1]),
                        calendar_color=cfg.get("calendar_color", "#FF6B6B"),
                        enabled=True,
                    )
                )
        return events

    def get_first_occurrence(self, event: TaxEvent, year: int) -> date:
        """
        Get first occurrence date for an event in the given year

        Args:
            event: Tax event
            year: Target year

        Returns:
            First occurrence date
        """
        freq = event.get_frequency_enum()

        if freq == TaxEventFrequency.MONTHLY:
            # First occurrence: January
            return date(year, 1, event.day)

        elif freq == TaxEventFrequency.QUARTERLY:
            # First occurrence: first quarter month
            first_month = event.quarter_months[0] if event.quarter_months else 1
            return date(year, first_month, event.day)

        elif freq == TaxEventFrequency.YEARLY:
            # Single occurrence
            return date(year, event.month or 1, event.day)

        return date(year, 1, 1)

    def build_rrule(self, event: TaxEvent) -> str:
        """
        Build RRULE string for recurring event

        Args:
            event: Tax event

        Returns:
            RRULE string (e.g., "RRULE:FREQ=MONTHLY;BYMONTHDAY=10")
        """
        freq = event.get_frequency_enum()

        if freq == TaxEventFrequency.MONTHLY:
            return f"RRULE:FREQ=MONTHLY;BYMONTHDAY={event.day}"

        elif freq == TaxEventFrequency.QUARTERLY:
            months = ",".join(map(str, event.quarter_months or [1, 4, 7, 10]))
            return f"RRULE:FREQ=YEARLY;BYMONTH={months};BYMONTHDAY={event.day}"

        elif freq == TaxEventFrequency.YEARLY:
            return f"RRULE:FREQ=YEARLY;BYMONTH={event.month};BYMONTHDAY={event.day}"

        return ""

    def build_calendar_event(self, event: TaxEvent, year: int) -> dict:
        """
        Build Google Calendar event structure

        Args:
            event: Tax event
            year: Start year

        Returns:
            Google Calendar event dict
        """
        first_date = self.get_first_occurrence(event, year)
        rrule = self.build_rrule(event)

        calendar_settings = self.config.get("calendar_settings", {})
        all_day = calendar_settings.get("all_day_event", True)

        # Build reminders
        reminders = []
        for days in event.reminder_days:
            reminders.append({"method": "popup", "minutes": days * 24 * 60})

        calendar_event = {
            "summary": event.name,
            "description": f"Secretary 자동 생성 - {event.frequency}\n{rrule}",
            "start": {
                "date": first_date.isoformat(),
                "timeZone": "Asia/Seoul",
            },
            "end": {
                "date": first_date.isoformat(),
                "timeZone": "Asia/Seoul",
            },
            "recurrence": [rrule],
            "reminders": {
                "useDefault": False,
                "overrides": reminders,
            },
        }

        # All-day event uses 'date', timed event uses 'dateTime'
        if not all_day:
            calendar_event["start"] = {
                "dateTime": f"{first_date.isoformat()}T09:00:00",
                "timeZone": "Asia/Seoul",
            }
            calendar_event["end"] = {
                "dateTime": f"{first_date.isoformat()}T09:30:00",
                "timeZone": "Asia/Seoul",
            }

        return calendar_event

    def generate_events(self, year: int) -> list[dict]:
        """
        Generate all calendar events for the year

        Args:
            year: Target year

        Returns:
            List of calendar event dicts
        """
        return [self.build_calendar_event(event, year) for event in self.events]

    def list_events(self) -> list[dict]:
        """
        List all configured tax events

        Returns:
            List of event info dicts
        """
        result = []
        for event in self.events:
            result.append(
                {
                    "name": event.name,
                    "frequency": event.frequency,
                    "day": event.day,
                    "month": event.month,
                    "quarter_months": event.quarter_months,
                    "reminder_days": event.reminder_days,
                    "rrule": self.build_rrule(event),
                }
            )
        return result

    def get_upcoming_events(self, days: int = 30) -> list[dict]:
        """
        Get tax events within the next N days

        Args:
            days: Number of days to look ahead

        Returns:
            List of upcoming tax events with days_until
        """
        from datetime import timedelta

        today = date.today()
        end_date = today + timedelta(days=days)
        upcoming = []

        for event in self.events:
            freq = event.get_frequency_enum()

            # Generate occurrences for current and next year
            for year in [today.year, today.year + 1]:
                if freq == TaxEventFrequency.MONTHLY:
                    # Check each month
                    for month in range(1, 13):
                        try:
                            event_date = date(year, month, event.day)
                            if today <= event_date <= end_date:
                                upcoming.append({
                                    "name": event.name,
                                    "date": event_date.isoformat(),
                                    "days_until": (event_date - today).days,
                                    "frequency": event.frequency,
                                })
                        except ValueError:
                            continue

                elif freq == TaxEventFrequency.QUARTERLY:
                    for month in (event.quarter_months or [1, 4, 7, 10]):
                        try:
                            event_date = date(year, month, event.day)
                            if today <= event_date <= end_date:
                                upcoming.append({
                                    "name": event.name,
                                    "date": event_date.isoformat(),
                                    "days_until": (event_date - today).days,
                                    "frequency": event.frequency,
                                })
                        except ValueError:
                            continue

                elif freq == TaxEventFrequency.YEARLY:
                    try:
                        event_date = date(year, event.month or 1, event.day)
                        if today <= event_date <= end_date:
                            upcoming.append({
                                "name": event.name,
                                "date": event_date.isoformat(),
                                "days_until": (event_date - today).days,
                                "frequency": event.frequency,
                            })
                    except ValueError:
                        continue

        # Sort by days_until and remove duplicates
        upcoming.sort(key=lambda x: x["days_until"])
        return upcoming


def get_credentials() -> Credentials:
    """Google OAuth authentication"""
    if not GOOGLE_API_AVAILABLE:
        print("Error: Google API not available")
        sys.exit(1)

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                print(f"Error: OAuth credentials file not found: {CREDENTIALS_FILE}")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        # Save token
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def create_calendar_events(
    events: list[dict], dry_run: bool = True, quiet: bool = False
) -> list[dict]:
    """
    Create Google Calendar events

    Args:
        events: List of calendar event dicts
        dry_run: If True, only print without creating
        quiet: If True, suppress console output (for JSON mode)

    Returns:
        List of created event results
    """
    if dry_run:
        if not quiet:
            print("\n[DRY-RUN] Events to be created:")
            for event in events:
                print(f"\n  {event['summary']}")
                print(f"    Start: {event['start'].get('date', event['start'].get('dateTime'))}")
                print(f"    RRULE: {event['recurrence'][0]}")
                print(f"    Reminders: {len(event['reminders']['overrides'])} configured")
            print(f"\nTotal: {len(events)} events")
            print("To create events, run with --confirm flag")
        return []

    if not GOOGLE_API_AVAILABLE:
        print("Error: Google API not available")
        return []

    print("Authenticating with Google Calendar...")
    creds = get_credentials()
    service = build("calendar", "v3", credentials=creds)

    results = []
    for event in events:
        try:
            created = (
                service.events()
                .insert(calendarId="primary", body=event)
                .execute()
            )
            print(f"Created: {event['summary']} - {created.get('htmlLink', '')}")
            results.append(
                {
                    "status": "created",
                    "summary": event["summary"],
                    "id": created.get("id"),
                    "link": created.get("htmlLink"),
                }
            )
        except HttpError as e:
            print(f"Failed: {event['summary']} - {e}")
            results.append(
                {
                    "status": "failed",
                    "summary": event["summary"],
                    "error": str(e),
                }
            )

    return results


def main() -> None:
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Tax Calendar Manager - Korean Corporate Tax Events"
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate calendar events")
    gen_parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Target year (default: current year)",
    )
    gen_parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually create events (default: dry-run)",
    )
    gen_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # list command
    list_parser = subparsers.add_parser("list", help="List configured tax events")
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    manager = TaxCalendarManager()

    if args.command == "generate":
        events = manager.generate_events(args.year)

        if args.json:
            # JSON output mode (quiet=True suppresses non-JSON output)
            results = create_calendar_events(events, dry_run=not args.confirm, quiet=True)
            output = {
                "year": args.year,
                "dry_run": not args.confirm,
                "events_count": len(events),
                "events": [
                    {
                        "summary": e["summary"],
                        "start": e["start"].get("date", e["start"].get("dateTime")),
                        "rrule": e["recurrence"][0],
                    }
                    for e in events
                ],
            }
            if results:
                output["results"] = results
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            # Human readable output
            print(f"\nTax Calendar Events for {args.year}")
            print("=" * 50)
            create_calendar_events(events, dry_run=not args.confirm)

    elif args.command == "list":
        events = manager.list_events()

        if args.json:
            print(json.dumps(events, ensure_ascii=False, indent=2))
        else:
            print("\nConfigured Tax Events")
            print("=" * 50)
            for event in events:
                print(f"\n  {event['name']}")
                print(f"    Frequency: {event['frequency']}")
                if event["month"]:
                    print(f"    Month: {event['month']}")
                if event["quarter_months"]:
                    print(f"    Quarters: {event['quarter_months']}")
                print(f"    Day: {event['day']}")
                print(f"    Reminders: D-{', D-'.join(map(str, event['reminder_days']))}")
                print(f"    RRULE: {event['rrule']}")
            print(f"\nTotal: {len(events)} events")


if __name__ == "__main__":
    main()
