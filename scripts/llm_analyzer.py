#!/usr/bin/env python3
"""
LLM Session Analyzer - Claude Code 및 ChatGPT 세션 분석

Usage:
    python llm_analyzer.py [--days N] [--source SOURCE] [--chatgpt-file PATH] [--json]

Options:
    --days N              최근 N일 세션 분석 (기본: 7)
    --source SOURCE       claude_code | chatgpt | all (기본: all)
    --chatgpt-file PATH   ChatGPT export 파일 경로
    --json                JSON 형식 출력

Output:
    세션 통계, 토픽 분석, 도구 사용 패턴, 프로젝트 활동
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from parsers import ClaudeCodeParser, ChatGPTParser
from parsers.claude_code_parser import LLMSession

# Claude Code 프로젝트 디렉토리
CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def collect_sessions(
    days: int, source: str, chatgpt_file: Path | None
) -> list[LLMSession]:
    """모든 소스에서 세션 수집"""
    sessions = []

    # Claude Code 세션
    if source in ["claude_code", "all"]:
        parser = ClaudeCodeParser(CLAUDE_PROJECTS_DIR)
        sessions.extend(list(parser.parse_all_sessions(days)))

    # ChatGPT 세션
    if source in ["chatgpt", "all"] and chatgpt_file:
        parser = ChatGPTParser(chatgpt_file)
        sessions.extend(list(parser.parse_export(days)))

    return sorted(sessions, key=lambda s: s.start_time, reverse=True)


def analyze_sessions(sessions: list[LLMSession]) -> dict:
    """세션 통계 분석"""
    if not sessions:
        return {
            "total_sessions": 0,
            "message_count": 0,
            "by_source": {},
            "by_day": {},
            "by_project": {},
            "top_topics": [],
            "top_tools": [],
            "top_files": [],
        }

    # 기본 통계
    total_messages = sum(s.message_count for s in sessions)
    by_source = defaultdict(int)
    by_day = defaultdict(int)
    by_project = defaultdict(int)
    all_topics = defaultdict(int)
    all_tools = defaultdict(int)
    all_files = defaultdict(int)

    for session in sessions:
        # 소스별
        by_source[session.source] += 1

        # 일별
        day_key = session.start_time.strftime("%Y-%m-%d")
        by_day[day_key] += 1

        # 프로젝트별
        if session.project:
            by_project[session.project] += 1

        # 토픽
        for topic in session.topics:
            all_topics[topic] += 1

        # 도구
        for tool, count in session.tools_used.items():
            all_tools[tool] += count

        # 파일
        for file in session.files_mentioned:
            all_files[file] += 1

    # 상위 항목 추출
    top_topics = sorted(all_topics.items(), key=lambda x: x[1], reverse=True)[:10]
    top_tools = sorted(all_tools.items(), key=lambda x: x[1], reverse=True)[:10]
    top_files = sorted(all_files.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "total_sessions": len(sessions),
        "message_count": total_messages,
        "by_source": dict(by_source),
        "by_day": dict(sorted(by_day.items(), reverse=True)),
        "by_project": dict(sorted(by_project.items(), key=lambda x: x[1], reverse=True)),
        "top_topics": top_topics,
        "top_tools": top_tools,
        "top_files": top_files,
    }


def format_output(sessions: list[LLMSession], stats: dict) -> str:
    """결과 포맷팅"""
    if not sessions:
        return "📊 분석된 세션이 없습니다."

    output = []

    # 전체 요약
    output.append(f"📊 LLM 세션 분석 결과 (최근 {len(sessions)}개 세션)")
    output.append(f"├── 총 메시지: {stats['message_count']}개")
    output.append("")

    # 소스별 통계
    output.append("📈 소스별 세션")
    for source, count in stats["by_source"].items():
        source_name = {"claude_code": "Claude Code", "chatgpt": "ChatGPT"}.get(
            source, source
        )
        output.append(f"├── {source_name}: {count}개")
    output.append("")

    # 일별 활동
    output.append("📅 일별 세션 수")
    for day, count in list(stats["by_day"].items())[:7]:  # 최근 7일
        output.append(f"├── {day}: {count}개")
    output.append("")

    # 프로젝트 활동
    if stats["by_project"]:
        output.append(f"📁 프로젝트별 활동 (상위 5개)")
        for project, count in list(stats["by_project"].items())[:5]:
            output.append(f"├── {project}: {count}개 세션")
        output.append("")

    # 주요 토픽
    if stats["top_topics"]:
        output.append("🔍 주요 토픽")
        for topic, count in stats["top_topics"][:5]:
            output.append(f"├── {topic}: {count}회")
        output.append("")

    # 도구 사용
    if stats["top_tools"]:
        output.append("🛠️ 도구 사용 빈도")
        for tool, count in stats["top_tools"][:5]:
            output.append(f"├── {tool}: {count}회")
        output.append("")

    # 자주 언급된 파일
    if stats["top_files"]:
        output.append("📄 자주 언급된 파일 (상위 5개)")
        for file, count in stats["top_files"][:5]:
            # 경로 단순화 (마지막 부분만)
            file_name = Path(file).name if "\\" in file or "/" in file else file
            output.append(f"├── {file_name}: {count}회")

    return "\n".join(output)


def export_json(sessions: list[LLMSession], stats: dict) -> str:
    """JSON 형식 출력"""
    # LLMSession을 dict로 변환 (datetime 직렬화)
    sessions_data = [
        {
            "source": s.source,
            "session_id": s.session_id,
            "title": s.title,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat(),
            "message_count": s.message_count,
            "project": s.project,
            "topics": s.topics,
            "files_mentioned": s.files_mentioned,
            "tools_used": s.tools_used,
        }
        for s in sessions
    ]

    return json.dumps(
        {"sessions": sessions_data, "statistics": stats}, ensure_ascii=False, indent=2
    )


def main():
    parser = argparse.ArgumentParser(description="LLM 세션 분석기")
    parser.add_argument("--days", type=int, default=7, help="최근 N일 세션 분석")
    parser.add_argument(
        "--source",
        choices=["claude_code", "chatgpt", "all"],
        default="all",
        help="분석 소스",
    )
    parser.add_argument("--chatgpt-file", type=Path, help="ChatGPT export 파일 경로")
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    args = parser.parse_args()

    # 세션 수집
    print(f"🔍 세션 수집 중... (최근 {args.days}일)")
    sessions = collect_sessions(args.days, args.source, args.chatgpt_file)

    if not sessions:
        print("📊 분석된 세션이 없습니다.")
        return

    # 통계 분석
    print(f"📈 {len(sessions)}개 세션 분석 중...")
    stats = analyze_sessions(sessions)

    # 출력
    if args.json:
        print(export_json(sessions, stats))
    else:
        print("\n" + format_output(sessions, stats))


if __name__ == "__main__":
    main()
