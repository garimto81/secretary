#!/usr/bin/env python3
"""
Slack Analyzer - 멘션/DM/긴급 메시지 자동 추출

Usage:
    python slack_analyzer.py [--days N] [--max N] [--json] [--channels CHANNELS]

Options:
    --days N         최근 N일 메시지 분석 (기본: 3일)
    --max N          최대 N개 메시지 분석 (기본: 50)
    --json           JSON 형식 출력
    --channels LIST  특정 채널만 분석 (쉼표 구분, 예: #general,#team)

Output:
    JSON 형식의 메시지 목록 또는 포맷된 텍스트 출력
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# lib.slack 라이브러리 import를 위해 C:\claude를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from lib.slack import SlackClient, get_token
    from lib.slack.errors import (
        SlackAuthError,
        SlackRateLimitError,
        SlackAPIError,
        SlackChannelNotFoundError,
        SlackTokenRevokedError,
    )
except ImportError as e:
    print("Error: lib.slack 라이브러리를 찾을 수 없습니다.")
    print(f"상세: {e}")
    print("경로: C:\\claude\\lib\\slack")
    sys.exit(1)


def get_authenticated_client() -> SlackClient:
    """Slack 인증 및 클라이언트 생성"""
    try:
        token = get_token()
        if not token:
            print("Error: Slack 토큰이 없습니다.")
            print("인증 방법:")
            print("  1. 직접 토큰 사용: C:\\claude\\json\\slack_credentials.json에 bot_token 추가")
            print("  2. OAuth 인증: python -m lib.slack login")
            sys.exit(1)

        return SlackClient(token=token.access_token)
    except SlackAuthError as auth_err:
        print(f"Error: 인증 실패 - {auth_err}")
        print("\n인증 방법:")
        print("  1. 직접 토큰 사용: C:\\claude\\json\\slack_credentials.json에 bot_token 추가")
        print("  2. OAuth 인증: python -m lib.slack login")
        sys.exit(1)
    except (AttributeError, TypeError) as err:
        print(f"Error: 클라이언트 생성 실패 - {err}")
        sys.exit(1)


def get_bot_user_id() -> Optional[str]:
    """봇의 User ID 조회"""
    try:
        # auth.test로 봇 정보 확인
        token = get_token()
        return token.bot_user_id if token else None
    except (SlackAuthError, AttributeError):
        return None


def is_mentioned(message: dict, bot_user_id: Optional[str]) -> bool:
    """메시지에 봇이 멘션되었는지 확인"""
    text = message.get("text", "")

    # @me 패턴 또는 <@USER_ID> 패턴
    if bot_user_id:
        mention_pattern = f"<@{bot_user_id}>"
        if mention_pattern in text:
            return True

    # 일반적인 멘션 패턴
    if re.search(r"<@[A-Z0-9]+>", text):
        return True

    return False


def detect_urgent_keywords(text: str) -> bool:
    """긴급 키워드 감지"""
    urgent_keywords = [
        "긴급",
        "urgent",
        "asap",
        "immediately",
        "오늘까지",
        "today",
        "지금",
        "now",
        "빨리",
        "quickly",
        "중요",
        "important",
    ]

    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in urgent_keywords)


def calculate_hours_since(timestamp: datetime) -> int:
    """메시지 작성 후 경과 시간 계산 (시간 단위)"""
    if not timestamp:
        return 0

    now = datetime.now()
    # timestamp가 timezone-aware일 경우 처리
    if timestamp.tzinfo is not None:
        from datetime import timezone

        now = datetime.now(timezone.utc)

    delta = now - timestamp
    return int(delta.total_seconds() / 3600)


def determine_priority(text: str, has_mention: bool, hours_since: int) -> str:
    """메시지 우선순위 판단"""
    # 긴급 키워드가 있으면 high
    if detect_urgent_keywords(text):
        return "high"

    # 멘션이 있고 48시간 이상 경과
    if has_mention and hours_since >= 48:
        return "high"

    # 멘션이 있으면 medium
    if has_mention:
        return "medium"

    # 24시간 이상 경과한 메시지
    if hours_since >= 24:
        return "medium"

    return "low"


def has_action_required(text: str) -> bool:
    """액션 필요 여부 판단"""
    action_keywords = [
        "확인해 주세요",
        "검토해 주세요",
        "요청",
        "부탁",
        "처리",
        "please review",
        "please check",
        "can you",
        "could you",
        "action required",
        "필요",
        "need",
        "답변",
        "reply",
    ]

    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in action_keywords)


def analyze_message(
    message: dict, channel_name: str, bot_user_id: Optional[str]
) -> dict:
    """메시지 분석"""
    text = message.get("text", "")
    user = message.get("user", "Unknown")
    ts = message.get("ts", "")
    thread_ts = message.get("thread_ts")

    # 타임스탬프 파싱
    timestamp = None
    if ts:
        try:
            timestamp = datetime.fromtimestamp(float(ts))
        except (ValueError, TypeError):
            pass

    # 멘션 확인
    is_mention = is_mentioned(message, bot_user_id)

    # 경과 시간
    hours_since = calculate_hours_since(timestamp)

    # 액션 필요 여부
    has_action = has_action_required(text)

    # 우선순위
    priority = determine_priority(text, is_mention, hours_since)

    return {
        "channel_id": message.get("channel", ""),
        "channel_name": channel_name,
        "message_id": ts,
        "sender": user,
        "text": text[:500],  # 최대 500자
        "timestamp": timestamp.isoformat() if timestamp else None,
        "has_action": has_action,
        "priority": priority,
        "is_mention": is_mention,
        "hours_since": hours_since,
        "is_thread": bool(thread_ts),
    }


def list_messages(
    client: SlackClient,
    days: int = 3,
    max_results: int = 50,
    channel_filter: Optional[list] = None,
) -> list:
    """메시지 목록 조회"""
    messages = []
    cutoff_time = datetime.now() - timedelta(days=days)

    # 봇 User ID 조회
    bot_user_id = get_bot_user_id()

    try:
        # 채널 목록 조회
        print("📡 채널 목록 조회 중...")
        channels = client.list_channels(include_private=True)

        # 채널 필터링
        if channel_filter:
            # #general 형식을 general로 변환
            filter_names = [
                c.strip().lstrip("#").lower() for c in channel_filter if c.strip()
            ]
            channels = [c for c in channels if c.name.lower() in filter_names]

        print(f"📡 {len(channels)}개 채널에서 메시지 조회 중...")

        for channel in channels:
            try:
                # 채널 히스토리 조회
                history = client.get_history(channel.id, limit=max_results)

                for msg in history:
                    # 시간 필터링
                    if msg.timestamp and msg.timestamp < cutoff_time:
                        continue

                    # 봇 자신의 메시지 제외
                    if msg.user == bot_user_id:
                        continue

                    # 분석
                    analyzed = analyze_message(
                        {
                            "text": msg.text,
                            "user": msg.user,
                            "ts": msg.ts,
                            "channel": msg.channel,
                            "thread_ts": msg.thread_ts,
                        },
                        channel.name,
                        bot_user_id,
                    )

                    messages.append(analyzed)

            except SlackChannelNotFoundError:
                print(f"⚠️ 채널 접근 불가: {channel.name}")
                continue
            except SlackRateLimitError as rate_err:
                print(f"⚠️ Rate Limit 도달. {rate_err.retry_after}초 대기 중...")
                import time

                time.sleep(rate_err.retry_after)
                continue
            except SlackAPIError as api_err:
                print(f"⚠️ API 에러 (채널: {channel.name}): {api_err.error}")
                continue

        return messages

    except SlackAuthError as auth_err:
        print(f"Error: 인증 에러 - {auth_err}")
        return []
    except SlackTokenRevokedError:
        print("Error: 토큰이 만료되었습니다. 재인증이 필요합니다.")
        print("실행: python -m lib.slack login")
        return []
    except (ValueError, TypeError, KeyError) as err:
        print(f"Error: 메시지 조회 실패 - {err}")
        import traceback

        traceback.print_exc()
        return []


def format_output(messages: list) -> str:
    """결과 포맷팅"""
    if not messages:
        return "💬 분석된 메시지가 없습니다."

    # 멘션된 메시지만 필터
    mentions = [m for m in messages if m["is_mention"]]

    # 액션 필요 메시지
    action_required = [m for m in messages if m["has_action"]]

    # 긴급 메시지
    urgent = [m for m in messages if m["priority"] == "high"]

    # 미응답 메시지 (멘션 + 24시간 이상)
    unanswered = [m for m in mentions if m["hours_since"] >= 24]

    output = []

    if urgent:
        output.append(f"🚨 긴급 메시지 ({len(urgent)}건)")
        for msg in sorted(urgent, key=lambda x: x["hours_since"], reverse=True):
            hours = msg["hours_since"]
            output.append(
                f"├── [{msg['channel_name']}] {msg['text'][:100]}... - {hours}시간 전"
            )
            output.append(f"│       발신: {msg['sender']}")

    if mentions:
        output.append("")
        output.append(f"💬 멘션된 메시지 ({len(mentions)}건)")
        for msg in sorted(mentions, key=lambda x: x["hours_since"], reverse=True):
            priority_icon = {"high": "🚨", "medium": "⚠️", "low": "📌"}[msg["priority"]]
            hours = msg["hours_since"]
            output.append(
                f"├── {priority_icon} [{msg['channel_name']}] {msg['text'][:100]}... - {hours}시간 전"
            )

    if unanswered:
        output.append("")
        output.append(f"⚠️ 미응답 메시지 ({len(unanswered)}건, 24시간+)")
        for msg in sorted(unanswered, key=lambda x: x["hours_since"], reverse=True):
            hours = msg["hours_since"]
            output.append(
                f"├── [{msg['channel_name']}] {msg['text'][:100]}... - {hours}시간 경과"
            )

    if action_required:
        output.append("")
        output.append(f"📋 액션 필요 메시지 ({len(action_required)}건)")
        for msg in sorted(
            action_required,
            key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]],
        ):
            priority_icon = {"high": "긴급", "medium": "보통", "low": "낮음"}[
                msg["priority"]
            ]
            output.append(
                f"├── [{priority_icon}] [{msg['channel_name']}] {msg['text'][:100]}..."
            )

    return (
        "\n".join(output)
        if output
        else "💬 주의 필요한 메시지가 없습니다."
    )


def main():
    parser = argparse.ArgumentParser(description="Slack 메시지 분석기")
    parser.add_argument("--days", type=int, default=3, help="최근 N일 메시지 분석")
    parser.add_argument("--max", type=int, default=50, help="채널당 최대 분석 메시지 수")
    parser.add_argument("--json", action="store_true", help="JSON 형식 출력")
    parser.add_argument(
        "--channels",
        type=str,
        help="특정 채널만 분석 (쉼표 구분, 예: general,team)",
    )
    args = parser.parse_args()

    # 인증
    print("🔐 Slack 인증 중...")
    client = get_authenticated_client()

    # 채널 필터 파싱
    channel_filter = None
    if args.channels:
        channel_filter = [c.strip() for c in args.channels.split(",")]
        print(f"📡 필터링된 채널: {', '.join(channel_filter)}")

    # 메시지 조회
    print(f"💬 최근 {args.days}일 메시지 분석 중...")
    messages = list_messages(
        client, days=args.days, max_results=args.max, channel_filter=channel_filter
    )

    if not messages:
        print("💬 조회된 메시지가 없습니다.")
        return

    # 출력
    if args.json:
        print(json.dumps(messages, ensure_ascii=False, indent=2))
    else:
        print(f"\n🔍 {len(messages)}개 메시지 분석 완료\n")
        print(format_output(messages))


if __name__ == "__main__":
    main()
