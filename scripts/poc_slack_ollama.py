"""
Slack + Ollama POC: 슬랙 메시지를 로컬 LLM으로 분석하는 개념 증명 스크립트

사용법:
    python scripts/poc_slack_ollama.py --channel <CHANNEL_ID> [--limit 10]
    python scripts/poc_slack_ollama.py --channel C09N8J3UJN9 --limit 5 --my-user-id U12345
    python scripts/poc_slack_ollama.py --list-channels
    python scripts/poc_slack_ollama.py --channel C09N8J3UJN9 --verbose  # Ollama 추론 전문 출력
"""

import argparse
import asyncio
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

# Windows cp949 stdout encoding fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


POC_ANALYZE_PROMPT = """당신은 Slack 메시지 분석기입니다. 아래 메시지를 분석하여 "내가 직접 응답해야 하는가"를 판단하세요.

## 핵심 판단 기준

"나"는 이 Slack 워크스페이스의 사용자(AidenKim)입니다.

### [NO_RESPONSE] 판정 (응답 불필요):
- 정보 공유, 공지, 알림성 메시지
- 다른 사람들끼리의 대화 (나와 무관)
- 봇이 보낸 자동 메시지
- 혼잣말, 독백, 메모
- 단순 이모지 반응, "ㅋㅋ", "ㅎㅎ" 등
- 이미 완료된 논의
- 일반적인 인사 ("좋은 아침!", "수고하셨습니다")

### [RESPONSE_NEEDED] 판정 (응답 필요):
- 나에게 직접 멘션(@)하거나 질문한 경우
- 내 의견/결정/승인을 요청하는 경우
- 내 담당 프로젝트에 대한 구체적 요청
- 마감일이 있는 업무 요청
- 문제 보고 또는 도움 요청

## 등록된 프로젝트
{project_list}

## 메시지 정보
- 발신자: {sender_name}
- 채널: {source_channel}

## 원본 메시지
{original_text}

---

위 기준에 따라 분석하세요. 대부분의 메시지는 응답이 불필요합니다.
마지막 줄에 판정을 출력하세요:
- [RESPONSE_NEEDED] project_id=프로젝트ID confidence=0.X
- [NO_RESPONSE] project_id=프로젝트ID confidence=0.X
"""


def load_projects() -> str:
    """config/projects.json에서 프로젝트 목록 로드"""
    config_path = Path(r"C:\claude\secretary\config\projects.json")
    if not config_path.exists():
        return "프로젝트 정보 없음"

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        projects = data.get("projects", [])

        lines = []
        for p in projects:
            lines.append(f"- {p['id']}: {p['name']}")
            lines.append(f"  키워드: {', '.join(p.get('keywords', []))}")

        return "\n".join(lines) if lines else "프로젝트 정보 없음"
    except Exception as e:
        return f"프로젝트 로드 실패: {e}"


def fetch_slack_messages(channel_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """lib.slack을 subprocess로 호출하여 메시지 수집"""
    result = subprocess.run(
        [sys.executable, "-m", "lib.slack", "history", channel_id, "--limit", str(limit), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=r"C:\claude"
    )

    if result.returncode != 0:
        print(f"❌ Slack 호출 실패: {result.stderr}")
        return []

    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            return data.get("messages", [])
        return data
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        print(f"Output: {result.stdout[:200]}")
        return []


def list_slack_channels():
    """Slack 채널 목록 표시"""
    result = subprocess.run(
        [sys.executable, "-m", "lib.slack", "channels", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=r"C:\claude"
    )

    if result.returncode != 0:
        print(f"❌ Slack 호출 실패: {result.stderr}")
        return

    try:
        data = json.loads(result.stdout)
        channels = data.get("channels", data) if isinstance(data, dict) else data
        print("\n" + "=" * 80)
        print(" Slack Channel List")
        print("=" * 80)
        print(f"\n {'ID':<15} {'Channel':<30} {'Members':<10}")
        print(f" {'-'*15} {'-'*30} {'-'*10}")

        for ch in channels:
            ch_id = ch.get("id", "")
            ch_name = ch.get("name", "")
            member_count = ch.get("num_members", 0)
            print(f" {ch_id:<15} #{ch_name:<29} {member_count:<10}")

        print("\n" + "=" * 80)
        print(f" Total: {len(channels)} channels")
        print("=" * 80 + "\n")
    except json.JSONDecodeError as e:
        print(f"❌ JSON 파싱 실패: {e}")


def extract_field(text: str, field: str, default: str = "") -> str:
    """마커에서 필드 추출: project_id=xxx confidence=0.8"""
    for part in text.split():
        if part.startswith(f"{field}="):
            return part.split("=", 1)[1]
    return default


def extract_decision(content: str) -> dict[str, Any]:
    """자유 추론 텍스트에서 [RESPONSE_NEEDED]/[NO_RESPONSE] 마커 추출"""
    result = {
        "needs_response": False,
        "project_id": None,
        "confidence": 0.0,
        "reasoning_preview": content[:100] + "..." if len(content) > 100 else content,
    }

    for line in reversed(content.strip().split('\n')):
        line = line.strip()
        if '[RESPONSE_NEEDED]' in line:
            result["needs_response"] = True
            result["project_id"] = extract_field(line, "project_id")
            result["confidence"] = float(extract_field(line, "confidence", "0.5"))
            break
        elif '[NO_RESPONSE]' in line:
            result["needs_response"] = False
            result["project_id"] = extract_field(line, "project_id")
            result["confidence"] = float(extract_field(line, "confidence", "0.5"))
            break

    if result["project_id"] == "unknown":
        result["project_id"] = None

    return result


async def analyze_message(
    text: str,
    sender: str,
    project_list: str,
    ollama_url: str,
    model: str,
    verbose: bool = False
) -> dict[str, Any]:
    """Ollama로 메시지 분석 (POC 전용 프롬프트 사용)"""
    prompt = POC_ANALYZE_PROMPT.format(
        project_list=project_list,
        sender_name=sender,
        source_channel="slack",
        original_text=text,
    )

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 2048},
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]

            if verbose:
                print(f"\n{'='*80}")
                print(f"Ollama 추론 전문 (sender={sender}):")
                print(f"{'='*80}")
                print(content)
                print(f"{'='*80}\n")

            return extract_decision(content)
    except httpx.ConnectError:
        return {
            "needs_response": False,
            "project_id": None,
            "confidence": 0.0,
            "reasoning_preview": "❌ Ollama 연결 실패 (서버 미실행?)",
        }
    except Exception as e:
        return {
            "needs_response": False,
            "project_id": None,
            "confidence": 0.0,
            "reasoning_preview": f"❌ 분석 실패: {e}",
        }


def should_skip_message(msg: dict[str, Any], my_user_id: str | None) -> tuple[bool, str]:
    """메시지를 건너뛸지 판단

    Returns:
        (should_skip, reason) - 건너뛸 경우 (True, "my msg" or "bot"), 분석할 경우 (False, "")
    """
    # 봇 메시지 필터링
    if msg.get("bot_id"):
        return True, "bot"

    # 내 메시지 필터링
    if my_user_id and msg.get("user") == my_user_id:
        return True, "my msg"

    return False, ""


async def analyze_all_messages(
    messages: list[dict[str, Any]],
    project_list: str,
    ollama_url: str,
    model: str,
    my_user_id: str | None = None,
    verbose: bool = False
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """모든 메시지를 비동기로 분석

    Returns:
        (results, stats) - results는 각 메시지의 분석 결과, stats는 필터링 통계
    """
    results: list[dict[str, Any]] = [None] * len(messages)  # type: ignore
    stats = {
        "total": len(messages),
        "skipped_my_msg": 0,
        "skipped_bot": 0,
        "analyzed": 0,
    }

    tasks = []
    task_indices = []  # 분석하는 메시지의 원본 인덱스 추적

    for idx, msg in enumerate(messages):
        should_skip, reason = should_skip_message(msg, my_user_id)

        if should_skip:
            if reason == "my msg":
                stats["skipped_my_msg"] += 1
            elif reason == "bot":
                stats["skipped_bot"] += 1

            results[idx] = {
                "needs_response": False,
                "project_id": None,
                "confidence": 0.0,
                "reasoning_preview": f"SKIP ({reason})",
                "skipped": True,
                "skip_reason": reason,
            }
        else:
            text = msg.get("text", "")
            sender = msg.get("user", "Unknown")
            task = analyze_message(text, sender, project_list, ollama_url, model, verbose)
            tasks.append(task)
            task_indices.append(idx)

    # 분석 태스크 실행
    if tasks:
        analysis_results = await asyncio.gather(*tasks)
        stats["analyzed"] = len(analysis_results)

        for i, idx in enumerate(task_indices):
            results[idx] = analysis_results[i]

    return results, stats


def truncate(text: str, length: int) -> str:
    """텍스트를 지정 길이로 자르기"""
    if len(text) <= length:
        return text
    return text[:length - 3] + "..."


def print_results(
    channel_id: str,
    messages: list[dict[str, Any]],
    results: list[dict[str, Any]],
    stats: dict[str, int],
    model: str
):
    """분석 결과를 테이블로 출력"""
    print("\n" + "=" * 100)
    print(" Slack + Ollama POC Analysis Results")
    print(f" Channel: {channel_id} | Messages: {len(messages)} | Model: {model}")
    print("=" * 100)

    # 필터링 통계
    print(f" Filter: {stats['total']} total -> {stats['skipped_my_msg']} skipped (my msg) -> "
          f"{stats['skipped_bot']} skipped (bot) -> {stats['analyzed']} analyzed")
    print("=" * 100)
    print()

    # Header
    print(f" {'#':<3} {'Sender':<15} {'Message (50 chars)':<52} {'Project':<12} {'Response':<10} {'Conf.':<6}")
    print(f" {'-'*3} {'-'*15} {'-'*52} {'-'*12} {'-'*10} {'-'*6}")

    # 데이터 행
    response_count = 0
    for idx, (msg, result) in enumerate(zip(messages, results), 1):
        sender = msg.get("user", "Unknown")[:15]
        text = msg.get("text", "")[:50]
        project = result.get("project_id") or "-"

        # SKIP 처리
        if result.get("skipped"):
            needs_resp = f"SKIP ({result.get('skip_reason', '')})"
            confidence = 0.0
        else:
            needs_resp = "YES" if result.get("needs_response") else "NO"
            confidence = result.get("confidence", 0.0)

            if result.get("needs_response"):
                response_count += 1

        print(f" {idx:<3} {sender:<15} {truncate(text, 50):<52} {project:<12} {needs_resp:<10} {confidence:<6.2f}")

    # Summary
    print()
    print("=" * 100)
    print(f" Summary: {response_count} need response / {stats['analyzed']} analyzed / {stats['total']} total")
    print("=" * 100 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Slack + Ollama POC 분석기")
    parser.add_argument("--channel", "-c", help="Slack 채널 ID")
    parser.add_argument("--limit", "-l", type=int, default=10, help="메시지 수 (기본: 10)")
    parser.add_argument("--list-channels", action="store_true", help="채널 목록 표시")
    parser.add_argument("--my-user-id", help="내 Slack User ID (이 사용자의 메시지는 분석 제외)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Ollama 추론 전문 출력")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama URL")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama 모델")

    args = parser.parse_args()

    if args.list_channels:
        list_slack_channels()
        return

    if not args.channel:
        parser.print_help()
        print("\n❌ --channel 또는 --list-channels 중 하나를 지정하세요")
        sys.exit(1)

    # 프로젝트 목록 로드
    print("프로젝트 목록 로드 중...")
    project_list = load_projects()

    # Slack 메시지 수집
    print(f"Slack 메시지 수집 중... (채널: {args.channel}, 최대: {args.limit}개)")
    messages = fetch_slack_messages(args.channel, args.limit)

    if not messages:
        print("❌ 수집된 메시지 없음")
        sys.exit(1)

    print(f"✓ {len(messages)}개 메시지 수집 완료")

    # Ollama 분석
    print(f"Ollama 분석 중... (모델: {args.model})")
    if args.my_user_id:
        print(f"  필터: User ID={args.my_user_id}의 메시지 제외")
    if args.verbose:
        print("  모드: Verbose (Ollama 추론 전문 출력)")

    results, stats = asyncio.run(
        analyze_all_messages(
            messages,
            project_list,
            args.ollama_url,
            args.model,
            args.my_user_id,
            args.verbose
        )
    )

    # 결과 출력
    print_results(args.channel, messages, results, stats, args.model)


if __name__ == "__main__":
    main()
