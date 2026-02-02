#!/usr/bin/env python3
"""
Automation Actions 테스트

각 액션 스크립트를 개별 테스트합니다.
"""

import json
import subprocess
import sys
from pathlib import Path

# 프로젝트 루트
ROOT_DIR = Path(__file__).parent.parent
ACTIONS_DIR = ROOT_DIR / "scripts" / "actions"


def test_toast_notifier():
    """Toast 알림 테스트"""
    print("\n=== Toast Notifier 테스트 ===")

    # CLI 테스트
    result = subprocess.run(
        [
            sys.executable,
            str(ACTIONS_DIR / "toast_notifier.py"),
            "--title",
            "테스트 알림",
            "--message",
            "이것은 테스트 알림입니다.",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False

    # JSON 테스트
    test_data = {
        "title": "JSON 알림",
        "message": "JSON으로 전송된 알림입니다.",
    }

    result = subprocess.run(
        [sys.executable, str(ACTIONS_DIR / "toast_notifier.py"), "--json"],
        input=json.dumps(test_data),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False

    return True


def test_todo_generator():
    """TODO 생성기 테스트"""
    print("\n=== TODO Generator 테스트 ===")

    # 테스트 데이터
    test_data = {
        "gmail": [
            {
                "subject": "프로젝트 리뷰 요청",
                "sender": "manager@example.com",
                "has_action": True,
                "priority": "high",
                "deadline": "2026-02-05",
                "hours_since": 24,
            },
            {
                "subject": "문서 확인 부탁",
                "sender": "colleague@example.com",
                "has_action": True,
                "priority": "medium",
                "hours_since": 48,
            },
        ],
        "calendar": [
            {
                "summary": "팀 미팅",
                "start_time": "2026-02-03T14:00:00",
                "time_str": "14:00",
                "needs_preparation": True,
            }
        ],
        "github": [
            {
                "type": "pr_review",
                "title": "Add new feature",
                "days_waiting": 3,
                "url": "https://github.com/user/repo/pull/123",
                "repo": "user/repo",
            }
        ],
    }

    # 출력만 테스트 (실제 파일 저장 안 함)
    result = subprocess.run(
        [sys.executable, str(ACTIONS_DIR / "todo_generator.py"), "--json", "--print"],
        input=json.dumps(test_data),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False

    return True


def test_calendar_creator():
    """Calendar 생성기 테스트 (Dry-run)"""
    print("\n=== Calendar Creator 테스트 (Dry-run) ===")

    # Dry-run 테스트
    result = subprocess.run(
        [
            sys.executable,
            str(ACTIONS_DIR / "calendar_creator.py"),
            "--title",
            "테스트 회의",
            "--start",
            "2026-02-10 14:00",
            "--end",
            "2026-02-10 15:00",
            "--description",
            "이것은 테스트 일정입니다.",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False

    print("\n⚠️ 실제 생성하려면 --confirm 플래그를 추가하세요.")
    return True


def test_response_drafter():
    """응답 초안 생성기 테스트"""
    print("\n=== Response Drafter 테스트 ===")

    # 테스트 데이터
    test_data = {
        "subject": "프로젝트 일정 문의",
        "sender": "client@example.com",
        "body": "다음 주 프로젝트 마일스톤 일정을 알려주실 수 있나요? 특히 데모 날짜가 궁금합니다.",
        "id": "test_email_001",
    }

    # 출력만 테스트 (실제 파일 저장 안 함)
    result = subprocess.run(
        [
            sys.executable,
            str(ACTIONS_DIR / "response_drafter.py"),
            "--json",
            "--print",
        ],
        input=json.dumps(test_data),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    print(result.stdout)
    if result.returncode != 0:
        error_msg = result.stderr or ""
        print(f"Error: {error_msg}")
        # ANTHROPIC_API_KEY가 없으면 실패는 정상
        if "ANTHROPIC_API_KEY" in error_msg:
            print("⚠️ ANTHROPIC_API_KEY 환경 변수가 필요합니다.")
            return True
        return False

    return True


def main():
    """모든 액션 테스트 실행"""
    print("=" * 60)
    print("Automation Actions 테스트 시작")
    print("=" * 60)

    tests = [
        ("Toast Notifier", test_toast_notifier),
        ("TODO Generator", test_todo_generator),
        ("Calendar Creator", test_calendar_creator),
        ("Response Drafter", test_response_drafter),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\nError in {name}: {e}")
            results.append((name, False))

    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")

    passed = sum(1 for _, success in results if success)
    total = len(results)
    print(f"\n총 {passed}/{total} 테스트 통과")


if __name__ == "__main__":
    main()
