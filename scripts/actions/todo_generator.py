#!/usr/bin/env python3
"""
TODO Generator - 분석 결과에서 할일 목록 생성

Usage:
    python todo_generator.py --input report.json
    python todo_generator.py  # stdin으로 JSON 입력

Output:
    C:\\claude\\secretary\\output\\todos\\YYYY-MM-DD.md

Format:
    # TODO - 2026-02-02

    ## 긴급 (High)
    - [ ] 항목 1 (발신: sender, 마감: deadline)

    ## 보통 (Medium)
    - [ ] 항목 2

    ## 낮음 (Low)
    - [ ] 항목 3
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 출력 디렉토리
OUTPUT_DIR = Path(r"C:\claude\secretary\output\todos")


def extract_todos_from_gmail(gmail_data: list) -> list:
    """Gmail 분석 결과에서 할일 추출"""
    todos = []

    for email in gmail_data:
        if not email.get("has_action"):
            continue

        priority = email.get("priority", "low")
        subject = email.get("subject", "")
        sender = email.get("sender", "Unknown")
        deadline = email.get("deadline", "")

        # 할일 항목 생성
        task = {
            "type": "email",
            "priority": priority,
            "title": subject,
            "sender": sender,
            "deadline": deadline,
            "hours_since": email.get("hours_since", 0),
        }

        todos.append(task)

    return todos


def extract_todos_from_calendar(calendar_data: list) -> list:
    """Calendar 분석 결과에서 할일 추출"""
    todos = []

    for event in calendar_data:
        if not event.get("needs_preparation"):
            continue

        summary = event.get("summary", "")
        start_time = event.get("start_time", "")
        time_str = event.get("time_str", "")

        # 우선순위 판단 (24시간 이내: high, 48시간 이내: medium)
        priority = "low"
        if start_time:
            try:
                event_dt = datetime.fromisoformat(
                    start_time.replace("Z", "+00:00")
                ).replace(tzinfo=None)
                now = datetime.now()
                hours_until = (event_dt - now).total_seconds() / 3600

                if hours_until <= 24:
                    priority = "high"
                elif hours_until <= 48:
                    priority = "medium"
            except (ValueError, AttributeError):
                pass

        # 할일 항목 생성
        task = {
            "type": "calendar",
            "priority": priority,
            "title": f"{summary} 준비",
            "time": time_str,
            "deadline": start_time,
        }

        todos.append(task)

    return todos


def extract_todos_from_github(github_data: list) -> list:
    """GitHub 분석 결과에서 할일 추출"""
    todos = []

    for item in github_data:
        item_type = item.get("type", "")
        priority = "medium"

        if item_type == "pr_review":
            title = f"PR 리뷰: {item.get('title', '')}"
            days_waiting = item.get("days_waiting", 0)
            if days_waiting >= 3:
                priority = "high"

        elif item_type == "issue":
            title = f"이슈 응답: {item.get('title', '')}"
            days_since = item.get("days_since_response", 0)
            if days_since >= 4:
                priority = "high"

        else:
            continue

        task = {
            "type": "github",
            "priority": priority,
            "title": title,
            "url": item.get("url", ""),
            "repo": item.get("repo", ""),
        }

        todos.append(task)

    return todos


def generate_markdown(todos: list, date: Optional[str] = None) -> str:
    """TODO 마크다운 생성"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    # 우선순위별 그룹화
    high = [t for t in todos if t["priority"] == "high"]
    medium = [t for t in todos if t["priority"] == "medium"]
    low = [t for t in todos if t["priority"] == "low"]

    output = [f"# TODO - {date}", ""]

    # 긴급
    if high:
        output.append("## 긴급 (High)")
        output.append("")
        for task in high:
            meta = []
            if task.get("sender"):
                meta.append(f"발신: {task['sender']}")
            if task.get("deadline"):
                meta.append(f"마감: {task['deadline']}")
            if task.get("time"):
                meta.append(f"시간: {task['time']}")
            if task.get("url"):
                meta.append(f"링크: {task['url']}")

            meta_str = f" ({', '.join(meta)})" if meta else ""
            output.append(f"- [ ] {task['title']}{meta_str}")
        output.append("")

    # 보통
    if medium:
        output.append("## 보통 (Medium)")
        output.append("")
        for task in medium:
            meta = []
            if task.get("sender"):
                meta.append(f"발신: {task['sender']}")
            if task.get("time"):
                meta.append(f"시간: {task['time']}")
            if task.get("repo"):
                meta.append(f"레포: {task['repo']}")

            meta_str = f" ({', '.join(meta)})" if meta else ""
            output.append(f"- [ ] {task['title']}{meta_str}")
        output.append("")

    # 낮음
    if low:
        output.append("## 낮음 (Low)")
        output.append("")
        for task in low:
            output.append(f"- [ ] {task['title']}")
        output.append("")

    return "\n".join(output)


def save_todo_file(content: str, date: Optional[str] = None) -> Path:
    """TODO 파일 저장"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"{date}.md"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    return output_file


def main():
    parser = argparse.ArgumentParser(description="TODO 목록 생성")
    parser.add_argument("--input", help="입력 JSON 파일 경로")
    parser.add_argument("--output", help="출력 파일 경로 (기본: output/todos/YYYY-MM-DD.md)")
    parser.add_argument("--date", help="날짜 (YYYY-MM-DD, 기본: 오늘)")
    parser.add_argument("--print", action="store_true", help="파일 저장 대신 출력")
    args = parser.parse_args()

    # JSON 입력 처리
    try:
        if args.input:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: JSON 파싱 실패 - {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: 파일을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        sys.exit(1)

    # 데이터에서 할일 추출
    todos = []

    if "gmail" in data:
        todos.extend(extract_todos_from_gmail(data["gmail"]))

    if "calendar" in data:
        todos.extend(extract_todos_from_calendar(data["calendar"]))

    if "github" in data:
        todos.extend(extract_todos_from_github(data["github"]))

    # 직접 todo 리스트인 경우
    if isinstance(data, list):
        todos.extend(data)

    if not todos:
        print("⚠️ 추출된 할일이 없습니다.")
        return

    # 마크다운 생성
    markdown = generate_markdown(todos, args.date)

    # 출력 또는 저장
    if args.print:
        print(markdown)
    else:
        if args.output:
            output_file = Path(args.output)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(markdown)
        else:
            output_file = save_todo_file(markdown, args.date)

        print(f"✅ TODO 파일 생성: {output_file}")


if __name__ == "__main__":
    main()
