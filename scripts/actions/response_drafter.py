#!/usr/bin/env python3
"""
Response Drafter - 응답 초안 생성 (자동 전송 절대 금지)

⚠️ CRITICAL: 이 스크립트는 절대 자동으로 이메일/메시지를 전송하지 않습니다.
           초안 파일 생성 + Toast 알림만 수행합니다.

Usage:
    python response_drafter.py --email-id EMAIL_ID
    python response_drafter.py --input message.json
    python response_drafter.py --json  # stdin으로 JSON 입력

Output:
    C:\\claude\\secretary\\output\\drafts\\{id}.md

Examples:
    # 이메일 ID로 초안 생성
    python response_drafter.py --email-id 12345

    # JSON 파일로 초안 생성
    python response_drafter.py --input unanswered_email.json

    # stdin으로 JSON 입력
    echo '{"subject":"질문","sender":"user@example.com","body":"..."}' | python response_drafter.py --json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔 UTF-8 설정
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 출력 디렉토리
OUTPUT_DIR = Path(r"C:\claude\secretary\output\drafts")

# Claude API (Anthropic)
try:
    import anthropic
except ImportError:
    print("Error: anthropic 라이브러리가 설치되지 않았습니다.")
    print("설치: pip install anthropic")
    sys.exit(1)


def get_claude_client() -> anthropic.Anthropic | None:
    """Claude API 클라이언트 생성"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        print("Error: ANTHROPIC_API_KEY 환경 변수가 설정되지 않았습니다.", file=sys.stderr)
        return None

    return anthropic.Anthropic(api_key=api_key)


def generate_response_draft(
    subject: str,
    sender: str,
    body: str,
    context: str | None = None,
) -> str | None:
    """
    Claude API로 응답 초안 생성

    Args:
        subject: 이메일 제목
        sender: 발신자
        body: 본문
        context: 추가 컨텍스트

    Returns:
        생성된 응답 초안 (실패 시 None)
    """
    client = get_claude_client()
    if not client:
        return None

    # 프롬프트 구성
    prompt = f"""다음 이메일에 대한 응답 초안을 작성해주세요.

발신자: {sender}
제목: {subject}

본문:
{body}

"""

    if context:
        prompt += f"\n추가 컨텍스트:\n{context}\n"

    prompt += """
응답 초안 작성 시:
1. 공손하고 전문적인 톤 유지
2. 발신자의 질문/요청에 명확히 답변
3. 필요 시 추가 정보 요청
4. 한글로 작성

응답 초안:"""

    try:
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        return message.content[0].text

    except Exception as e:
        print(f"Error: Claude API 호출 실패 - {e}", file=sys.stderr)
        return None


def save_draft(
    draft_content: str,
    subject: str,
    sender: str,
    item_id: str | None = None,
) -> Path:
    """
    초안 파일 저장

    Args:
        draft_content: 초안 내용
        subject: 원본 제목
        sender: 발신자
        item_id: 이메일/메시지 ID

    Returns:
        저장된 파일 경로
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 파일명 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if item_id:
        filename = f"{timestamp}_{item_id}.md"
    else:
        filename = f"{timestamp}.md"

    output_file = OUTPUT_DIR / filename

    # 메타데이터와 함께 저장
    content = f"""---
subject: {subject}
sender: {sender}
generated_at: {datetime.now().isoformat()}
---

# 응답 초안

**발신자**: {sender}
**제목**: {subject}

---

{draft_content}

---

⚠️ 이 초안은 AI가 생성한 것입니다. 반드시 검토 후 사용하세요.
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    return output_file


def send_notification(title: str, message: str):
    """Toast 알림 전송 (toast_notifier 사용)"""
    try:
        from . import toast_notifier

        toast_notifier.send_notification(title, message)
    except Exception as e:
        print(f"Warning: 알림 전송 실패 - {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="응답 초안 생성 (자동 전송 절대 금지)")
    parser.add_argument("--email-id", help="Gmail 이메일 ID")
    parser.add_argument("--input", help="입력 JSON 파일 경로")
    parser.add_argument("--json", action="store_true", help="stdin으로 JSON 입력")
    parser.add_argument("--print", action="store_true", help="파일 저장 대신 출력")
    args = parser.parse_args()

    # JSON 입력 처리
    try:
        if args.input:
            with open(args.input, encoding="utf-8") as f:
                data = json.load(f)
        elif args.json:
            data = json.load(sys.stdin)
        elif args.email_id:
            # Gmail에서 이메일 가져오기 (TODO: gmail_analyzer 재사용)
            print("Error: --email-id는 아직 구현되지 않았습니다.", file=sys.stderr)
            print("대신 --input 또는 --json을 사용하세요.", file=sys.stderr)
            sys.exit(1)
        else:
            print("Error: --email-id, --input, 또는 --json 중 하나는 필수입니다.", file=sys.stderr)
            sys.exit(1)

    except json.JSONDecodeError as e:
        print(f"Error: JSON 파싱 실패 - {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: 파일을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        sys.exit(1)

    # 데이터 추출
    subject = data.get("subject", "(제목 없음)")
    sender = data.get("sender", "Unknown")
    body = data.get("body", data.get("snippet", ""))
    context = data.get("context", "")
    item_id = data.get("id", data.get("email_id", ""))

    if not body:
        print("Error: 본문이 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 응답 초안 생성
    print("🤖 Claude API로 응답 초안 생성 중...")
    draft = generate_response_draft(subject, sender, body, context)

    if not draft:
        print("Error: 응답 초안 생성 실패", file=sys.stderr)
        sys.exit(1)

    # 출력 또는 저장
    if args.print:
        print("\n" + "=" * 60)
        print(draft)
        print("=" * 60)
    else:
        output_file = save_draft(draft, subject, sender, item_id)
        print(f"✅ 응답 초안 생성 완료: {output_file}")

        # Toast 알림
        send_notification(
            title="응답 초안 생성 완료",
            message=f"{subject[:50]}... - 초안을 확인하세요.",
        )

        print("\n⚠️ CRITICAL: 이 초안은 자동으로 전송되지 않습니다.")
        print("⚠️ 반드시 파일을 검토 후 수동으로 전송하세요.")


if __name__ == "__main__":
    main()
