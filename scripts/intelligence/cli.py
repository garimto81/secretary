#!/usr/bin/env python3
"""
Intelligence CLI - Project Intelligence 명령줄 인터페이스

Usage:
    python cli.py register <project_id>
    python cli.py analyze [--project ID] [--source slack|gmail|github]
    python cli.py pending [--json]
    python cli.py review <message_id> <project_id>
    python cli.py drafts [--status pending|approved|rejected]
    python cli.py drafts approve <id>
    python cli.py drafts reject <id>
    python cli.py drafts send <id> [--dry-run] [--force]
    python cli.py drafts log [--limit N] [--json]
    python cli.py stats [--json]
    python cli.py cleanup [--days N] [--dry-run]
    python cli.py learn --project ID --source gmail|slack [--label L] [--channel C] [--limit N]
    python cli.py search --project ID "query" [--source gmail|slack] [--limit N] [--json]
    python cli.py knowledge stats [--project ID] [--json]
    python cli.py knowledge cleanup [--days N] [--dry-run]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 경로 추가
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Windows 콘솔 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


REASON_CHOICES = ["부정확함", "어조부적절", "누락정보", "반복", "기타"]


async def get_storage():
    """IntelligenceStorage 인스턴스 생성 및 연결"""
    from scripts.intelligence.context_store import IntelligenceStorage
    storage = IntelligenceStorage()
    await storage.connect()
    return storage


async def get_registry(storage):
    """ProjectRegistry 인스턴스 생성"""
    from scripts.intelligence.project_registry import ProjectRegistry
    registry = ProjectRegistry(storage)
    await registry.load_from_config()
    return registry


async def cmd_register(args):
    """프로젝트 등록"""
    storage = await get_storage()
    try:
        registry = await get_registry(storage)
        count = await registry.load_from_config()
        print(f"config/projects.json에서 {count}개 프로젝트 로드 완료")

        projects = await registry.list_all()
        for p in projects:
            print(f"  - {p['id']}: {p['name']}")
    finally:
        await storage.close()


async def cmd_analyze(args):
    """증분 분석 실행"""
    storage = await get_storage()
    try:
        registry = await get_registry(storage)

        from scripts.intelligence.context_collector import ContextCollector
        collector = ContextCollector(storage, registry)

        sources = [args.source] if args.source else None
        results = await collector.collect(args.project, sources)

        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
        else:
            for project_id, project_result in results.items():
                print(f"\n[{project_id}]")
                for source, detail in project_result.items():
                    if "error" in detail:
                        print(f"  {source}: 오류 - {detail['error']}")
                    else:
                        print(f"  {source}: {detail.get('collected', 0)}개 수집")
    finally:
        await storage.close()


async def cmd_pending(args):
    """미매칭 pending 메시지 조회"""
    storage = await get_storage()
    try:
        messages = await storage.get_pending_messages()

        if args.json:
            print(json.dumps(messages, ensure_ascii=False, indent=2, default=str))
        else:
            if not messages:
                print("pending 메시지 없음")
                return

            print(f"pending 메시지 {len(messages)}건:\n")
            for msg in messages:
                print(f"  #{msg['id']} [{msg['source_channel']}] {msg.get('sender_name', msg.get('sender_id', 'unknown'))}")
                text = msg.get("original_text", "")[:80]
                print(f"    {text}")
                print()
    finally:
        await storage.close()


async def cmd_review(args):
    """pending 메시지 수동 매칭"""
    storage = await get_storage()
    try:
        success = await storage.update_match(
            draft_id=int(args.message_id),
            project_id=args.project_id,
            match_confidence=1.0,
            match_tier="manual",
        )
        if success:
            print(f"메시지 #{args.message_id} → 프로젝트 '{args.project_id}' 매칭 완료")
        else:
            print("매칭 실패")
    finally:
        await storage.close()


async def cmd_drafts(args):
    """초안 목록 조회"""
    storage = await get_storage()
    try:
        drafts = await storage.list_drafts(
            status=args.status,
            project_id=args.project,
        )

        if args.json:
            print(json.dumps(drafts, ensure_ascii=False, indent=2, default=str))
        else:
            if not drafts:
                print("초안 없음")
                return

            print(f"초안 {len(drafts)}건:\n")
            for d in drafts:
                status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(d["status"], "?")
                print(f"  #{d['id']} {status_icon} [{d['source_channel']}] {d.get('sender_name', '-')}")
                print(f"    프로젝트: {d.get('project_id', '미매칭')}")
                print(f"    매칭: {d.get('match_tier', '-')} ({d.get('match_confidence', 0):.2f})")
                if d.get("draft_file"):
                    print(f"    파일: {d['draft_file']}")
                print()
    finally:
        await storage.close()


async def cmd_drafts_approve(args):
    """초안 승인"""
    storage = await get_storage()
    try:
        success = await storage.update_draft_status(
            draft_id=int(args.id),
            status="approved",
            reviewer_note=args.note,
        )
        if success:
            reason = getattr(args, "reason", None)
            modification = getattr(args, "modification", None)
            from scripts.intelligence.feedback_store import FeedbackStore
            fb_store = FeedbackStore(storage)
            await fb_store.save_feedback(
                draft_id=int(args.id),
                decision="approved",
                reason=reason,
                modification_summary=modification,
            )
            reason_info = f" (사유: {reason})" if reason else ""
            print(f"초안 #{args.id} 승인 완료{reason_info}")
        else:
            print("승인 실패")
    finally:
        await storage.close()


async def cmd_drafts_reject(args):
    """초안 거부"""
    storage = await get_storage()
    try:
        success = await storage.update_draft_status(
            draft_id=int(args.id),
            status="rejected",
            reviewer_note=args.note,
        )
        if success:
            reason = getattr(args, "reason", None)
            modification = getattr(args, "modification", None)
            from scripts.intelligence.feedback_store import FeedbackStore
            fb_store = FeedbackStore(storage)
            await fb_store.save_feedback(
                draft_id=int(args.id),
                decision="rejected",
                reason=reason,
                modification_summary=modification,
            )
            reason_info = f" (사유: {reason})" if reason else ""
            print(f"초안 #{args.id} 거부 완료{reason_info}")
        else:
            print("거부 실패")
    finally:
        await storage.close()


async def cmd_drafts_send(args):
    """승인된 초안 전송"""
    storage = await get_storage()
    try:
        # 1. Draft 조회
        draft = await storage.get_draft(int(args.id))
        if not draft:
            print(f"초안 #{args.id}을 찾을 수 없습니다")
            sys.exit(1)

        # 2. Status 검증
        if draft["status"] not in ("approved", "send_failed"):
            print(f"approved 또는 send_failed 상태만 전송 가능합니다 (현재: {draft['status']})")
            sys.exit(1)

        # 3. 전송 정보 표시
        channel = draft.get("source_channel", "unknown")
        recipient = draft.get("sender_id", "unknown")
        recipient_name = draft.get("sender_name", recipient)
        draft_text = draft.get("draft_text", "")
        preview = draft_text[:200] + "..." if len(draft_text) > 200 else draft_text

        print("\n전송 정보:")
        print(f"  채널: {channel}")
        print(f"  수신: {recipient_name} ({recipient})")
        print(f"  내용: {preview}")

        # 4. Dry-run 체크
        if args.dry_run:
            print("\n[DRY RUN] 실제 전송하지 않았습니다.")
            return

        # 5. 확인 프롬프트
        if not args.force:
            confirm = input("\n전송하시겠습니까? [y/N] ").strip().lower()
            if confirm != "y":
                print("전송 취소")
                return

        # 6. 채널 타입 해석 및 어댑터 생성
        from scripts.gateway.models import ChannelType, OutboundMessage
        channel_type = _resolve_channel_type(channel)
        if channel_type == ChannelType.UNKNOWN:
            print(f"지원하지 않는 채널: {channel}")
            sys.exit(1)

        adapter = _create_adapter(channel_type)
        connected = await adapter.connect()
        if not connected:
            await storage.update_draft_send_failed(int(args.id), "어댑터 연결 실패")
            print("어댑터 연결 실패")
            sys.exit(1)

        try:
            # 7. OutboundMessage 생성 및 전송
            outbound = OutboundMessage(
                channel=channel_type,
                to=recipient,
                text=draft_text,
                subject=draft.get("subject"),
                confirmed=True,
                reply_to=draft.get("source_message_id"),
            )

            result = await adapter.send(outbound)

            # 8. SendLogger 기록
            from scripts.intelligence.send_log import SendLogger
            logger = SendLogger()

            if result.success:
                await storage.update_draft_sent(int(args.id), result.message_id)
                logger.log_send(
                    draft_id=int(args.id),
                    channel=channel,
                    recipient=recipient,
                    status="sent",
                    message_id=result.message_id,
                )
                print(f"\n전송 완료: message_id={result.message_id}")
            else:
                await storage.update_draft_send_failed(int(args.id), result.error or "Unknown error")
                logger.log_send(
                    draft_id=int(args.id),
                    channel=channel,
                    recipient=recipient,
                    status="failed",
                    error=result.error,
                )
                print(f"\n전송 실패: {result.error}")
                sys.exit(1)

        finally:
            await adapter.disconnect()

    finally:
        await storage.close()


async def cmd_drafts_log(args):
    """전송 이력 조회"""
    from scripts.intelligence.send_log import SendLogger
    logger = SendLogger()
    records = logger.get_recent(limit=args.limit)

    if not records:
        print("전송 이력 없음")
        return

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        print(f"전송 이력 (최근 {len(records)}건):\n")
        for r in records:
            ts = r.get("timestamp", "?")[:19]
            draft_id = r.get("draft_id", "?")
            ch = r.get("channel", "?")
            recipient = r.get("recipient", "?")
            status = r.get("status", "?")
            error = f" ({r['error']})" if r.get("error") else ""
            print(f"  {ts} | #{draft_id} | {ch:<8} | {recipient} | {status}{error}")


def _resolve_channel_type(source_channel: str):
    """source_channel 문자열을 ChannelType으로 변환"""
    from scripts.gateway.models import ChannelType
    mapping = {
        "slack": ChannelType.SLACK,
        "email": ChannelType.EMAIL,
        "gmail": ChannelType.EMAIL,
        "github": ChannelType.GITHUB,
    }
    return mapping.get(source_channel.lower(), ChannelType.UNKNOWN)


def _create_adapter(channel_type):
    """채널 타입에 따라 어댑터 인스턴스 생성"""
    from scripts.gateway.models import ChannelType
    config_path = Path(r"C:\claude\secretary\config\gateway.json")

    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))

    if channel_type == ChannelType.SLACK:
        from scripts.gateway.adapters.slack import SlackAdapter
        return SlackAdapter(config.get("channels", {}).get("slack", {}))
    elif channel_type == ChannelType.EMAIL:
        from scripts.gateway.adapters.gmail import GmailAdapter
        return GmailAdapter(config.get("channels", {}).get("gmail", {}))
    else:
        raise ValueError(f"지원하지 않는 채널: {channel_type.value}")


async def cmd_undrafted(args):
    """매칭되었지만 draft 미생성 메시지 조회"""
    storage = await get_storage()
    try:
        registry = await get_registry(storage)
        drafts = await storage.get_awaiting_drafts(
            project_id=args.project,
            limit=args.limit,
        )

        if args.json:
            output = []
            for d in drafts:
                entry = dict(d)
                # 프로젝트 컨텍스트 추가
                if d.get("project_id"):
                    context_entries = await storage.get_context_entries(d["project_id"], limit=10)
                    context_parts = []
                    for ce in context_entries:
                        source = ce.get("source", "")
                        title = ce.get("title", "")
                        content = ce.get("content", "")[:500]
                        context_parts.append(f"[{source}] {title}: {content}")
                    entry["project_context"] = "\n".join(context_parts)

                    project = await registry.get(d["project_id"])
                    if project:
                        entry["project_name"] = project.get("name", d["project_id"])
                output.append(entry)

            print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        else:
            if not drafts:
                print("draft 미생성 메시지 없음")
                return

            print(f"draft 미생성 메시지 {len(drafts)}건:\n")
            for d in drafts:
                print(f"  #{d['id']} [{d['source_channel']}] {d.get('sender_name', d.get('sender_id', 'unknown'))}")
                print(f"    프로젝트: {d.get('project_id', '미매칭')}")
                text = d.get("original_text", "")[:80]
                print(f"    메시지: {text}")
                print()
    finally:
        await storage.close()


async def cmd_save_draft(args):
    """draft 텍스트 저장"""
    storage = await get_storage()
    try:
        draft = await storage.get_draft(int(args.id))
        if not draft:
            print(f"초안 #{args.id}을 찾을 수 없습니다")
            return

        # 파일 저장
        draft_file = args.file
        if not draft_file and args.text:
            from datetime import datetime
            from pathlib import Path

            drafts_dir = Path(r"C:\claude\secretary\data\drafts")
            drafts_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_project = (draft.get("project_id") or "unknown").replace("/", "_").replace("\\", "_")
            draft_filename = f"{safe_project}_{draft.get('source_channel', 'unknown')}_{timestamp}.md"
            draft_path = drafts_dir / draft_filename

            draft_content = (
                f"# Draft Response\n\n"
                f"- Project: {draft.get('project_id', 'unknown')}\n"
                f"- Channel: {draft.get('source_channel', 'unknown')}\n"
                f"- Sender: {draft.get('sender_name', draft.get('sender_id', 'unknown'))}\n"
                f"- Match: {draft.get('match_tier', '-')} (confidence: {draft.get('match_confidence', 0):.2f})\n"
                f"- Generated: {datetime.now().isoformat()}\n\n"
                f"## Original Message\n\n"
                f"{(draft.get('original_text') or '')[:2000]}\n\n"
                f"## Draft Response\n\n"
                f"{args.text}\n"
            )
            draft_path.write_text(draft_content, encoding="utf-8")
            draft_file = str(draft_path)

        success = await storage.save_draft_text(
            draft_id=int(args.id),
            draft_text=args.text,
            draft_file=draft_file,
        )

        if success:
            print(f"초안 #{args.id} draft 저장 완료")
            if draft_file:
                print(f"  파일: {draft_file}")
        else:
            print("저장 실패")
    finally:
        await storage.close()


async def cmd_stats(args):
    """통계 조회"""
    storage = await get_storage()
    try:
        stats = await storage.get_stats()

        if args.json:
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            print("Intelligence 통계:")
            print(f"  프로젝트: {stats['projects']}개")
            print(f"  컨텍스트 항목: {stats['context_entries']}개")
            print(f"  pending 초안: {stats['pending_drafts']}개")
            print(f"  미매칭 메시지: {stats['pending_matches']}개")
    finally:
        await storage.close()


async def cmd_cleanup(args):
    """오래된 데이터 정리"""
    storage = await get_storage()
    try:
        counts = await storage.cleanup_old_entries(
            retention_days=args.days,
            dry_run=args.dry_run,
        )

        mode = "[DRY RUN] " if args.dry_run else ""
        print(f"{mode}정리 결과:")
        print(f"  context_entries: {counts.get('context_entries', 0)}건")
        print(f"  draft_responses: {counts.get('draft_responses', 0)}건")

        if args.dry_run:
            print("\n실제 삭제하려면 --dry-run 옵션을 제거하세요.")
    finally:
        await storage.close()


async def cmd_learn(args):
    """Knowledge Store 초기 학습"""
    from scripts.knowledge.bootstrap import KnowledgeBootstrap
    from scripts.knowledge.store import KnowledgeStore

    store = KnowledgeStore()
    await store.init_db()

    bootstrap = KnowledgeBootstrap(store)

    if args.source == "gmail":
        result = await bootstrap.learn_gmail(
            project_id=args.project,
            label=args.label,
            query=args.query,
            limit=args.limit,
        )
    elif args.source == "slack":
        if not args.channel:
            print("Slack 학습에는 --channel이 필요합니다")
            sys.exit(1)
        result = await bootstrap.learn_slack(
            project_id=args.project,
            channel_id=args.channel,
            limit=args.limit,
        )
    else:
        print(f"지원하지 않는 소스: {args.source}")
        sys.exit(1)

    print(f"\n학습 완료 ({result.elapsed_seconds:.1f}초):")
    print(f"  프로젝트: {result.project_id}")
    print(f"  소스: {result.source}")
    print(f"  수집: {result.total_fetched}건")
    print(f"  저장: {result.total_ingested}건")
    print(f"  중복: {result.duplicates_skipped}건")
    if result.errors > 0:
        print(f"  오류: {result.errors}건")


async def cmd_search(args):
    """Knowledge Store 검색"""
    from scripts.knowledge.store import KnowledgeStore

    store = KnowledgeStore()
    await store.init_db()

    results = await store.search(
        query=args.query,
        project_id=args.project,
        source=args.source,
        limit=args.limit,
    )

    if not results:
        print("검색 결과 없음")
        return

    if args.json:
        output = []
        for r in results:
            output.append({
                "id": r.document.id,
                "source": r.document.source,
                "sender": r.document.sender_name,
                "subject": r.document.subject,
                "content": r.document.content[:500],
                "score": r.score,
                "created_at": r.document.created_at.isoformat() if r.document.created_at else None,
            })
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"검색 결과 {len(results)}건:\n")
        for i, r in enumerate(results, 1):
            doc = r.document
            date_str = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else "?"
            source_icon = "📧" if doc.source == "gmail" else "💬"
            print(f"  {i}. {source_icon} [{date_str}] {doc.sender_name}")
            if doc.subject:
                print(f"     제목: {doc.subject}")
            content_preview = doc.content[:200].replace("\n", " ")
            print(f"     {content_preview}")
            print(f"     (score: {r.score:.2f})")
            print()


async def cmd_knowledge_stats(args):
    """Knowledge Store 통계"""
    from scripts.knowledge.store import KnowledgeStore

    store = KnowledgeStore()
    await store.init_db()

    stats = await store.get_stats(project_id=args.project)

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print("Knowledge Store 통계:")
        if "projects" in stats:
            for proj, proj_stats in stats.get("projects", {}).items():
                print(f"\n  [{proj}]")
                print(f"    총 문서: {proj_stats.get('total', 0)}건")
                for source, count in proj_stats.get("by_source", {}).items():
                    print(f"    {source}: {count}건")
        else:
            print(f"  총 문서: {stats.get('total', 0)}건")
            for source, count in stats.get("by_source", {}).items():
                print(f"  {source}: {count}건")


async def cmd_knowledge_cleanup(args):
    """Knowledge Store 정리"""
    from scripts.knowledge.store import KnowledgeStore

    store = KnowledgeStore()
    await store.init_db()

    deleted = await store.cleanup(retention_days=args.days)

    mode = "[DRY RUN] " if args.dry_run else ""
    print(f"{mode}정리 결과: {deleted}건 삭제")
    if args.dry_run:
        print("실제 삭제하려면 --dry-run 옵션을 제거하세요.")


def main():
    parser = argparse.ArgumentParser(
        description="Project Intelligence CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="명령")

    # register
    subparsers.add_parser("register", help="프로젝트 등록 (config에서 로드)")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="증분 분석 실행")
    analyze_parser.add_argument("--project", help="프로젝트 ID")
    analyze_parser.add_argument("--source", choices=["slack", "gmail", "github"], help="소스 필터")
    analyze_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # pending
    pending_parser = subparsers.add_parser("pending", help="미매칭 메시지 조회")
    pending_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # review
    review_parser = subparsers.add_parser("review", help="수동 매칭")
    review_parser.add_argument("message_id", help="메시지 ID")
    review_parser.add_argument("project_id", help="프로젝트 ID")

    # drafts
    drafts_parser = subparsers.add_parser("drafts", help="초안 관리")
    drafts_sub = drafts_parser.add_subparsers(dest="drafts_command")

    # drafts list (기본)
    drafts_parser.add_argument("--status", choices=["pending", "approved", "rejected"], help="상태 필터")
    drafts_parser.add_argument("--project", help="프로젝트 필터")
    drafts_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # drafts approve
    approve_parser = drafts_sub.add_parser("approve", help="초안 승인")
    approve_parser.add_argument("id", help="초안 ID")
    approve_parser.add_argument("--note", default="", help="리뷰 노트")
    approve_parser.add_argument("--reason", choices=REASON_CHOICES, default=None, help="승인 사유")
    approve_parser.add_argument("--modification", default=None, help="수정 내용 요약")

    # drafts reject
    reject_parser = drafts_sub.add_parser("reject", help="초안 거부")
    reject_parser.add_argument("id", help="초안 ID")
    reject_parser.add_argument("--note", default="", help="리뷰 노트")
    reject_parser.add_argument("--reason", choices=REASON_CHOICES, default=None, help="거부 사유")
    reject_parser.add_argument("--modification", default=None, help="수정 내용 요약")

    # drafts send
    send_parser = drafts_sub.add_parser("send", help="승인된 초안 전송")
    send_parser.add_argument("id", help="초안 ID")
    send_parser.add_argument("--dry-run", action="store_true", help="전송하지 않고 내용만 표시")
    send_parser.add_argument("--force", action="store_true", help="확인 프롬프트 생략")

    # drafts log
    log_parser = drafts_sub.add_parser("log", help="전송 이력 조회")
    log_parser.add_argument("--limit", type=int, default=20, help="조회 건수")
    log_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # undrafted
    undrafted_parser = subparsers.add_parser("undrafted", help="draft 미생성 메시지 조회")
    undrafted_parser.add_argument("--project", help="프로젝트 필터")
    undrafted_parser.add_argument("--limit", type=int, default=20, help="최대 조회 수")
    undrafted_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # save-draft
    save_draft_parser = subparsers.add_parser("save-draft", help="draft 텍스트 저장")
    save_draft_parser.add_argument("id", help="초안 ID")
    save_draft_parser.add_argument("--text", required=True, help="draft 텍스트")
    save_draft_parser.add_argument("--file", default=None, help="draft 파일 경로 (생략 시 자동 생성)")

    # stats
    stats_parser = subparsers.add_parser("stats", help="통계 조회")
    stats_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="오래된 데이터 정리")
    cleanup_parser.add_argument("--days", type=int, default=90, help="보관 기간 (기본 90일)")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 건수만 확인")

    # learn
    learn_parser = subparsers.add_parser("learn", help="Knowledge Store 초기 학습")
    learn_parser.add_argument("--project", required=True, help="프로젝트 ID")
    learn_parser.add_argument("--source", required=True, choices=["gmail", "slack"], help="소스")
    learn_parser.add_argument("--label", help="Gmail 라벨")
    learn_parser.add_argument("--query", help="Gmail 검색 쿼리")
    learn_parser.add_argument("--channel", help="Slack 채널 ID")
    learn_parser.add_argument("--limit", type=int, default=100, help="최대 수집 수")

    # search
    search_parser = subparsers.add_parser("search", help="Knowledge Store 검색")
    search_parser.add_argument("query", help="검색 쿼리")
    search_parser.add_argument("--project", required=True, help="프로젝트 ID")
    search_parser.add_argument("--source", choices=["gmail", "slack"], help="소스 필터")
    search_parser.add_argument("--limit", type=int, default=10, help="최대 결과 수")
    search_parser.add_argument("--json", action="store_true", help="JSON 출력")

    # knowledge
    knowledge_parser = subparsers.add_parser("knowledge", help="Knowledge Store 관리")
    knowledge_sub = knowledge_parser.add_subparsers(dest="knowledge_command")

    stats_k_parser = knowledge_sub.add_parser("stats", help="통계 조회")
    stats_k_parser.add_argument("--project", help="프로젝트 필터")
    stats_k_parser.add_argument("--json", action="store_true", help="JSON 출력")

    kcleanup_parser = knowledge_sub.add_parser("cleanup", help="오래된 문서 정리")
    kcleanup_parser.add_argument("--days", type=int, default=180, help="보관 기간")
    kcleanup_parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 건수만 확인")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "register":
        asyncio.run(cmd_register(args))
    elif args.command == "analyze":
        asyncio.run(cmd_analyze(args))
    elif args.command == "pending":
        asyncio.run(cmd_pending(args))
    elif args.command == "review":
        asyncio.run(cmd_review(args))
    elif args.command == "drafts":
        if hasattr(args, "drafts_command") and args.drafts_command == "approve":
            asyncio.run(cmd_drafts_approve(args))
        elif hasattr(args, "drafts_command") and args.drafts_command == "reject":
            asyncio.run(cmd_drafts_reject(args))
        elif hasattr(args, "drafts_command") and args.drafts_command == "send":
            asyncio.run(cmd_drafts_send(args))
        elif hasattr(args, "drafts_command") and args.drafts_command == "log":
            asyncio.run(cmd_drafts_log(args))
        else:
            asyncio.run(cmd_drafts(args))
    elif args.command == "undrafted":
        asyncio.run(cmd_undrafted(args))
    elif args.command == "save-draft":
        asyncio.run(cmd_save_draft(args))
    elif args.command == "stats":
        asyncio.run(cmd_stats(args))
    elif args.command == "cleanup":
        asyncio.run(cmd_cleanup(args))
    elif args.command == "learn":
        asyncio.run(cmd_learn(args))
    elif args.command == "search":
        asyncio.run(cmd_search(args))
    elif args.command == "knowledge":
        if hasattr(args, "knowledge_command") and args.knowledge_command == "stats":
            asyncio.run(cmd_knowledge_stats(args))
        elif hasattr(args, "knowledge_command") and args.knowledge_command == "cleanup":
            asyncio.run(cmd_knowledge_cleanup(args))
        else:
            knowledge_parser.print_help()


if __name__ == "__main__":
    main()
