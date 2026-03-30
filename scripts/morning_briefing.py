"""매일 아침 9시 자동 실행 — /daily 파이프라인

Windows Task Scheduler에서 호출되어:
1. 어제 날짜 기준 커밋 수집
2. summary --json 데이터 준비
3. Claude Code CLI 호출로 3시제 분석 + Slack 전송
"""

import json
import logging
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

SECRETARY_DIR = Path(r"C:\claude\secretary")
LOG_DIR = SECRETARY_DIR / "logs"
LOG_FILE = LOG_DIR / "morning_briefing.log"
SLACK_TOKEN_FILE = Path(r"C:\claude\json\slack_token.json")
HOLIDAYS_FILE = SECRETARY_DIR / "config" / "holidays.json"

# 절대 경로 — PATH 의존 제거
PYTHON_PATH = r"C:\Users\AidenKim\AppData\Local\Programs\Python\Python312\python.exe"
CLAUDE_PATH = r"C:\Users\AidenKim\.local\bin\claude.exe"

WORK_TRACKER = [PYTHON_PATH, "-m", "scripts.work_tracker"]


def is_holiday(today: datetime) -> bool:
    """주말 또는 공휴일이면 True 반환."""
    if today.weekday() >= 5:  # 토(5), 일(6)
        return True
    try:
        with open(HOLIDAYS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        year_holidays = data.get(str(today.year), [])
        return today.strftime("%m-%d") in year_holidays
    except FileNotFoundError:
        return False


def setup_logger() -> logging.Logger:
    """로그 디렉토리 생성 + FileHandler/StreamHandler 설정."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("morning_briefing")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    # 파일 핸들러
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # 콘솔 핸들러 (Windows cp949 대응)
    sh = logging.StreamHandler(open(sys.stdout.fileno(), mode="w", encoding="utf-8", closefd=False))
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def send_slack_error(message: str) -> None:
    """파이프라인 실패 시 #claude-auto 채널에 에러 알림 전송."""
    try:
        with open(SLACK_TOKEN_FILE, encoding="utf-8") as f:
            token_data = json.load(f)
        token = token_data["access_token"]
    except Exception as e:
        print(f"[morning] Slack 토큰 읽기 실패: {e}", file=sys.stderr)
        return

    payload = json.dumps({
        "channel": "#claude-auto",
        "text": f":x: *morning_briefing 실패*\n```{message}```",
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if not result.get("ok"):
                print(f"[morning] Slack API 오류: {result.get('error')}", file=sys.stderr)
    except Exception as e:
        print(f"[morning] Slack 전송 실패: {e}", file=sys.stderr)


def run_cmd(args: list[str], logger: logging.Logger, check: bool = True) -> subprocess.CompletedProcess:
    """커맨드 실행 + 로그 출력."""
    logger.info(f"Running: {' '.join(args)}")
    result = subprocess.run(
        args,
        cwd=SECRETARY_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if result.stdout:
        logger.info(result.stdout.rstrip())
    if result.stderr:
        logger.error(result.stderr.rstrip())
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed with code {result.returncode}: {' '.join(args)}")
    return result


def main():
    logger = setup_logger()
    now = datetime.now()

    # 주말/공휴일 체크
    if is_holiday(now):
        logger.info(f"Skipped — {now.strftime('%Y-%m-%d')} is weekend or holiday")
        return

    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")
    logger.info(f"Morning briefing started — collect date: {yesterday}")

    # Step 1: 어제 커밋 수집
    run_cmd([*WORK_TRACKER, "collect", "--date", yesterday], logger)

    # Step 2: 데이터 준비 (summary)
    run_cmd([*WORK_TRACKER, "summary", "--json", "--date", today], logger, check=False)

    # Step 3: Claude Code CLI로 /daily 실행
    logger.info("Invoking Claude Code for 3시제 analysis...")
    claude_result = subprocess.run(
        [CLAUDE_PATH, "-p", "/daily"],
        cwd=SECRETARY_DIR,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if claude_result.stdout:
        logger.info(claude_result.stdout.rstrip())
    if claude_result.stderr:
        logger.error(claude_result.stderr.rstrip())

    if claude_result.returncode == 0:
        logger.info(f"Briefing completed successfully — {today}")
    else:
        raise RuntimeError(f"Claude Code exited with code {claude_result.returncode}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        error_msg = str(exc)
        print(f"[morning] FATAL: {error_msg}", file=sys.stderr)
        send_slack_error(error_msg)
        sys.exit(1)
