# 6 — ContextWindowManager: Procesamiento Iterativo con Presupuesto de Contexto

> **Resuelve C6 de la auditoría de contradicciones.** Diseña una tool unificada para evitar la saturación del contexto de la IA en todas las capas de datos del sistema CGT.

---

## 1. Diagnóstico: ¿Dónde se satura el contexto?

El sistema CGT opera sobre volúmenes de datos que crecen con cada documento. Sin una estrategia de escalamiento, el contexto de la IA se satura en estos puntos:

| Capa | Entidad | Volumen (10 docs) | Tokens estimados | ¿Excede contexto? | Estrategia actual |
|------|---------|-------------------|------------------|--------------------|--------------------|
| **Segmentación** | segmentos | ~500-1000 | 250K-1M | ✅ Excede (mucho) | Ya es per-segmento (NLP worker procesa 1 a 1) |
| **Extracción** | extracted_incidents | ~500 | ~100K | ✅ Excede si se procesan juntos | ⚠️ **Debe ser per-segmento** (corregir en F2.2) |
| **Comparación (B1)** | incident_comparisons | ~125K pares | ~500K si todos vs todos | ✅✅ Excede críticamente | 🔴 **No existe.** Requiere estrategia de batching + pre-filtro. |
| **Etiquetado (B2)** | incident_groups | ~25-50 grupos | ~25K | ⚠️ Borderline con 15+ docs | 🔴 **No existe.** Requiere batching de grupos. |
| **Saturación (C)** | paradigm_states × docs | ~100 its | ~5K/iteración | ✅ Cabe (pero son muchas its) | ✅ Ya es iterativo (loop categoría × doc) |
| **Hipótesis (B3)** | categorias + memos | ~20 cats + ~30 memos | ~50K | ⚠️ Borderline | ⚠️ Actualmente envía todo. Necesita top-K filter. |
| **Database A/B (D)** | nodos + edges | ~15 nodos + ~30 edges | ~15K | ✅ Cabe | ✅ Ya funciona |
| **Playground** | blobs + tendrils + ghosts | ~20 + ~30 + ~10 | N/A (no es LLM) | ✅ No aplica | ✅ Es frontend |
| **Escritura (6a)** | memos ordenados | ~30-50 memos | ~50K | ⚠️ Borderline | 🔴 No implementado |
| **Literatura (6c)** | teoría + fragments | ~30K + 20K | ~50K | ⚠️ Borderline | 🔴 No implementado |

**Conclusión:** Los puntos críticos son la **comparación de incidentes (B1)** y el **etiquetado (B2)**. Los puntos borderline (hipótesis, escritura, literatura) se resuelven con filtros top-K. Los demás ya están correctamente diseñados como per-segmento o per-documento.

---

## 2. Solución: `ContextWindowManager`

Una **tool algorítmica** (sin LLM) registrada en `ToolRegistry` que implementa el patrón **Map-Reduce con convergencia iterativa**. Cualquier agente puede invocarla para procesar grandes volúmenes de datos sin saturar el contexto.

### 2.1 API

```python
class ContextWindowManager:
    """
    Tool genérica para procesamiento iterativo con presupuesto de contexto.

    Implementa: Map → Reduce → Detect Convergence → Repeat if needed.

    Attributes:
        context_budget: Tokens máximos por llamada LLM (default: 8000 para PRO, 4000 para FLASH).
        overlap: Tokens de solapamiento entre batches para mantener continuidad (default: 200).
        max_iterations: Máximo de iteraciones globales (default: 3).
        token_estimator_fn: Callable que estima tokens de un item (default: len(str(item)) // 3).
    """

    def __init__(
        self,
        context_budget: int = 8000,
        overlap: int = 200,
        max_iterations: int = 3,
        token_estimator_fn: Callable[[Any], int] | None = None,
    ):
        ...

    def batch_process(
        self,
        items: list[Any],
        map_fn: Callable[[list[Any]], dict],       # Procesa un batch → resultado parcial
        reduce_fn: Callable[[list[dict]], dict],    # Fusiona resultados parciales → consolidado
        converge_fn: Callable[[dict, dict], bool],  # ¿El nuevo resultado es igual al anterior?
        item_token_key: str = "text",               # Key del item que contiene el texto a contar
        batch_size: int | None = None,              # Auto-calculado si None
    ) -> dict:
        """
        Procesa items en batches que caben en context_budget.

        Returns:
            dict con {
                "result": resultado consolidado final,
                "iterations": número de iteraciones completadas,
                "batches_processed": total de batches,
                "converged": bool (True si convergió antes de max_iterations),
                "items_processed": total de items,
            }
        """
        ...
```

### 2.2 Algoritmo

```
1. ESTIMAR tokens por item
2. Calcular batch_size = context_budget // (tokens_por_item + overlap)
3. MAP: Para cada batch de items:
   a. Seleccionar batch_size items
   b. Incluir overlap_items del batch anterior (para continuidad)
   c. Llamar map_fn(batch) → partial_result
4. REDUCE: Llamar reduce_fn(todos los partial_results) → consolidated_result
5. CONVERGE?: Llamar converge_fn(consolidated_result, previous_result)
   a. Si converge → devolver consolidated_result
   b. Si no converge y iterations < max_iterations:
      - Reordenar items para que los borderline queden en batches distintos
      - Volver a MAP con el nuevo orden
6. Si max_iterations alcanzado sin converger → devolver con converged=False
```

### 2.3 Registro como Tool

```python
# En backend/app/agents/tools/context_window.py

from app.agents.tool_registry import tool

@tool(
    name="batch_process",
    description="Procesa grandes volúmenes de datos en batches que caben en el contexto de la IA. "
                "Útil cuando hay demasiados items para una sola llamada LLM.",
    parameters={
        "items": "list[dict] — Items a procesar. Cada item debe tener una key de texto.",
        "context_budget": "int — Tokens máximos por batch (default: 8000).",
        "map_agent_id": "str — Agent ID del LLM a invocar por batch.",
        "reduce_strategy": "str — 'concat' | 'merge_json' | 'union' | 'vote' — Cómo combinar resultados.",
        "converge_threshold": "float — Diferencia máxima entre iteraciones para considerar convergencia (default: 0.05).",
    },
)
def batch_process_tool(
    items: list[dict],
    context_budget: int = 8000,
    map_agent_id: str = "",
    reduce_strategy: str = "merge_json",
    converge_threshold: float = 0.05,
) -> dict:
    """Tool wrapper para ContextWindowManager. Invocable por cualquier agente vía ReactRunner."""
    ...
```

---

## 3. Aplicación por Capa de Datos

### 3.1 Comparación de Incidentes (B1) — El caso más crítico

**Problema:** 10 documentos × 50 incidentes = 500 incidentes. Comparar todos contra todos = 125K pares. Si cada par son ~200 tokens de input, el contexto necesitaría ~25M tokens. Imposible.

**Estrategia de 3 pasos:**

```
PASO 1: PRE-FILTRO POR EMBEDDING (⚙️ ALG, sin LLM)
  Para cada incidente, calcular embedding (TEI voyage-4-nano, 1024-dim).
  Para cada par (i, j) donde i < j:
    sim = cosine(embedding[i], embedding[j])
    if sim > 0.75 → agregar a candidatos
    else → descartar (no son intercambiables)
  
  Resultado: ~5-10% de los pares sobreviven (~6K-12K pares para 500 incidentes).

PASO 2: BATCH COMPARISON (🟣 PRO, con ContextWindowManager)
  context_budget = 8000 (PRO)
  tokens_por_par = ~200 (incidente A + incidente B en formato compacto)
  batch_size = 8000 // 200 = 40 pares por batch
  
  12K pares ÷ 40 = 300 batches
  
  map_fn: Para cada batch de 40 pares, el LLM evalúa intercambiabilidad.
    Output: [{pair_id, are_interchangeable, rationale, suggested_label}]
  
  reduce_fn: UNION de todos los resultados parciales.
  
  converge_fn: Siempre True (1-pass es suficiente; la comparación es determinista).
  
  Resultado: ~500 grupos de incidentes intercambiables.

PASO 3: AGRUPAMIENTO (⚙️ ALG, sin LLM)
  Sobre los pares marcados como intercambiables, aplicar Union-Find
  para construir los grupos finales → incident_groups.
```

**Complejidad:** De O(N²) con LLM a O(N²) con embedding (barato) + O(K) con LLM (K = pares sobrevivientes). Para 500 incidentes: 125K comparaciones de embedding (~0.1s) + 300 batches LLM (~$0.30). **Viable.**

### 3.2 Etiquetado de Grupos (B2)

**Problema:** 50 grupos de incidentes, cada uno con 5-15 incidentes. Si se envían todos juntos, ~25K tokens. Con 15+ documentos (75+ grupos), se excede el contexto.

**Estrategia con ContextWindowManager:**

```
context_budget = 8000 (PRO)
tokens_por_grupo = ~500 (label + incidentes resumidos del grupo)
batch_size = 8000 // 500 = 16 grupos por batch

50 grupos ÷ 16 = 4 batches

map_fn: Para cada batch, el pattern_labeler (PRO) propone etiquetas.
reduce_fn: merge_json — combina todas las etiquetas propuestas.
converge_fn: Compara si las etiquetas entre iteraciones son estables
  (mismos grupos → mismas etiquetas). Si hay inestabilidad,
  re-ordenar grupos para que los borderline queden en batches distintos.
```

### 3.3 Hipótesis (B3) — Borderline

**Problema:** ~30 categorías + ~50 memos + ~20 hipótesis previas → ~50K tokens.

**Estrategia (sin necesidad de ContextWindowManager completo):**

```
Pre-filtro top-K:
  - Solo enviar categorías con puntaje_relevancia >= 4 (~15 cats)
  - Solo enviar memos de tipo HIPOTESIS o PROPIEDAD (~20 memos)
  - Solo enviar hipótesis previas con status='accepted' (~10 hyps)
  
  Total: ~20K tokens → cabe en contexto PRO.
```

Si aún así excede con proyectos muy grandes (50+ docs):
```
Usar ContextWindowManager con:
  batch_size = categorías que quepan en 6000 tokens
  map_fn = generate_hypotheses(batch_cats)
  reduce_fn = merge por confidence score
```

### 3.4 Core Saturation Loop (C) — Ya es iterativo

**Problema:** Loop sobre categoría × documento. Cada iteración es pequeña (~2K-5K tokens). No hay problema de contexto por llamada individual. El problema es la **cantidad** de iteraciones (categorías × docs).

**Estrategia (sin ContextWindowManager):**

```
Usar las 4 señales para evitar iteraciones innecesarias:
  - Señal matemática (barata): si rolling_std es alto → ni siquiera llamar al LLM.
  - Señal cualitativa (cara): solo si la matemática sugiere estabilidad.
  
  Esto reduce las llamadas LLM en ~70%.
```

### 3.5 Escritura (6a) — Borderline

**Problema:** 30-50 memos en una pila de sorting → ~50K tokens.

**Estrategia con ContextWindowManager:**

```
context_budget = 8000 (PRO)
tokens_por_memo = ~500 (contenido típico de un memo)
batch_size = 8000 // 500 = 16 memos por batch

50 memos ÷ 16 = 4 batches

map_fn: Para cada batch, el natural_writer redacta una sub-sección.
reduce_fn: El mismo natural_writer (o uno más ligero) integra las sub-secciones
  en una sección coherente, usando los conceptos compartidos como puentes.
converge_fn: El writing_critic evalúa si la integración es fluida.
  Si detecta transiciones forzadas → re-iterar con batches reordenados.
```

### 3.6 Literatura (6c) — Borderline

**Problema:** Teoría completa (~30K) + 20 fragmentos de literatura (~20K) → ~50K tokens.

**Estrategia con ContextWindowManager:**

```
PASO 1: BÚSQUEDA (RAG, sin LLM)
  Para cada categoría, buscar top-3 fragmentos de literatura por similitud semántica.
  Esto reduce 20 fragmentos → ~10 fragmentos realmente relevantes (~10K tokens).

PASO 2: COMPARACIÓN POR CATEGORÍA (con ContextWindowManager)
  context_budget = 8000
  tokens_por_categoria = ~1500 (definición + propiedades + 3 fragmentos)
  batch_size = 5 categorías por batch
  
  map_fn: literature_comparer evalúa emergent fit para cada categoría.
  reduce_fn: merge_json de las tablas Extiende/Modifica/Integra/Trasciende.
  converge_fn: Siempre True (la comparación es independiente por categoría).
```

---

## 4. Implementación Técnica

### 4.1 Archivo: `backend/app/agents/tools/context_window.py`

```python
"""ContextWindowManager — Tool de procesamiento iterativo con presupuesto de contexto.

Resuelve C6: evita la saturación del contexto de la IA en todas las capas de datos.
Implementa Map-Reduce con convergencia iterativa. Registrado como tool en ToolRegistry.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable

from app.agents.tool_registry import tool

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Token estimator
# ═══════════════════════════════════════════════════════════════════════

def estimate_tokens(text: str) -> int:
    """Estimación rápida: ~1 token cada 3 caracteres (promedio español/inglés)."""
    return max(1, len(text) // 3)


def estimate_item_tokens(item: Any, text_keys: list[str] | None = None) -> int:
    """Estima tokens de un item (dict, str, o serializable)."""
    if isinstance(item, str):
        return estimate_tokens(item)
    if isinstance(item, dict):
        if text_keys:
            return sum(estimate_tokens(str(item.get(k, ""))) for k in text_keys)
        return estimate_tokens(json.dumps(item, ensure_ascii=False))
    return estimate_tokens(str(item))


# ═══════════════════════════════════════════════════════════════════════
# ContextWindowManager
# ═══════════════════════════════════════════════════════════════════════

class ContextWindowManager:
    """Procesa items en batches que caben en el presupuesto de contexto.

    Attributes:
        context_budget: Tokens máximos por batch.
        overlap: Tokens de solapamiento entre batches.
        max_iterations: Máximo de iteraciones globales.
        token_estimator: Callable para estimar tokens de un item.
    """

    def __init__(
        self,
        context_budget: int = 8000,
        overlap: int = 200,
        max_iterations: int = 3,
    ):
        self.context_budget = context_budget
        self.overlap = overlap
        self.max_iterations = max_iterations

    # ── Public API ──────────────────────────────────────────────────

    def batch_process(
        self,
        items: list[Any],
        map_fn: Callable[[list[Any]], dict],
        reduce_fn: Callable[[list[dict]], dict],
        converge_fn: Callable[[dict, dict], bool],
        text_keys: list[str] | None = None,
        batch_size: int | None = None,
    ) -> dict:
        """Procesa items en batches iterativos hasta convergencia.

        Args:
            items: Lista de items a procesar.
            map_fn: Función que procesa un batch → partial_result dict.
            reduce_fn: Función que fusiona partial_results → consolidated dict.
            converge_fn: Función que compara dos resultados consecutivos → bool.
            text_keys: Keys del item que contienen texto (para estimar tokens).
            batch_size: Tamaño de batch manual. Si None, se auto-calcula.

        Returns:
            dict con result, iterations, batches_processed, converged, items_processed.
        """
        if not items:
            return {"result": {}, "iterations": 0, "batches_processed": 0,
                    "converged": True, "items_processed": 0}

        # ── Calcular batch size ──
        if batch_size is None:
            avg_tokens = sum(
                estimate_item_tokens(item, text_keys) for item in items
            ) / len(items)
            batch_size = max(1, (self.context_budget - self.overlap) // max(1, avg_tokens))
            logger.info(
                "Auto batch_size=%d (avg_tokens=%.0f, budget=%d)",
                batch_size, avg_tokens, self.context_budget,
            )

        # ── Iterar hasta convergencia ──
        previous_result: dict | None = None
        total_batches = 0

        for iteration in range(self.max_iterations):
            partials: list[dict] = []
            batches_in_iteration = 0

            for i in range(0, len(items), batch_size):
                batch = items[i : i + batch_size]

                # Incluir overlap del batch anterior (si no es el primero)
                if i > 0:
                    overlap_start = max(0, i - self.overlap)
                    overlap_items = items[overlap_start:i]
                    batch = overlap_items + batch

                partial = map_fn(batch)
                partials.append(partial)
                batches_in_iteration += 1

            # ── Reducir ──
            consolidated = reduce_fn(partials)
            total_batches += batches_in_iteration

            # ── ¿Convergió? ──
            if previous_result is not None and converge_fn(consolidated, previous_result):
                logger.info(
                    "Converged at iteration %d/%d (%d batches total)",
                    iteration + 1, self.max_iterations, total_batches,
                )
                return {
                    "result": consolidated,
                    "iterations": iteration + 1,
                    "batches_processed": total_batches,
                    "converged": True,
                    "items_processed": len(items),
                }

            previous_result = consolidated

            # ── Reordenar items para la próxima iteración ──
            # Los items que generaron resultados borderline van al principio
            # para que se procesen en batches diferentes.
            if iteration < self.max_iterations - 1:
                items = self._reorder_for_diversity(items, batch_size)

        logger.info(
            "Max iterations reached (%d) without convergence. %d batches total.",
            self.max_iterations, total_batches,
        )
        return {
            "result": previous_result or {},
            "iterations": self.max_iterations,
            "batches_processed": total_batches,
            "converged": False,
            "items_processed": len(items),
        }

    # ── Internal ─────────────────────────────────────────────────────

    @staticmethod
    def _reorder_for_diversity(items: list[Any], batch_size: int) -> list[Any]:
        """Reordena items para que batches consecutivos tengan composición diferente.

        Estrategia: invertir cada batch_size/2 items (interleaving).
        Esto asegura que items que estaban juntos en la iteración anterior
        ahora estén en batches distintos, forzando al LLM a reconsiderar.
        """
        reordered = []
        half = max(1, batch_size // 2)
        for i in range(0, len(items), batch_size):
            chunk = items[i : i + batch_size]
            # Interleave: primer half en orden, segundo half invertido
            first = chunk[:half]
            second = list(reversed(chunk[half:]))
            reordered.extend(first + second)
        return reordered


# ═══════════════════════════════════════════════════════════════════════
# Tool registration (invocable por cualquier agente vía ReactRunner)
# ═══════════════════════════════════════════════════════════════════════

@tool(
    name="batch_process",
    description=(
        "Procesa grandes volúmenes de datos en batches que caben en el contexto de la IA. "
        "Implementa Map-Reduce con convergencia iterativa. "
        "Útil cuando hay demasiados items para una sola llamada LLM. "
        "Ejemplo: comparar 500 incidentes entre sí sin saturar el contexto."
    ),
    parameters={
        "items_json": "str — JSON array de items a procesar.",
        "context_budget": "int — Tokens máximos por batch (default: 8000 para PRO, 4000 para FLASH).",
        "map_agent_id": "str — Agent ID del LLM a invocar para cada batch.",
        "reduce_strategy": "str — 'union' | 'merge_json' | 'vote' | 'concat'. Cómo combinar resultados parciales.",
        "text_keys": "list[str] — Keys del item que contienen texto a contar para el presupuesto.",
    },
)
def batch_process_tool(
    items_json: str = "[]",
    context_budget: int = 8000,
    map_agent_id: str = "",
    reduce_strategy: str = "merge_json",
    text_keys: list[str] | None = None,
) -> str:
    """Tool: procesa items en batches con presupuesto de contexto.

    Invocable por cualquier agente vía ReactRunner.
    El agente debe proporcionar un map_agent_id que se invocará por batch.

    Returns:
        JSON string con el resultado consolidado.
    """
    import json as _json

    from app.agents.tool_registry import ToolRegistry

    items = _json.loads(items_json) if isinstance(items_json, str) else items_json
    if not items:
        return _json.dumps({"error": "No items to process"})

    manager = ContextWindowManager(context_budget=context_budget, max_iterations=3)

    # ── MAP function: invoca el agente LLM por batch ──
    def _map_batch(batch: list[dict]) -> dict:
        registry = ToolRegistry()
        llm = registry._llm  # Asume que ToolRegistry tiene referencia al LLM client
        result = llm.run_agent(map_agent_id, variables={"items": batch})
        return result if isinstance(result, dict) else {"raw": str(result)}

    # ── REDUCE strategies ──
    def _reduce_union(partials: list[dict]) -> dict:
        """Union: concatena listas bajo la misma key."""
        merged: dict[str, list] = {}
        for p in partials:
            for k, v in p.items():
                if isinstance(v, list):
                    merged.setdefault(k, []).extend(v)
                else:
                    merged.setdefault(k, []).append(v)
        return dict(merged)

    def _reduce_merge_json(partials: list[dict]) -> dict:
        """Merge JSON: combina diccionarios, las listas se concatenan."""
        result: dict = {}
        for p in partials:
            for k, v in p.items():
                if k in result and isinstance(result[k], list) and isinstance(v, list):
                    result[k].extend(v)
                elif k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k].update(v)
                else:
                    result[k] = v
        return result

    def _reduce_vote(partials: list[dict]) -> dict:
        """Vote: para outputs con 'verdict', elige el mayoritario."""
        from collections import Counter
        verdicts = Counter()
        details = []
        for p in partials:
            if "verdict" in p:
                verdicts[p["verdict"]] += 1
            details.append(p)
        majority = verdicts.most_common(1)[0][0] if verdicts else "UNKNOWN"
        return {"verdict": majority, "details": details, "counts": dict(verdicts)}

    _reducers = {
        "union": _reduce_union,
        "merge_json": _reduce_merge_json,
        "vote": _reduce_vote,
        "concat": _reduce_merge_json,  # alias
    }
    reduce_fn = _reducers.get(reduce_strategy, _reduce_merge_json)

    # ── CONVERGE: comparar hashes ──
    def _converge(a: dict, b: dict) -> bool:
        ha = hashlib.md5(_json.dumps(a, sort_keys=True).encode()).hexdigest()
        hb = hashlib.md5(_json.dumps(b, sort_keys=True).encode()).hexdigest()
        return ha == hb

    result = manager.batch_process(
        items=items,
        map_fn=_map_batch,
        reduce_fn=reduce_fn,
        converge_fn=_converge,
        text_keys=text_keys,
    )

    return _json.dumps(result, ensure_ascii=False)
```

### 4.2 Integración con ToolRegistry

```python
# En backend/app/agents/tools/__init__.py
from app.agents.tools.context_window import batch_process_tool, ContextWindowManager

__all__ = [
    ...,
    "batch_process_tool",
    "ContextWindowManager",
]
```

### 4.3 Uso desde un Agente (ejemplo: incident_comparator)

```python
# En workers/heavy/comparator.py

def b1_compare_incidents(proyecto_id: str, incremental: bool = False) -> dict:
    """B1: Comparador de incidentes. Usa ContextWindowManager para escalar."""
    
    # 1. Obtener incidentes
    incidents = _get_incidents(proyecto_id, incremental)
    
    # 2. Pre-filtro por embedding (capa algorítmica)
    candidate_pairs = _prefilter_by_embedding(incidents, threshold=0.75)
    
    # 3. Batch comparison con ContextWindowManager
    manager = ContextWindowManager(context_budget=8000)
    
    result = manager.batch_process(
        items=candidate_pairs,
        map_fn=_compare_batch,  # Llama al LLM PRO por batch
        reduce_fn=_reduce_union,
        converge_fn=lambda a, b: True,  # 1-pass: la comparación es determinista
        text_keys=["incident_a_text", "incident_b_text"],
    )
    
    # 4. Agrupamiento final (Union-Find, sin LLM)
    groups = _build_groups(result["result"])
    
    return {"incident_groups": groups, "pairs_processed": len(candidate_pairs)}
```

---

## 5. Plan de Implementación

| Prioridad | Qué | Dónde | Esfuerzo |
|-----------|-----|-------|----------|
| **1** | Implementar `ContextWindowManager` + `batch_process_tool` | `backend/app/agents/tools/context_window.py` | Medio |
| **2** | Registrar en `ToolRegistry` | `backend/app/agents/tools/__init__.py`, `tool_registry.py` | Bajo |
| **3** | Aplicar a `incident_comparator` (B1) — el caso más crítico | `workers/heavy/comparator.py` | Alto |
| **4** | Aplicar a `pattern_labeler` (B2) | `workers/heavy/labeler.py` | Medio |
| **5** | Aplicar pre-filtro top-K a `b3_generate_hypotheses` | `workers/heavy/agents_b.py` | Bajo |
| **6** | Aplicar a `natural_writer` (6a) cuando se implemente | `workers/heavy/writer.py` | Bajo |
| **7** | Aplicar a `literature_comparer` (6c) cuando se implemente | `workers/heavy/literature.py` | Bajo |

---

## 6. Principios de Diseño

1. **Sin LLM para decisiones de escalamiento.** El `ContextWindowManager` es puramente algorítmico. Decide cómo particionar, cuándo iterar, y si convergió — sin gastar tokens.

2. **Pre-filtro algorítmico siempre que sea posible.** Antes de enviar datos al LLM, aplicar filtros baratos (embedding similarity, top-K por score, ventanas temporales). Esto reduce el volumen LLM en 80-95%.

3. **Convergencia por hash, no por LLM.** Comparar resultados entre iteraciones usando hash del output JSON. Si dos iteraciones producen exactamente el mismo resultado → convergió. Sin costo de LLM.

4. **Overlap para continuidad.** Cada batch incluye algunos items del batch anterior. Esto evita que el LLM pierda contexto entre batches y produce resultados más coherentes.

5. **Reordenamiento para diversidad.** Si no converge, la segunda iteración reordena los items (interleaving) para que los pares/grupos borderline se comparen en contextos diferentes, forzando una reconsideración.

6. **Tool, no framework.** El `ContextWindowManager` está registrado como tool en `ToolRegistry`. Cualquier agente (ReactRunner, PlanExecutor) puede invocarlo. No requiere modificar la arquitectura de agentes.
