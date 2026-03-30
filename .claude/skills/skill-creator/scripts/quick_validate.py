#!/usr/bin/env python3
"""
Quick validation script for skills - minimal version
Uses proper YAML parsing to handle multiline descriptions correctly.
"""

import sys
import re
import yaml
from pathlib import Path


def validate_skill(skill_path):
    """Basic validation of a skill"""
    skill_path = Path(skill_path)

    # Check SKILL.md exists
    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, "SKILL.md not found"

    # Read content
    content = skill_md.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return False, "No YAML frontmatter found"

    # Extract and parse frontmatter with YAML
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format"

    try:
        fm = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        return False, f"YAML parse error: {e}"

    if not fm or not isinstance(fm, dict):
        return False, "Frontmatter is empty or not a mapping"

    # Check required fields
    if "name" not in fm:
        return False, "Missing 'name' in frontmatter"
    if "description" not in fm:
        return False, "Missing 'description' in frontmatter"

    # Validate name
    name = str(fm["name"]).strip()
    if not re.match(r"^[a-z0-9-]+$", name):
        return False, f"Name '{name}' should be hyphen-case (lowercase letters, digits, and hyphens only)"
    if name.startswith("-") or name.endswith("-") or "--" in name:
        return False, f"Name '{name}' cannot start/end with hyphen or contain consecutive hyphens"

    # Validate description
    description = str(fm["description"]).strip()
    if "<" in description or ">" in description:
        return False, "Description cannot contain angle brackets (< or >)"
    if len(description) < 30:
        return False, f"Description too short ({len(description)} chars, minimum 30)"
    if description.upper().startswith("TODO"):
        return False, "Description contains placeholder text"

    return True, "Skill is valid!"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python quick_validate.py <skill_directory>")
        sys.exit(1)

    valid, message = validate_skill(sys.argv[1])
    print(message)
    sys.exit(0 if valid else 1)
