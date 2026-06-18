#!/usr/bin/env python3
"""
Phase 2 migration: Create agents/{agent_id}/ folder structure from
deepseek_flash/ and deepseek_pro/ .md prompt files.

For each .md file:
  1. Create folder agents/{agent_id}/
  2. Extract YAML frontmatter + ## System + ## User → prompt.md (or .flash.md / .pro.md)
  3. Extract ## Output Schema JSON → schema.en.json

.txt legacy files are skipped.
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
    base = Path(__file__).resolve().parent
    agents_dir = base / "agents"

    # Collect all .md files from deepseek_flash/ and deepseek_pro/
    flash_dir = base / "deepseek_flash"
    pro_dir = base / "deepseek_pro"

    flash_files: dict[str, Path] = {}
    pro_files: dict[str, Path] = {}

    for f in sorted(flash_dir.glob("*.md")):
        agent_id = f.stem  # filename without extension
        flash_files[agent_id] = f

    for f in sorted(pro_dir.glob("*.md")):
        agent_id = f.stem
        pro_files[agent_id] = f

    # All unique agent_ids
    all_ids = sorted(set(flash_files.keys()) | set(pro_files.keys()))

    print(f"Found {len(flash_files)} flash .md files, {len(pro_files)} pro .md files")
    print(f"Unique agent IDs: {len(all_ids)}")
    print()

    stats = {"created": 0, "flash_only": 0, "pro_only": 0, "dual": 0, "errors": 0}

    for agent_id in all_ids:
        print(f"Agent: {agent_id}")
        agent_folder = agents_dir / agent_id
        agent_folder.mkdir(parents=True, exist_ok=True)

        in_flash = agent_id in flash_files
        in_pro = agent_id in pro_files

        schema = None

        if in_flash and in_pro:
            # Dual: create both .flash.md and .pro.md
            stats["dual"] += 1
            print(f"  DUAL (flash + pro)")

            # Process flash version
            _ = process_file(flash_files[agent_id], agent_folder, suffix=".flash")

            # Process pro version, use its schema
            schema = process_file(pro_files[agent_id], agent_folder, suffix=".pro")

        elif in_flash:
            # Flash only
            stats["flash_only"] += 1
            print(f"  FLASH only")
            schema = process_file(flash_files[agent_id], agent_folder, suffix="")

        elif in_pro:
            # Pro only
            stats["pro_only"] += 1
            print(f"  PRO only")
            schema = process_file(pro_files[agent_id], agent_folder, suffix="")

        # Write schema.en.json
        if schema is not None:
            schema_path = agent_folder / "schema.en.json"
            schema_path.write_text(
                json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(f"    Wrote: {schema_path}")
        else:
            print(f"    WARNING: No schema extracted, skipping schema.en.json")
            stats["errors"] += 1

        stats["created"] += 1
        print()

    print("=" * 60)
    print(f"Migration complete!")
    print(f"  Total agents created: {stats['created']}")
    print(f"  Flash only: {stats['flash_only']}")
    print(f"  Pro only:   {stats['pro_only']}")
    print(f"  Dual:       {stats['dual']}")
    print(f"  Errors:     {stats['errors']}")


if __name__ == "__main__":
    main()
