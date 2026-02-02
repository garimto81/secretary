"""
Tests for Claude API client and prompt loader.

Uses mocked Anthropic client to avoid actual API calls.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Test imports
from secretary.core.exceptions import AuthenticationError


class TestClaudeClientInit:
    """Tests for ClaudeClient initialization."""

    def test_init_without_api_key_raises_error(self):
        """Should raise AuthenticationError when API key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("secretary.llm.claude_client.load_dotenv"):
                # Clear any existing ANTHROPIC_API_KEY
                if "ANTHROPIC_API_KEY" in os.environ:
                    del os.environ["ANTHROPIC_API_KEY"]

                from secretary.llm.claude_client import ClaudeClient

                with pytest.raises(AuthenticationError) as exc_info:
                    ClaudeClient()

                assert "ANTHROPIC_API_KEY" in str(exc_info.value)
                assert ".env" in str(exc_info.value)

    def test_init_with_api_key_succeeds(self):
        """Should initialize successfully with valid API key."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("secretary.llm.claude_client.Anthropic") as mock_anthropic:
                from secretary.llm.claude_client import ClaudeClient

                client = ClaudeClient()

                assert client.client is not None
                mock_anthropic.assert_called_once_with(api_key="test-key")


class TestClaudeClientModels:
    """Tests for model tier constants."""

    def test_model_tiers_defined(self):
        """Should have all model tiers defined."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("secretary.llm.claude_client.Anthropic"):
                from secretary.llm.claude_client import ClaudeClient

                assert ClaudeClient.HAIKU == "claude-3-5-haiku-20241022"
                assert ClaudeClient.SONNET == "claude-sonnet-4-20250514"
                assert ClaudeClient.OPUS == "claude-opus-4-20250514"


class TestClaudeClientChat:
    """Tests for chat functionality."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked ClaudeClient."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("secretary.llm.claude_client.Anthropic") as mock_anthropic:
                mock_response = MagicMock()
                mock_response.content = [MagicMock(text="Test response")]
                mock_anthropic.return_value.messages.create.return_value = mock_response

                from secretary.llm.claude_client import ClaudeClient
                client = ClaudeClient()
                client._mock_anthropic = mock_anthropic
                yield client

    @pytest.mark.asyncio
    async def test_chat_returns_response(self, mock_client):
        """Should return response text from API."""
        messages = [{"role": "user", "content": "Hello"}]

        result = await mock_client.chat(messages)

        assert result == "Test response"

    @pytest.mark.asyncio
    async def test_chat_uses_default_model(self, mock_client):
        """Should use SONNET as default model."""
        messages = [{"role": "user", "content": "Hello"}]

        await mock_client.chat(messages)

        call_kwargs = mock_client._mock_anthropic.return_value.messages.create.call_args.kwargs
        assert call_kwargs["model"] == mock_client.SONNET

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self, mock_client):
        """Should include system prompt when provided."""
        messages = [{"role": "user", "content": "Hello"}]

        await mock_client.chat(messages, system="You are helpful")

        call_kwargs = mock_client._mock_anthropic.return_value.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are helpful"


class TestClaudeClientClassifyIntent:
    """Tests for intent classification."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked ClaudeClient."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("secretary.llm.claude_client.Anthropic") as mock_anthropic:
                from secretary.llm.claude_client import ClaudeClient
                client = ClaudeClient()
                client._mock_anthropic = mock_anthropic
                yield client

    @pytest.mark.asyncio
    async def test_classify_intent_query(self, mock_client):
        """Should classify question as 'query'."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="query")]
        mock_client._mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await mock_client.classify_intent("What meetings do I have today?")

        assert result == "query"

    @pytest.mark.asyncio
    async def test_classify_intent_summary(self, mock_client):
        """Should classify summary request as 'summary'."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="summary")]
        mock_client._mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await mock_client.classify_intent("Summarize my emails from today")

        assert result == "summary"

    @pytest.mark.asyncio
    async def test_classify_intent_action(self, mock_client):
        """Should classify action request as 'action'."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="action")]
        mock_client._mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await mock_client.classify_intent("Create a meeting for tomorrow at 2pm")

        assert result == "action"

    @pytest.mark.asyncio
    async def test_classify_intent_alert(self, mock_client):
        """Should classify alert request as 'alert'."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="alert")]
        mock_client._mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await mock_client.classify_intent("Notify me about urgent emails")

        assert result == "alert"

    @pytest.mark.asyncio
    async def test_classify_intent_invalid_defaults_to_query(self, mock_client):
        """Should default to 'query' for invalid responses."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="invalid_intent")]
        mock_client._mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await mock_client.classify_intent("Some weird input")

        assert result == "query"

    @pytest.mark.asyncio
    async def test_classify_intent_uses_haiku(self, mock_client):
        """Should use HAIKU model for fast classification."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="query")]
        mock_client._mock_anthropic.return_value.messages.create.return_value = mock_response

        await mock_client.classify_intent("Test input")

        call_kwargs = mock_client._mock_anthropic.return_value.messages.create.call_args.kwargs
        assert call_kwargs["model"] == mock_client.HAIKU


class TestPromptLoader:
    """Tests for prompt template loading."""

    @pytest.fixture
    def prompts_dir(self, tmp_path):
        """Create a temporary prompts directory with test templates."""
        prompts = tmp_path / "prompts"
        prompts.mkdir()

        # Create test templates
        (prompts / "system.md").write_text("You are a test assistant.", encoding="utf-8")
        (prompts / "analyze.md").write_text("Analyze: {{data}}", encoding="utf-8")
        (prompts / "notify.md").write_text("Notify about: {{context}}", encoding="utf-8")
        (prompts / "multi.md").write_text("{{var1}} and {{var2}}", encoding="utf-8")

        return prompts

    def test_load_template(self, prompts_dir):
        """Should load template content from file."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)
        content = loader.load("system")

        assert content == "You are a test assistant."

    def test_load_template_caches(self, prompts_dir):
        """Should cache loaded templates."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)
        loader.load("system")

        # Modify file after loading
        (prompts_dir / "system.md").write_text("Modified content", encoding="utf-8")

        # Should return cached version
        content = loader.load("system")
        assert content == "You are a test assistant."

    def test_load_nonexistent_raises_error(self, prompts_dir):
        """Should raise FileNotFoundError for missing templates."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)

        with pytest.raises(FileNotFoundError) as exc_info:
            loader.load("nonexistent")

        assert "Prompt template not found" in str(exc_info.value)

    def test_render_substitutes_variables(self, prompts_dir):
        """Should substitute variables in template."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)
        result = loader.render("analyze", data="test data")

        assert result == "Analyze: test data"

    def test_render_multiple_variables(self, prompts_dir):
        """Should substitute multiple variables."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)
        result = loader.render("multi", var1="first", var2="second")

        assert result == "first and second"

    def test_render_missing_variable_preserved(self, prompts_dir):
        """Should preserve unsubstituted variables."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)
        result = loader.render("multi", var1="first")  # var2 not provided

        assert result == "first and {{var2}}"

    def test_clear_cache(self, prompts_dir):
        """Should clear the template cache."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)
        loader.load("system")
        assert "system" in loader._cache

        loader.clear_cache()
        assert "system" not in loader._cache

    def test_list_templates(self, prompts_dir):
        """Should list available template names."""
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader(prompts_dir)
        templates = loader.list_templates()

        assert "system" in templates
        assert "analyze" in templates
        assert "notify" in templates
        assert "multi" in templates


class TestPromptLoaderDefaultDir:
    """Tests for default prompts directory."""

    def test_default_prompts_dir_exists(self):
        """Should have default prompts directory configured."""
        from secretary.llm.prompts import PROMPTS_DIR

        assert PROMPTS_DIR == Path(r"C:\claude\secretary\config\prompts")

    def test_load_actual_system_prompt(self):
        """Should load actual system prompt from config/prompts."""
        from secretary.llm.prompts import PROMPTS_DIR, PromptLoader

        if not PROMPTS_DIR.exists():
            pytest.skip("Prompts directory not found")

        loader = PromptLoader()
        content = loader.load("system")

        assert "Secretary" in content
        assert "AI 비서" in content

    def test_load_actual_analyze_prompt(self):
        """Should load actual analyze prompt from config/prompts."""
        from secretary.llm.prompts import PROMPTS_DIR, PromptLoader

        if not PROMPTS_DIR.exists():
            pytest.skip("Prompts directory not found")

        loader = PromptLoader()
        content = loader.load("analyze")

        assert "{{data}}" in content
        assert "우선순위" in content

    def test_load_actual_notify_prompt(self):
        """Should load actual notify prompt from config/prompts."""
        from secretary.llm.prompts import PROMPTS_DIR, PromptLoader

        if not PROMPTS_DIR.exists():
            pytest.skip("Prompts directory not found")

        loader = PromptLoader()
        content = loader.load("notify")

        assert "{{context}}" in content
        assert "50자" in content
