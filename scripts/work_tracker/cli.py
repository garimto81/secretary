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
    from scripts.work_tracker.fs_scanner import FileSystemScanner
except ImportError:
    try:
        from work_tracker.collector import GitCollector
        from work_tracker.storage import WorkTrackerStorage
        from work_tracker.stream_detector import StreamDetector
        from work_tracker.metrics import MetricsCalculator
        from work_tracker.formatter import SlackFormatter
        from work_tracker.fs_scanner import FileSystemScanner
    except ImportError:
        from .collector import GitCollector
        from .storage import WorkTrackerStorage
        from .stream_detector import StreamDetector
        from .metrics import MetricsCalculator
        from .formatter import SlackFormatter
        from .fs_scanner import FileSystemScanner


def _create_ai_analyzer(args):
    """AI 분석기 생성 — v4.0: 항상 None (Claude Code가 직접 분석)"""
    return None


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
        summary = await calc.calculate_daily(date, use_snapshots=True)

        commits = await storage.get_commits_by_date(date)
        streams = await storage.get_streams(status="active")

        fmt = SlackFormatter()
        if args.json:
            # v4.0: JSON에 스냅샷 데이터 포함 (Claude Code가 읽을 데이터)
            snapshots = await storage.get_latest_snapshots()
            snapshot_data = [s.to_dict() for s in snapshots] if snapshots else []
            json_str = fmt.format_json(summary, commits, streams)
            # JSON에 snapshots 필드 추가
            data = json.loads(json_str)
            data["snapshots"] = snapshot_data
            print(json.dumps(data, ensure_ascii=False, indent=2))
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
            summary = await calc.calculate_daily(date, use_snapshots=True)
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

    # --report-file: Claude 분석 결과 파일 우선 사용
    report_file = getattr(args, "report_file", None)
    if report_file:
        report_path = Path(report_file)
        if report_path.exists():
            text = report_path.read_text(encoding="utf-8").strip()
            print(f"   보고서 파일 로드: {report_path.name}")
        else:
            print(f"보고서 파일 없음: {report_file}")
            print("SlackFormatter fallback으로 전환합니다.")
            report_file = None

    # fallback: SlackFormatter 기계적 포맷팅
    if not report_file:
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
        client.send_message(channel=channel, text=text)
        print(f"Slack 전송 완료 (#{channel})")
    except ImportError:
        print("lib.slack 모듈을 찾을 수 없습니다.")
    except Exception as e:  # noqa: BLE001
        print(f"Slack 전송 실패: {e}")


async def cmd_scan(args):
    """scan 커맨드: 파일시스템 스냅샷 생성"""
    today = datetime.now().strftime("%Y-%m-%d")
    scanner = FileSystemScanner()

    if args.project:
        print(f"스캔 중... ({args.project})")
        records = scanner.scan_project(args.project)
        scan_data = {args.project: records} if records else {}
    else:
        print("전체 스캔 중...")
        scan_data = scanner.scan_all()

    # DB 저장
    total_files = 0
    total_size = 0
    db_records = []
    for proj_name, records in scan_data.items():
        for r in records:
            db_records.append({
                "project_dir": proj_name,
                "file_path": r.file_path,
                "file_size": r.file_size,
                "modified_at": r.modified_at,
                "snapshot_date": today,
            })
            total_size += r.file_size
        total_files += len(records)

    async with WorkTrackerStorage() as storage:
        saved = await storage.save_file_snapshots(db_records)

    print(f"  프로젝트: {len(scan_data)}개")
    print(f"  파일: {total_files:,}개")
    print(f"  용량: {total_size / 1024 / 1024:.1f} MB")
    print(f"  저장: {saved:,}건")

    if args.json:
        result = {
            "date": today,
            "projects": len(scan_data),
            "files": total_files,
            "size_mb": round(total_size / 1024 / 1024, 1),
            "saved": saved,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_changes(args):
    """changes 커맨드: 최근 스냅샷 대비 파일시스템 변경 감지"""
    scanner = FileSystemScanner()

    # 현재 파일시스템 live 스캔
    print("파일시스템 스캔 중...")
    if args.project:
        live_records = scanner.scan_project(args.project)
        live_dicts = [r.to_dict() for r in live_records]
    else:
        all_data = scanner.scan_all()
        live_dicts = []
        for records in all_data.values():
            live_dicts.extend(r.to_dict() for r in records)

    # DB에서 마지막 스냅샷 로드
    async with WorkTrackerStorage() as storage:
        old_snapshot = await storage.get_latest_file_snapshot(
            project_dir=args.project if args.project else None
        )

    if not old_snapshot:
        print("기존 스냅샷 없음 — 먼저 'scan' 커맨드로 baseline을 생성하세요.")
        return

    snapshot_date = old_snapshot[0]["snapshot_date"] if old_snapshot else "?"
    print(f"비교 기준: {snapshot_date} 스냅샷")

    # days 필터: modified_at이 N일 이내인 변경만
    if args.days:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=args.days)).isoformat()
        live_dicts = [r for r in live_dicts if r["modified_at"] >= cutoff]
        old_snapshot_filtered = [r for r in old_snapshot if r["modified_at"] >= cutoff]
    else:
        old_snapshot_filtered = old_snapshot

    # 변경 감지
    changes = scanner.detect_changes(old_snapshot_filtered, live_dicts)
    project_summary = scanner.summarize_by_project(changes)

    total_added = len(changes["added"])
    total_modified = len(changes["modified"])
    total_deleted = len(changes["deleted"])

    if not project_summary:
        print("변경 프로젝트 없음")
    else:
        days_label = f" (최근 {args.days}일)" if args.days else ""
        print(f"\n변경 프로젝트{days_label}: {len(project_summary)}개")
        for proj, counts in sorted(project_summary.items()):
            parts = []
            if counts["added"]:
                parts.append(f"+{counts['added']}")
            if counts["modified"]:
                parts.append(f"~{counts['modified']}")
            if counts["deleted"]:
                parts.append(f"-{counts['deleted']}")
            print(f"  {proj}: {' '.join(parts)} 파일")

    if args.detail:
        for change_type, label in [("added", "추가"), ("modified", "수정"), ("deleted", "삭제")]:
            items = changes[change_type]
            if items:
                print(f"\n{label} ({len(items)}건):")
                for item in items[:20]:  # 최대 20건만
                    print(f"  {item['file_path']}")
                if len(items) > 20:
                    print(f"  ... 외 {len(items) - 20}건")

    if args.json:
        result = {
            "snapshot_date": snapshot_date,
            "total_added": total_added,
            "total_modified": total_modified,
            "total_deleted": total_deleted,
            "projects": project_summary,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))


async def cmd_diagnose(args):
    """diagnose 커맨드: 매핑 vs 물리 레포 불일치 진단 + 파일시스템 변경 감지"""
    from pathlib import Path
    import json as json_mod

    base_dir = Path(r"C:\claude")
    config_path = Path(r"C:\claude\secretary\config\projects.json")

    # 물리 레포 탐색 (git 있는 것)
    physical = set()
    if (base_dir / ".git").exists():
        physical.add(base_dir.name)
    for item in sorted(base_dir.iterdir()):
        if item.is_dir() and (item / ".git").exists():
            physical.add(item.name)

    # 전체 디렉토리 (git 유무 무관)
    all_dirs = set()
    for item in sorted(base_dir.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            all_dirs.add(item.name)

    # 매핑 로드
    with open(config_path, encoding="utf-8") as f:
        mapping = set(json_mod.load(f).get("local_repo_mapping", {}).keys())

    # 비교
    mapped_no_physical = mapping - physical
    physical_no_mapped = physical - mapping

    print(f"물리 레포: {len(physical)}개 (git)")
    print(f"전체 프로젝트: {len(all_dirs)}개 (파일시스템)")
    print(f"매핑: {len(mapping)}개")

    if mapped_no_physical:
        print(f"\n매핑 O + 물리 X ({len(mapped_no_physical)}개):")
        for name in sorted(mapped_no_physical):
            reason = "git 없음" if (base_dir / name).exists() else "디렉토리 없음"
            print(f"  - {name} ({reason})")

    if physical_no_mapped:
        print(f"\n물리 O + 매핑 X ({len(physical_no_mapped)}개):")
        for name in sorted(physical_no_mapped):
            print(f"  - {name}")

    if not mapped_no_physical and not physical_no_mapped:
        print("\n불일치 없음 — 매핑 정상")

    # 파일시스템 변경 감지 (최근 5일)
    print("\n--- 파일시스템 변경 (최근 5일) ---")
    scanner = FileSystemScanner()
    async with WorkTrackerStorage() as storage:
        old_snapshot = await storage.get_latest_file_snapshot()

    if old_snapshot:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=5)).isoformat()
        all_data = scanner.scan_all()
        live_dicts = []
        for records in all_data.values():
            live_dicts.extend(r.to_dict() for r in records)

        live_recent = [r for r in live_dicts if r["modified_at"] >= cutoff]
        old_recent = [r for r in old_snapshot if r["modified_at"] >= cutoff]

        changes = scanner.detect_changes(old_recent, live_recent)
        project_summary = scanner.summarize_by_project(changes)

        if project_summary:
            print(f"최근 5일 변경: {len(project_summary)}개 프로젝트")
            for proj, counts in sorted(project_summary.items()):
                parts = []
                if counts["added"]:
                    parts.append(f"+{counts['added']}")
                if counts["modified"]:
                    parts.append(f"~{counts['modified']}")
                if counts["deleted"]:
                    parts.append(f"-{counts['deleted']}")
                print(f"  {proj}: {' '.join(parts)} 파일")
        else:
            print("변경 프로젝트 없음")
    else:
        print("스냅샷 없음 — 'scan' 커맨드로 baseline 생성 필요")

    if args.json:
        result = {
            "physical_count": len(physical),
            "all_dirs_count": len(all_dirs),
            "mapping_count": len(mapping),
            "mapped_no_physical": sorted(mapped_no_physical),
            "physical_no_mapped": sorted(physical_no_mapped),
        }
        print(json_mod.dumps(result, ensure_ascii=False, indent=2))


async def cmd_snapshot(args):
    """snapshot 커맨드: 프로젝트 스냅샷 생성"""
    print("프로젝트 스냅샷 생성 중...")

    try:
        from scripts.work_tracker.snapshot_builder import SnapshotBuilder
    except ImportError:
        try:
            from work_tracker.snapshot_builder import SnapshotBuilder
        except ImportError:
            from .snapshot_builder import SnapshotBuilder

    async with WorkTrackerStorage() as storage:
        builder = SnapshotBuilder(storage)

        if args.project:
            snapshot = await builder.build_project(args.project)
            if snapshot:
                print(f"\n스냅샷 생성 완료: {snapshot.project}")
                print(f"  진행률: {snapshot.estimated_progress}%")
                print(f"  레포: {', '.join(snapshot.repos)}")
                print(f"  PRD: {len(snapshot.prd_status)}건")
                print(f"  문서: {len(snapshot.doc_inventory)}건")
                if args.json:
                    print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
            else:
                print(f"프로젝트 '{args.project}' 스냅샷 생성 실패")
        else:
            snapshots = await builder.build_all()
            print(f"\n전체 스냅샷 생성 완료: {len(snapshots)}개 프로젝트")
            for s in snapshots:
                prd_count = len(s.prd_status)
                doc_count = len(s.doc_inventory)
                print(
                    f"  {s.project}: {s.estimated_progress}% "
                    f"(레포 {len(s.repos)} / PRD {prd_count} / 문서 {doc_count})"
                )
            if args.json:
                print(json.dumps(
                    [s.to_dict() for s in snapshots],
                    ensure_ascii=False, indent=2,
                ))


async def cmd_update_analysis(args):
    """update-analysis 커맨드: 스냅샷에 분석 결과 저장 (Claude Code → DB)"""
    project = args.project
    if not project:
        print("--project 필수")
        return

    async with WorkTrackerStorage() as storage:
        progress = args.progress
        summary = args.summary or ""
        milestones = []
        risks = []

        if args.milestones:
            milestones = [{"name": m.strip(), "status": "진행중"} for m in args.milestones.split(",")]
        if args.risks:
            risks = [r.strip() for r in args.risks.split(",")]

        await storage.update_snapshot_analysis(
            project=project,
            progress=progress,
            summary=summary,
            milestones=milestones,
            risks=risks,
        )
        print(f"분석 결과 저장 완료: {project} (진행률 {progress}%)")
        if summary:
            print(f"   요약: {summary}")


async def cmd_roadmap(args):
    """roadmap 커맨드: 프로젝트 로드맵 관리

    액션:
      gantt     — 기존 브랜치 기반 Mermaid gantt (RoadmapGenerator)
      init      — 프로젝트 로드맵 심층 분석 + DB 초기화 (DeepAnalyzer)
      update    — 일일 업데이트 (DailyUpdater)
      recommend — 오늘 추천 Task (TaskRecommender)
      report    — Mermaid Gantt 보고서 저장 + ASCII 출력 (RoadmapFormatter)
      status    — ASCII 현황 출력 (기본)
    """
    action = getattr(args, "action", "status")
    project = getattr(args, "project", None)

    # ------------------------------------------------------------------
    # gantt: 기존 브랜치 기반 Mermaid gantt 유지 (RoadmapGenerator)
    # ------------------------------------------------------------------
    if action == "gantt":
        try:
            from scripts.work_tracker.roadmap_generator import RoadmapGenerator
        except ImportError:
            try:
                from work_tracker.roadmap_generator import RoadmapGenerator
            except ImportError:
                from .roadmap_generator import RoadmapGenerator

        gen = RoadmapGenerator()

        if getattr(args, "render", False):
            channel = args.channel or "C0985UXQN6Q"
            if getattr(args, "slack", False):
                sent = gen.render_and_send(channel=channel, project=project)
                print(f"로드맵 전송 완료: {len(sent)}건")
            else:
                import sys as _sys
                _sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
                from lib.google_docs.mermaid_renderer import render_mermaid

                roadmaps = {}
                if project:
                    code = gen.generate_project_roadmap(project)
                    if code:
                        roadmaps[project] = code
                else:
                    roadmaps = gen.generate_all_roadmaps()

                for proj_name, mermaid_code in roadmaps.items():
                    png_path = render_mermaid(mermaid_code)
                    if png_path:
                        print(f"  {proj_name}: {png_path}")
                    else:
                        print(f"  {proj_name}: 렌더링 실패")
        else:
            if project:
                code = gen.generate_project_roadmap(project)
                if code:
                    print(f"\n```mermaid\n{code}\n```")
                else:
                    print(f"프로젝트 '{project}'에 활성 브랜치 없음")
            else:
                roadmaps = gen.generate_all_roadmaps()
                if not roadmaps:
                    print("로드맵 생성 대상 없음")
                for proj_name, code in roadmaps.items():
                    print(f"\n--- {proj_name} ---")
                    print(f"```mermaid\n{code}\n```")
        return

    # ------------------------------------------------------------------
    # init: 심층 분석으로 DB 초기화
    # ------------------------------------------------------------------
    if action == "init":
        if not project:
            print("--project 필수 (예: --project EBS)")
            return
        try:
            from scripts.work_tracker.roadmap.deep_analyzer import DeepAnalyzer
        except ImportError:
            try:
                from work_tracker.roadmap.deep_analyzer import DeepAnalyzer
            except ImportError:
                from .roadmap.deep_analyzer import DeepAnalyzer

        print(f"로드맵 심층 분석 시작: {project}")
        analyzer = DeepAnalyzer()
        result = await analyzer.init_roadmap(project)
        print(f"완료: {result}")
        return

    # ------------------------------------------------------------------
    # update: 일일 업데이트
    # ------------------------------------------------------------------
    if action == "update":
        try:
            from scripts.work_tracker.roadmap.daily_updater import DailyUpdater
        except ImportError:
            try:
                from work_tracker.roadmap.daily_updater import DailyUpdater
            except ImportError:
                from .roadmap.daily_updater import DailyUpdater

        updater = DailyUpdater()
        proj = project or "EBS"
        result = await updater.update(proj, getattr(args, "date", None))
        print(f"업데이트: {result}")
        return

    # ------------------------------------------------------------------
    # recommend: 오늘 추천 Task
    # ------------------------------------------------------------------
    if action == "recommend":
        try:
            from scripts.work_tracker.roadmap.recommender import TaskRecommender
        except ImportError:
            try:
                from work_tracker.roadmap.recommender import TaskRecommender
            except ImportError:
                from .roadmap.recommender import TaskRecommender

        recommender = TaskRecommender()
        proj = project or "EBS"
        top = getattr(args, "top", 5)
        recommendations = await recommender.recommend(proj, top)
        if getattr(args, "json", False):
            print(json.dumps(recommendations, ensure_ascii=False, indent=2))
        else:
            print(f"\n=== {proj} 오늘 추천 Task ===\n")
            for i, rec in enumerate(recommendations, 1):
                print(f"  {i}. [{rec['priority'].upper()}] {rec['title']}")
                print(f"     Phase: {rec['phase']} > {rec['milestone']}")
                print(f"     이유: {rec['reason']}")
                print()
        return

    # ------------------------------------------------------------------
    # report: Mermaid Gantt 파일 저장 + ASCII 출력
    # ------------------------------------------------------------------
    if action == "report":
        try:
            from scripts.work_tracker.roadmap.formatter import RoadmapFormatter
        except ImportError:
            try:
                from work_tracker.roadmap.formatter import RoadmapFormatter
            except ImportError:
                from .roadmap.formatter import RoadmapFormatter

        fmt = RoadmapFormatter()
        proj = project or "EBS"

        if getattr(args, "slack", False):
            text = await fmt.format_slack(proj)
            print(text)
            # Slack 전송
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))
                from lib.slack.client import SlackClient  # noqa: PLC0415

                client = SlackClient()
                channel = getattr(args, "channel", None) or "C0985UXQN6Q"
                if getattr(args, "confirm", False):
                    client.send_message(channel=channel, text=text)
                    print(f"Slack 전송 완료 (#{channel})")
                else:
                    print("\n[dry-run] --confirm 추가 시 실제 전송됩니다.")
            except ImportError:
                print("lib.slack 모듈을 찾을 수 없습니다.")
            except Exception as e:  # noqa: BLE001
                print(f"Slack 전송 실패: {e}")
        else:
            mermaid = await fmt.format_mermaid_gantt(proj)
            if mermaid:
                report_dir = Path(r"C:\claude\task_manager\docs\02-design")
                report_dir.mkdir(parents=True, exist_ok=True)
                report_file = report_dir / f"{proj.lower()}-roadmap.md"
                report_file.write_text(
                    f"# {proj} 로드맵\n\n```mermaid\n{mermaid}\n```\n",
                    encoding="utf-8",
                )
                print(f"저장: {report_file}")
            else:
                print("Gantt 생성 불가 (날짜 정보 없는 Task)")

            ascii_status = await fmt.format_ascii_status(proj)
            print(ascii_status)
        return

    # ------------------------------------------------------------------
    # status (기본): ASCII 현황 출력
    # ------------------------------------------------------------------
    if action == "status":
        if not project:
            # 전체 프로젝트 요약
            config_path = Path(r"C:\claude\secretary\config\projects.json")
            try:
                import json as _json
                mapping = _json.loads(config_path.read_text(encoding="utf-8"))
                projects = sorted(set(
                    info["project"]
                    for info in mapping.get("local_repo_mapping", {}).values()
                    if "project" in info
                ))
            except Exception:
                projects = ["EBS", "WSOPTV", "Secretary"]

            try:
                from scripts.work_tracker.roadmap.storage import RoadmapStorage
            except ImportError:
                try:
                    from work_tracker.roadmap.storage import RoadmapStorage
                except ImportError:
                    from .roadmap.storage import RoadmapStorage

            async with RoadmapStorage() as storage:
                for proj in projects:
                    summary = await storage.get_project_summary(proj)
                    if summary["tasks"]["total"] == 0:
                        continue
                    t = summary["tasks"]
                    print(
                        f"  {proj}: {t['total']} tasks | "
                        f"✓{t['done']} ●{t['in_progress']} ○{t['pending']} ✗{t['blocked']}"
                    )
        else:
            try:
                from scripts.work_tracker.roadmap.formatter import RoadmapFormatter
            except ImportError:
                try:
                    from work_tracker.roadmap.formatter import RoadmapFormatter
                except ImportError:
                    from .roadmap.formatter import RoadmapFormatter

            fmt = RoadmapFormatter()
            ascii_status = await fmt.format_ascii_status(project)
            print(ascii_status)

            if getattr(args, "json", False):
                try:
                    from scripts.work_tracker.roadmap.storage import RoadmapStorage
                except ImportError:
                    try:
                        from work_tracker.roadmap.storage import RoadmapStorage
                    except ImportError:
                        from .roadmap.storage import RoadmapStorage

                async with RoadmapStorage() as storage:
                    summary = await storage.get_project_summary(project)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
        return

    print(f"알 수 없는 액션: {action}. choices: init, update, recommend, report, status, gantt")


async def cmd_daily(args):
    """daily 커맨드: collect + post 원스텝"""
    # Step 1: collect
    collect_ns = argparse.Namespace(
        date=args.date, json=False,
    )
    await cmd_collect(collect_ns)

    # Step 2: post (항상 스냅샷 참조)
    post_ns = argparse.Namespace(
        weekly=args.weekly, date=args.date,
        confirm=args.confirm, channel=args.channel,
        report_file=getattr(args, "report_file", None),
        json=False, dry_run=not args.confirm,
    )
    await cmd_post(post_ns)


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
  python -m scripts.work_tracker daily --confirm
""",
    )
    subparsers = parser.add_subparsers(dest="command", help="커맨드")

    # collect
    p_collect = subparsers.add_parser("collect", help="지정일 git 수집")
    p_collect.add_argument("--date", help="수집일 (YYYY-MM-DD, 기본: 오늘)")
    p_collect.add_argument("--json", action="store_true", help="JSON 출력")
    p_collect.add_argument("--no-ai", action="store_true", help="AI 분석 건너뛰기")

    # summary
    p_summary = subparsers.add_parser("summary", help="일일 요약")
    p_summary.add_argument("--date", help="날짜 (YYYY-MM-DD, 기본: 오늘)")
    p_summary.add_argument("--json", action="store_true", help="JSON 출력")
    p_summary.add_argument("--no-ai", action="store_true", help="AI 분석 건너뛰기")

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
    p_metrics.add_argument("--no-ai", action="store_true", help="AI 분석 건너뛰기")

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
    p_post.add_argument("--report-file", dest="report_file", help="Claude 분석 보고서 파일 경로 (우선 사용)")
    p_post.add_argument("--json", action="store_true", help="JSON 출력")

    # daily (collect + post 원스텝)
    p_daily = subparsers.add_parser("daily", help="일일 수집 + Slack 전송")
    p_daily.add_argument("--confirm", action="store_true", help="실제 전송")
    p_daily.add_argument("--weekly", action="store_true", help="주간 모드")
    p_daily.add_argument("--date", help="기준일 (YYYY-MM-DD, 기본: 오늘)")
    p_daily.add_argument("--channel", help="Slack 채널 ID")
    p_daily.add_argument("--no-ai", action="store_true", help="AI 분석 건너뛰기")
    p_daily.add_argument("--all", action="store_true", help="스냅샷 참조 + GitHub 포함")

    # roadmap
    p_roadmap = subparsers.add_parser("roadmap", help="프로젝트 로드맵 관리")
    p_roadmap.add_argument(
        "action", nargs="?", default="status",
        choices=["init", "update", "recommend", "report", "status", "gantt"],
        help="액션 (기본: status)",
    )
    p_roadmap.add_argument("--project", help="특정 프로젝트 (기본: 전체)")
    p_roadmap.add_argument("--render", action="store_true", help="PNG 파일 생성")
    p_roadmap.add_argument("--slack", action="store_true", help="Slack 전송")
    p_roadmap.add_argument("--channel", help="Slack 채널 ID")
    p_roadmap.add_argument("--json", action="store_true", help="JSON 출력")
    p_roadmap.add_argument("--date", help="기준일 (YYYY-MM-DD)")
    p_roadmap.add_argument("--top", type=int, default=5, help="추천 개수 (기본: 5)")
    p_roadmap.add_argument("--confirm", action="store_true", help="실제 Slack 전송")

    # scan (파일시스템 스냅샷)
    p_scan = subparsers.add_parser("scan", help="파일시스템 스냅샷 생성")
    p_scan.add_argument("--project", help="특정 프로젝트만 (기본: 전체)")
    p_scan.add_argument("--json", action="store_true", help="JSON 출력")

    # changes (파일시스템 변경 감지)
    p_changes = subparsers.add_parser("changes", help="파일시스템 변경 감지")
    p_changes.add_argument("--project", help="특정 프로젝트만")
    p_changes.add_argument("--days", type=int, help="최근 N일 변경만 (기본: 전체)")
    p_changes.add_argument("--detail", action="store_true", help="변경 파일 상세 출력")
    p_changes.add_argument("--json", action="store_true", help="JSON 출력")

    # diagnose
    p_diag = subparsers.add_parser("diagnose", help="매핑 vs 물리 레포 불일치 진단")
    p_diag.add_argument("--json", action="store_true", help="JSON 출력")

    # snapshot (프로젝트 스냅샷 생성)
    p_snap = subparsers.add_parser("snapshot", help="프로젝트 스냅샷 생성 (최초 1회)")
    p_snap.add_argument("--project", help="특정 프로젝트만 (기본: 전체)")
    p_snap.add_argument("--refresh", action="store_true", help="기존 스냅샷 갱신")
    p_snap.add_argument("--json", action="store_true", help="JSON 출력")
    p_snap.add_argument("--no-ai", action="store_true", help="AI 분석 건너뛰기")

    # update-analysis (스냅샷 분석 결과 저장)
    p_update = subparsers.add_parser("update-analysis", help="스냅샷에 분석 결과 저장")
    p_update.add_argument("--project", required=True, help="프로젝트명")
    p_update.add_argument("--progress", type=int, default=0, help="진행률 (0-100)")
    p_update.add_argument("--summary", help="프로젝트 요약")
    p_update.add_argument("--milestones", help="마일스톤 (쉼표 구분)")
    p_update.add_argument("--risks", help="위험 요소 (쉼표 구분)")

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
        "daily": cmd_daily,
        "roadmap": cmd_roadmap,
        "scan": cmd_scan,
        "changes": cmd_changes,
        "diagnose": cmd_diagnose,
        "snapshot": cmd_snapshot,
        "update-analysis": cmd_update_analysis,
    }

    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
