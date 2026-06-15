"""
Cargador de prompts desde archivos .txt versionados.

Estructura:
    prompts/
    ├── deepseek_pro/        ← CoT, razonamiento paso a paso
    │   ├── a1_population_context.txt
    │   ├── a2_process_identifier.txt
    │   ├── a3_sense_maker.txt
    │   ├── b1_sampling_distiller.txt
    │   ├── b2_open_coder.txt
    │   └── b3_hypothesis_generator.txt
    ├── deepseek_flash/      ← Directo, instrucciones cortas
    │   └── (mismos archivos)
    └── schemas.py            ← JSON schemas para structured output

Uso:
    loader = PromptLoader("/app/prompts")
    system, schema = loader.load("a1", "POWERFUL")
    # system = plantilla con {variables} sin reemplazar
    # schema = dict JSON Schema para structured output
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

TierName = Literal["POWERFUL", "BALANCED", "FAST"]

# Mapeo tier → carpeta de prompts
TIER_DIR: dict[TierName, str] = {
    "POWERFUL": "deepseek_pro",
    "BALANCED": "deepseek_pro",  # Gemma usa mismo formato que Pro
    "FAST": "deepseek_flash",
}

# Mapeo agent_id → nombre de archivo
AGENT_FILES: dict[str, str] = {
    "a1": "a1_population_context.txt",
    "a2": "a2_process_identifier.txt",
    "a3": "a3_sense_maker.txt",
    "b1": "b1_sampling_distiller.txt",
    "b2": "b2_open_coder.txt",
    "b3": "b3_hypothesis_generator.txt",
}


class PromptLoader:
    """Carga prompts desde archivos y los combina con JSON schemas."""

    def __init__(self, prompts_dir: str | None = None):
        self.base = Path(prompts_dir or os.path.join(os.path.dirname(__file__)))
        self._cache: dict[tuple[str, str], str] = {}

        # Import schemas (lazy)
        from app.prompts.schemas import AGENT_SCHEMAS

        self._schemas = AGENT_SCHEMAS

    def load(self, agent_id: str, tier: TierName) -> tuple[str, dict | None]:
        """
        Carga el prompt para un agente y tier.

        Returns:
            (system_prompt_template, json_schema_or_none)

        El system_prompt_template contiene {variables} que deben ser
        reemplazadas con .format() antes de enviar al LLM.
        """
        tier_dir = TIER_DIR.get(tier, "deepseek_pro")
        filename = AGENT_FILES.get(agent_id)
        if not filename:
            raise ValueError(f"Agente desconocido: {agent_id}")

        filepath = self.base / tier_dir / filename

        cache_key = (agent_id, tier)
        if cache_key not in self._cache:
            if not filepath.exists():
                raise FileNotFoundError(f"Prompt no encontrado: {filepath}")
            self._cache[cache_key] = filepath.read_text(encoding="utf-8")

        template = self._cache[cache_key]
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
