#!/usr/bin/env python3
"""
Notification Analyzer - Android 알림 분석 스크립트

Usage:
    python notification_analyzer.py [--days N] [--app APP] [--json]

Options:
    --days N    최근 N일 알림 분석 (기본: 3일)
    --app APP   특정 앱만 분석 (kakao, whatsapp, line, telegram, sms)
    --json      JSON 형식 출력

Output:
    긴급 알림, 미응답 메시지 등 분석 결과
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 기본 설정
DEFAULT_DB = Path(r"C:\claude\json\notifications.db")

# 앱 패키지명 매핑
APP_PACKAGES = {
    "kakao": "com.kakao.talk",
    "whatsapp": "com.whatsapp",
    "line": "jp.naver.line.android",
    "telegram": "org.telegram.messenger",
    "sms": "com.google.android.apps.messaging",
}

# 앱 이름 역매핑
PACKAGE_TO_NAME = {v: k for k, v in APP_PACKAGES.items()}


def get_notifications(
    db_path: Path,
    days: int = 3,
    app_filter: str | None = None
) -> list:
    """SQLite에서 알림 조회"""
    if not db_path.exists():
        print(f"Error: Database 파일이 없습니다 - {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 날짜 필터
    date_filter = (datetime.now() - timedelta(days=days)).isoformat()

    # 쿼리 구성
    if app_filter:
        package = APP_PACKAGES.get(app_filter, app_filter)
        cursor.execute("""
            SELECT * FROM notifications
            WHERE timestamp >= ?
              AND app = ?
            ORDER BY timestamp DESC
        """, (date_filter, package))
    else:
        cursor.execute("""
            SELECT * FROM notifications
            WHERE timestamp >= ?
            ORDER BY timestamp DESC
        """, (date_filter,))

    rows = cursor.fetchall()
    conn.close()

    # dict 변환
    notifications = []
    for row in rows:
        notifications.append({
            "id": row["id"],
            "app": row["app"],
            "app_name": PACKAGE_TO_NAME.get(row["app"], row["app"]),
            "title": row["title"],
            "text": row["text"],
            "timestamp": row["timestamp"],
            "conversation_id": row["conversation_id"],
            "is_group": bool(row["is_group"]),
            "received_at": row["received_at"],
        })

    return notifications


def analyze_notifications(notifications: list) -> dict:
    """알림 분석 (긴급 키워드, 미응답 등)"""
    # 긴급 키워드
    urgent_keywords = [
        "긴급", "urgent", "asap", "immediately",
        "오늘까지", "today", "지금", "now",
        "빨리", "quick", "fast", "중요", "important"
    ]

    # 질문 키워드 (응답 필요)
    question_keywords = [
        "?", "어떻게", "언제", "where", "when", "how",
        "확인해", "알려", "보내", "회신", "reply"
    ]

    urgent_notifications = []
    unanswered_notifications = []

    for notif in notifications:
        text = (notif.get("text", "") + " " + notif.get("title", "")).lower()

        # 긴급 알림 감지
        if any(kw.lower() in text for kw in urgent_keywords):
            notif["priority"] = "high"
            notif["reason"] = "긴급 키워드 포함"
            urgent_notifications.append(notif)
            continue

        # 질문/응답 필요 감지
        if any(kw.lower() in text for kw in question_keywords):
            # 타임스탬프 파싱
            try:
                notif_time = datetime.fromisoformat(notif["timestamp"].replace("Z", "+00:00"))
                hours_since = (datetime.now(notif_time.tzinfo) - notif_time).total_seconds() / 3600
                notif["hours_since"] = int(hours_since)

                # 12시간 이상 미응답
                if hours_since >= 12:
                    notif["priority"] = "medium"
                    notif["reason"] = f"미응답 {int(hours_since)}시간"
                    unanswered_notifications.append(notif)
            except Exception:
                pass

    # 앱별 통계
    app_stats = {}
    for notif in notifications:
        app_name = notif.get("app_name", "unknown")
        if app_name not in app_stats:
            app_stats[app_name] = {"count": 0, "urgent": 0, "unanswered": 0}
        app_stats[app_name]["count"] += 1

    for notif in urgent_notifications:
        app_name = notif.get("app_name", "unknown")
        if app_name in app_stats:
            app_stats[app_name]["urgent"] += 1

    for notif in unanswered_notifications:
        app_name = notif.get("app_name", "unknown")
        if app_name in app_stats:
            app_stats[app_name]["unanswered"] += 1

    return {
        "urgent": urgent_notifications,
        "unanswered": unanswered_notifications,
        "app_stats": app_stats,
        "total_count": len(notifications),
    }


def format_output(analysis: dict) -> str:
    """결과 포맷팅"""
    output = []

    urgent = analysis.get("urgent", [])
    unanswered = analysis.get("unanswered", [])
    app_stats = analysis.get("app_stats", {})
    total_count = analysis.get("total_count", 0)

    output.append(f"📱 Android 알림 분석 (총 {total_count}건)")

    # 긴급 알림
    if urgent:
        output.append("")
        output.append(f"🚨 긴급 알림 ({len(urgent)}건)")
        for notif in urgent[:5]:
            app_name = notif.get("app_name", "unknown").upper()
            title = notif.get("title", "")[:20]
            text = notif.get("text", "")[:30]
            output.append(f"├── [{app_name}] {title}")
            output.append(f"│   {text}...")

    # 미응답 알림
    if unanswered:
        output.append("")
        output.append(f"⚠️ 미응답 알림 ({len(unanswered)}건)")
        for notif in unanswered[:5]:
            app_name = notif.get("app_name", "unknown").upper()
            title = notif.get("title", "")[:20]
            hours = notif.get("hours_since", 0)
            output.append(f"├── [{app_name}] {title} - {hours}시간 경과")

    # 앱별 통계
    if app_stats:
        output.append("")
        output.append("📊 앱별 통계")
        for app_name, stats in sorted(
            app_stats.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        ):
            count = stats["count"]
            urgent_count = stats.get("urgent", 0)
            unanswered_count = stats.get("unanswered", 0)
            output.append(
                f"├── {app_name.upper()}: {count}건 "
                f"(긴급 {urgent_count}, 미응답 {unanswered_count})"
            )

    if not urgent and not unanswered:
        output.append("")
        output.append("✅ 주의 필요한 알림이 없습니다.")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description="Android 알림 분석 스크립트")
    parser.add_argument("--days", type=int, default=3, help="최근 N일 알림 분석")
    parser.add_argument(
        "--app",
        choices=list(APP_PACKAGES.keys()),
        help="특정 앱만 분석"
    )
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite DB 경로")
    args = parser.parse_args()

    # 알림 조회
    print(f"📱 알림 조회 중... (최근 {args.days}일)")
    notifications = get_notifications(args.db, days=args.days, app_filter=args.app)

    if not notifications:
        print("📱 조회된 알림이 없습니다.")
        return

    # 분석
    print(f"🔍 {len(notifications)}개 알림 분석 중...")
    analysis = analyze_notifications(notifications)

    # 출력
    if args.json:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
    else:
        print("\n" + format_output(analysis))


if __name__ == "__main__":
    main()
