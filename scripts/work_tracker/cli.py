#!/usr/bin/env python3
"""Work Tracker CLI — Git 활동 자동 수집 + 업무 현황 추적"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Windows UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 3-way import for each dependency
try:
    from scripts.work_tracker.collector import GitCollector
    from scripts.work_tracker.storage import WorkTrackerStorage
    from scripts.work_tracker.stream_detector import StreamDetector
    from scripts.work_tracker.metrics import MetricsCalculator
    from scripts.work_tracker.formatter import SlackFormatter
except ImportError:
    try:
        from work_tracker.collector import GitCollector
        from work_tracker.storage import WorkTrackerStorage
        from work_tracker.stream_detector import StreamDetector
        from work_tracker.metrics import MetricsCalculator
        from work_tracker.formatter import SlackFormatter
    except ImportError:
        from .collector import GitCollector
        from .storage import WorkTrackerStorage
        from .stream_detector import StreamDetector
        from .metrics import MetricsCalculator
        from .formatter import SlackFormatter


async def cmd_collect(args):
    """collect 커맨드: git 수집 → DB 저장 → stream 감지"""
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    print(f"Git 수집 중... ({date})")

    collector = GitCollector()
    commits = collector.collect_date(date)
    print(f"   수집: {len(commits)}건")

    if not commits:
        print("   커밋 없음")
        if args.json:
            result = {
                "date": date,
                "commits_collected": 0,
                "commits_saved": 0,
                "streams_detected": 0,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    saved = 0
    streams = []
    async with WorkTrackerStorage() as storage:
        saved = await storage.save_commits(commits)
        print(f"   저장: {saved}건 (신규)")

        # Stream 감지
        detector = StreamDetector(storage)
        streams = await detector.detect_streams(commits)
        await storage.save_streams(streams)
        print(f"   Stream: {len(streams)}건 감지")

    if args.json:
        result = {
            "date": date,
            "commits_collected": len(commits),
            "commits_saved": saved,
            "streams_detected": len(streams),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_summary(args):
    """summary 커맨드: 일일 요약 출력"""
    date = args.date or datetime.now().strftime("%Y-%m-%d")

    async with WorkTrackerStorage() as storage:
        calc = MetricsCalculator(storage)
        summary = await calc.calculate_daily(date)

        commits = await storage.get_commits_by_date(date)
        streams = await storage.get_streams(status="active")

        fmt = SlackFormatter()
        if args.json:
            print(fmt.format_json(summary, commits, streams))
        else:
            print(fmt.format_daily(summary, commits, streams))


async def cmd_streams(args):
    """streams 커맨드: Work Stream 목록"""
    status_filter = args.status if args.status != "all" else None

    async with WorkTrackerStorage() as storage:
        streams = await storage.get_streams(status=status_filter)

    if args.json:
        print(json.dumps([s.to_dict() for s in streams], ensure_ascii=False, indent=2))
    else:
        if not streams:
            print("Work Stream 없음")
            return
        status_labels = {
            "active": "진행 중",
            "idle": "미활동",
            "completed": "완료",
            "new": "신규",
        }
        for s in streams:
            status_text = status_labels.get(s.status.value, s.status.value)
            print(
                f"  [{status_text}] {s.name} ({s.project})"
                f" — {s.total_commits} commits, {s.duration_days}일"
            )


async def cmd_metrics(args):
    """metrics 커맨드: 성과 지표"""
    async with WorkTrackerStorage() as storage:
        calc = MetricsCalculator(storage)
        fmt = SlackFormatter()

        if args.weekly:
            date = args.date or datetime.now().strftime("%Y-%m-%d")
            summary = await calc.calculate_weekly(date)
            streams = await storage.get_streams()
            if args.json:
                print(fmt.format_json(summary, streams=streams))
            else:
                print(fmt.format_weekly(summary, streams))
        else:
            date = args.date or datetime.now().strftime("%Y-%m-%d")
            summary = await calc.calculate_daily(date)
            commits = await storage.get_commits_by_date(date)
            streams = await storage.get_streams(status="active")
            if args.json:
                print(fmt.format_json(summary, commits, streams))
            else:
                print(fmt.format_daily(summary, commits, streams))


async def cmd_post(args):
    """post 커맨드: Slack 전송"""
    if not args.confirm:
        # dry-run 모드 (기본)
        dry_ns = argparse.Namespace(
            weekly=args.weekly,
            date=args.date,
            json=False,
        )
        await cmd_metrics(dry_ns)
        print("\n--- DRY RUN ---")
        print("실제 전송하려면 --confirm 플래그를 추가하세요.")
        return

    # 실제 전송
    print("Slack 전송 중...")
    async with WorkTrackerStorage() as storage:
        calc = MetricsCalculator(storage)
        fmt = SlackFormatter()

        if args.weekly:
            date = args.date or datetime.now().strftime("%Y-%m-%d")
            summary = await calc.calculate_weekly(date)
            streams = await storage.get_streams()
            text = fmt.format_weekly(summary, streams)
        else:
            date = args.date or datetime.now().strftime("%Y-%m-%d")
            summary = await calc.calculate_daily(date)
            commits = await storage.get_commits_by_date(date)
            streams = await storage.get_streams(status="active")
            text = fmt.format_daily(summary, commits, streams)

        # Slack 전송 시도
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
            from lib.slack.client import SlackClient  # noqa: PLC0415

            client = SlackClient()
            channel = args.channel or "C0985UXQN6Q"
            await client.send_message(channel=channel, text=text)
            print(f"Slack 전송 완료 (#{channel})")
        except ImportError:
            print("lib.slack 모듈을 찾을 수 없습니다.")
        except Exception as e:  # noqa: BLE001
            print(f"Slack 전송 실패: {e}")


def build_parser() -> argparse.ArgumentParser:
    """argparse 파서 생성 (테스트에서 재사용 가능)"""
    parser = argparse.ArgumentParser(
        description="Work Tracker — Git 활동 자동 수집 + 업무 현황 추적",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python -m scripts.work_tracker collect
  python -m scripts.work_tracker collect --date 2026-03-17
  python -m scripts.work_tracker summary --json
  python -m scripts.work_tracker streams --status active
  python -m scripts.work_tracker metrics --weekly
  python -m scripts.work_tracker post --weekly --confirm
""",
    )
    subparsers = parser.add_subparsers(dest="command", help="커맨드")

    # collect
    p_collect = subparsers.add_parser("collect", help="지정일 git 수집")
    p_collect.add_argument("--date", help="수집일 (YYYY-MM-DD, 기본: 오늘)")
    p_collect.add_argument("--json", action="store_true", help="JSON 출력")

    # summary
    p_summary = subparsers.add_parser("summary", help="일일 요약")
    p_summary.add_argument("--date", help="날짜 (YYYY-MM-DD, 기본: 오늘)")
    p_summary.add_argument("--json", action="store_true", help="JSON 출력")

    # streams
    p_streams = subparsers.add_parser("streams", help="Work Stream 목록")
    p_streams.add_argument(
        "--status",
        choices=["active", "idle", "completed", "all"],
        default="all",
        help="상태 필터 (기본: all)",
    )
    p_streams.add_argument("--json", action="store_true", help="JSON 출력")

    # metrics
    p_metrics = subparsers.add_parser("metrics", help="성과 지표")
    p_metrics.add_argument("--weekly", action="store_true", help="주간 지표")
    p_metrics.add_argument(
        "--weeks", type=int, default=1, help="주 수 (기본: 1)"
    )
    p_metrics.add_argument("--date", help="기준일 (YYYY-MM-DD)")
    p_metrics.add_argument("--json", action="store_true", help="JSON 출력")

    # post
    p_post = subparsers.add_parser("post", help="Slack 전송")
    p_post.add_argument("--daily", action="store_true", help="일일 (기본)")
    p_post.add_argument("--weekly", action="store_true", help="주간")
    p_post.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="미리보기만 출력 (기본)",
    )
    p_post.add_argument("--confirm", action="store_true", help="실제 전송")
    p_post.add_argument("--date", help="기준일 (YYYY-MM-DD)")
    p_post.add_argument("--channel", help="Slack 채널 ID")
    p_post.add_argument("--json", action="store_true", help="JSON 출력")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Command dispatch
    commands = {
        "collect": cmd_collect,
        "summary": cmd_summary,
        "streams": cmd_streams,
        "metrics": cmd_metrics,
        "post": cmd_post,
    }

    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
