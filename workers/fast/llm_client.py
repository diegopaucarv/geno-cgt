"""
Cliente LLM síncrono para workers Celery. Usa Together.ai como proveedor.

Plan §2.1: Patrón Factory. Plan §2.8: Prompt Engineering Skill.

Los prompts son archivos .txt autónomos con formato:
  -- agent: a1
  -- tier: PRO
  -- description: ...
  -- notes: ...

  [ROL]
  Eres un...

  ---
  SCHEMA
  {{...}}

La metadata (líneas --) guía al orquestador.
El bloque SCHEMA se extrae para structured output.
El prompt enviado al LLM solo contiene las secciones [ROL]...[RAZONAMIENTO].
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

ModelTier = Literal["FAST", "BALANCED", "POWERFUL"]

TIER_MODELS: dict[ModelTier, str] = {
    "FAST": "deepseek-ai/DeepSeek-V3",
    "BALANCED": "google/gemma-2-27b-it",
    "POWERFUL": "deepseek-ai/DeepSeek-R1",
}

PROMPTS_DIR = os.getenv("PROMPTS_DIR", "/app/prompts")


# ═══════════════════════════════════════════════════════════════════════
# Parseo de archivos .txt unificados
# ═══════════════════════════════════════════════════════════════════════


def _parse_prompt_file(raw: str) -> dict[str, Any]:
    """
    Extrae metadata, prompt y schema de un archivo .txt unificado.

    Estructura esperada:
        -- agent: a1
        -- tier: PRO
        -- description: ...
        -- notes: ...

        [ROL]
        Eres un...

        ---
        SCHEMA
        {{...}}
    """
    lines = raw.split("\n")
    metadata: dict[str, str] = {}
    notes: list[str] = []
    prompt_lines: list[str] = []
    schema_lines: list[str] = []
    in_schema = False

    for line in lines:
        if in_schema:
            schema_lines.append(line)
        elif line.strip().startswith("-- agent:"):
            metadata["agent"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("-- tier:"):
            metadata["tier"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("-- description:"):
            metadata["description"] = line.split(":", 1)[1].strip()
        elif line.strip().startswith("-- notes:"):
            notes.append(line.split(":", 1)[1].strip())
        elif line.strip() == "---":
            # Check if next non-empty line is SCHEMA
            in_schema = True
        elif line.strip().startswith("--"):
            continue  # otros metadatos
        elif not in_schema:
            prompt_lines.append(line)

    # Parsear schema JSON
    schema: dict | None = None
    schema_text = "\n".join(schema_lines).strip()
    if schema_text and schema_text.upper().startswith("SCHEMA"):
        schema_text = schema_text[len("SCHEMA") :].strip()
        # Des-escapar {{ }} → { }
        schema_text = schema_text.replace("{{", "{").replace("}}", "}")
        try:
            schema = json.loads(schema_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse SCHEMA block in prompt file")

    prompt = "\n".join(prompt_lines).strip()

    return {
        "metadata": metadata,
        "notes": notes,
        "prompt": prompt,
        "schema": schema,
    }


def _load_agent_prompt(agent_id: str, tier: ModelTier) -> dict[str, Any]:
    """Carga y parsea el archivo de prompt para un agente y tier."""
    tier_dir = {
        "POWERFUL": "deepseek_pro",
        "BALANCED": "deepseek_pro",
        "FAST": "deepseek_flash",
    }
    agent_files = {
        "a1": "a1_population_context.txt",
        "a2": "a2_process_identifier.txt",
        "a3": "a3_sense_maker.txt",
        "b1": "b1_sampling_distiller.txt",
        "b2a": "b2a_extract_indicators.txt",
        "b2b": "b2b_generate_codes.txt",
        "b3": "b3_hypothesis_generator.txt",
    }
    filename = agent_files.get(agent_id, f"{agent_id}.txt")

    # Primero buscar en la raíz de prompts/ (archivos sin subdirectorio de tier)
    filepath = Path(PROMPTS_DIR) / filename
    if not filepath.exists():
        # Fallback: buscar en subdirectorio de tier (deepseek_pro/ o deepseek_flash/)
        filepath = Path(PROMPTS_DIR) / tier_dir[tier] / filename

    if not filepath.exists():
        raise FileNotFoundError(f"Prompt no encontrado: {filepath}")

    raw = filepath.read_text(encoding="utf-8")
    return _parse_prompt_file(raw)


# ═══════════════════════════════════════════════════════════════════════
# Mock responses
# ═══════════════════════════════════════════════════════════════════════

MOCK_RESPONSES: dict[str, dict] = {
    "a1": {
        "surprising_details": "[MOCK] Tensión autonomía-dependencia.",
        "language_patterns": "[MOCK] Metáforas espaciales.",
        "data_production_context": "[MOCK] Entrevistas en zonas de espera.",
    },
    "a2": {"process_description": "[MOCK] Negociando permanencia.", "data_classification": "baseline"},
    "a3": {
        "sense_status": "no_change",
        "hypotheses": [
            {
                "text": "[MOCK] Micro-resistencia adaptativa.",
                "level": "emergent",
                "evidence": "Docs 1 y 3.",
            }
        ],
    },
    "b1": {
        "sampling_dimensions": [
            {
                "name": "Antigüedad",
                "description": "Novatos vs veteranos",
                "evidence_of_variation": "Doc1 (<3 meses) vs Doc2 (>1 año)",
                "contrast_criteria": "Buscar novatos sin experiencia",
                "extreme_criteria": "Veteranos >3 años",
                "consistent_criteria": "Perfiles 6-12 meses",
            }
        ]
    },
    "b2a": {
        "indicators": [
            {"segment_index": 0, "key_phrases": ["cambio de zona"], "suggested_pattern": "Evita zonas sin pedidos"},
            {"segment_index": 1, "key_phrases": ["acepto las que valen"], "suggested_pattern": "Rechazo selectivo por rentabilidad"}
        ]
    },
    "b2": {
        "codes": [
            {
                "code_name": "Evadiendo control algorítmico",
                "definition": "...",
                "indicators": ["cambio de zona"],
                "variations": "...",
                "relationship_to_existing": "Nuevo.",
            }
        ]
    },
    "b3": {
        "hypotheses": [
            {
                "text": "[MOCK] Experiencia → sofisticación de estrategias.",
                "level": "general",
                "evidence": "Doc1 y Doc2 muestran progresión.",
                "type": "relational",
                "related_codes": [],
            }
        ]
    },
}


# ═══════════════════════════════════════════════════════════════════════
# LLMClient
# ═══════════════════════════════════════════════════════════════════════


class LLMClient:
    """Cliente síncrono para llamadas LLM desde workers Celery.

    Carga prompts desde archivos .txt autónomos en /app/prompts/.
    Cada archivo contiene: metadata (--), prompt, y SCHEMA embebido.
    """

    def __init__(self, api_key: str | None = None):
        raw_key = (api_key or os.getenv("TOGETHER_API_KEY", "")).strip()
        self.is_mock = not raw_key or raw_key.startswith("${") or raw_key == "changeme"

        if self.is_mock:
            logger.warning("TOGETHER_API_KEY no configurada. Usando modo MOCK.")
        else:
            try:
                from together import Together

                self.client = Together(api_key=raw_key)
                logger.info("LLMClient: Together.ai inicializado")
            except Exception as e:
                logger.warning("Together.ai init failed: %s. MOCK mode.", e)
                self.is_mock = True

    # ── API de alto nivel ───────────────────────────────────────────

    def run_agent(
        self,
        agent_id: str,
        variables: dict[str, str],
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """
        Flujo completo:
        1. Carga el archivo .txt → extrae metadata, prompt template, schema
        2. Usa el tier declarado en el archivo (-- tier: PRO/FLASH)
        3. Reemplaza {variables} en el prompt
        4. Inyecta el SCHEMA como output format
        5. Llama al LLM (o devuelve mock)
        """
        if self.is_mock:
            return dict(
                MOCK_RESPONSES.get(agent_id, {"mock_note": f"No mock for {agent_id}"})
            )

        # 1. Primero intenta PRO, si no existe usa FLASH
        for tier in ("POWERFUL", "FAST"):
            try:
                parsed = _load_agent_prompt(agent_id, tier)  # type: ignore[arg-type]
                break
            except FileNotFoundError:
                continue
        else:
            return {"error": f"Prompt no encontrado para {agent_id}"}

        # 2. Usar el tier del archivo si está declarado, si no el que cargó
        declared_tier = parsed["metadata"].get("tier", "PRO")
        tier_map = {"PRO": "POWERFUL", "FLASH": "FAST"}
        model_tier: ModelTier = tier_map.get(declared_tier, "POWERFUL")  # type: ignore[assignment]

        logger.info("Agent %s → tier=%s (%s)", agent_id, declared_tier, model_tier)

        # 3. Reemplazar variables en el prompt
        prompt_template = parsed["prompt"]
        try:
            system_prompt = prompt_template.format(**variables)
        except KeyError as e:
            logger.error("Missing variable %s for %s", e, agent_id)
            system_prompt = prompt_template
            for k, v in variables.items():
                system_prompt = system_prompt.replace("{" + k + "}", str(v))

        # 4. Inyectar schema
        schema = parsed["schema"]

        # 5. Llamar al LLM
        model = TIER_MODELS[model_tier]
        return self._call_llm(
            model_tier, model, system_prompt, schema, max_tokens, temperature
        )

    def _call_llm(
        self,
        tier: ModelTier,
        model: str,
        system_prompt: str,
        schema: dict | None,
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        """Llama a Together.ai con schema inyectado como output format."""

        if schema:
            system_prompt += f"\n\n[OUTPUT FORMAT — responde EXCLUSIVAMENTE en JSON]\n{json.dumps(schema, indent=2)}"

        user_prompt = (
            "[TAREA]\nResponde según el formato y razonamiento indicados arriba."
        )

        logger.info(
            "LLM: tier=%s model=%s prompt_chars=%d", tier, model, len(system_prompt)
        )

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = response.choices[0].message.content or ""
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)
            return json.loads(content)
        except json.JSONDecodeError:
            logger.warning("JSON parse failed for %s. Mock fallback.", tier)
            return dict(MOCK_RESPONSES.get(tier, {"error": "JSON parse failed"}))
        except Exception as e:
            logger.error("LLM call failed: %s. Mock fallback.", e)
            return dict(MOCK_RESPONSES.get(tier, {"error": str(e)}))
