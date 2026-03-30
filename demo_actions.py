#!/usr/bin/env python3
"""
Automation Actions Demo

Phase 3 자동화 액션 데모 스크립트
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent
ACTIONS_DIR = ROOT_DIR / "scripts" / "actions"


def demo_toast():
    """Toast 알림 데모"""
    print("\n" + "=" * 60)
    print("1. Toast Notifier")
    print("=" * 60)

    result = subprocess.run(
        [
            sys.executable,
            str(ACTIONS_DIR / "toast_notifier.py"),
            "--title",
            "Secretary AI",
            "--message",
            "일일 리포트 분석 완료 - 긴급 항목 3건",
        ],
        capture_output=True,
        text=True,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")


def demo_todo():
    """TODO 생성 데모"""
    print("\n" + "=" * 60)
    print("2. TODO Generator")
    print("=" * 60)

    test_data = ROOT_DIR / "test_data.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ACTIONS_DIR / "todo_generator.py"),
            "--input",
            str(test_data),
            "--print",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")


def demo_calendar():
    """Calendar 생성 데모 (Dry-run)"""
    print("\n" + "=" * 60)
    print("3. Calendar Creator (Dry-run)")
    print("=" * 60)
    print("⚠️ 실제 API 호출 없이 dry-run 모드 데모만 표시")
    print()

    event_data = {
        "summary": "팀 미팅",
        "description": "주간 팀 미팅",
        "start": {"dateTime": "2026-02-10T14:00:00", "timeZone": "Asia/Seoul"},
        "end": {"dateTime": "2026-02-10T15:00:00", "timeZone": "Asia/Seoul"},
        "location": "회의실 A",
    }

    print("다음 일정이 생성됩니다:")
    print(json.dumps(event_data, ensure_ascii=False, indent=2))
    print("\n실제 생성하려면 --confirm 플래그를 추가하세요.")


def demo_response():
    """응답 초안 생성 데모"""
    print("\n" + "=" * 60)
    print("4. Response Drafter")
    print("=" * 60)
    print("⚠️ ANTHROPIC_API_KEY 환경 변수가 필요합니다.")
    print()

    sample_email = {
        "subject": "프로젝트 일정 문의",
        "sender": "client@example.com",
        "body": "다음 주 프로젝트 마일스톤 일정을 알려주실 수 있나요?",
        "id": "demo_001",
    }

    print("입력 이메일:")
    print(json.dumps(sample_email, ensure_ascii=False, indent=2))
    print("\n→ 응답 초안 생성 후 C:\\claude\\secretary\\output\\drafts\\에 저장됩니다.")
    print("→ Toast 알림으로 사용자에게 알림됩니다.")
    print("→ 절대 자동으로 전송되지 않습니다 (파일 + 알림만).")


def main():
    print("=" * 60)
    print("Secretary AI - Automation Actions Demo (Phase 3)")
    print("=" * 60)

    demos = [
        demo_toast,
        demo_todo,
        demo_calendar,
        demo_response,
    ]

    for demo in demos:
        try:
            demo()
        except Exception as e:
            print(f"\nError: {e}")

    print("\n" + "=" * 60)
    print("데모 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
