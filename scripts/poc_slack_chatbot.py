"""
Slack + Ollama Chatbot POC: Slack 채널에서 메시지를 받으면 웹 검색 + Ollama로 응답하는 챗봇

사용법:
    python scripts/poc_slack_chatbot.py --channel C0985UXQN6Q --my-user-id U040EUZ6JRY
    python scripts/poc_slack_chatbot.py --channel C0985UXQN6Q --my-user-id U040EUZ6JRY --verbose

동작:
    1. Slack 채널을 3초 간격으로 polling
    2. 사용자(--my-user-id)의 새 메시지 감지
    3. 실시간 정보가 필요한 질문인지 자동 판단
    4. 필요하면 DuckDuckGo로 웹 검색 → 결과를 Ollama 컨텍스트에 주입
    5. Ollama로 응답 생성 → Slack 채널에 전송

웹 검색:
    - DuckDuckGo 범용 검색 (API 키 불필요)
    - 날씨, 뉴스, 주가, 환율, 인물, 이벤트 등 모든 실시간 정보 대응
    - 일상 대화("안녕하세요")에는 검색하지 않아 불필요한 호출 방지
"""

import argparse
import asyncio
import io
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

# Windows cp949 stdout encoding fix (only for console, not pipes)
if sys.platform == "win32" and hasattr(sys.stdout, "buffer") and sys.stdout.isatty():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


# ==========================================
# 웹 검색 엔진
# ==========================================

# 웹 검색이 필요한 키워드 (이 중 하나라도 포함되면 검색)
SEARCH_TRIGGER_KEYWORDS = [
    # 실시간 정보
    "날씨", "기온", "비", "눈", "weather",
    "뉴스", "소식", "news", "헤드라인",
    "환율", "달러", "엔화", "유로", "원화",
    "주가", "주식", "코스피", "나스닥", "stock",
    # 질문 패턴
    "검색", "찾아줘", "찾아봐", "알아봐",
    "누구", "어디", "언제", "얼마",
    # 외부 지식
    "최근", "최신", "현재", "지금", "올해", "이번",
    "결과", "점수", "순위", "경기",
    "맛집", "추천", "리뷰",
    "사건", "사고", "이슈",
]

# 검색 불필요 패턴 (이 패턴이면 검색 스킵)
SKIP_PATTERNS = [
    r"^(안녕|ㅎㅇ|ㅋㅋ|ㅎㅎ|네|응|ㅇㅇ|감사|고마워|수고|bye|hi|hello)",
    r"^.{1,3}$",  # 3자 이하 짧은 메시지
]


def needs_web_search(message: str) -> bool:
    """메시지가 웹 검색이 필요한지 판단"""
    msg_lower = message.lower().strip()

    # 스킵 패턴 체크
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, msg_lower):
            return False

    # 트리거 키워드 체크
    for keyword in SEARCH_TRIGGER_KEYWORDS:
        if keyword in msg_lower:
            return True

    # 물음표가 있으면 검색 (질문일 가능성 높음)
    if "?" in message or "?" in message:
        return True

    return False


def build_search_query(message: str) -> str:
    """사용자 메시지에서 검색 쿼리 생성"""
    query = message.strip()

    # 물음표 제거
    query = query.rstrip("?？")

    # 불필요한 접미사/접두사 제거 (긴 것부터 매칭)
    for suffix in [
        "알려주세요", "알려줘", "찾아주세요", "찾아줘", "찾아봐줘", "찾아봐",
        "검색해줘", "검색해주세요", "검색", "해주세요", "해줘", "부탁해",
        "어때", "어떤가요", "어떻게 돼", "어떻게 되나요", "얼마야",
        "뭐야", "뭔가요", "인가요", "인지", "좀",
    ]:
        query = query.replace(suffix, "")

    query = query.strip()

    # 너무 짧으면 원본 사용
    if len(query) < 2:
        query = message.strip()

    return query


NEWS_KEYWORDS = ["뉴스", "소식", "news", "헤드라인", "사건", "사고", "이슈"]


def web_search(query: str, max_results: int = 3) -> str:
    """DuckDuckGo로 웹 검색 (뉴스 키워드면 뉴스 검색 사용)"""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "[웹 검색 불가] pip install duckduckgo-search 필요"

    try:
        is_news = any(kw in query.lower() for kw in NEWS_KEYWORDS)

        with DDGS() as ddgs:
            if is_news:
                results = list(ddgs.news(query, region="kr-kr", max_results=max_results))
            else:
                results = list(ddgs.text(query, region="kr-kr", max_results=max_results))

        if not results:
            return ""

        lines = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", r.get("url", ""))
            lines.append(f"{i}. {title}\n   {body}\n   출처: {href}")

        return "\n\n".join(lines)
    except Exception as e:
        return f"[웹 검색 오류] {e}"


# ==========================================
# 챗봇 코어
# ==========================================

CHATBOT_SYSTEM_PROMPT = """당신은 AI 비서 "Secretary"입니다. 사용자의 Slack 메시지에 자연스럽고 도움이 되는 한국어로 응답하세요.

## 현재 시간 정보
- 현재 날짜: {current_date}
- 현재 시간: {current_time}
- 요일: {current_day}

## 역할
- 사용자의 질문에 명확하고 간결하게 답변
- 날짜, 시간, 요일 관련 질문은 위 시간 정보를 활용하여 정확히 답변
- [웹 검색 결과]가 제공되면 그 데이터를 기반으로 사실적인 답변을 하세요
- 검색 결과의 출처를 자연스럽게 언급하세요
- 검색 결과가 질문과 관련 없으면 무시하고 자체 지식으로 답변하세요
- 업무 관련 요청은 구체적으로 대응

## 등록된 프로젝트
{project_list}

## 스타일
- 존댓말 사용
- 간결하게 (3-5문장)
- Slack 포맷 (마크다운) 사용 가능
- 이모지는 자연스럽게 최소한으로"""


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
            lines.append(f"- {p['id']}: {p['name']} - {p.get('description', '')}")

        return "\n".join(lines) if lines else "프로젝트 정보 없음"
    except Exception as e:
        return f"프로젝트 로드 실패: {e}"


def fetch_slack_messages(channel_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Slack 채널에서 최근 메시지 가져오기"""
    result = subprocess.run(
        [sys.executable, "-m", "lib.slack", "history", channel_id, "--limit", str(limit), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=r"C:\claude"
    )

    if result.returncode != 0:
        return []

    try:
        data = json.loads(result.stdout)
        if isinstance(data, dict):
            return data.get("messages", [])
        return data
    except json.JSONDecodeError:
        return []


def send_slack_message(channel_id: str, message: str) -> bool:
    """Slack 채널에 메시지 전송"""
    result = subprocess.run(
        [sys.executable, "-m", "lib.slack", "send", channel_id, message, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=r"C:\claude"
    )

    if result.returncode != 0:
        print(f"  [ERROR] Slack 전송 실패: {result.stderr[:200]}", flush=True)
        return False

    return True


async def generate_response(
    user_message: str,
    system_prompt: str,
    ollama_url: str,
    model: str,
    search_context: str = "",
    conversation_history: list[dict[str, str]] | None = None,
    verbose: bool = False,
) -> str:
    """Ollama로 응답 생성"""
    messages = [{"role": "system", "content": system_prompt}]

    # 최근 대화 히스토리 추가 (컨텍스트 유지)
    if conversation_history:
        messages.extend(conversation_history[-6:])  # 최근 3턴 (6메시지)

    # 웹 검색 결과가 있으면 user 메시지에 컨텍스트 주입
    if search_context:
        augmented_message = (
            f"{user_message}\n\n"
            f"---\n"
            f"[웹 검색 결과 - 이 정보를 활용하여 답변하세요]\n"
            f"{search_context}"
        )
    else:
        augmented_message = user_message

    messages.append({"role": "user", "content": augmented_message})

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{ollama_url}/api/chat",
                json={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 1024},
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]

            if verbose:
                print(f"\n  [OLLAMA] {content[:200]}...", flush=True)

            return content

    except httpx.ConnectError:
        return "Ollama 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요."
    except Exception as e:
        return f"응답 생성 중 오류가 발생했습니다: {e}"


def run_chatbot(
    channel_id: str,
    my_user_id: str,
    ollama_url: str,
    model: str,
    poll_interval: int,
    verbose: bool,
):
    """챗봇 메인 루프"""
    project_list = load_projects()

    def build_system_prompt() -> str:
        """매 메시지마다 현재 시간을 반영한 system prompt 생성"""
        now = datetime.now()
        day_names = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        return CHATBOT_SYSTEM_PROMPT.format(
            current_date=now.strftime("%Y년 %m월 %d일"),
            current_time=now.strftime("%H시 %M분"),
            current_day=day_names[now.weekday()],
            project_list=project_list,
        )

    # 대화 히스토리 (Ollama 컨텍스트용)
    conversation_history: list[dict[str, str]] = []

    def log(msg: str):
        print(msg, flush=True)

    log(f"\nSlack 채널 초기화 중... (채널: {channel_id})")
    initial_messages = fetch_slack_messages(channel_id, limit=1)

    last_ts = "0"
    if initial_messages:
        last_ts = initial_messages[0].get("ts", "0")
        log(f"  마지막 메시지 ts: {last_ts}")

    log(f"\n{'='*60}")
    log(" Slack + Ollama Chatbot (Web Search Enabled)")
    log(f" Channel: {channel_id}")
    log(f" My User: {my_user_id}")
    log(f" Model:   {model}")
    log(f" Poll:    {poll_interval}s")
    log(" Search:  DuckDuckGo (API 키 불필요)")
    log(f"{'='*60}")
    log(" 대기 중... Slack 채널에 메시지를 보내세요.")
    log(" 종료: Ctrl+C")
    log(f"{'='*60}\n")

    try:
        while True:
            messages = fetch_slack_messages(channel_id, limit=5)

            new_messages = []
            for msg in messages:
                msg_ts = msg.get("ts", "0")
                msg_user = msg.get("user", "")

                if float(msg_ts) <= float(last_ts):
                    continue
                if msg.get("bot_id"):
                    continue
                if msg_user != my_user_id:
                    continue

                new_messages.append(msg)

            new_messages.sort(key=lambda m: float(m.get("ts", "0")))

            for msg in new_messages:
                msg_ts = msg.get("ts", "0")
                msg_text = msg.get("text", "")

                if not msg_text.strip():
                    last_ts = msg_ts
                    continue

                timestamp = time.strftime("%H:%M:%S")
                log(f"  [{timestamp}] USER: {msg_text[:80]}")

                # 1단계: 웹 검색 필요 여부 판단
                search_context = ""
                if needs_web_search(msg_text):
                    query = build_search_query(msg_text)
                    log(f"  [{timestamp}] SEARCH: \"{query}\"")
                    search_context = web_search(query)
                    if search_context and verbose:
                        log(f"  [{timestamp}] RESULT: {search_context[:120]}...")
                    elif not search_context:
                        log(f"  [{timestamp}] SEARCH: 결과 없음")

                # 2단계: Ollama로 응답 생성 (검색 결과 포함)
                response = asyncio.run(
                    generate_response(
                        user_message=msg_text,
                        system_prompt=build_system_prompt(),
                        ollama_url=ollama_url,
                        model=model,
                        search_context=search_context,
                        conversation_history=conversation_history,
                        verbose=verbose,
                    )
                )

                # 응답이 너무 길면 Slack 제한에 맞게 자르기
                if len(response) > 3900:
                    response = response[:3900] + "\n\n_(응답이 잘렸습니다)_"

                # Slack에 응답 전송
                success = send_slack_message(channel_id, response)

                if success:
                    log(f"  [{timestamp}] BOT:  {response[:80]}...")
                    conversation_history.append({"role": "user", "content": msg_text})
                    conversation_history.append({"role": "assistant", "content": response})
                else:
                    log(f"  [{timestamp}] [FAIL] 전송 실패")

                last_ts = msg_ts

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        log(f"\n\n{'='*60}")
        log(" 챗봇 종료")
        log(f" 총 대화: {len(conversation_history) // 2}턴")
        log(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Slack + Ollama Chatbot (Web Search)")
    parser.add_argument("--channel", "-c", required=True, help="Slack 채널 ID")
    parser.add_argument("--my-user-id", required=True, help="내 Slack User ID")
    parser.add_argument("--model", default="qwen3:8b", help="Ollama 모델 (기본: qwen3:8b)")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama URL")
    parser.add_argument("--poll-interval", type=int, default=3, help="polling 간격 초 (기본: 3)")
    parser.add_argument("--verbose", "-v", action="store_true", help="검색 결과 + Ollama 응답 전문 출력")

    args = parser.parse_args()

    # Ollama 연결 확인
    print("Ollama 연결 확인 중...", flush=True)
    try:
        resp = httpx.get(f"{args.ollama_url}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        if args.model not in models and f"{args.model}:latest" not in models:
            matched = [m for m in models if args.model.split(":")[0] in m]
            if not matched:
                print(f"  [WARN] 모델 '{args.model}' 미발견. 사용 가능: {', '.join(models[:5])}")
            else:
                print(f"  Ollama: {matched[0]}")
        else:
            print(f"  Ollama: {args.model}")
    except Exception as e:
        print(f"  [ERROR] Ollama 연결 실패: {e}")
        print("  ollama serve 실행 필요")
        sys.exit(1)

    # 웹 검색 확인
    try:
        from duckduckgo_search import DDGS
        print("  Search: DuckDuckGo (ready)", flush=True)
    except ImportError:
        print("  [WARN] duckduckgo-search 미설치. pip install duckduckgo-search", flush=True)
        print("  웹 검색 없이 실행합니다.", flush=True)

    run_chatbot(
        channel_id=args.channel,
        my_user_id=args.my_user_id,
        ollama_url=args.ollama_url,
        model=args.model,
        poll_interval=args.poll_interval,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
