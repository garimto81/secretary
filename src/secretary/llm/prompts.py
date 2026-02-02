"""
Prompt template loader and renderer for Secretary.

Loads prompt templates from config/prompts directory
and supports variable substitution.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Absolute path to prompts directory
PROMPTS_DIR = Path(r"C:\claude\secretary\config\prompts")


class PromptLoader:
    """
    Prompt template loader with caching and variable substitution.

    Templates are loaded from config/prompts/*.md files.
    Variables use Mustache-style syntax: {{variable_name}}

    Usage:
        loader = PromptLoader()
        system_prompt = loader.load("system")
        analysis_prompt = loader.render("analyze", data="...")
    """

    def __init__(self, prompts_dir: Path | None = None):
        """
        Initialize prompt loader.

        Args:
            prompts_dir: Custom prompts directory (defaults to config/prompts)
        """
        self.prompts_dir = prompts_dir or PROMPTS_DIR
        self._cache: dict[str, str] = {}
        logger.debug("PromptLoader initialized with dir: %s", self.prompts_dir)

    def load(self, name: str) -> str:
        """
        Load prompt template by name (with caching).

        Args:
            name: Template name (without .md extension)

        Returns:
            Template content as string

        Raises:
            FileNotFoundError: If template file doesn't exist
        """
        if name in self._cache:
            logger.debug("Loading prompt '%s' from cache", name)
            return self._cache[name]

        file_path = self.prompts_dir / f"{name}.md"

        if not file_path.exists():
            raise FileNotFoundError(
                f"Prompt template not found: {file_path}. "
                f"Create the file or check the prompts directory."
            )

        content = file_path.read_text(encoding="utf-8")
        self._cache[name] = content

        logger.debug("Loaded prompt '%s': %d chars", name, len(content))
        return content

    def render(self, name: str, **kwargs: Any) -> str:
        """
        Load template and substitute variables.

        Variables in template use {{variable_name}} syntax.

        Args:
            name: Template name
            **kwargs: Variables to substitute

        Returns:
            Rendered template with variables substituted

        Example:
            loader.render("analyze", data="...", format="json")
            # Template: "Analyze {{data}} and output as {{format}}"
            # Result: "Analyze ... and output as json"
        """
        template = self.load(name)

        # Find all {{variable}} patterns
        pattern = re.compile(r"\{\{(\w+)\}\}")

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            if var_name in kwargs:
                return str(kwargs[var_name])
            logger.warning("Variable '%s' not provided for template '%s'", var_name, name)
            return match.group(0)  # Keep original if not found

        result = pattern.sub(replacer, template)
        logger.debug("Rendered prompt '%s' with %d variables", name, len(kwargs))
        return result

    def clear_cache(self) -> None:
        """Clear the template cache."""
        self._cache.clear()
        logger.debug("Prompt cache cleared")

    def list_templates(self) -> list[str]:
        """
        List available template names.

        Returns:
            List of template names (without .md extension)
        """
        if not self.prompts_dir.exists():
            return []

        templates = [
            f.stem for f in self.prompts_dir.glob("*.md") if f.is_file()
        ]
        return sorted(templates)
