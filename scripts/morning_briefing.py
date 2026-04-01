"""매일 아침 9시 자동 실행 — /daily + /audit + auto-remediation 파이프라인

Windows Task Scheduler에서 호출되어:
1. 어제 날짜 기준 커밋 수집
2. summary --json 데이터 준비
3. Claude Code CLI 호출로 3시제 분석 + Slack 전송
4. /audit --auto-implement 설정 점검 + 자동 개선 + Slack 보고
5. 브리핑 '앞으로 대비' 항목 자동 해결 (이슈 트리아지, 스냅샷 갱신)
"""

import json
import logging
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

SECRETARY_DIR = Path(r"C:\claude\secretary")
CLAUDE_ROOT = Path(r"C:\claude")
LOG_DIR = SECRETARY_DIR / "logs"
LOG_FILE = LOG_DIR / "morning_briefing.log"
SLACK_TOKEN_FILE = Path(r"C:\claude\json\slack_token.json")
HOLIDAYS_FILE = SECRETARY_DIR / "config" / "holidays.json"
AUDIT_DIR = CLAUDE_ROOT / "docs" / "audit"

# 절대 경로 — PATH 의존 제거
PYTHON_PATH = r"C:\Users\AidenKim\AppData\Local\Programs\Python\Python312\python.exe"
CLAUDE_PATH = r"C:\Users\AidenKim\.local\bin\claude.exe"

WORK_TRACKER = [PYTHON_PATH, "-m", "scripts.work_tracker"]

# UTF-8 강제 — Windows cp949 이모지 깨짐 방지
_UTF8_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


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


def send_slack_message(channel: str, text: str) -> None:
    """Slack 채널에 메시지 전송."""
    try:
        with open(SLACK_TOKEN_FILE, encoding="utf-8") as f:
            token_data = json.load(f)
        token = token_data["access_token"]
    except Exception as e:
        print(f"[morning] Slack 토큰 읽기 실패: {e}", file=sys.stderr)
        return

    payload = json.dumps({"channel": channel, "text": text}).encode("utf-8")

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


def send_slack_error(message: str) -> None:
    """파이프라인 실패 시 #claude-auto 채널에 에러 알림 전송."""
    send_slack_message("#claude-auto", f":x: *morning_briefing 실패*\n```{message}```")


def extract_audit_summary(report_path: Path) -> str:
    """audit 보고서에서 '## 요약' 섹션을 추출. 최대 1500자."""
    try:
        content = report_path.read_text(encoding="utf-8")
    except Exception:
        return "(보고서 읽기 실패)"

    # '## 요약' ~ 다음 '---' 또는 '## ' 까지 추출
    start = content.find("## 요약")
    if start == -1:
        # 요약 섹션 없으면 첫 1500자
        return content[:1500]

    end = content.find("\n---", start + 6)
    if end == -1:
        end = content.find("\n## ", start + 6)
    if end == -1:
        end = start + 1500

    summary = content[start:end].strip()
    return summary[:1500]


def run_audit(logger: logging.Logger, today: str) -> None:
    """설정 점검 (/audit) 실행 + Slack 보고."""
    logger.info("Invoking Claude Code for /audit...")
    try:
        audit_result = subprocess.run(
            [CLAUDE_PATH, "-p", "/audit --auto-implement"],
            cwd=CLAUDE_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_UTF8_ENV,
            timeout=3600,
        )
    except subprocess.TimeoutExpired:
        logger.error("Audit timed out (3600s)")
        send_slack_message(
            "#claude-auto",
            f":warning: *Daily Audit ({today})* — 타임아웃 (60분 초과)",
        )
        return
    except Exception as exc:
        logger.error(f"Audit failed: {exc}")
        send_slack_message(
            "#claude-auto",
            f":x: *Daily Audit ({today})* — 실행 실패\n```{exc}```",
        )
        return

    if audit_result.stdout:
        logger.info(audit_result.stdout.rstrip())
    if audit_result.stderr:
        logger.error(audit_result.stderr.rstrip())

    # 결과 요약 추출
    audit_report = AUDIT_DIR / f"daily-{today}.md"
    if audit_report.exists():
        summary = extract_audit_summary(audit_report)
    else:
        summary = audit_result.stdout[:1500] if audit_result.stdout else "(출력 없음)"

    status = ":white_check_mark:" if audit_result.returncode == 0 else ":warning:"
    send_slack_message(
        "#claude-auto",
        f"{status} *Daily Audit ({today})*\n```{summary}```",
    )
    logger.info(f"Audit completed — {today} (exit={audit_result.returncode})")


def run_auto_remediation(logger: logging.Logger, today: str) -> None:
    """Step 5: 브리핑 '앞으로 대비' 항목 자동 해결."""
    logger.info("Step 5: Auto-remediation starting...")
    try:
        result = subprocess.run(
            [CLAUDE_PATH, "-p",
             "아래 작업을 자동으로 처리하세요. 각 항목 처리 후 Slack #claude-auto에 결과를 보고하세요:\n"
             "1. GitHub 이슈 트리아지: 30일+ 방치된 이슈에 자동 코멘트 (진행 상황 확인 요청)\n"
             "2. 60일+ 방치 이슈는 stale 라벨 추가\n"
             "3. 스냅샷 갱신: work_tracker로 최신 스냅샷 생성\n"
             "처리 결과를 간단히 요약하세요."],
            cwd=CLAUDE_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_UTF8_ENV,
            timeout=1800,
        )
        if result.stdout:
            logger.info(result.stdout[-2000:].rstrip())
        if result.stderr:
            logger.error(result.stderr[-1000:].rstrip())

        status = ":white_check_mark:" if result.returncode == 0 else ":warning:"
        summary = result.stdout[-1500:] if result.stdout else "(출력 없음)"
        send_slack_message(
            "#claude-auto",
            f"{status} *Auto-Remediation ({today})*\n```{summary[:1500]}```",
        )
        logger.info(f"Auto-remediation completed — {today} (exit={result.returncode})")
    except subprocess.TimeoutExpired:
        logger.error("Auto-remediation timed out (1800s)")
        send_slack_message(
            "#claude-auto",
            f":warning: *Auto-Remediation ({today})* — 타임아웃 (30분 초과)",
        )
    except Exception as exc:
        logger.error(f"Auto-remediation failed: {exc}")


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
        env=_UTF8_ENV,
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

    # Step 1-3: /daily 파이프라인 (실패해도 Step 4 진행)
    try:
        run_cmd([*WORK_TRACKER, "collect", "--date", yesterday], logger)
        run_cmd([*WORK_TRACKER, "summary", "--json", "--date", today], logger, check=False)

        logger.info("Invoking Claude Code for 3시제 analysis...")
        claude_result = subprocess.run(
            [CLAUDE_PATH, "-p", "/daily"],
            cwd=SECRETARY_DIR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_UTF8_ENV,
            timeout=600,
        )
        if claude_result.stdout:
            logger.info(claude_result.stdout.rstrip())
        if claude_result.stderr:
            logger.error(claude_result.stderr.rstrip())

        if claude_result.returncode == 0:
            logger.info(f"Briefing completed successfully — {today}")
        else:
            logger.error(f"Claude Code /daily exited with code {claude_result.returncode}")
    except Exception as exc:
        logger.error(f"/daily pipeline failed: {exc}")
        send_slack_error(str(exc))

    # Step 4: /audit 설정 점검 + Slack 보고 (/daily 실패와 무관하게 실행)
    run_audit(logger, today)

    # Step 5: 자동 해결 파이프라인 (/daily 및 /audit 실패와 무관하게 실행)
    run_auto_remediation(logger, today)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        error_msg = str(exc)
        print(f"[morning] FATAL: {error_msg}", file=sys.stderr)
        send_slack_error(error_msg)
        sys.exit(1)
