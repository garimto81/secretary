"""
Claude API client wrapper for Secretary.

Provides model-tiered access to Claude API with specialized methods
for intent classification, analysis, and summarization.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

from secretary.core.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class ClaudeClient:
    """
    Claude API client wrapper with model tiering.

    Model Tiers:
        - HAIKU: Fast, lightweight tasks (intent classification, simple queries)
        - SONNET: Balanced tasks (analysis, summarization)
        - OPUS: Complex reasoning (deep analysis, multi-step planning)

    Usage:
        client = ClaudeClient()
        intent = await client.classify_intent("What meetings do I have today?")
        analysis = await client.analyze({"emails": [...], "calendar": [...]})
    """

    # Model tiers
    HAIKU = "claude-3-5-haiku-20241022"
    SONNET = "claude-sonnet-4-20250514"
    OPUS = "claude-opus-4-20250514"

    def __init__(self):
        """
        Initialize Claude client with API key from environment.

        Raises:
            AuthenticationError: If ANTHROPIC_API_KEY is not found in .env
        """
        load_dotenv()
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise AuthenticationError(
                "ANTHROPIC_API_KEY not found in .env file. "
                "Copy .env.example to .env and add your API key.",
                service="anthropic",
            )
        self.client = Anthropic(api_key=api_key)
        logger.debug("Claude client initialized")

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """
        Send messages and receive response.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            model: Model to use (defaults to SONNET)
            system: System prompt (optional)
            max_tokens: Maximum response tokens
            temperature: Sampling temperature (0-1)

        Returns:
            Response text from Claude

        Raises:
            AuthenticationError: If API call fails due to auth issues
        """
        model = model or self.SONNET

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            kwargs["system"] = system

        # Sonnet/Opus 사용 시 temperature 설정
        if temperature != 1.0:
            kwargs["temperature"] = temperature

        logger.debug("Sending chat request to %s with %d messages", model, len(messages))

        try:
            response = self.client.messages.create(**kwargs)
            result = response.content[0].text
            logger.debug("Received response: %d chars", len(result))
            return result
        except Exception as e:
            logger.error("Chat request failed: %s", e)
            raise

    async def classify_intent(self, text: str) -> str:
        """
        Classify user intent using Haiku for fast response.

        Args:
            text: User input text to classify

        Returns:
            Intent type: 'query', 'summary', 'alert', or 'action'
        """
        system = """You are an intent classifier. Classify the user's intent into exactly one of these categories:
- query: User is asking a question or requesting information
- summary: User wants a summary or overview of their data
- alert: User wants to be notified about something important
- action: User wants to perform an action (create event, send message, etc.)

Respond with ONLY the intent category name, nothing else."""

        messages = [{"role": "user", "content": text}]

        result = await self.chat(
            messages=messages,
            model=self.HAIKU,
            system=system,
            max_tokens=20,
            temperature=0.0,
        )

        intent = result.strip().lower()
        valid_intents = {"query", "summary", "alert", "action"}

        if intent not in valid_intents:
            logger.warning("Invalid intent '%s', defaulting to 'query'", intent)
            return "query"

        logger.debug("Classified intent: %s", intent)
        return intent

    async def analyze(
        self,
        data: dict[str, Any],
        prompt_template: str | None = None,
    ) -> str:
        """
        Analyze data using Sonnet for balanced performance.

        Args:
            data: Dictionary of data to analyze (e.g., emails, calendar, github)
            prompt_template: Optional custom prompt template with {{data}} placeholder

        Returns:
            Analysis result as formatted text
        """
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader()

        if prompt_template:
            prompt = prompt_template.replace("{{data}}", str(data))
        else:
            prompt = loader.render("analyze", data=str(data))

        system = loader.load("system")

        messages = [{"role": "user", "content": prompt}]

        result = await self.chat(
            messages=messages,
            model=self.SONNET,
            system=system,
            max_tokens=4096,
            temperature=0.3,
        )

        logger.debug("Analysis complete: %d chars", len(result))
        return result

    async def summarize(self, content: str, max_length: int = 500) -> str:
        """
        Summarize content concisely.

        Args:
            content: Text content to summarize
            max_length: Target maximum length of summary

        Returns:
            Concise summary of the content
        """
        system = f"""You are a summarization expert. Create a concise summary in Korean.
Target length: approximately {max_length} characters.
Focus on key points and actionable items.
Use bullet points for clarity."""

        messages = [
            {
                "role": "user",
                "content": f"다음 내용을 요약해주세요:\n\n{content}",
            }
        ]

        result = await self.chat(
            messages=messages,
            model=self.SONNET,
            system=system,
            max_tokens=1024,
            temperature=0.3,
        )

        return result.strip()

    async def generate_notification(self, context: dict[str, Any]) -> str:
        """
        Generate a notification message based on context.

        Args:
            context: Notification context (type, data, urgency, etc.)

        Returns:
            Brief notification message (50 chars or less)
        """
        from secretary.llm.prompts import PromptLoader

        loader = PromptLoader()
        prompt = loader.render("notify", context=str(context))

        messages = [{"role": "user", "content": prompt}]

        result = await self.chat(
            messages=messages,
            model=self.HAIKU,
            system="You are a notification generator. Be concise and clear.",
            max_tokens=100,
            temperature=0.5,
        )

        return result.strip()

    async def draft_response(
        self,
        email_content: str,
        sender: str,
        subject: str,
    ) -> str:
        """
        Draft an email response.

        Args:
            email_content: Original email body
            sender: Email sender
            subject: Email subject

        Returns:
            Draft response text
        """
        system = """You are an email assistant. Draft professional, polite responses in Korean.
Keep responses concise but complete.
Match the formality level of the original email.
Never include placeholder text like [Name] or [Your Name]."""

        prompt = f"""다음 이메일에 대한 응답 초안을 작성해주세요:

보낸 사람: {sender}
제목: {subject}

본문:
{email_content}

응답 초안:"""

        messages = [{"role": "user", "content": prompt}]

        result = await self.chat(
            messages=messages,
            model=self.SONNET,
            system=system,
            max_tokens=2048,
            temperature=0.7,
        )

        return result.strip()
