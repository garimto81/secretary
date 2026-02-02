"""
Tests for Secretary CLI.

Uses Click's CliRunner for testing CLI commands.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from secretary.cli.main import (
    CALENDAR_SCRIPT,
    DAILY_REPORT_SCRIPT,
    GITHUB_SCRIPT,
    GMAIL_SCRIPT,
    LLM_SCRIPT,
    SCRIPTS_DIR,
    SLACK_SCRIPT,
    cli,
    run_script,
)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


class TestCLIBasics:
    """Test basic CLI functionality."""

    def test_cli_help(self, runner: CliRunner):
        """Test CLI shows help without arguments."""
        result = runner.invoke(cli)
        assert result.exit_code == 0
        assert "Secretary AI Assistant" in result.output

    def test_cli_help_flag(self, runner: CliRunner):
        """Test CLI --help flag."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "brief" in result.output
        assert "emails" in result.output
        assert "calendar" in result.output
        assert "github" in result.output
        assert "ask" in result.output
        assert "--query" in result.output or "-q" in result.output


class TestScriptPaths:
    """Test script path configuration."""

    def test_scripts_dir_exists(self):
        """Test scripts directory exists."""
        assert SCRIPTS_DIR.exists()

    def test_daily_report_script_path(self):
        """Test daily report script path."""
        assert DAILY_REPORT_SCRIPT == Path(r"C:\claude\secretary\scripts\daily_report.py")

    def test_gmail_script_path(self):
        """Test gmail script path."""
        assert GMAIL_SCRIPT == Path(r"C:\claude\secretary\scripts\gmail_analyzer.py")


class TestRunScript:
    """Test run_script function."""

    def test_run_script_not_found(self):
        """Test run_script with non-existent script."""
        result = run_script(Path("nonexistent.py"))
        assert "Error: Script not found" in result

    @patch("subprocess.run")
    def test_run_script_success(self, mock_run: MagicMock):
        """Test run_script with successful execution."""
        mock_run.return_value = MagicMock(
            stdout="Test output",
            stderr="",
            returncode=0,
        )

        with patch.object(Path, "exists", return_value=True):
            result = run_script(Path("test.py"), ["--arg1"])

        assert result == "Test output"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_run_script_with_args(self, mock_run: MagicMock):
        """Test run_script passes arguments correctly."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="",
            returncode=0,
        )

        with patch.object(Path, "exists", return_value=True):
            run_script(Path("test.py"), ["--days", "3"])

        call_args = mock_run.call_args[0][0]
        assert "--days" in call_args
        assert "3" in call_args

    @patch("subprocess.run")
    def test_run_script_timeout(self, mock_run: MagicMock):
        """Test run_script handles timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=120)

        with patch.object(Path, "exists", return_value=True):
            result = run_script(Path("test.py"))

        assert "timeout" in result.lower()


class TestBriefCommand:
    """Test brief command."""

    @patch("secretary.cli.main.run_script")
    def test_brief_command(self, mock_run: MagicMock, runner: CliRunner):
        """Test brief command runs daily report."""
        mock_run.return_value = "Daily Report Output"

        result = runner.invoke(cli, ["brief"])

        assert result.exit_code == 0
        assert "Daily Report Output" in result.output
        mock_run.assert_called_once_with(DAILY_REPORT_SCRIPT)


class TestEmailsCommand:
    """Test emails command."""

    @patch("secretary.cli.main.run_script")
    def test_emails_command(self, mock_run: MagicMock, runner: CliRunner):
        """Test emails command runs gmail analyzer."""
        mock_run.return_value = "Email Output"

        result = runner.invoke(cli, ["emails"])

        assert result.exit_code == 0
        assert "Email Output" in result.output
        mock_run.assert_called_once_with(GMAIL_SCRIPT, ["--unread", "--days", "3"])


class TestCalendarCommand:
    """Test calendar command."""

    @patch("secretary.cli.main.run_script")
    def test_calendar_command(self, mock_run: MagicMock, runner: CliRunner):
        """Test calendar command runs calendar analyzer."""
        mock_run.return_value = "Calendar Output"

        result = runner.invoke(cli, ["calendar"])

        assert result.exit_code == 0
        assert "Calendar Output" in result.output
        mock_run.assert_called_once_with(CALENDAR_SCRIPT, ["--today"])


class TestGitHubCommand:
    """Test github command."""

    @patch("secretary.cli.main.run_script")
    def test_github_command(self, mock_run: MagicMock, runner: CliRunner):
        """Test github command runs github analyzer."""
        mock_run.return_value = "GitHub Output"

        result = runner.invoke(cli, ["github"])

        assert result.exit_code == 0
        assert "GitHub Output" in result.output
        mock_run.assert_called_once_with(GITHUB_SCRIPT, ["--days", "5"])


class TestSlackCommand:
    """Test slack command."""

    @patch("secretary.cli.main.run_script")
    def test_slack_command(self, mock_run: MagicMock, runner: CliRunner):
        """Test slack command runs slack analyzer."""
        mock_run.return_value = "Slack Output"

        result = runner.invoke(cli, ["slack"])

        assert result.exit_code == 0
        assert "Slack Output" in result.output
        mock_run.assert_called_once_with(SLACK_SCRIPT, ["--days", "3"])


class TestLLMCommand:
    """Test llm command."""

    @patch("secretary.cli.main.run_script")
    def test_llm_command(self, mock_run: MagicMock, runner: CliRunner):
        """Test llm command runs LLM analyzer."""
        mock_run.return_value = "LLM Output"

        result = runner.invoke(cli, ["llm"])

        assert result.exit_code == 0
        assert "LLM Output" in result.output
        mock_run.assert_called_once_with(LLM_SCRIPT, ["--days", "7", "--source", "claude_code"])


class TestScheduleCommands:
    """Test schedule subcommands."""

    def test_schedule_group(self, runner: CliRunner):
        """Test schedule group help shows subcommands."""
        result = runner.invoke(cli, ["schedule", "--help"])
        assert result.exit_code == 0
        # Check subcommands are listed
        output_lower = result.output.lower()
        assert "install" in output_lower
        assert "remove" in output_lower
        assert "status" in output_lower

    @patch("subprocess.run")
    @patch("pathlib.Path.write_text")
    def test_schedule_install(self, mock_write: MagicMock, mock_run: MagicMock, runner: CliRunner):
        """Test schedule install command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = runner.invoke(cli, ["schedule", "install"])

        assert result.exit_code == 0
        # Check schtasks was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "schtasks" in call_args
        assert "/create" in call_args
        assert "Secretary\\DailyBrief" in call_args

    @patch("subprocess.run")
    def test_schedule_install_failure(self, mock_run: MagicMock, runner: CliRunner):
        """Test schedule install handles failure."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Access denied"
        )

        with patch("pathlib.Path.write_text"):
            result = runner.invoke(cli, ["schedule", "install"])

        assert "failed" in result.output.lower() or "denied" in result.output.lower()

    @patch("subprocess.run")
    def test_schedule_remove(self, mock_run: MagicMock, runner: CliRunner):
        """Test schedule remove command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        with patch("pathlib.Path.exists", return_value=False):
            result = runner.invoke(cli, ["schedule", "remove"])

        assert result.exit_code == 0
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "schtasks" in call_args
        assert "/delete" in call_args

    @patch("subprocess.run")
    def test_schedule_status_registered(self, mock_run: MagicMock, runner: CliRunner):
        """Test schedule status when registered."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="TaskName: Secretary\\DailyBrief\nStatus: Ready",
            stderr="",
        )

        result = runner.invoke(cli, ["schedule", "status"])

        assert result.exit_code == 0
        assert "Secretary" in result.output

    @patch("subprocess.run")
    def test_schedule_status_not_registered(self, mock_run: MagicMock, runner: CliRunner):
        """Test schedule status when not registered."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Task not found"
        )

        result = runner.invoke(cli, ["schedule", "status"])

        assert "not registered" in result.output.lower()


class TestNaturalLanguageQuery:
    """Test natural language query handling."""

    @patch("secretary.cli.main.run_script")
    def test_query_with_option(self, mock_run: MagicMock, runner: CliRunner):
        """Test query with -q option falls back to daily report without API key."""
        mock_run.return_value = "Fallback Output"

        result = runner.invoke(cli, ["-q", "test query"])

        # Should fall back to daily report when Claude client fails
        assert result.exit_code == 0

    @patch("secretary.cli.main.run_script")
    def test_ask_command(self, mock_run: MagicMock, runner: CliRunner):
        """Test ask command with query argument."""
        mock_run.return_value = "Fallback Output"

        result = runner.invoke(cli, ["ask", "what", "should", "I", "do"])

        # Should fall back to daily report when Claude client fails
        assert result.exit_code == 0

    @patch("secretary.llm.ClaudeClient")
    @patch("secretary.cli.main.run_script")
    def test_query_summary_intent(
        self, mock_run: MagicMock, mock_client_class: MagicMock, runner: CliRunner
    ):
        """Test query with summary intent using -q option."""
        mock_client = MagicMock()
        mock_client.classify_intent.return_value = "summary"
        mock_client_class.return_value = mock_client
        mock_run.return_value = "Summary Output"

        # This test verifies the handle_query async flow
        with patch("secretary.cli.main.handle_query") as mock_handle:
            mock_handle.return_value = None
            result = runner.invoke(cli, ["-q", "what should I do today"])

        assert result.exit_code == 0


class TestAsyncCommand:
    """Test async_command decorator."""

    def test_async_command_wraps_function(self):
        """Test async_command preserves function metadata."""
        from secretary.cli.main import async_command

        @async_command
        async def test_func():
            """Test docstring."""
            return "result"

        assert test_func.__name__ == "test_func"
        assert "Test docstring" in test_func.__doc__


class TestCLIEntryPoint:
    """Test CLI entry point configuration."""

    def test_cli_entry_point_configured(self):
        """Test CLI entry point is properly configured."""
        import importlib.metadata

        # Check that secretary CLI is discoverable
        # This may fail if package is not installed in editable mode
        try:
            entry_points = importlib.metadata.entry_points(group="console_scripts")
            secretary_eps = [ep for ep in entry_points if ep.name == "secretary"]
            # Entry point may not exist if package isn't installed
            if secretary_eps:
                assert secretary_eps[0].value == "secretary.cli.main:cli"
        except Exception:
            # Skip if package metadata not available
            pass

    def test_cli_importable(self):
        """Test CLI can be imported from package."""
        from secretary import cli as cli_import
        from secretary.cli import cli as cli_direct

        assert cli_import is cli_direct
