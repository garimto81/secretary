"""
LLM integration module for Secretary.

Provides Claude API client and prompt template management.
"""

from secretary.llm.claude_client import ClaudeClient
from secretary.llm.prompts import PromptLoader

__all__ = ["ClaudeClient", "PromptLoader"]
