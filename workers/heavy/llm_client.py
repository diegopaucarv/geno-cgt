"""
Cliente LLM síncrono para workers Celery. Usa Together.ai como proveedor.

Plan §1.2: Modelos y niveles de enrutamiento.
Plan §2.1: Patrón Factory — este es el punto único de entrada a LLMs desde workers.

Modo mock: cuando TOGETHER_API_KEY no está configurada o es inválida,
devuelve respuestas placeholder realistas para testear el pipeline sin costo.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

logger = logging.getLogger(__name__)

ModelTier = Literal["FAST", "BALANCED", "POWERFUL"]

TIER_MODELS: dict[ModelTier, str] = {
    "FAST": "deepseek-ai/DeepSeek-V3",
    "BALANCED": "google/gemma-2-27b-it",
    "POWERFUL": "deepseek-ai/DeepSeek-R1",
}

# ── Respuestas mock por tipo de agente ──────────────────────────

MOCK_RESPONSES: dict[str, dict] = {
    "POPULATION_CONTEXT_BUILDER": {
        "surprising_details": (
            "[MOCK] Los participantes muestran una tensión constante entre "
            "autonomía percibida y dependencia estructural. Revelan estrategias "
            "de micro-resistencia que no habíamos anticipado: no evitan el sistema, "
            "lo redirigen. La creatividad adaptativa emerge como patrón transversal "
            "inesperado. Sin cambios respecto a la versión anterior en cuanto a "
            "la dimensión de producción de datos."
        ),
        "language_patterns": (
            "[MOCK] Predominan metáforas espaciales ('zona', 'lado', 'ruta', 'borde') "
            "y verbos de movimiento ('saltar', 'moverme', 'caer'). Usan 'dar la vuelta' "
            "como eufemismo sistemático — nunca dicen 'engañar' o 'mentir'. "
            "El lenguaje de agencia ('yo decido', 'yo elijo') contrasta con "
            "descripciones pasivas cuando hablan del algoritmo ('me tocó', 'me mandó')."
        ),
        "data_production_context": (
            "[MOCK] Entrevistas realizadas en zonas de espera (parques, estacionamientos). "
            "Varios participantes bajaron la voz al mencionar plataformas específicas. "
            "Uno pidió explícitamente que no se grabara cierta sección. "
            "Deseabilidad social visible en preguntas sobre ingresos — tienden a "
            "redondear hacia arriba. Fatiga hacia el final de entrevistas >45 min."
        ),
    },
    "PROCESS_IDENTIFIER_FIRST": {
        "process_description": (
            "[MOCK] Negociando permanencia en condiciones de incertidumbre: "
            "el entrevistado intenta continuamente maximizar la estabilidad de sus "
            "ingresos mientras minimiza el desgaste físico y emocional. Este proceso "
            "implica evaluar constantemente señales del entorno (densidad de repartidores, "
            "hora del día, tipo de pedido) y tomar decisiones rápidas sobre aceptar, "
            "rechazar o redirigir."
        ),
    },
    "PROCESS_IDENTIFIER_COMPARE": {
        "process_description": (
            "[MOCK] Balanceando visibilidad y control: a diferencia de otros "
            "entrevistados que priorizan el ingreso inmediato, este participante "
            "intenta mantener un perfil bajo ante la plataforma mientras maximiza "
            "su autonomía real. Su proceso central es gestionar la tensión entre "
            "'que el sistema me vea lo justo' y 'hacer lo que yo quiero'."
        ),
        "similarity_to_previous": (
            "[MOCK] Similar al entrevistado anterior en la evaluación constante "
            "de señales del entorno y en el uso de estrategias de micro-evasión. "
            "Ambos comparten la metáfora espacial y el lenguaje de agencia."
        ),
        "difference_from_previous": (
            "[MOCK] A diferencia del anterior, que prioriza maximizar ingresos, "
            "este participante prioriza mantener autonomía y control sobre su tiempo. "
            "No busca 'ganar más' sino 'que no me controlen'. Su relación con la "
            "plataforma es más adversarial que transaccional."
        ),
    },
    "SENSE_MAKER_FIRST": {
        "sense_status": "no_change",
        "hypotheses": [
            {
                "text": (
                    "La micro-resistencia a sistemas algorítmicos no es reactiva "
                    "sino adaptativa: los participantes desarrollan un repertorio de "
                    "estrategias que evoluciona con su experiencia en la plataforma."
                ),
                "level": "emergent",
                "evidence": "Entrevistados 1 y 3 muestran evolución de estrategias.",
            },
            {
                "text": (
                    "La visibilidad ante la plataforma opera como un continuo: "
                    "los participantes más experimentados aprenden a modular cuánto "
                    "'los ve' el sistema, mientras los novatos oscilan entre "
                    "hipervisibilidad e invisibilidad total."
                ),
                "level": "specific",
                "evidence": "Entrevistado 1 menciona 'cuando empecé aceptaba todo'.",
            },
        ],
    },
    "SENSE_MAKER_CONTINUE": {
        "sense_status": "modifies",
        "hypotheses": [
            {
                "text": (
                    "[ACTUALIZADA] La micro-resistencia no es solo adaptativa sino "
                    "también colectiva: los participantes comparten estrategias "
                    "informalmente, creando un conocimiento tácito grupal."
                ),
                "level": "emergent",
                "evidence": "Nuevo entrevistado menciona aprender de un colega.",
            },
        ],
    },
}


class LLMClient:
    """
    Cliente síncrono para llamadas LLM desde workers Celery.

    - TOGETHER_API_KEY válida → llama a Together.ai
    - Sin key, key vacía, o key inválida → modo mock con placeholders
    """

    def __init__(self, api_key: str | None = None):
        raw_key = (api_key or os.getenv("TOGETHER_API_KEY", "")).strip()
        # Considerar mock si: key vacía, key es whitespace, o es variable sin expandir
        self.is_mock = not raw_key or raw_key.startswith("${") or raw_key == "changeme"

        if self.is_mock:
            logger.warning(
                "TOGETHER_API_KEY no configurada o inválida. "
                "Usando modo MOCK con respuestas placeholder."
            )
        else:
            try:
                from together import Together

                self.client = Together(api_key=raw_key)
                logger.info("LLMClient: Together.ai inicializado")
            except Exception as e:
                logger.warning(
                    "No se pudo inicializar Together.ai: %s. Usando MOCK.", e
                )
                self.is_mock = True

    def invoke(
        self,
        tier: ModelTier,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.3,
    ) -> str:
        if self.is_mock:
            return self._mock_invoke(system_prompt, user_prompt)

        model = TIER_MODELS[tier]
        logger.info("LLM call: tier=%s model=%s", tier, model)
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
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.error("Together.ai call failed: %s. Falling back to MOCK.", e)
            self.is_mock = True
            return self._mock_invoke(system_prompt, user_prompt)

    def invoke_structured(
        self,
        tier: ModelTier,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if self.is_mock:
            return self._mock_structured(system_prompt, user_prompt)

        if output_schema:
            schema_str = json.dumps(output_schema, indent=2)
            system_prompt += (
                f"\n\n[OUTPUT FORMAT]\n"
                f"Responde EXCLUSIVAMENTE en JSON con esta estructura:\n"
                f"{schema_str}\n"
                f"No incluyas texto fuera del JSON. No uses markdown code blocks."
            )

        try:
            response_text = self.invoke(
                tier,
                system_prompt,
                user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            # Si invoke() cayó a mock, devolver la respuesta mock directamente
            if response_text.startswith("[MOCK]"):
                return self._mock_structured(system_prompt, user_prompt)

            response_text = response_text.strip()
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                response_text = "\n".join(lines)

            return json.loads(response_text)
        except json.JSONDecodeError:
            logger.warning("JSON parse failed, falling back to MOCK")
            return self._mock_structured(system_prompt, user_prompt)
        except Exception as e:
            logger.error("invoke_structured failed: %s. Falling back to MOCK.", e)
            return self._mock_structured(system_prompt, user_prompt)

    # ── Mock responses ────────────────────────────────────────────

    def _mock_invoke(self, system_prompt: str, user_prompt: str) -> str:
        logger.info(
            "MOCK LLM: %d chars system + %d chars user",
            len(system_prompt),
            len(user_prompt),
        )
        return "[MOCK] Placeholder. Define TOGETHER_API_KEY para usar IA real."

    def _mock_structured(self, system_prompt: str, user_prompt: str) -> dict:
        combined = (system_prompt + " " + user_prompt).lower()

        if "etnógrafo" in combined or "population_context" in combined:
            logger.info("MOCK: A1 POPULATION_CONTEXT_BUILDER")
            return dict(MOCK_RESPONSES["POPULATION_CONTEXT_BUILDER"])

        elif "proceso sociocognitivo" in combined or "process_identifier" in combined:
            if "entrevistado anterior" in combined:
                logger.info("MOCK: A2 PROCESS_IDENTIFIER (compare)")
                return dict(MOCK_RESPONSES["PROCESS_IDENTIFIER_COMPARE"])
            else:
                logger.info("MOCK: A2 PROCESS_IDENTIFIER (first)")
                return dict(MOCK_RESPONSES["PROCESS_IDENTIFIER_FIRST"])

        elif "sentido emergente" in combined or "sense_maker" in combined:
            if "primera vez" in combined or "no hay hipótesis previas" in combined:
                logger.info("MOCK: A3 SENSE_MAKER (first)")
                return dict(MOCK_RESPONSES["SENSE_MAKER_FIRST"])
            else:
                logger.info("MOCK: A3 SENSE_MAKER (continue)")
                return dict(MOCK_RESPONSES["SENSE_MAKER_CONTINUE"])

        logger.info("MOCK: unknown agent, generic response")
        return {"mock_response": True, "note": "Agente no reconocido."}
