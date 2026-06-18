#!/usr/bin/env python3
"""
Phase 2 migration: Create agents/{agent_id}/ folder structure.

This script has been run. The deepseek_pro/ and deepseek_flash/
directories have been deleted. All prompts now live in agents/{agent_id}/prompt.md.

This file is kept for historical reference.
"""

import json
import re
import sys
from pathlib import Path


def parse_frontmatter_and_body(content: str) -> tuple[str, str]:
    """Split content into YAML frontmatter (including --- delimiters) and body."""
    # Match YAML frontmatter between --- markers
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        print("  WARNING: No YAML frontmatter found", file=sys.stderr)
        return "", content
    return m.group(0), content[m.end() :]


def strip_output_schema(body: str) -> str:
    """Remove the ## Output Schema section and everything after it."""
    # Split on ## Output Schema (case insensitive, with optional trailing text)
    parts = re.split(r"\n## Output Schema\b", body, maxsplit=1, flags=re.IGNORECASE)
    return parts[0].rstrip() + "\n"


def extract_schema_json(body: str) -> dict | None:
    """Extract JSON from ```json ... ``` block in ## Output Schema section."""
    # Find the ## Output Schema section
    m = re.search(r"\n## Output Schema\b(.*)", body, re.DOTALL | re.IGNORECASE)
    if not m:
        print("  WARNING: No ## Output Schema section found", file=sys.stderr)
        return None

    schema_section = m.group(1)

    # Extract JSON from ```json ... ``` block
    json_m = re.search(r"```json\s*\n(.*?)\n```", schema_section, re.DOTALL)
    if not json_m:
        # Try without language specifier
        json_m = re.search(r"```\s*\n(.*?)\n```", schema_section, re.DOTALL)
    if not json_m:
        print("  WARNING: No JSON block found in ## Output Schema", file=sys.stderr)
        return None

    json_str = json_m.group(1)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  WARNING: Invalid JSON in schema: {e}", file=sys.stderr)
        return None


def get_model_profile(content: str) -> str | None:
    """Determine model_profile from YAML frontmatter."""
    m = re.search(r"^model_profile:\s*(\S+)", content, re.MULTILINE)
    if m:
        return m.group(1).strip().lower()
    # Check for tier field (pro files use this)
    m = re.search(r"^tier:\s*(\S+)", content, re.MULTILINE)
    if m:
        tier = m.group(1).strip().upper()
        if tier == "PRO":
            return "pro"
    return None


def process_file(filepath: Path, output_dir: Path, suffix: str) -> dict | None:
    """
    Process a single .md file:
    - Write prompt{suffix}.md (without Output Schema)
    - Return the extracted schema JSON (or None)
    """
    print(f"  Processing: {filepath}")
    content = filepath.read_text(encoding="utf-8")

    frontmatter, body = parse_frontmatter_and_body(content)
    prompt_body = strip_output_schema(body)
    schema = extract_schema_json(body)

    # Write prompt file
    prompt_filename = f"prompt{suffix}.md"
    prompt_path = output_dir / prompt_filename
    prompt_content = frontmatter + prompt_body
    prompt_path.write_text(prompt_content, encoding="utf-8")
    print(f"    Wrote: {prompt_path}")

    return schema


def main():
    print("Migration already complete. All prompts live in agents/{agent_id}/prompt.md")
    print("This script is kept for historical reference only.")
    return


if __name__ == "__main__":
    main()
