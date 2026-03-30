"""
Gmail → Ollama 분석 → Slack 전송 POC

Gmail 라벨 폴더의 이메일을 분석하여 Slack 채널에 구조화된 요약을 전송합니다.

사용법:
    python scripts/poc_gmail_to_slack.py --label ebs --channel C0985UXQN6Q
    python scripts/poc_gmail_to_slack.py --label ebs --channel C0985UXQN6Q --limit 20 --verbose
    python scripts/poc_gmail_to_slack.py --label ebs --channel C0985UXQN6Q --dry-run  # Slack 전송 없이 분석만
"""

import argparse
import asyncio
import io
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx

# Windows cp949 stdout encoding fix
if sys.platform == "win32" and hasattr(sys.stdout, "buffer") and sys.stdout.isatty():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def log(msg: str):
    print(msg, flush=True)


# ==========================================
# Gmail 수집
# ==========================================

def fetch_emails(label: str, limit: int = 20) -> list[dict[str, Any]]:
    """Gmail에서 라벨별 이메일 수집"""
    result = subprocess.run(
        [sys.executable, "-m", "lib.gmail", "search", f"label:{label}", "--limit", str(limit), "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=r"C:\claude"
    )

    if result.returncode != 0:
        log(f"  [ERROR] Gmail 검색 실패: {result.stderr[:200]}")
        return []

    try:
        data = json.loads(result.stdout)
        return data.get("emails", [])
    except json.JSONDecodeError:
        return []


def read_email(email_id: str) -> dict[str, Any]:
    """이메일 본문 읽기"""
    result = subprocess.run(
        [sys.executable, "-m", "lib.gmail", "read", email_id, "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=r"C:\claude"
    )

    if result.returncode != 0:
        return {}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def extract_text_from_html(html: str) -> str:
    """HTML에서 텍스트 추출"""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ==========================================
# 이메일 그룹핑
# ==========================================

def group_emails_by_thread(emails: list[dict]) -> dict[str, list[dict]]:
    """발신자별로 이메일 그룹핑"""
    groups: dict[str, list[dict]] = defaultdict(list)

    for email in emails:
        sender = email.get("from", "Unknown")
        # 이메일 주소에서 이름 추출
        match = re.match(r'(.+?)\s*<', sender)
        name = match.group(1).strip() if match else sender
        groups[name].append(email)

    return dict(groups)


def build_email_summary(emails: list[dict], read_limit: int = 3) -> str:
    """이메일 목록에서 분석용 요약 텍스트 생성"""
    groups = group_emails_by_thread(emails)

    lines = []
    lines.append(f"총 {len(emails)}개 이메일, {len(groups)}명 발신자\n")

    for sender, msgs in groups.items():
        lines.append(f"## {sender} ({len(msgs)}건)")

        # 읽기 수수료(메시지 본문) - 발신자당 최대 read_limit개
        own_msgs = [m for m in msgs if "aiden" not in m.get("from", "").lower()]
        for msg in own_msgs[:read_limit]:
            lines.append(f"- [{msg.get('date', '')[:10]}] {msg.get('subject', '')}")
            lines.append(f"  {msg.get('snippet', '')}")

            # 핵심 이메일 본문 읽기
            detail = read_email(msg.get("id", ""))
            if detail:
                body_text = detail.get("body_text", "")
                if not body_text:
                    body_text = extract_text_from_html(detail.get("body_html", ""))
                if body_text:
                    lines.append(f"  본문: {body_text[:500]}")

            lines.append("")

    return "\n".join(lines)


# ==========================================
# Ollama 분석
# ==========================================

ANALYSIS_PROMPT = """당신은 비즈니스 이메일 분석 전문가입니다. 아래 이메일들을 분석하여 구조화된 요약을 작성하세요.

## 이메일 데이터
{email_summary}

---

## 분석 요청

아래 형식으로 분석 결과를 작성하세요:

### 1. 전체 현황 요약 (2-3문장)

### 2. 업체별 진행 상황
각 업체/발신자별로:
- 업체명 및 담당자
- 주요 제안/논의 내용
- 현재 단계 (문의/견적/협상/계약 등)
- 핵심 가격 정보 (있으면)

### 3. 주요 의사결정 사항
- 결정이 필요한 항목들

### 4. 다음 액션 아이템
- 회신 필요한 메일
- 확인/검토 필요한 사항
- 기한이 있는 항목

한국어로 작성하세요. 가격과 구체적인 수치는 정확히 포함하세요.
"""


async def analyze_with_ollama(
    email_summary: str,
    ollama_url: str,
    model: str,
    verbose: bool = False,
) -> str:
    """Ollama로 이메일 분석"""
    prompt = ANALYSIS_PROMPT.format(email_summary=email_summary[:8000])

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 4096},
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]

            if verbose:
                log(f"\n{'='*60}")
                log("Ollama 분석 전문:")
                log(f"{'='*60}")
                log(content)
                log(f"{'='*60}\n")

            return content

    except httpx.ConnectError:
        return "[ERROR] Ollama 서버 연결 실패"
    except Exception as e:
        return f"[ERROR] 분석 실패: {e}"


# ==========================================
# Slack 전송
# ==========================================

def format_for_slack(analysis: str, label: str, email_count: int) -> str:
    """분석 결과를 Slack 메시지 형식으로 포맷"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    header = (
        f":email: *[Secretary] Gmail 라벨 분석: `{label}`*\n"
        f"분석 시각: {now} | 이메일: {email_count}건\n"
        f"{'─' * 40}\n\n"
    )

    # Markdown → Slack 형식 변환
    slack_text = analysis
    # ### 헤딩 → *볼드*
    slack_text = re.sub(r'###\s+(\d+\..*)', r'*\1*', slack_text)
    # **볼드** 유지 (Slack도 지원)
    # - 리스트는 Slack에서도 동일

    footer = f"\n{'─' * 40}\n_Powered by Secretary AI + Ollama_"

    return header + slack_text + footer


def send_to_slack(channel_id: str, message: str) -> bool:
    """Slack 채널에 메시지 전송"""
    # Slack 메시지 4000자 제한 대응
    if len(message) > 3900:
        # 2개로 분할
        mid = message.rfind('\n', 0, 3900)
        if mid == -1:
            mid = 3900

        part1 = message[:mid]
        part2 = message[mid:]

        ok1 = _send_slack_message(channel_id, part1)
        time.sleep(1)
        ok2 = _send_slack_message(channel_id, part2)
        return ok1 and ok2

    return _send_slack_message(channel_id, message)


def _send_slack_message(channel_id: str, text: str) -> bool:
    """단일 Slack 메시지 전송"""
    result = subprocess.run(
        [sys.executable, "-m", "lib.slack", "send", channel_id, text, "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=r"C:\claude"
    )

    if result.returncode != 0:
        log(f"  [ERROR] Slack 전송 실패: {result.stderr[:200]}")
        return False

    return True


# ==========================================
# 메인
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="Gmail → Ollama 분석 → Slack 전송 POC")
    parser.add_argument("--label", "-l", required=True, help="Gmail 라벨명 (예: ebs)")
    parser.add_argument("--channel", "-c", required=True, help="Slack 채널 ID")
    parser.add_argument("--limit", type=int, default=20, help="이메일 수 (기본: 20)")
    parser.add_argument("--read-limit", type=int, default=3, help="발신자당 본문 읽기 수 (기본: 3)")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama 모델")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama URL")
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 출력")
    parser.add_argument("--dry-run", action="store_true", help="Slack 전송 없이 분석만")

    args = parser.parse_args()

    log(f"\n{'='*60}")
    log(" Gmail → Slack 분석 리포트")
    log(f" Label: {args.label} | Channel: {args.channel}")
    log(f" Model: {args.model}")
    log(f"{'='*60}\n")

    # 1. Gmail 이메일 수집
    log(f"[1/4] Gmail 이메일 수집 중... (label:{args.label}, limit:{args.limit})")
    emails = fetch_emails(args.label, args.limit)

    if not emails:
        log("  이메일 없음. 종료.")
        sys.exit(1)

    log(f"  {len(emails)}개 이메일 수집 완료")

    # 내 메일 제외한 외부 발신자 메일만 필터
    external = [e for e in emails if "aiden" not in e.get("from", "").lower()]
    log(f"  외부 발신자 메일: {len(external)}건")

    # 2. 이메일 요약 생성 (본문 읽기 포함)
    log(f"\n[2/4] 이메일 본문 분석 중... (발신자당 최대 {args.read_limit}건 본문 읽기)")
    email_summary = build_email_summary(emails, read_limit=args.read_limit)

    if args.verbose:
        log("\n--- 이메일 요약 ---")
        log(email_summary[:2000])
        log(f"--- (총 {len(email_summary)}자) ---\n")

    # 3. Ollama 분석
    log(f"\n[3/4] Ollama 분석 중... (모델: {args.model})")
    analysis = asyncio.run(
        analyze_with_ollama(email_summary, args.ollama_url, args.model, args.verbose)
    )

    if analysis.startswith("[ERROR]"):
        log(f"  {analysis}")
        sys.exit(1)

    log(f"  분석 완료 ({len(analysis)}자)")

    # 4. Slack 전송
    slack_message = format_for_slack(analysis, args.label, len(emails))

    if args.dry_run:
        log("\n[4/4] DRY RUN - Slack 전송 생략")
        log(f"\n{'='*60}")
        log("Slack 메시지 미리보기:")
        log(f"{'='*60}")
        log(slack_message)
        log(f"{'='*60}")
    else:
        log(f"\n[4/4] Slack 전송 중... (채널: {args.channel})")
        success = send_to_slack(args.channel, slack_message)
        if success:
            log("  Slack 전송 완료!")
        else:
            log("  Slack 전송 실패")
            sys.exit(1)

    log(f"\n{'='*60}")
    log(" 완료!")
    log(f"{'='*60}\n")


if __name__ == "__main__":
    main()
