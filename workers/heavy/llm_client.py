"""
Cliente LLM síncrono para workers Celery. Usa Together.ai como proveedor.

Plan §2.1: Patrón Factory. Plan §2.8: Prompt Engineering Skill.

Soporta dos formatos de prompt:
  1. YAML (.md):  ---\nkey: value\n---\n## System\n...\n## Output Schema\n```json...```
  2. Legacy (.txt): -- agent: a1\n[ROL]...\n---\nSCHEMA\n{{...}}

El parser detecta el formato automáticamente.
Las variables {nombre} se reemplazan con Python .format().
El schema se extrae del bloque Output Schema (md) o SCHEMA (txt).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

ModelTier = Literal["PRO", "FLASH"]

# ── Model configuration — SINGLE SOURCE: environment variables ──

_MODEL_FLASH = os.getenv("MODEL_FLASH", "google/gemma-4-31B-it")
_MODEL_PRO = os.getenv("MODEL_PRO", "deepseek-ai/DeepSeek-V4")

_TIER_MODELS: dict[ModelTier, str] = {
    "FLASH": _MODEL_FLASH,
    "PRO": _MODEL_PRO,
}

_TIER_MAX_TOKENS: dict[ModelTier, int] = {
    "FLASH": int(os.getenv("MODEL_FLASH_MAX_TOKENS", "4096")),
    "PRO": int(os.getenv("MODEL_PRO_MAX_TOKENS", "8192")),
}

_TIER_TEMPERATURE: dict[ModelTier, float] = {
    "FLASH": float(os.getenv("MODEL_FLASH_TEMPERATURE", "0.1")),
    "PRO": float(os.getenv("MODEL_PRO_TEMPERATURE", "0.3")),
}

PROMPTS_DIR = os.getenv("PROMPTS_DIR", "/app/prompts")


# ═══════════════════════════════════════════════════════════════════════
# Parseo unificado de prompts (.md YAML + .txt legacy)
# ═══════════════════════════════════════════════════════════════════════


def _parse_prompt_file(raw: str) -> dict[str, Any]:
    """Detecta formato y despacha al parser adecuado."""
    stripped = raw.strip()
    if stripped.startswith("---"):
        return _parse_yaml_format(stripped)
    return _parse_legacy_format(stripped)


# ── YAML simple (sin dependencia PyYAML) ──────────────────────────


def _parse_simple_yaml(yaml_str: str) -> dict[str, Any]:
    """Keys simples, valores string/quoted, multi-línea indentada."""
    result: dict[str, Any] = {}
    current_key: str | None = None
    current_value: list[str] = []

    for raw_line in yaml_str.split("\n"):
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            if current_key and current_value:
                result[current_key] = "\n".join(current_value).strip()
                current_key = None
                current_value = []
            continue

        if line.startswith(" ") or line.startswith("\t"):
            if current_key:
                current_value.append(line.strip())
            continue

        if ":" in line:
            if current_key and current_value:
                result[current_key] = "\n".join(current_value).strip()
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            elif val.startswith("'") and val.endswith("'"):
                val = val[1:-1]
            current_key = key
            current_value = [val] if val else []

    if current_key and current_value:
        result[current_key] = "\n".join(current_value).strip()
    return result


def _extract_json_block(section_text: str) -> dict | None:
    """Extrae JSON de ```json ... ``` o ``` ... ```."""
    match = re.search(r"```(?:json)?\s*\n(.*?)\n```", section_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON block in Output Schema")
    return None


def _parse_markdown_sections(body: str) -> dict[str, str]:
    """Divide cuerpo Markdown en secciones ## Heading."""
    sections: dict[str, str] = {}
    current_heading: str | None = None
    current_lines: list[str] = []

    for line in body.split("\n"):
        if line.startswith("## "):
            if current_heading:
                sections[current_heading] = "\n".join(current_lines).strip()
            current_heading = line[3:].strip()
            current_lines = []
        elif current_heading:
            current_lines.append(line)

    if current_heading:
        sections[current_heading] = "\n".join(current_lines).strip()
    return sections


def _parse_yaml_format(raw: str) -> dict[str, Any]:
    """Formato .md: YAML frontmatter + ## System / ## User / ## Output Schema."""
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Formato YAML: falta cierre de frontmatter (---)")

    frontmatter_str = parts[1].strip()
    body = parts[2].strip()

    metadata = _parse_simple_yaml(frontmatter_str)

    notes: list[str] = []
    raw_notes = metadata.get("notes", "")
    if isinstance(raw_notes, str) and raw_notes:
        notes = [n.strip() for n in raw_notes.split("\n") if n.strip()]
    elif isinstance(raw_notes, list):
        notes = raw_notes

    sections = _parse_markdown_sections(body)

    prompt_parts = []
    if sections.get("System"):
        prompt_parts.append(sections["System"])
    if sections.get("User"):
        prompt_parts.append(sections["User"])
    prompt = "\n\n".join(prompt_parts).strip()

    schema = None
    schema_section = sections.get("Output Schema", "")
    if schema_section:
        schema = _extract_json_block(schema_section)

    return {"metadata": metadata, "notes": notes, "prompt": prompt, "schema": schema}


def _parse_legacy_format(raw: str) -> dict[str, Any]:
    """Formato .txt: -- metadata + [ROL]...[TAREA]... + --- SCHEMA {{...}}."""
    lines = raw.split("\n")
    metadata: dict[str, str] = {}
    notes: list[str] = []
    prompt_lines: list[str] = []
    schema_lines: list[str] = []
    in_schema = False

    for line in lines:
        stripped = line.strip()
        if in_schema:
            schema_lines.append(line)
        elif stripped.startswith("-- agent:"):
            metadata["agent"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("-- tier:"):
            metadata["tier"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("-- description:"):
            metadata["description"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("-- notes:"):
            notes.append(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("-- constraints:"):
            metadata["constraints"] = stripped.split(":", 1)[1].strip()
        elif stripped == "---":
            in_schema = True
        elif stripped.startswith("--"):
            continue
        elif not in_schema:
            prompt_lines.append(line)

    schema: dict | None = None
    schema_text = "\n".join(schema_lines).strip()
    if schema_text and schema_text.upper().startswith("SCHEMA"):
        schema_text = schema_text[len("SCHEMA") :].strip()
        schema_text = schema_text.replace("{{", "{").replace("}}", "}")
        try:
            schema = json.loads(schema_text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse SCHEMA block in legacy prompt")

    prompt = "\n".join(prompt_lines).strip()
    return {"metadata": metadata, "notes": notes, "prompt": prompt, "schema": schema}


# ═══════════════════════════════════════════════════════════════════════
# Carga de archivos
# ═══════════════════════════════════════════════════════════════════════


def _load_agent_prompt(agent_id: str, tier: ModelTier) -> dict[str, Any]:
    """Busca el prompt en deepseek_pro/ o deepseek_flash/. Prueba .md y .txt."""
    tier_dir = {
        "PRO": "deepseek_pro",
        "FLASH": "deepseek_flash",
    }
    agent_files = {
        "fa_population_context": "a1_population_context",
        "fa_process_identifier": "a2_process_identifier",
        "fa_sense_maker": "a3_sense_maker",
        "b1": "b1_sampling_distiller",
        "fb_indicators_extractor": "b2a_extract_indicators",
        "fb_code_generator": "b2b_generate_codes",
        "fb_hypothesis_generator": "b3_hypothesis_generator",
        "graph_entity_extractor": "entity_extraction",
    }
    base_name = agent_files.get(agent_id, agent_id)
    extensions = [".md", ".txt"]

    for ext in extensions:
        filename = base_name + ext
        # Primero en raíz, luego en subdirectorio de tier
        for candidate_dir in ("", tier_dir[tier]):
            dir_path = (
                Path(PROMPTS_DIR) / candidate_dir
                if candidate_dir
                else Path(PROMPTS_DIR)
            )
            filepath = dir_path / filename
            if filepath.exists():
                raw = filepath.read_text(encoding="utf-8")
                return _parse_prompt_file(raw)

    raise FileNotFoundError(
        f"Prompt no encontrado para {agent_id} (tier={tier}): "
        f"buscado como {base_name}.md y {base_name}.txt"
    )


# ═══════════════════════════════════════════════════════════════════════
# Mock responses
# ═══════════════════════════════════════════════════════════════════════

MOCK_RESPONSES: dict[str, dict] = {
    "fa_population_context": {
        "surprising_details": "[MOCK] Tensión autonomía-dependencia.",
        "language_patterns": "[MOCK] Metáforas espaciales.",
        "data_production_context": "[MOCK] Entrevistas en zonas de espera.",
    },
    "fa_process_identifier": {
        "process_description": "[MOCK] Negociando permanencia.",
        "data_classification": "baseline",
    },
    "fa_sense_maker": {
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
    "fb_indicators_extractor": {
        "indicators": [
            {
                "segment_index": 0,
                "key_phrases": ["cambio de zona"],
                "suggested_pattern": "Evita zonas sin pedidos",
            },
            {
                "segment_index": 1,
                "key_phrases": ["acepto las que valen"],
                "suggested_pattern": "Rechazo selectivo por rentabilidad",
            },
        ]
    },
    "fb_code_generator": {
        "codes": [
            {
                "code_name": "Evadiendo control algorítmico",
                "definition": "Patrón de comportamiento donde...",
                "indicators": ["cambio de zona"],
                "variations": "Varía según hora del día",
                "relationship_to_existing": "Nuevo.",
            }
        ]
    },
    "fb_hypothesis_generator": {
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
    "fb_incident_comparator": {
        "comparisons": [
            {
                "incident_a_id": "00000000-0000-0000-0000-000000000001",
                "incident_b_id": "00000000-0000-0000-0000-000000000002",
                "are_interchangeable": True,
                "rationale": "[MOCK]",
                "similarity_score": 0.85,
            }
        ],
        "groups": [
            {
                "incident_ids": [
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000002",
                ],
                "common_pattern": "[MOCK]",
            }
        ],
        "ungrouped": [],
    },
    "fb_pattern_labeler": {
        "proposed_labels": [
            {
                "group_index": 0,
                "label": "Negociando limites",
                "definition": "[MOCK]",
                "properties": [],
                "supporting_incidents": ["00000000-0000-0000-0000-000000000001"],
                "relationship_to_existing": "Nuevo",
            }
        ],
        "anomalies": [],
    },
    "fb_label_critic": {"all_valid": True, "issues": []},
}


# ═══════════════════════════════════════════════════════════════════════
# LLMClient
# ═══════════════════════════════════════════════════════════════════════


class LLMClient:
    """Cliente síncrono para llamadas LLM desde workers Celery.

    Carga prompts desde archivos .md (YAML) o .txt (legacy) en /app/prompts/.
    Soporta ambos formatos automáticamente.
    """

    # ── Translation Pattern (T1): idioma global para outputs ──
    _user_language: str = "es"  # default Spanish

    @classmethod
    def set_user_language(cls, lang: str) -> None:
        """Configura el idioma de output para todas las llamadas subsecuentes."""
        if lang in ("es", "en", "de", "pt"):
            cls._user_language = lang

    def __init__(self, api_key: str | None = None):
        from config import TOGETHER_API_KEY as _cfg_key

        raw_key = (api_key or _cfg_key).strip()
        self.is_mock = not raw_key or raw_key.startswith("${") or raw_key == "changeme"

        if self.is_mock:
            logger.warning("TOGETHER_API_KEY no configurada. Usando modo MOCK.")
        else:
            try:
                from together import Together

                self.client = Together(
                    api_key=raw_key,
                    timeout=600,  # 10 minutos para textos largos
                )
                logger.info("LLMClient: Together.ai inicializado (timeout=180s)")
            except Exception as e:
                logger.warning("Together.ai init failed: %s. MOCK mode.", e)
                self.is_mock = True

    def run_agent(
        self,
        agent_id: str,
        variables: dict[str, str],
        max_tokens: int | None = None,
        temperature: float | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        """Carga prompt, reemplaza variables, inyecta schema i18n, llama al LLM.

        Args:
            language: 'en','es','de','pt'. Default: class-level _user_language.
        """
        lang = language or self._user_language
        LANG_NAMES = {
            "en": "English",
            "es": "español",
            "de": "Deutsch",
            "pt": "português",
        }
        variables["language_code"] = lang
        variables["language_name"] = LANG_NAMES.get(lang, "English")
        if self.is_mock:
            return dict(
                MOCK_RESPONSES.get(agent_id, {"mock_note": f"No mock for {agent_id}"})
            )

        for tier in ("PRO", "FLASH"):
            try:
                parsed = _load_agent_prompt(agent_id, tier)
                break
            except FileNotFoundError:
                continue
        else:
            return {"error": f"Prompt no encontrado para {agent_id}"}

        declared_tier = parsed["metadata"].get("tier", "PRO")
        model_tier: ModelTier = (
            declared_tier if declared_tier in ("PRO", "FLASH") else "PRO"
        )

        defaults = None
        if max_tokens is None:
            max_tokens = _TIER_MAX_TOKENS[model_tier]
        if temperature is None:
            temperature = _TIER_TEMPERATURE[model_tier]

        logger.info(
            "Agent %s → tier=%s tokens=%d temp=%.2f",
            agent_id,
            model_tier,
            max_tokens,
            temperature,
        )

        prompt_template = parsed["prompt"]
        try:
            system_prompt = prompt_template.format(**variables)
        except KeyError as e:
            logger.error("Missing variable %s for %s", e, agent_id)
            system_prompt = prompt_template
            for k, v in variables.items():
                system_prompt = system_prompt.replace("{" + k + "}", str(v))

        schema = parsed["schema"]
        # Fase 2: override with i18n schema from agents/{id}/schema.{lang}.json
        try:
            import os as _os

            agents_schema = _os.path.join(
                _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                "backend",
                "app",
                "prompts",
                "agents",
                agent_id,
                f"schema.{lang}.json",
            )
            if _os.path.exists(agents_schema):
                with open(agents_schema, "r") as f:
                    schema = json.load(f)
                logger.debug("Agent %s: loaded i18n schema %s", agent_id, agents_schema)
        except Exception:
            pass  # fallback to inline schema
        model = _TIER_MODELS[model_tier]
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
        retry: bool = True,
    ) -> dict[str, Any]:
        """Llama a Together.ai con response_format json_object. Retry 1 vez."""
        if schema:
            system_prompt += (
                "\n\n[OUTPUT FORMAT — responde EXCLUSIVAMENTE en JSON]\n"
                + json.dumps(schema, indent=2)
            )

        user_prompt = (
            "[TAREA]\nResponde según el formato y razonamiento indicados arriba.\n"
            f"Output language: {self._user_language}. "
            "All natural language values (names, definitions, descriptions, jots, rationale) "
            f"must be in {self._user_language}. "
            "Source quotes stay in original language. System codes (SAT, MOD, FORCED) are language-neutral."
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
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
                temperature=temperature,
            )
            message = response.choices[0].message
            content = message.content or ""
            reasoning = getattr(message, "reasoning_content", None)
            content = content.strip()
            # Strip markdown code fences if present
            if content.startswith("```"):
                lines = content.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines)
            result = json.loads(content)
            if reasoning:
                result["_reasoning_content"] = reasoning
            return result

        except json.JSONDecodeError as e:
            if retry:
                logger.warning(
                    "JSON parse failed for %s: %s. Retrying with error hint.",
                    tier,
                    str(e)[:100],
                )
                hint = (
                    f"\n\n[ERROR EN RESPUESTA ANTERIOR]\n"
                    f"Tu respuesta no era JSON válido: {str(e)[:200]}\n"
                    f"Corrige y responde SOLO el JSON."
                )
                return self._call_llm(
                    tier,
                    model,
                    system_prompt + hint,
                    schema,
                    max_tokens + 512,
                    temperature,
                    retry=False,
                )
            logger.warning("JSON parse failed after retry. Mock fallback.")
            return dict(MOCK_RESPONSES.get(tier, {"error": "JSON parse failed"}))

        except Exception as e:
            logger.error("LLM call failed: %s. Mock fallback.", e)
            return dict(MOCK_RESPONSES.get(tier, {"error": str(e)}))
