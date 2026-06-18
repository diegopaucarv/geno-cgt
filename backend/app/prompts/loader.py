"""
Cargador de prompts desde la estructura agents/{agent_id}/.

Estructura:
    prompts/
    └── agents/
        └── {agent_id}/
            ├── prompt.md       ← YAML frontmatter + ## System / ## User
            └── schema.en.json  ← JSON Schema para structured output

Uso:
    loader = PromptLoader("/app/prompts")
    system, schema = loader.load("a1", "POWERFUL")
    # system = plantilla con {variables} sin reemplazar
    # schema = dict JSON Schema para structured output
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

TierName = Literal["POWERFUL", "BALANCED", "FAST"]


class PromptLoader:
    """Carga prompts desde agents/{agent_id}/ y los combina con JSON schemas."""

    def __init__(self, prompts_dir: str | None = None):
        self.base = Path(prompts_dir or os.path.join(os.path.dirname(__file__)))
        self._cache: dict[tuple[str, str], str] = {}

        # Import schemas (lazy) — used as fallback if no schema file
        from app.prompts.schemas import AGENT_SCHEMAS

        self._schemas = AGENT_SCHEMAS

    def load(self, agent_id: str, tier: TierName) -> tuple[str, dict | None]:
        """
        Carga el prompt para un agente.

        Returns:
            (system_prompt_template, json_schema_or_none)

        El system_prompt_template contiene {variables} que deben ser
        reemplazadas con .format() antes de enviar al LLM.
        """
        prompt_path = self.base / "agents" / agent_id / "prompt.md"

        cache_key = (agent_id, tier)
        if cache_key not in self._cache:
            if not prompt_path.exists():
                raise FileNotFoundError(f"Prompt no encontrado: {prompt_path}")
            self._cache[cache_key] = prompt_path.read_text(encoding="utf-8")

        template = self._cache[cache_key]

        # Load schema from schema.en.json if available; fall back to AGENT_SCHEMAS
        schema = None
        schema_path = self.base / "agents" / agent_id / "schema.en.json"
        if schema_path.exists():
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if schema is None:
            schema = self._schemas.get(agent_id)

        return template, schema

    def format(
        self, agent_id: str, tier: TierName, **variables
    ) -> tuple[str, dict | None]:
        """
        Carga y reemplaza variables en el prompt.

        Ejemplo:
            loader.format("a1", "POWERFUL",
                          population_assumption="...",
                          existing_context="...",
                          segments="...")
        """
        template, schema = self.load(agent_id, tier)
        try:
            filled = template.format(**variables)
        except KeyError as e:
            missing = e.args[0]
            raise KeyError(
                f"Variable '{missing}' requerida por {agent_id}/{tier} "
                f"pero no proporcionada. Variables disponibles: {list(variables.keys())}"
            ) from e

        return filled, schema
