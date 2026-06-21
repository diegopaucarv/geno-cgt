"""
Cliente LLM síncrono para workers Celery. Usa Together.ai como proveedor.

Plan §2.1: Patrón Factory. Plan §2.8: Prompt Engineering Skill.

Soporta el formato de prompt:
  YAML (.md):  ---\nkey: value\n---\n## System\n...\n## Output Schema\n```json...```

Las variables {nombre} se reemplazan con Python .format().
El schema se extrae del bloque Output Schema (md) o del archivo schema.en.json.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.core.runtime_config import get_config_value

logger = logging.getLogger(__name__)

ModelTier = Literal["PRO", "FLASH"]

# ═══════════════════════════════════════════════════════════════════════
# ChainOrchestrator v3 — Dataclasses y fallback para _self_evaluation
# ═══════════════════════════════════════════════════════════════════════

DEFAULT_SELF_EVAL: dict[str, Any] = {
    "needs_retry": False,
    "retry_reason": None,
    "suggested_action": "proceed",
}


@dataclass
class SelfEval:
    """Parsed _self_evaluation from agent output."""

    needs_retry: bool
    retry_reason: str | None
    suggested_action: str  # "proceed" | "retry" | "escalate_to_hitl" | "skip" | "abort"


@dataclass
class AgentOutput:
    """Resultado estructurado de una ejecucion de agente.

    Compatible con ChainOrchestrator v3.
    Supports dict-like access for backward compatibility (response["key"] -> response.data["key"]).
    """

    success: bool
    data: dict  # The parsed JSON output
    tokens_used: int  # Total tokens for this call
    conversation: list[dict]  # Full conversation messages
    self_eval: SelfEval | None = None  # Parsed _self_evaluation from data
    error: str | None = None
    iterations: int = 0

    def __getitem__(self, key: str) -> Any:
        """Backward-compatible dict access: output['codes'] -> output.data['codes']."""
        # Special keys exposed at AgentOutput level
        if key == "error" and self.error:
            return self.error
        if key == "mock_note":
            if isinstance(self.data, dict) and "mock_note" in self.data:
                return self.data["mock_note"]
            return None
        if isinstance(self.data, dict):
            return self.data[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        """Backward-compatible .get(): output.get('codes', []) -> output.data.get('codes', [])."""
        # Special keys exposed at AgentOutput level
        if key == "error":
            return self.error or default
        if key == "mock_note":
            if isinstance(self.data, dict) and "mock_note" in self.data:
                return self.data["mock_note"]
            return default
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default

    def get(self, key: str, default: Any = None) -> Any:
        """Backward-compatible .get(): output.get('codes', []) -> output.data.get('codes', [])."""
        if isinstance(self.data, dict):
            return self.data.get(key, default)
        return default

    def __contains__(self, key: str) -> bool:
        """Backward-compatible 'in' operator."""
        if isinstance(self.data, dict):
            return key in self.data
        return False

    def keys(self):
        """Backward-compatible .keys()."""
        if isinstance(self.data, dict):
            return self.data.keys()
        return {}.keys()

    def items(self):
        """Backward-compatible .items()."""
        if isinstance(self.data, dict):
            return self.data.items()
        return {}.items()

    def values(self):
        """Backward-compatible .values()."""
        if isinstance(self.data, dict):
            return self.data.values()
        return {}.values()

    def __len__(self) -> int:
        if isinstance(self.data, dict):
            return len(self.data)
        return 0


# ── Model configuration — SINGLE SOURCE: runtime_config + env vars ──

_MODEL_FLASH = get_config_value(
    "MODEL_FLASH", default="nvidia/nemotron-3-ultra-550b-a55b"
)
_MODEL_PRO = get_config_value("MODEL_PRO", default="deepseek-ai/DeepSeek-V4-Pro")

_TIER_MODELS: dict[ModelTier, str] = {
    "FLASH": _MODEL_FLASH,
    "PRO": _MODEL_PRO,
}

_TIER_MAX_TOKENS: dict[ModelTier, int] = {
    "FLASH": int(get_config_value("MODEL_FLASH_MAX_TOKENS", default="4096")),
    "PRO": int(get_config_value("MODEL_PRO_MAX_TOKENS", default="8192")),
}

_TIER_TEMPERATURE: dict[ModelTier, float] = {
    "FLASH": float(get_config_value("MODEL_FLASH_TEMPERATURE", default="0.1")),
    "PRO": float(get_config_value("MODEL_PRO_TEMPERATURE", default="0.3")),
}

PROMPTS_DIR = os.getenv("PROMPTS_DIR", "/app/prompts")

# ── Coding style i18n tokens ─────────────────────────────────────
try:
    import sys as _csys

    _csys.path.insert(0, "/app/backend")
    _csys.path.insert(0, "/app/backend/app")
    from app.core.coding_styles import get_style_tokens as _get_style_tokens
except ImportError:
    _get_style_tokens = None


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
    if sections.get("Task"):
        prompt_parts.append(sections["Task"])
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
    """Load prompt from agents/{agent_id}/prompt.md and schema from schema.en.json."""
    agent_dir = Path(PROMPTS_DIR) / "agents" / agent_id
    prompt_path = agent_dir / "prompt.md"

    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt no encontrado para {agent_id}: {prompt_path}")

    raw = prompt_path.read_text(encoding="utf-8")
    result = _parse_prompt_file(raw)

    # Load schema from schema.en.json if available and not already in prompt
    if result.get("schema") is None:
        schema_path = agent_dir / "schema.en.json"
        if schema_path.exists():
            try:
                result["schema"] = json.loads(schema_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                logger.warning("Failed to load schema from %s", schema_path)

    return result


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
    "fb_label_critic": {
        "all_valid": True,
        "issues": [],
        "conceptually_fitted": False,
        "ready_for_selective": False,
    },
    "fa_document_pattern_extractor": {
        "patterns": [
            {
                "id": "p1",
                "label": "Negociando agencia creativa",
                "definition": "[MOCK] El participante negocia continuamente su libertad creativa frente a presiones externas.",
                "confidence": "MEDIUM",
            },
            {
                "id": "p2",
                "label": "Gestionando obsolescencia profesional",
                "definition": "[MOCK] Estrategias para mantenerse relevante ante cambios tecnológicos.",
                "confidence": "MEDIUM",
            },
        ],
        "incidents": [
            {
                "description": "[MOCK] [document] describes rejecting commercial projects that contradict personal style",
                "segment_refs": [1, 3],
                "patterns": ["p1"],
                "exact_quote": "No voy a hacer algo que no me representa solo porque pagan bien.",
            },
            {
                "description": "[MOCK] [document] spends evenings learning new design tools to stay competitive",
                "segment_refs": [5],
                "patterns": ["p2"],
            },
            {
                "description": "[MOCK] [document] mentions that younger colleagues get more opportunities",
                "segment_refs": [7],
                "patterns": ["p1", "p2"],
            },
        ],
        "document_signals": {
            "prime_mover": "Negociando identidad profesional en un mercado cambiante",
            "main_concern_signal": "El participante teme quedar obsoleto pero se niega a traicionar sus principios creativos",
            "surprising_detail": "A pesar de la presión económica, prioriza la autenticidad sobre la estabilidad",
            "confidence": "MEDIUM",
        },
    },
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

    def chat(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Simple chat interface for agents (orchestrator, plan_executor, react).

        Compatible with backend TogetherLLM.chat() interface.
        """
        if self.is_mock:
            return {
                "content": '{"next_step": "final_report"}',
                "reasoning_content": "",
                "usage": {"total_tokens": 0},
            }

        model = model or _MODEL_PRO
        system_msg = ""
        user_msg = ""
        for m in messages:
            if m.get("role") == "system":
                system_msg = m.get("content", "")
            elif m.get("role") == "user":
                user_msg = m.get("content", "")

        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            msg = response.choices[0].message
            return {
                "content": msg.content or "",
                "reasoning_content": getattr(msg, "reasoning_content", ""),
                "usage": {
                    "total_tokens": response.usage.total_tokens if response.usage else 0
                },
            }
        except Exception as e:
            logger.warning("LLMClient.chat failed: %s", e)
            return {
                "content": "",
                "reasoning_content": "",
                "usage": {"total_tokens": 0},
            }

    def run_agent(
        self,
        agent_id: str,
        variables: dict[str, str],
        max_tokens: int | None = None,
        temperature: float | None = None,
        language: str | None = None,
        history: list[dict] | None = None,
        override_user_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> AgentOutput:
        """Carga prompt, reemplaza variables, inyecta schema i18n, llama al LLM.

        Args:
            language: 'en','es','de','pt'. Default: class-level _user_language.
            history: Optional conversation history (list of {"role":..., "content":...})
                     inserted between system and user messages for conversational refinement.
            override_user_prompt: If provided, replaces the default generic user prompt.
            conversation_history: ChainOrchestrator v3 retry history.
                     When provided, injected as prior attempts before current user input.

        Returns:
            AgentOutput with parsed data, tokens, conversation, and _self_evaluation.
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
        # ── Inject coding style i18n tokens ──────────────────────
        if _get_style_tokens is not None:
            style_key = variables.get("coding_style_key", "gerundio")
            try:
                tokens = _get_style_tokens(style_key, lang)
                for k, v in tokens.items():
                    if k not in variables:  # don't override caller-provided values
                        variables[k] = v
            except Exception:
                pass  # graceful fallback — tokens simply won't be injected
        if self.is_mock:
            mock_data = MOCK_RESPONSES.get(
                agent_id, {"mock_note": f"No mock for {agent_id}"}
            )
            return AgentOutput(
                success=True,
                data=mock_data,
                tokens_used=0,
                conversation=[],
                self_eval=SelfEval(
                    needs_retry=False,
                    retry_reason=None,
                    suggested_action="proceed",
                ),
                iterations=1,
            )

        for tier in ("PRO", "FLASH"):
            try:
                parsed = _load_agent_prompt(agent_id, tier)
                break
            except FileNotFoundError:
                continue
        else:
            return AgentOutput(
                success=False,
                data={},
                tokens_used=0,
                conversation=[],
                error=f"Prompt no encontrado para {agent_id}",
            )

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
        # ── Inject coding style tokens into schema descriptions ──
        if _get_style_tokens is not None:
            try:
                style_key = variables.get("coding_style_key", "gerundio")
                tokens = _get_style_tokens(style_key, lang)
                schema_str = json.dumps(schema, ensure_ascii=False)
                for k, v in tokens.items():
                    schema_str = schema_str.replace("{" + k + "}", v)
                schema = json.loads(schema_str)
            except Exception:
                pass  # graceful fallback
        model = _TIER_MODELS[model_tier]

        # ── Log populated prompt before sending to LLM ───────────────
        try:
            from prompt_logger import log_prompt_call

            project_id = variables.get("project_id", "") or variables.get(
                "proyecto_id", ""
            )
            if project_id:
                log_prompt_call(agent_id, project_id, system_prompt, schema)
        except Exception:
            pass

        result, conversation = self._call_llm(
            model_tier,
            model,
            system_prompt,
            schema,
            max_tokens,
            temperature,
            history=history,
            override_user_prompt=override_user_prompt,
            conversation_history=conversation_history,
        )

        # ── Log LLM response after receiving it ──────────────────────
        try:
            from prompt_logger import log_prompt_response

            project_id = variables.get("project_id", "") or variables.get(
                "proyecto_id", ""
            )
            if project_id:
                tokens = result.get("usage", {}).get("total_tokens", 0)
                log_prompt_response(agent_id, project_id, result, tokens)
        except Exception:
            pass

        # ── Build AgentOutput with _self_evaluation parsing ────────────
        tokens_used = result.get("usage", {}).get("total_tokens", 0) if isinstance(result, dict) else 0
        error = result.get("error") if isinstance(result, dict) else None

        # Parse _self_evaluation from agent output
        self_eval = None
        if isinstance(result, dict) and "_self_evaluation" in result:
            raw_eval = result["_self_evaluation"]
            if isinstance(raw_eval, dict):
                try:
                    self_eval = SelfEval(
                        needs_retry=bool(raw_eval.get("needs_retry", False)),
                        retry_reason=raw_eval.get("retry_reason"),
                        suggested_action=raw_eval.get("suggested_action", "proceed"),
                    )
                except Exception:
                    logger.warning(
                        "Agent %s: failed to parse _self_evaluation, using default",
                        agent_id,
                    )
                    self_eval = SelfEval(
                        needs_retry=False,
                        retry_reason=None,
                        suggested_action="proceed",
                    )
        elif isinstance(result, dict) and "_self_evaluation" not in result:
            # Agent doesn't have _self_evaluation — use fallback
            logger.info(
                "Agent %s: no _self_evaluation in output, using DEFAULT_SELF_EVAL",
                agent_id,
            )
            self_eval = SelfEval(**DEFAULT_SELF_EVAL)

        return AgentOutput(
            success=error is None,
            data=result if isinstance(result, dict) else {},
            tokens_used=tokens_used,
            conversation=conversation,
            self_eval=self_eval,
            error=error,
            iterations=1,
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
        history: list[dict] | None = None,
        override_user_prompt: str | None = None,
        conversation_history: list[dict] | None = None,
    ) -> tuple[dict[str, Any], list[dict]]:
        """Llama a Together.ai con response_format json_object.

        Returns:
            (parsed_result, conversation_messages)

        Retry strategy:
        - 429 (rate limit): exponential backoff 2s, 4s, 8s, 16s, max 4 retries
        - 5xx (server error): 1 retry after 2s
        - JSON parse error: 1 retry with error hint
        """
        import time as _time

        if schema:
            system_prompt += (
                "\n\n[OUTPUT FORMAT — responde EXCLUSIVAMENTE en JSON]\n"
                + json.dumps(schema, indent=2)
            )

        user_prompt = override_user_prompt or (
            "[TAREA]\nResponde según el formato y razonamiento indicados arriba.\n"
            f"Output language: {self._user_language}. "
            "All natural language values (names, definitions, descriptions, jots, rationale) "
            f"must be in {self._user_language}. "
            "Source quotes stay in original language. System codes (SAT, MOD, FORCED) are language-neutral."
        )

        logger.info(
            "LLM: tier=%s model=%s prompt_chars=%d", tier, model, len(system_prompt)
        )

        last_error = None
        rate_limit_retries = 0
        max_rate_limit_retries = 4

        while True:
            try:
                messages = [
                    {"role": "system", "content": system_prompt},
                ]
                if conversation_history:
                    messages.extend(conversation_history)
                if history:
                    messages.extend(history)
                messages.append({"role": "user", "content": user_prompt})

                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
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
                # Build full conversation for caller
                full_conversation = list(messages)
                full_conversation.append({
                    "role": "assistant",
                    "content": content,
                })
                if reasoning:
                    full_conversation[-1]["reasoning_content"] = reasoning
                return result, full_conversation

            except json.JSONDecodeError as e:
                last_error = e
                if retry:
                    logger.warning(
                        "JSON parse failed for %s: %s. Retrying with error hint.",
                        model,
                        e,
                    )
                    retry = False
                    system_prompt += (
                        "\n\n[ERROR — Your previous response was not valid JSON. "
                        "You MUST output ONLY valid JSON. No markdown, no preambles.]"
                    )
                    continue
                break

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                # Rate limit (429) — exponential backoff
                if (
                    "429" in error_str
                    or "throttl" in error_str
                    or "rate limit" in error_str
                ):
                    if rate_limit_retries < max_rate_limit_retries:
                        wait = 2 ** (rate_limit_retries + 1)  # 2, 4, 8, 16 seconds
                        rate_limit_retries += 1
                        logger.warning(
                            "Rate limited (429). Backing off %ds (attempt %d/%d)...",
                            wait,
                            rate_limit_retries,
                            max_rate_limit_retries,
                        )
                        _time.sleep(wait)
                        continue
                    else:
                        logger.error(
                            "Rate limit retries exhausted after %d attempts.",
                            max_rate_limit_retries,
                        )
                        break

                # Server error (5xx) — 1 retry
                if "500" in error_str or "502" in error_str or "503" in error_str:
                    if retry:
                        logger.warning(
                            "Server error (%s). Retrying once after 2s...",
                            error_str[:80],
                        )
                        retry = False
                        _time.sleep(2)
                        continue
                    break

                # Network/timeout — 1 retry
                if "timeout" in error_str or "connection" in error_str:
                    if retry:
                        logger.warning(
                            "Network error: %s. Retrying once after 3s...",
                            error_str[:80],
                        )
                        retry = False
                        _time.sleep(3)
                        continue
                    break

                # Unknown error — don't retry
                logger.error("LLM call failed: %s", e)
                break

        # All retries exhausted
        return {
            "error": str(last_error),
            "mock_note": f"LLM failed after retries: {str(last_error)[:100]}",
        }, []


# ═══════════════════════════════════════════════════════════════════════
