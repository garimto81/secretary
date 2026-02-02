"""
Secretary CLI - Click-based command line interface.

Usage:
    secretary "오늘 할 일 알려줘"     # Natural language query
    secretary brief                    # Daily briefing
    secretary emails                   # Email tasks
    secretary calendar                 # Today's calendar
    secretary github                   # GitHub status
    secretary schedule install         # Install Windows Task Scheduler
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import TypeVar

import click

# Windows UTF-8 encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Script paths
SCRIPTS_DIR = Path(r"C:\claude\secretary\scripts")
DAILY_REPORT_SCRIPT = SCRIPTS_DIR / "daily_report.py"
GMAIL_SCRIPT = SCRIPTS_DIR / "gmail_analyzer.py"
CALENDAR_SCRIPT = SCRIPTS_DIR / "calendar_analyzer.py"
GITHUB_SCRIPT = SCRIPTS_DIR / "github_analyzer.py"
SLACK_SCRIPT = SCRIPTS_DIR / "slack_analyzer.py"
LLM_SCRIPT = SCRIPTS_DIR / "llm_analyzer.py"

T = TypeVar("T")


def async_command(f: Callable[..., T]) -> Callable[..., T]:
    """Decorator to convert async function to Click command."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


def run_script(script_path: Path, args: list[str] | None = None) -> str:
    """Run a Python script and return output."""
    if not script_path.exists():
        return f"Error: Script not found - {script_path}"

    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=SCRIPTS_DIR.parent,
        )

        output = result.stdout
        if result.stderr and result.returncode != 0:
            output += f"\n{result.stderr}"

        return output

    except subprocess.TimeoutExpired:
        return f"Error: Script timeout - {script_path.name}"
    except Exception as e:
        return f"Error: {e}"


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("-q", "--query", help="Natural language query")
def cli(ctx: click.Context, query: str | None) -> None:
    """Secretary AI Assistant

    Natural language query:
        secretary -q "What do I need to do today?"
        secretary ask "What do I need to do today?"

    Explicit commands:
        secretary brief
        secretary emails
        secretary calendar
        secretary github
    """
    if ctx.invoked_subcommand is None and query:
        # Natural language query
        asyncio.run(handle_query(query))
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


async def handle_query(query: str) -> None:
    """Handle natural language query."""
    try:
        from secretary.llm import ClaudeClient

        client = ClaudeClient()
        intent = await client.classify_intent(query)

        if intent == "summary":
            # Run daily report
            click.echo("Generating daily briefing...")
            output = run_script(DAILY_REPORT_SCRIPT)
            click.echo(output)
        elif intent == "query":
            # Handle specific question with context
            click.echo(f"Processing query: {query}")
            # Gather context and respond
            output = run_script(DAILY_REPORT_SCRIPT, ["--json"])
            analysis = await client.analyze(
                {"query": query, "context": output[:5000]},
                prompt_template="User query: {{data}}\n\nProvide a helpful response in Korean.",
            )
            click.echo(analysis)
        elif intent == "alert":
            # Check alerts
            click.echo("Checking alerts...")
            output = run_script(DAILY_REPORT_SCRIPT, ["--json"])
            click.echo(output)
        elif intent == "action":
            # Action required - show help
            click.echo("Action commands available:")
            click.echo("  secretary schedule install  - Install daily briefing scheduler")
            click.echo("  secretary schedule remove   - Remove scheduler")
        else:
            click.echo(f"Unknown intent: {intent}")

    except ImportError:
        click.echo("Error: ClaudeClient not available. Set ANTHROPIC_API_KEY.")
        click.echo("Running default daily briefing instead...")
        output = run_script(DAILY_REPORT_SCRIPT)
        click.echo(output)
    except Exception as e:
        click.echo(f"Error processing query: {e}")
        click.echo("Running default daily briefing instead...")
        output = run_script(DAILY_REPORT_SCRIPT)
        click.echo(output)


@cli.command()
@click.argument("query", nargs=-1, required=True)
@async_command
async def ask(query: tuple[str, ...]) -> None:
    """Ask a natural language question.

    Example:
        secretary ask What should I do today?
        secretary ask "오늘 일정 알려줘"
    """
    query_text = " ".join(query)
    await handle_query(query_text)


@cli.command()
@async_command
async def brief() -> None:
    """Daily briefing output."""
    output = run_script(DAILY_REPORT_SCRIPT)
    click.echo(output)


@cli.command()
@async_command
async def emails() -> None:
    """Email tasks output."""
    output = run_script(GMAIL_SCRIPT, ["--unread", "--days", "3"])
    click.echo(output)


@cli.command()
@async_command
async def calendar() -> None:
    """Today's calendar output."""
    output = run_script(CALENDAR_SCRIPT, ["--today"])
    click.echo(output)


@cli.command()
@async_command
async def github() -> None:
    """GitHub status output."""
    output = run_script(GITHUB_SCRIPT, ["--days", "5"])
    click.echo(output)


@cli.command()
@async_command
async def slack() -> None:
    """Slack mentions output."""
    output = run_script(SLACK_SCRIPT, ["--days", "3"])
    click.echo(output)


@cli.command()
@async_command
async def llm() -> None:
    """LLM session analysis output."""
    output = run_script(LLM_SCRIPT, ["--days", "7", "--source", "claude_code"])
    click.echo(output)


@cli.group()
def schedule() -> None:
    """Scheduler management."""
    pass


@schedule.command("install")
def schedule_install() -> None:
    """Register daily briefing to Windows Task Scheduler."""
    task_name = "Secretary\\DailyBrief"
    script_path = DAILY_REPORT_SCRIPT
    python_exe = sys.executable

    # Create batch file for proper execution
    batch_content = f'@echo off\ncd /d "{SCRIPTS_DIR.parent}"\n"{python_exe}" "{script_path}"\n'
    batch_path = SCRIPTS_DIR.parent / "run_daily_report.bat"

    try:
        batch_path.write_text(batch_content, encoding="utf-8")
    except OSError as e:
        click.echo(f"Failed to create batch file: {e}")
        return

    cmd = [
        "schtasks",
        "/create",
        "/tn",
        task_name,
        "/tr",
        str(batch_path),
        "/sc",
        "daily",
        "/st",
        "09:00",
        "/f",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        click.echo("Daily briefing registered to run daily at 09:00.")
        click.echo(f"  Task name: {task_name}")
        click.echo(f"  Script: {script_path}")
    else:
        click.echo(f"Registration failed: {result.stderr or result.stdout}")


@schedule.command("remove")
def schedule_remove() -> None:
    """Remove from Windows Task Scheduler."""
    task_name = "Secretary\\DailyBrief"

    cmd = [
        "schtasks",
        "/delete",
        "/tn",
        task_name,
        "/f",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        click.echo("Schedule removed.")

        # Also remove batch file
        batch_path = SCRIPTS_DIR.parent / "run_daily_report.bat"
        if batch_path.exists():
            batch_path.unlink()
            click.echo("Batch file removed.")
    else:
        click.echo(f"Removal failed: {result.stderr or result.stdout}")


@schedule.command("status")
def schedule_status() -> None:
    """Check schedule status."""
    task_name = "Secretary\\DailyBrief"

    cmd = [
        "schtasks",
        "/query",
        "/tn",
        task_name,
        "/v",
        "/fo",
        "list",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="cp949", errors="replace")

    if result.returncode == 0:
        click.echo(result.stdout)
    else:
        click.echo("Schedule not registered.")


if __name__ == "__main__":
    cli()
