"""
Configuración de ventana de contexto para modelos LLM.

Principios:
- MAX_CONTEXT_TOKENS: límite físico del modelo (250K para DeepSeek V4 Pro y Nemotron 3 Ultra)
- OVERHEAD_RATIOS: porcentajes de la ventana que se reservan para system prompt, conversation history, y JSON schema
- El usuario puede configurar CONTEXT_WINDOW_REAL (solo disminuir, nunca aumentar)
- Si se cambia a un modelo más potente en el futuro, solo se actualizan estos valores
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class ContextConfig(BaseSettings):
    """Configuración de ventana de contexto. Sobreescribible por variables de entorno."""

    # ── Límite físico del modelo ──
    MODEL_MAX_CONTEXT_TOKENS: int = Field(
        default=250_000,
        description="Límite físico de tokens del modelo (DeepSeek V4 Pro / Nemotron 3 Ultra)",
    )

    # ── Overhead: tokens reservados para infraestructura del prompt ──
    SYSTEM_PROMPT_OVERHEAD_RATIO: float = Field(
        default=0.05,  # 5% = 12,500 tokens
        description="Porcentaje reservado para system prompt, YAML frontmatter, instrucciones",
    )
    CONVERSATION_HISTORY_OVERHEAD_RATIO: float = Field(
        default=0.10,  # 10% = 25,000 tokens
        description="Porcentaje reservado para historial de conversación (SelfRefinement loops)",
    )
    JSON_SCHEMA_OVERHEAD_RATIO: float = Field(
        default=0.03,  # 3% = 7,500 tokens
        description="Porcentaje reservado para JSON Schema inline o response_format",
    )
    OUTPUT_BUFFER_RATIO: float = Field(
        default=0.07,  # 7% = 17,500 tokens
        description="Porcentaje reservado para el output del modelo (max_tokens)",
    )

    # ── Ventana "real" para datos (configurable por proyecto, solo disminuir) ──
    CONTEXT_WINDOW_REAL_DEFAULT: int = Field(
        default=150_000,  # tokens disponibles para segmentos, incidentes, memos
        description="Ventana real default para datos. El usuario puede disminuirla, nunca aumentarla.",
    )

    # ── Umbrales de fragmentación ──
    FRAGMENTATION_THRESHOLD_RATIO: float = Field(
        default=0.85,  # Fragmentar si los datos ocupan >85% de la ventana real
        description="Si datos > 85% de CONTEXT_WINDOW_REAL, activar Map-Reduce",
    )
    ITEMS_PER_BATCH_TARGET: int = Field(
        default=100,
        description="Número objetivo de items por batch en Map-Reduce",
    )
    MAX_BATCHES: int = Field(
        default=20,
        description="Máximo número de batches (protección contra proyectos enormes)",
    )

    # ── Estimación de tokens ──
    CHARS_PER_TOKEN_ESTIMATE: float = Field(
        default=3.5,  # ~3.5 caracteres por token en promedio (inglés + español)
        description="Estimación conservadora de caracteres por token",
    )

    @property
    def available_for_data(self) -> int:
        """Tokens disponibles para datos después de restar overhead."""
        overhead = (
            self.SYSTEM_PROMPT_OVERHEAD_RATIO
            + self.CONVERSATION_HISTORY_OVERHEAD_RATIO
            + self.JSON_SCHEMA_OVERHEAD_RATIO
            + self.OUTPUT_BUFFER_RATIO
        )
        return int(self.MODEL_MAX_CONTEXT_TOKENS * (1.0 - overhead))

    @property
    def effective_window(self) -> int:
        """La ventana efectiva es el mínimo entre available_for_data y CONTEXT_WINDOW_REAL_DEFAULT."""
        return min(self.available_for_data, self.CONTEXT_WINDOW_REAL_DEFAULT)

    def estimate_tokens(self, text: str) -> int:
        """Estima tokens de un texto usando chars_per_token."""
        return int(len(text) / self.CHARS_PER_TOKEN_ESTIMATE)

    def should_fragment(self, total_estimated_tokens: int) -> bool:
        """Determina si se debe fragmentar basado en el umbral."""
        return total_estimated_tokens > (
            self.effective_window * self.FRAGMENTATION_THRESHOLD_RATIO
        )

    def calculate_batches(self, total_items: int, avg_tokens_per_item: int) -> dict:
        """Calcula cuántos batches se necesitan."""
        total_tokens = total_items * avg_tokens_per_item
        if not self.should_fragment(total_tokens):
            return {
                "needs_fragmentation": False,
                "batches": 1,
                "items_per_batch": total_items,
            }

        max_items_per_batch = max(
            10,  # mínimo 10 items por batch
            int(
                self.effective_window
                * self.FRAGMENTATION_THRESHOLD_RATIO
                / avg_tokens_per_item
            ),
        )
        batches = min(
            self.MAX_BATCHES,
            max(
                1,
                total_items // max_items_per_batch
                + (1 if total_items % max_items_per_batch else 0),
            ),
        )
        items_per_batch = total_items // batches + (1 if total_items % batches else 0)

        return {
            "needs_fragmentation": True,
            "batches": batches,
            "items_per_batch": items_per_batch,
            "estimated_tokens_per_batch": items_per_batch * avg_tokens_per_item,
            "total_estimated_tokens": total_tokens,
            "effective_window": self.effective_window,
        }


# Singleton
context_config = ContextConfig()
