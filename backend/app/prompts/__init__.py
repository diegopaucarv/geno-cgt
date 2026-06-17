"""
Prompt template loader.

Each prompt is a .md file with frontmatter metadata and sections:
  ## System
  ## User
  ## Output Schema (JSON codeblock)

Usage:
    from app.prompts import PROMPT_REGISTRY
    template = PROMPT_REGISTRY["batch_coder_producer"]
    messages = template.build_messages(segments_batch="...", existing_codes="...")
"""

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent

# ── Simple YAML-like frontmatter parser (avoids pyyaml dependency) ─────
# Parses:
#   ---
#   key: value
#   key_with_list: item1, item2
#   ---
# Does NOT support nested YAML structures — we only need flat key:value pairs.

_YAML_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def _parse_yaml_frontmatter(text: str) -> dict[str, str]:
    """Extract key: value pairs from YAML frontmatter between --- delimiters."""
    match = _YAML_FRONTMATTER_RE.match(text)
    if not match:
        return {}

    metadata: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
    return metadata


class PromptTemplate:
    """A versioned, hash-tracked prompt template loaded from a .md file."""

    def __init__(
        self,
        prompt_id: str,
        version: str,
        model_profile: str,
        description: str,
        system_template: str,
        user_template: str,
        output_schema: dict[str, Any] | None = None,
        source_path: str = "",
    ):
        self.prompt_id = prompt_id
        self.version = version
        self.model_profile = model_profile
        self.description = description
        self.system_template = system_template
        self.user_template = user_template
        self.output_schema = output_schema or {}
        self.source_path = source_path
        self._hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = (
            f"{self.system_template}\n"
            f"{self.user_template}\n"
            f"{json.dumps(self.output_schema, sort_keys=True)}"
        )
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @property
    def hash(self) -> str:
        return self._hash

    def build_messages(self, **kwargs) -> list[dict[str, str]]:
        """Build the full messages array for the Together.ai API call."""
        system = self.system_template
        user = self.user_template
        if kwargs:
            system = system.format(**kwargs) if "{" in system else system
            user = user.format(**kwargs)
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def build_payload(self, **kwargs) -> dict[str, Any]:
        """Build the complete API payload including output schema."""
        payload: dict[str, Any] = {
            "messages": self.build_messages(**kwargs),
        }
        if self.output_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": self.prompt_id,
                    "schema": self.output_schema,
                },
            }
        return payload

    def __repr__(self) -> str:
        return (
            f"<PromptTemplate {self.prompt_id} v{self.version} [{self.model_profile}]>"
        )


# ── Markdown loader ────────────────────────────────────────────────────────

_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)


def _load_prompt_from_md(path: Path) -> PromptTemplate:
    """Parse a .md prompt file and return a PromptTemplate."""
    content = path.read_text(encoding="utf-8")

    # ── Extract YAML frontmatter (between --- delimiters) ──────────────
    metadata = _parse_yaml_frontmatter(content)

    # ── Strip frontmatter block before parsing sections ─────────────────
    body = _YAML_FRONTMATTER_RE.sub("", content, count=1).strip()

    # ── Split into sections ───────────────────────────────────────────
    sections: dict[str, str] = {}
    splits = list(_SECTION_RE.finditer(body))
    for i, m in enumerate(splits):
        section_name = m.group(1).strip().lower().replace(" ", "_")
        start = m.end()
        end = splits[i + 1].start() if i + 1 < len(splits) else len(body)
        sections[section_name] = body[start:end].strip()

    # ── Extract JSON schema from the "output_schema" section ──────────
    output_schema: dict[str, Any] | None = None
    schema_section = sections.get("output_schema") or sections.get("output schema")
    if schema_section:
        json_match = _JSON_BLOCK_RE.search(schema_section)
        if json_match:
            try:
                output_schema = json.loads(json_match.group(1))
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON schema in %s: %s", path.name, e)

    # ── Build template ────────────────────────────────────────────────
    return PromptTemplate(
        prompt_id=metadata.get("prompt_id", path.stem),
        version=metadata.get("version", "0.0.0"),
        model_profile=metadata.get("model_profile", "pro"),
        description=metadata.get("description", ""),
        system_template=sections.get("system", ""),
        user_template=sections.get("user", ""),
        output_schema=output_schema,
        source_path=str(path),
    )


# ── Load all prompts at import time ────────────────────────────────────────


def _discover_prompts() -> dict[str, PromptTemplate]:
    registry: dict[str, PromptTemplate] = {}
    for md_file in PROMPTS_DIR.rglob("*.md"):
        if md_file.name == "README.md":
            continue
        if "zlegacy" in md_file.parts:
            continue
        try:
            template = _load_prompt_from_md(md_file)
            registry[template.prompt_id] = template
        except Exception as e:
            logger.warning("Failed to load prompt %s: %s", md_file, e)
    return registry


PROMPT_REGISTRY: dict[str, PromptTemplate] = _discover_prompts()


def get_prompt(prompt_id: str) -> PromptTemplate:
    """Get a prompt template by ID. Raises KeyError if not found."""
    if prompt_id not in PROMPT_REGISTRY:
        available = ", ".join(sorted(PROMPT_REGISTRY.keys()))
        raise KeyError(f"Unknown prompt_id: '{prompt_id}'. Available: {available}")
    return PROMPT_REGISTRY[prompt_id]
