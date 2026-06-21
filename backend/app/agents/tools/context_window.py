"""ContextWindowManager — Tools de exploración contextual para la IA.

La IA no puede cargar todos los segmentos e incidentes en una sola llamada LLM.
En lugar de eso, recibe resúmenes y usa estas tools como "ojos" para abrir
segmentos específicos cuando necesita verificar un patrón, entender el contexto
narrativo, o buscar evidencia relacionada.

Patrón de uso (descrito por el usuario):
    1. La IA recibe un resumen con N incidentes agrupados
    2. Llama a expand_incident() para "abrir" los segmentos fuente de incidentes clave
    3. Si necesita más contexto, llama a get_document_window() para ver el flujo narrativo
    4. Si busca menciones exactas de entidades, llama a search_precise_entities()
    5. Toma una decisión basada en la evidencia revisada

Las tools están registradas en ToolRegistry. Cualquier agente (ReactRunner,
PlanExecutor) puede invocarlas.

Registro:
    from app.agents.tools.context_window import (
        expand_incident, search_precise_entities, get_document_window,
        estimate_batch_tokens, batch_map_reduce,
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.agents.tool_registry import tool
from app.core.context_config import context_config

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════


def _run_async(coro):
    """Ejecuta una coroutine en el event loop actual, seguro desde sync."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            with ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _safe_uuid(value: UUID | str | None) -> UUID | None:
    """Convierte a UUID de forma segura, retornando None si inválido."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None


def _extract_entities(text: str | None) -> list[str]:
    """Extrae entidades concretas (nombres, lugares, objetos) de un texto.

    Heurística simple: palabras capitalizadas consecutivas (en español/inglés)
    y sustantivos propios. No usa embeddings — es puramente léxico.
    """
    if not text:
        return []
    # Captura secuencias de palabras capitalizadas (nombres propios, lugares, etc.)
    # También captura frases entre comillas
    entities: set[str] = set()

    # 1. Comillas (frases exactas mencionadas por el LLM)
    quoted = re.findall(r'"([^"]+)"', text)
    for q in quoted:
        q = q.strip()
        if len(q) > 3:
            entities.add(q)

    # 2. Secuencias de palabras capitalizadas (nombres propios)
    proper = re.findall(
        r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)\b", text
    )
    for p in proper:
        p = p.strip()
        if len(p) > 3:
            entities.add(p)

    # 3. Palabras clave en minúscula que podrían ser entidades (lugares, objetos específicos)
    #    Filtradas por longitud mínima para evitar ruido
    potential = re.findall(
        r"\b(?:hospital|escuela|empresa|gobierno|algoritmo|"
        r"aplicaci[oó]n|plataforma|sistema|m[aá]quina|"
        r"internet|mercado|barrio|ciudad|pa[ií]s|doctor|"
        r"m[aá]quina de|inteligencia artificial)\b",
        text,
        re.IGNORECASE,
    )
    for p in potential:
        entities.add(p.lower())

    return list(entities)


# ══════════════════════════════════════════════════════════════════
# Clase principal
# ══════════════════════════════════════════════════════════════════


class ContextWindowManager:
    """Gestor de contexto para exploración de segmentos e incidentes.

    Orquesta el acceso a la base de datos para que la IA pueda "abrir"
    segmentos bajo demanda, sin necesidad de cargar todo el corpus en
    una sola llamada LLM.

    Filosofía:
        - Búsqueda PRECISA (ILIKE en PostgreSQL), NO semántica (embeddings/RAG).
          En investigación cualitativa, el lenguaje no es homogéneo. RAG puede
          devolver resultados engañosos por similitud semántica superficial.
          Solo búsqueda exacta de entidades concretas.
        - La IA decide el tamaño de ventana (no hay ventana hardcodeada).
        - Las tools se componen: expand_incident usa get_document_window y
          opcionalmente search_precise_entities.

    Attributes:
        db_session_factory: Factory de sesiones SQLAlchemy (async).
            Si es None, se usa AsyncSessionLocal por defecto.
    """

    def __init__(self, db_session_factory=None):
        """Inicializa el manager con dependencias inyectables.

        Args:
            db_session_factory: Factory de sesiones async. Si None, usa
                AsyncSessionLocal de app.db.database.
        """
        self.db_session_factory = db_session_factory

    def _get_session_factory(self):
        """Resuelve lazy la session factory para evitar imports circulares."""
        if self.db_session_factory is not None:
            return self.db_session_factory
        from app.db.database import AsyncSessionLocal

        return AsyncSessionLocal

    # ── Métodos públicos ─────────────────────────────────────────

    def search_precise_entities(
        self,
        query_text: str,
        proyecto_id: UUID | str,
        document_id: UUID | str | None = None,
        max_results: int = 10,
    ) -> list[dict]:
        """Búsqueda PRECISA (no semántica) de entidades en segmentos.

        Usa PostgreSQL ILIKE para encontrar menciones EXACTAS de entidades
        concretas (nombres, lugares, objetos, frases específicas).
        NO usa embeddings. NO usa RAG.

        RAZÓN: El lenguaje cualitativo no es homogéneo ni estructurado.
        RAG puede devolver resultados engañosos por similitud semántica
        superficial. Solo búsqueda precisa.

        Args:
            query_text: Texto exacto o patrón a buscar
                (ej: "María", "hospital", "despido", "negociando límites").
            proyecto_id: UUID del proyecto para limitar el scope.
            document_id: Opcional, limitar a un documento específico.
            max_results: Máximo de resultados (default: 10, max: 50).

        Returns:
            Lista de segmentos que contienen el texto exacto, cada uno con:
            {
                "segmento_id": str,
                "texto": str (truncado a 300 chars),
                "documento_id": str,
                "documento_nombre": str,
                "posicion": int,
                "es_foco": false,
            }

        Uso típico:
            La IA encuentra un incidente que menciona "María" o "el hospital
            de la esquina". Quiere encontrar TODAS las menciones de esa
            entidad en el corpus (no conceptos similares, sino la entidad
            concreta). Llama a search_precise_entities(query_text="María").

        Implementación:
            SELECT s.*, d.original_filename
            FROM segmentos s
            JOIN documentos d ON s.documento_id = d.id
            WHERE d.proyecto_id = :proyecto_id
              AND s.texto ILIKE '%' || :query || '%'
            [AND s.documento_id = :documento_id]
            ORDER BY d.original_filename, s.posicion
            LIMIT :max_results
        """
        proyecto_uuid = _safe_uuid(proyecto_id)
        if proyecto_uuid is None:
            logger.error(
                "search_precise_entities: proyecto_id inválido=%s", proyecto_id
            )
            return [{"error": f"proyecto_id inválido: {proyecto_id}"}]

        doc_uuid = _safe_uuid(document_id)
        query_text = query_text.strip()
        if not query_text:
            logger.warning("search_precise_entities: query_text vacío")
            return []

        max_results = max(1, min(max_results, 50))

        async def _search():
            from sqlalchemy import select

            from app.models.domain.document import Documento
            from app.models.domain.segment import Segmento

            AsyncSessionLocal = self._get_session_factory()
            async with AsyncSessionLocal() as db:
                # ILIKE: case-insensitive LIKE — busca menciones exactas
                # Usamos texto SQL parametrizado para evitar inyección
                stmt = (
                    select(
                        Segmento.id,
                        Segmento.texto,
                        Segmento.posicion,
                        Segmento.documento_id,
                        Documento.original_filename,
                    )
                    .join(Documento, Segmento.documento_id == Documento.id)
                    .where(Documento.proyecto_id == proyecto_uuid)
                    .where(Segmento.texto.ilike(f"%{query_text}%"))
                )

                if doc_uuid is not None:
                    stmt = stmt.where(Segmento.documento_id == doc_uuid)

                stmt = stmt.order_by(
                    Documento.original_filename, Segmento.posicion
                ).limit(max_results)

                result = await db.execute(stmt)
                rows = result.all()

                return [
                    {
                        "segmento_id": str(row.id),
                        "texto": (
                            row.texto[:300] + "..."
                            if len(row.texto or "") > 300
                            else row.texto or ""
                        ),
                        "documento_id": str(row.documento_id),
                        "documento_nombre": row.original_filename or "",
                        "posicion": row.posicion,
                    }
                    for row in rows
                ]

        try:
            results = _run_async(_search())
            logger.info(
                "search_precise_entities: query=%r proyecto=%s → %d resultados",
                query_text,
                proyecto_uuid,
                len(results),
            )
            return results
        except Exception as e:
            logger.error("search_precise_entities failed: %s", e, exc_info=True)
            return [{"error": str(e)}]

    def get_document_window(
        self,
        document_id: UUID | str,
        focus_segment_id: UUID | str | None = None,
        radius: int | None = None,
        start_position: int | None = None,
        end_position: int | None = None,
    ) -> dict:
        """Ventana flexible de segmentos de un documento.

        Dos modos de operación (la IA elige cuál usar):

        Modo 1 (radio): focus_segment_id + radius
            Devuelve ±N segmentos alrededor del segmento foco.
            Ej: focus_segment_id=X, radius=3 → posiciones [X-3, X+3].

        Modo 2 (rango): start_position + end_position
            Devuelve segmentos en el rango exacto de posiciones.
            Ej: start=5, end=12 → posiciones 5, 6, ..., 12.

        La IA decide cuánto contexto necesita. No hay ventana hardcodeada.

        Args:
            document_id: UUID del documento (obligatorio).
            focus_segment_id: UUID del segmento foco (centro del radio).
                Requerido en Modo 1.
            radius: Número de segmentos antes y después del foco en Modo 1.
                Default: 3 si no se especifica.
            start_position: Posición inicial en Modo 2 (1-indexed, inclusivo).
            end_position: Posición final en Modo 2 (1-indexed, inclusivo).

        Returns:
            dict con:
            {
                "documento_id": str,
                "documento_nombre": str,
                "focus_segmento_id": str | null,
                "focus_posicion": int | null,
                "radius": int | null,
                "modo": "radius" | "range",
                "segmentos": [
                    {
                        "segmento_id": str,
                        "posicion": int,
                        "texto": str,
                        "es_foco": bool,
                        "distancia": int | None,
                    },
                    ...
                ],
                "total_segmentos_en_documento": int,
                "rango_cubierto": str,
            }

        Uso típico:
            La IA está analizando el flujo narrativo de una entrevista.
            Sabe que en el segmento 15 hay un incidente clave, pero necesita
            entender qué se dijo antes (pregunta del entrevistador) y después
            (elaboración del participante). Llama a get_document_window()
            con focus_segment_id y radius=5 para ver el arco narrativo completo.

            Alternativamente, la IA ya sabe que el rango de interés son las
            posiciones 10-25. Usa Modo 2 con start_position=10, end_position=25.
        """
        doc_uuid = _safe_uuid(document_id)
        if doc_uuid is None:
            msg = f"document_id inválido: {document_id}"
            logger.error("get_document_window: %s", msg)
            return {"error": msg}

        focus_uuid = _safe_uuid(focus_segment_id)

        # Determinar modo; inicializar _radius para el type checker
        modo: str
        _radius: int | None = None

        if focus_uuid is not None:
            modo = "radius"
            _radius = radius if radius is not None else 3
        elif start_position is not None and end_position is not None:
            modo = "range"
            if start_position < 1 or end_position < start_position:
                return {
                    "error": f"Rango inválido: start={start_position}, end={end_position}"
                }
            focus_uuid = None
        else:
            return {
                "error": (
                    "Debe especificar Modo 1 (focus_segment_id [+ radius]) "
                    "o Modo 2 (start_position + end_position)"
                )
            }

        async def _get_window():
            from sqlalchemy import func, select

            from app.models.domain.document import Documento
            from app.models.domain.segment import Segmento

            AsyncSessionLocal = self._get_session_factory()
            async with AsyncSessionLocal() as db:
                # 1. Obtener metadata del documento
                doc_stmt = select(Documento.original_filename).where(
                    Documento.id == doc_uuid
                )
                doc_result = await db.execute(doc_stmt)
                doc_row = doc_result.one_or_none()
                doc_nombre = doc_row.original_filename if doc_row else ""

                # 2. Total de segmentos
                total_stmt = select(func.count(Segmento.id)).where(
                    Segmento.documento_id == doc_uuid
                )
                total_result = await db.execute(total_stmt)
                total_segmentos = total_result.scalar() or 0

                if total_segmentos == 0:
                    return {
                        "documento_id": str(doc_uuid),
                        "documento_nombre": doc_nombre,
                        "focus_segmento_id": str(focus_uuid) if focus_uuid else None,
                        "focus_posicion": None,
                        "radius": _radius if modo == "radius" else None,
                        "modo": modo,
                        "segmentos": [],
                        "total_segmentos_en_documento": 0,
                        "rango_cubierto": "documento vacío",
                    }

                focus_position: int | None = None

                if modo == "radius":
                    # Buscar posición del segmento foco
                    focus_stmt = select(Segmento.posicion).where(
                        Segmento.id == focus_uuid,
                        Segmento.documento_id == doc_uuid,
                    )
                    focus_result = await db.execute(focus_stmt)
                    focus_row = focus_result.one_or_none()
                    if focus_row is None:
                        return {
                            "error": f"Segmento foco {focus_uuid} no encontrado en documento {doc_uuid}"
                        }
                    focus_position = focus_row.posicion

                    seg_start = max(1, focus_position - _radius)
                    seg_end = focus_position + _radius
                else:
                    # Modo range
                    seg_start = start_position
                    seg_end = end_position

                # 3. Query de segmentos en la ventana
                seg_stmt = (
                    select(
                        Segmento.id,
                        Segmento.texto,
                        Segmento.posicion,
                    )
                    .where(Segmento.documento_id == doc_uuid)
                    .where(Segmento.posicion >= seg_start)
                    .where(Segmento.posicion <= seg_end)
                    .order_by(Segmento.posicion)
                )
                seg_result = await db.execute(seg_stmt)
                seg_rows = seg_result.all()

                segmentos = []
                for row in seg_rows:
                    distancia = None
                    if modo == "radius" and focus_position is not None:
                        distancia = row.posicion - focus_position

                    segmentos.append(
                        {
                            "segmento_id": str(row.id),
                            "posicion": row.posicion,
                            "texto": row.texto or "",
                            "es_foco": (
                                row.id == focus_uuid if modo == "radius" else False
                            ),
                            "distancia": distancia,
                        }
                    )

                rango = (
                    f"posiciones {seg_start}-{seg_end} de {total_segmentos}"
                    if segmentos
                    else f"sin segmentos en rango {seg_start}-{seg_end}"
                )

                return {
                    "documento_id": str(doc_uuid),
                    "documento_nombre": doc_nombre,
                    "focus_segmento_id": str(focus_uuid) if focus_uuid else None,
                    "focus_posicion": focus_position,
                    "radius": _radius if modo == "radius" else None,
                    "modo": modo,
                    "segmentos": segmentos,
                    "total_segmentos_en_documento": total_segmentos,
                    "rango_cubierto": rango,
                }

        try:
            result = _run_async(_get_window())
            logger.info(
                "get_document_window: doc=%s modo=%s → %d segmentos",
                doc_uuid,
                modo,
                len(result.get("segmentos", [])),
            )
            return result
        except Exception as e:
            logger.error("get_document_window failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def expand_incident(
        self,
        incident_id: UUID | str,
        context_radius: int = 3,
        search_entities: bool = False,
    ) -> dict:
        """Expande un incidente a su contexto completo.

        Flujo interno (usa las otras tools, no tiene lógica propia de búsqueda):
        1. Busca el segmento fuente del incidente (FK directa en BD)
        2. Llama a get_document_window() con ese segmento como foco
        3. Opcionalmente, si el incidente menciona entidades concretas,
           llama a search_precise_entities() para cada una

        Args:
            incident_id: UUID del ExtractedIncident a expandir.
            context_radius: Número de segmentos antes y después del segmento
                fuente a incluir (default: 3).
            search_entities: Si True, extrae entidades del jot_text y las
                busca en todo el corpus con search_precise_entities().

        Returns:
            dict con:
            {
                "incident": {
                    "incident_id": str,
                    "jot_text": str | null,
                    "tipo_dato_glaser": str | null,
                    "keep_moving": bool,
                    "documento_id": str,
                    "segmento_id": str,
                },
                "source_segment": {
                    "segmento_id": str,
                    "posicion": int,
                    "texto": str,
                },
                "context_before": [...],   # segmentos antes del foco
                "context_after": [...],    # segmentos después del foco
                "entities_found": [...] | null
            }
        """
        incident_uuid = _safe_uuid(incident_id)
        if incident_uuid is None:
            logger.error("expand_incident: incident_id inválido=%s", incident_id)
            return {"error": f"incident_id inválido: {incident_id}"}

        context_radius = max(1, min(context_radius, 20))

        async def _expand():
            from sqlalchemy import select

            from app.models.domain.document import Documento
            from app.models.domain.incident import ExtractedIncident
            from app.models.domain.segment import Segmento

            AsyncSessionLocal = self._get_session_factory()
            async with AsyncSessionLocal() as db:
                # 1. Buscar el incidente → obtener FK a segmento y documento
                inc_stmt = select(
                    ExtractedIncident.id,
                    ExtractedIncident.jot_text,
                    ExtractedIncident.tipo_dato_glaser,
                    ExtractedIncident.keep_moving,
                    ExtractedIncident.segmento_id,
                    ExtractedIncident.documento_id,
                    ExtractedIncident.proyecto_id,
                ).where(ExtractedIncident.id == incident_uuid)

                inc_result = await db.execute(inc_stmt)
                inc_row = inc_result.one_or_none()

                if inc_row is None:
                    return {"error": f"Incidente {incident_uuid} no encontrado"}

                segmento_id = inc_row.segmento_id
                documento_id = inc_row.documento_id
                proyecto_id = inc_row.proyecto_id

                # 2. Buscar el segmento fuente para obtener posición y texto
                seg_stmt = select(Segmento.id, Segmento.posicion, Segmento.texto).where(
                    Segmento.id == segmento_id
                )

                seg_result = await db.execute(seg_stmt)
                seg_row = seg_result.one_or_none()

                if seg_row is None:
                    return {"error": f"Segmento fuente {segmento_id} no encontrado"}

                # 3. Obtener metadata del documento
                doc_stmt = select(Documento.original_filename).where(
                    Documento.id == documento_id
                )
                doc_result = await db.execute(doc_stmt)
                doc_row = doc_result.one_or_none()
                doc_nombre = doc_row.original_filename if doc_row else ""

                incident_data = {
                    "incident_id": str(inc_row.id),
                    "jot_text": inc_row.jot_text,
                    "tipo_dato_glaser": inc_row.tipo_dato_glaser,
                    "keep_moving": inc_row.keep_moving,
                    "documento_id": str(documento_id),
                    "segmento_id": str(segmento_id),
                    "documento_nombre": doc_nombre,
                }

                source_segment = {
                    "segmento_id": str(seg_row.id),
                    "posicion": seg_row.posicion,
                    "texto": seg_row.texto or "",
                }

                # 4. Obtener ventana de contexto (usa get_document_window internamente)
                #    Pero lo hacemos inline aquí para no hacer doble query async
                #    — ya tenemos la session abierta.
                from sqlalchemy import select as _sel

                focus_pos = seg_row.posicion
                seg_start = max(1, focus_pos - context_radius)
                seg_end = focus_pos + context_radius

                ctx_stmt = (
                    _sel(Segmento.id, Segmento.texto, Segmento.posicion)
                    .where(Segmento.documento_id == documento_id)
                    .where(Segmento.posicion >= seg_start)
                    .where(Segmento.posicion <= seg_end)
                    .order_by(Segmento.posicion)
                )
                ctx_result = await db.execute(ctx_stmt)
                ctx_rows = ctx_result.all()

                context_before: list[dict] = []
                context_after: list[dict] = []

                for row in ctx_rows:
                    if row.posicion == focus_pos:
                        continue  # ya está en source_segment
                    entry = {
                        "segmento_id": str(row.id),
                        "posicion": row.posicion,
                        "texto": row.texto or "",
                        "distancia": row.posicion - focus_pos,
                    }
                    if row.posicion < focus_pos:
                        context_before.append(entry)
                    else:
                        context_after.append(entry)

                result = {
                    "incident": incident_data,
                    "source_segment": source_segment,
                    "context_before": context_before,
                    "context_after": context_after,
                    "entities_found": None,
                }

                return result, proyecto_id, inc_row.jot_text

        try:
            expand_result, proyecto_id, jot_text = _run_async(_expand())

            if "error" in expand_result:
                return expand_result

            # 5. Opcional: buscar entidades mencionadas
            if search_entities and jot_text:
                entities = _extract_entities(jot_text)
                if entities:
                    all_entities: list[dict] = []
                    for entity in entities[:5]:  # máximo 5 entidades para no saturar
                        entity_results = self.search_precise_entities(
                            query_text=entity,
                            proyecto_id=proyecto_id,
                            max_results=5,
                        )
                        # Anotar cada resultado con la entidad que lo encontró
                        for r in entity_results:
                            if "error" not in r:
                                r["_entity_searched"] = entity
                        all_entities.extend(entity_results)
                    # Deduplicar por segmento_id
                    seen: set[str] = set()
                    deduped: list[dict] = []
                    for e in all_entities:
                        sid = e.get("segmento_id", "")
                        if sid and sid not in seen:
                            seen.add(sid)
                            deduped.append(e)
                    expand_result["entities_found"] = deduped

            logger.info(
                "expand_incident: incident=%s radius=%d entities=%s → %d before + %d after",
                incident_uuid,
                context_radius,
                search_entities,
                len(expand_result.get("context_before", [])),
                len(expand_result.get("context_after", [])),
            )
            return expand_result

        except Exception as e:
            logger.error("expand_incident failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def estimate_batch_tokens(
        self,
        items: list[dict[str, Any]],
        max_tokens: int | None = None,
        text_keys: list[str] | None = None,
    ) -> dict:
        """Estima cuántos items caben en una ventana de contexto.

        Usa context_config de app.core.context_config para los cálculos.
        No hardcodea valores — todo parametrizado en la configuración.

        Args:
            items: Lista de items (dicts) a estimar.
            max_tokens: Presupuesto máximo de tokens. Si None, usa
                context_config.effective_window.
            text_keys: Keys del dict que contienen texto a contar.
                Si None, se estima sobre el JSON completo del item.

        Returns:
            dict con:
            {
                "fits": bool,
                "total_items": int,
                "total_tokens_estimated": int,
                "avg_tokens_per_item": float,
                "max_tokens": int,
                "batches": int,
                "items_per_batch": int,
                "utilization_pct": float,
                "recommendation": str,
                "needs_fragmentation": bool,
            }
        """
        if not items:
            return {
                "fits": True,
                "total_items": 0,
                "total_tokens_estimated": 0,
                "avg_tokens_per_item": 0.0,
                "max_tokens": max_tokens or context_config.effective_window,
                "batches": 1,
                "items_per_batch": 0,
                "utilization_pct": 0.0,
                "recommendation": "Sin items para estimar.",
                "needs_fragmentation": False,
            }

        # Resolver max_tokens
        effective_max = max_tokens or context_config.effective_window

        # Extraer texto de cada item
        text_items: list[str] = []
        for item in items:
            if text_keys:
                parts = []
                for key in text_keys:
                    val = item.get(key, "")
                    if val:
                        parts.append(str(val))
                text_items.append(" ".join(parts) if parts else "")
            else:
                # Serializar el item completo
                try:
                    text_items.append(json.dumps(item, ensure_ascii=False, default=str))
                except Exception:
                    text_items.append(str(item))

        # Estimar tokens usando context_config
        total_chars = sum(len(t) for t in text_items)
        total_tokens_estimated = context_config.estimate_tokens(
            " " * total_chars
        )  # hack: usamos estimate_tokens que toma str

        # Mejor: cálculo directo
        total_tokens_estimated = int(
            total_chars / context_config.CHARS_PER_TOKEN_ESTIMATE
        )
        avg_tokens_per_item = total_tokens_estimated / len(items)

        # Determinar fragmentación
        needs_fragmentation = context_config.should_fragment(total_tokens_estimated)

        if needs_fragmentation:
            batch_info = context_config.calculate_batches(
                len(items), int(avg_tokens_per_item)
            )
            batches = batch_info["batches"]
            items_per_batch = batch_info["items_per_batch"]
            recommendation = (
                f"NO caben. Se necesitan {batches} batches "
                f"de ~{items_per_batch} items cada uno "
                f"(estimado: {total_tokens_estimated} tokens totales "
                f"vs {effective_max} disponibles)."
            )
        else:
            batches = 1
            items_per_batch = len(items)
            recommendation = (
                f"Caben todos en un solo batch "
                f"({total_tokens_estimated} / {effective_max} tokens, "
                f"{round(total_tokens_estimated / effective_max * 100, 1)}% utilización)."
            )

        utilization_pct = round(total_tokens_estimated / effective_max * 100, 1)

        result = {
            "fits": not needs_fragmentation,
            "total_items": len(items),
            "total_tokens_estimated": total_tokens_estimated,
            "avg_tokens_per_item": round(avg_tokens_per_item, 1),
            "max_tokens": effective_max,
            "batches": batches,
            "items_per_batch": items_per_batch,
            "utilization_pct": utilization_pct,
            "recommendation": recommendation,
            "needs_fragmentation": needs_fragmentation,
        }

        logger.info(
            "estimate_batch_tokens: %d items → %d tokens, fits=%s, batches=%d",
            len(items),
            total_tokens_estimated,
            not needs_fragmentation,
            batches,
        )
        return result

    def batch_map_reduce(
        self,
        items: list[dict[str, Any]],
        map_prompt_template: str,
        proyecto_id: UUID | str | None = None,
        reduce_strategy: str = "merge_json",
        max_tokens_per_batch: int | None = None,
        text_keys: list[str] | None = None,
    ) -> dict:
        """Divide items en batches, aplica map a cada batch, reduce resultados.

        Implementa el patrón Map-Reduce para procesar volúmenes de datos
        que no caben en una sola llamada LLM. El orquestador principal:

        1. Estima tokens con context_config.calculate_batches()
        2. Si no necesita fragmentación → llamada directa (bypass)
        3. Si necesita → MAP (ThreadPoolExecutor, FLASH) → REDUCE (PRO)
        4. Opcionalmente → ReAct (PRO + tools) para refinamiento
        5. Loggea en batch_executions

        Args:
            items: Lista de items (dicts) a procesar.
            map_prompt_template: Template de prompt para el map.
                Debe contener `{items}` como placeholder.
            proyecto_id: UUID del proyecto (para logging en batch_executions).
            reduce_strategy: Estrategia de reducción:
                - "merge_json": Combina diccionarios; listas se concatenan
                  bajo la misma key (default).
                - "union": Unión de conjuntos (items únicos).
                - "vote": Votación mayoritaria para outputs con 'verdict'.
                - "concat": Concatenación simple de resultados.
            max_tokens_per_batch: Tokens máximos por batch. Si None,
                usa context_config.effective_window.
            text_keys: Keys del item que contienen texto para estimar tokens.

        Returns:
            dict con:
            {
                "result": dict,
                "batches_processed": int,
                "items_processed": int,
                "reduce_strategy": str,
                "tokens_per_batch": int,
                "items_per_batch": int,
                "fits_in_one_batch": bool,
                "strategy_used": "direct" | "map_reduce" | "error",
            }
        """
        if not items:
            return {
                "result": {},
                "batches_processed": 0,
                "items_processed": 0,
                "reduce_strategy": reduce_strategy,
                "tokens_per_batch": 0,
                "items_per_batch": 0,
                "fits_in_one_batch": True,
                "strategy_used": "direct",
            }

        proj_uuid = _safe_uuid(proyecto_id)

        # 1. Estimar tokens
        effective_max = max_tokens_per_batch or context_config.effective_window
        estimation = self.estimate_batch_tokens(
            items=items,
            max_tokens=effective_max,
            text_keys=text_keys,
        )

        if "error" in estimation:
            return {"error": estimation["error"], "strategy_used": "error"}

        start_time = time.time()
        batch_execution_id: UUID | None = None

        # 2. Bypass: si todo cabe en un solo batch
        if not estimation["needs_fragmentation"]:
            logger.info(
                "batch_map_reduce: bypass — %d items caben en un solo batch",
                len(items),
            )
            try:
                result = self._execute_single_batch(items, map_prompt_template)
                return {
                    "result": result,
                    "batches_processed": 1,
                    "items_processed": len(items),
                    "reduce_strategy": reduce_strategy,
                    "tokens_per_batch": estimation["total_tokens_estimated"],
                    "items_per_batch": len(items),
                    "fits_in_one_batch": True,
                    "strategy_used": "direct",
                }
            except Exception as e:
                logger.error("batch_map_reduce direct failed: %s", e, exc_info=True)
                return {"error": str(e), "strategy_used": "error"}

        # 3. Fragmentación necesaria → MAP + REDUCE
        batches_count = estimation["batches"]
        items_per_batch = estimation["items_per_batch"]

        # Crear registro en batch_executions
        batch_execution_id = self._log_batch_start(
            proj_uuid,
            len(items),
            batches_count,
            items_per_batch,
            estimation["total_tokens_estimated"],
        )

        # 4. MAP: procesar batches en paralelo con asyncio.gather
        #    (thread-safe: cada batch crea su propio LLMClient,
        #     no se comparten sesiones SQLAlchemy entre workers)
        batch_items_list: list[list[dict]] = []
        for i in range(batches_count):
            start_idx = i * items_per_batch
            end_idx = min(start_idx + items_per_batch, len(items))
            batch = items[start_idx:end_idx]
            if batch:
                batch_items_list.append(batch)

        logger.info(
            "batch_map_reduce: MAP phase — %d batches de ~%d items c/u",
            len(batch_items_list),
            items_per_batch,
        )

        partial_results: list[dict] = []

        try:
            partial_results = _run_async(
                self._execute_batches_async(batch_items_list, map_prompt_template)
            )

            logger.info(
                "batch_map_reduce: MAP completado — %d/%d batches exitosos",
                sum(1 for r in partial_results if "error" not in r),
                len(partial_results),
            )

        except Exception as e:
            logger.error("batch_map_reduce MAP phase failed: %s", e, exc_info=True)
            self._log_batch_end(batch_execution_id, "failed", start_time)
            return {"error": f"MAP phase failed: {e}", "strategy_used": "error"}

        # 5. REDUCE: combinar resultados parciales
        try:
            reduced = self._reduce_results(partial_results, reduce_strategy)
            logger.info(
                "batch_map_reduce: REDUCE completado con estrategia=%s",
                reduce_strategy,
            )
        except Exception as e:
            logger.error("batch_map_reduce REDUCE failed: %s", e, exc_info=True)
            self._log_batch_end(batch_execution_id, "failed", start_time)
            return {"error": f"REDUCE phase failed: {e}", "strategy_used": "error"}

        # Actualizar registro
        self._log_batch_end(batch_execution_id, "completed", start_time)

        return {
            "result": reduced,
            "batches_processed": len(partial_results),
            "items_processed": len(items),
            "reduce_strategy": reduce_strategy,
            "tokens_per_batch": estimation["total_tokens_estimated"] // batches_count,
            "items_per_batch": items_per_batch,
            "fits_in_one_batch": False,
            "strategy_used": "map_reduce",
        }

    # ── Helpers internos ─────────────────────────────────────────

    async def _execute_batches_async(
        self, batches: list[list[dict]], prompt_template: str
    ) -> list[dict]:
        """Ejecuta batches en paralelo usando asyncio.gather.

        Thread-safe: cada batch ejecuta _execute_single_batch (sync)
        vía loop.run_in_executor(), evitando compartir sesiones
        SQLAlchemy entre workers. _execute_single_batch crea su
        propio LLMClient por invocación.

        Args:
            batches: Lista de batches, cada uno es una lista de dicts.
            prompt_template: Template con placeholder {items}.

        Returns:
            Lista de resultados (dict), preservando el orden de batches.
        """
        import asyncio as _asyncio

        async def _process_one(batch: list[dict]) -> dict:
            loop = _asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._execute_single_batch, batch, prompt_template
            )

        return await _asyncio.gather(*[_process_one(b) for b in batches])

    def _execute_single_batch(
        self, batch_items: list[dict], prompt_template: str
    ) -> dict:
        """Ejecuta un solo batch: reemplaza {items} en el template y llama al LLM.

        Este método es el punto de integración con el LLM. En producción,
        usa LLMClient.run_agent(). Si no está disponible, opera en modo
        "passthrough" devolviendo los items sin procesar para que el caller
        (agente IA) los procese.
        """
        # Serializar items como JSON para el placeholder
        try:
            items_json = json.dumps(batch_items, ensure_ascii=False, indent=2)
        except Exception:
            items_json = str(batch_items)

        # Reemplazar placeholder
        prompt = prompt_template.replace("{items}", items_json)

        # Intentar llamar al LLM
        try:
            import sys as _sys

            _sys.path.insert(0, "/app")
            from workers.heavy.llm_client import LLMClient

            llm = LLMClient()

            if llm.is_mock:
                logger.debug("batch_map_reduce: LLM en modo MOCK, passthrough")
                return {"items": batch_items, "note": "mock — sin procesar"}

            # Usar chat() con el prompt como user message
            response = llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Eres un agente de análisis cualitativo. "
                            "Procesa los datos y devuelve JSON válido."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4096,
            )

            content = response.get("content", "")
            if not content:
                return {"items": batch_items, "note": "LLM no devolvió contenido"}

            # Intentar parsear como JSON
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # Intentar extraer JSON de entre markdown code blocks
                json_match = re.search(
                    r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL
                )
                if json_match:
                    try:
                        return json.loads(json_match.group(1))
                    except json.JSONDecodeError:
                        pass
                return {"raw_output": content, "items": batch_items}

        except ImportError:
            logger.debug("batch_map_reduce: LLMClient no disponible, passthrough")
            return {"items": batch_items, "note": "LLMClient no disponible"}
        except Exception as e:
            logger.error("_execute_single_batch LLM call failed: %s", e)
            return {"error": str(e), "items": batch_items}

    def _reduce_results(self, partial_results: list[dict], strategy: str) -> dict:
        """Reduce resultados parciales según la estrategia especificada."""
        if not partial_results:
            return {}

        valid = [r for r in partial_results if "error" not in r]
        if not valid:
            return {"error": "Todos los batches fallaron", "raw": partial_results}

        if strategy == "merge_json":
            return self._reduce_merge_json(valid)
        elif strategy == "union":
            return self._reduce_union(valid)
        elif strategy == "vote":
            return self._reduce_vote(valid)
        elif strategy == "concat":
            return {"results": valid}
        else:
            logger.warning(
                "batch_map_reduce: estrategia desconocida=%s, usando merge_json",
                strategy,
            )
            return self._reduce_merge_json(valid)

    @staticmethod
    def _reduce_merge_json(results: list[dict]) -> dict:
        """Merge JSON: combina diccionarios; listas se concatenan bajo la misma key."""
        merged: dict = {}
        for r in results:
            if not isinstance(r, dict):
                continue
            for key, val in r.items():
                if key not in merged:
                    merged[key] = val
                elif isinstance(merged[key], list) and isinstance(val, list):
                    merged[key].extend(val)
                elif isinstance(merged[key], dict) and isinstance(val, dict):
                    merged[key].update(val)
                else:
                    # Conflicto: crear nueva key con sufijo
                    c = 2
                    new_key = f"{key}_{c}"
                    while new_key in merged:
                        c += 1
                        new_key = f"{key}_{c}"
                    merged[new_key] = val
        return merged

    @staticmethod
    def _reduce_union(results: list[dict]) -> dict:
        """Union: conjuntos de items únicos."""
        all_items: set[str] = set()
        for r in results:
            for key, val in r.items():
                if isinstance(val, list):
                    for item in val:
                        all_items.add(json.dumps(item, sort_keys=True, default=str))
        return {"union": [json.loads(item) for item in sorted(all_items)]}

    @staticmethod
    def _reduce_vote(results: list[dict]) -> dict:
        """Votación mayoritaria para outputs con 'verdict'."""
        verdicts: dict[str, int] = {}
        rationale_votes: dict[str, list[str]] = {}

        for r in results:
            verdict = r.get("verdict", "UNKNOWN")
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            if "rationale" in r:
                rationale_votes.setdefault(verdict, []).append(r["rationale"])

        winner = max(verdicts, key=lambda k: verdicts[k])
        return {
            "verdict": winner,
            "votes": verdicts,
            "total_votes": sum(verdicts.values()),
            "rationales": rationale_votes.get(winner, []),
        }

    def _log_batch_start(
        self,
        proyecto_id: UUID | None,
        total_items: int,
        batches: int,
        items_per_batch: int,
        tokens_per_batch: int,
    ) -> UUID | None:
        """Crea registro en batch_executions al iniciar."""
        if proyecto_id is None:
            return None

        import uuid as _uuid

        batch_id = _uuid.uuid4()

        async def _insert():
            from sqlalchemy import insert

            from app.models.domain.pipeline_run import BatchExecution

            AsyncSessionLocal = self._get_session_factory()
            async with AsyncSessionLocal() as db:
                stmt = insert(BatchExecution).values(
                    id=batch_id,
                    project_id=proyecto_id,
                    agent_id="batch_map_reduce",
                    total_items=total_items,
                    batches=batches,
                    items_per_batch=items_per_batch,
                    tokens_per_batch=tokens_per_batch,
                    map_strategy="map_reduce",
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                await db.execute(stmt)
                await db.commit()

        try:
            _run_async(_insert())
            logger.info("batch_executions: creado registro %s", batch_id)
            return batch_id
        except Exception as e:
            logger.warning("batch_executions: no se pudo crear registro: %s", e)
            return None

    def _log_batch_end(
        self,
        batch_id: UUID | None,
        status: str,
        start_time: float,
    ) -> None:
        """Actualiza registro en batch_executions al finalizar."""
        if batch_id is None:
            return

        elapsed = time.time() - start_time

        async def _update():
            from sqlalchemy import update

            from app.models.domain.pipeline_run import BatchExecution

            AsyncSessionLocal = self._get_session_factory()
            async with AsyncSessionLocal() as db:
                stmt = (
                    update(BatchExecution)
                    .where(BatchExecution.id == batch_id)
                    .values(
                        status=status,
                        finished_at=datetime.now(timezone.utc),
                    )
                )
                await db.execute(stmt)
                await db.commit()

        try:
            _run_async(_update())
            logger.info(
                "batch_executions: actualizado %s → %s (%.1fs)",
                batch_id,
                status,
                elapsed,
            )
        except Exception as e:
            logger.warning("batch_executions: no se pudo actualizar: %s", e)


# ══════════════════════════════════════════════════════════════════
# Tools registradas en ToolRegistry
# ══════════════════════════════════════════════════════════════════
#
# Cada tool es una función independiente decorada con @tool.
# El ToolRegistry las expone al LLM como function calls.
# Internamente, cada tool instancia ContextWindowManager y delega.


@tool(
    name="expand_incident",
    description=(
        "Expande un incidente a su contexto narrativo completo en el documento original. "
        "Dado un incident_id, busca el segmento fuente (FK directa en BD), "
        "obtiene la ventana de contexto alrededor con get_document_window, "
        "y opcionalmente busca entidades mencionadas en el corpus con search_precise_entities. "
        "Útil cuando la IA necesita verificar si dos incidentes realmente miden el mismo "
        "fenómeno viendo el contexto completo en que ocurrieron."
    ),
    parameters={
        "incident_id": "UUID del incidente (ExtractedIncident) a expandir",
        "context_radius": "Número de segmentos antes y después (default: 3)",
        "search_entities": "Si buscar entidades mencionadas en el corpus (default: false)",
    },
)
def expand_incident(
    incident_id: str,
    context_radius: int = 3,
    search_entities: bool = False,
) -> dict:
    """Tool: expande un incidente a su contexto narrativo.

    Wrapper sobre ContextWindowManager.expand_incident().
    """
    manager = ContextWindowManager()
    return manager.expand_incident(
        incident_id=UUID(incident_id),
        context_radius=context_radius,
        search_entities=search_entities,
    )


@tool(
    name="search_precise_entities",
    description=(
        "Busca menciones EXACTAS de entidades concretas en los segmentos del corpus. "
        "Usa PostgreSQL ILIKE — búsqueda precisa, NO semántica (no usa embeddings/RAG). "
        "Ideal para encontrar nombres, lugares, objetos o frases específicas mencionadas "
        "en las entrevistas. "
        "IMPORTANTE: El lenguaje cualitativo no es homogéneo. RAG puede devolver "
        "resultados engañosos. Usa esta tool para búsqueda exacta de entidades."
    ),
    parameters={
        "query_text": "Texto exacto a buscar (ej: 'María', 'hospital', 'despido')",
        "proyecto_id": "UUID del proyecto donde buscar",
        "document_id": "UUID del documento (opcional, para limitar scope)",
        "max_results": "Máximo de resultados (default: 10, max: 50)",
    },
)
def search_precise_entities(
    query_text: str,
    proyecto_id: str,
    document_id: str = "",
    max_results: int = 10,
) -> list:
    """Tool: búsqueda PRECISA (no semántica) de entidades en segmentos.

    Wrapper sobre ContextWindowManager.search_precise_entities().
    """
    manager = ContextWindowManager()
    return manager.search_precise_entities(
        query_text=query_text,
        proyecto_id=UUID(proyecto_id),
        document_id=UUID(document_id) if document_id else None,
        max_results=min(max_results, 50),
    )


@tool(
    name="get_document_window",
    description=(
        "Obtiene una ventana flexible de segmentos de un documento. "
        "Dos modos: "
        "(1) Radio: focus_segment_id + radius → ±N segmentos alrededor del foco. "
        "(2) Rango: start_position + end_position → segmentos en ese rango exacto. "
        "La IA decide cuánto contexto necesita. No hay ventana hardcodeada. "
        "Útil para entender el flujo narrativo de una entrevista o revisar "
        "un rango específico de posiciones."
    ),
    parameters={
        "document_id": "UUID del documento (obligatorio)",
        "focus_segment_id": "UUID del segmento foco — Modo Radio (opcional si se usa Modo Rango)",
        "radius": "Número de segmentos antes y después del foco — Modo Radio (default: 3)",
        "start_position": "Posición inicial — Modo Rango (1-indexed)",
        "end_position": "Posición final — Modo Rango (1-indexed, inclusivo)",
    },
)
def get_document_window(
    document_id: str,
    focus_segment_id: str = "",
    radius: int = 3,
    start_position: int = 0,
    end_position: int = 0,
) -> dict:
    """Tool: obtiene ventana flexible de segmentos de un documento.

    Wrapper sobre ContextWindowManager.get_document_window().
    """
    manager = ContextWindowManager()
    return manager.get_document_window(
        document_id=UUID(document_id),
        focus_segment_id=UUID(focus_segment_id) if focus_segment_id else None,
        radius=radius if focus_segment_id and radius > 0 else None,
        start_position=start_position if start_position > 0 else None,
        end_position=end_position if end_position > 0 else None,
    )


@tool(
    name="estimate_batch_tokens",
    description=(
        "Estima cuántos items caben en una ventana de contexto. "
        "Usa la configuración de contexto del sistema (context_config). "
        "Devuelve si todos los items caben juntos o si es necesario particionar en batches. "
        "Útil ANTES de procesar grandes volúmenes de datos: la IA puede decidir "
        "si necesita usar batch_map_reduce o si todo cabe en una sola llamada."
    ),
    parameters={
        "items_json": "JSON array de items a estimar (string)",
        "max_tokens": "Presupuesto máximo de tokens. Si no se especifica, usa el del sistema.",
        "text_keys": "Keys del item que contienen texto, separadas por coma (opcional)",
    },
)
def estimate_batch_tokens(
    items_json: str = "[]",
    max_tokens: int = 0,
    text_keys: str = "",
) -> dict:
    """Tool: estima presupuesto de tokens para una lista de items.

    Wrapper sobre ContextWindowManager.estimate_batch_tokens().
    """
    items = json.loads(items_json) if isinstance(items_json, str) else items_json
    keys = [k.strip() for k in text_keys.split(",") if k.strip()] if text_keys else None

    manager = ContextWindowManager()
    return manager.estimate_batch_tokens(
        items=items,
        max_tokens=max_tokens if max_tokens > 0 else None,
        text_keys=keys or None,
    )


@tool(
    name="batch_map_reduce",
    description=(
        "Divide items en batches que caben en el contexto, aplica map a cada batch "
        "en paralelo (ThreadPoolExecutor), y reduce los resultados. "
        "La IA recibe el resultado reducido, no los batches crudos. "
        "Flujo: estimate → [bypass | MAP → REDUCE]. "
        "Loggea en batch_executions para trazabilidad. "
        "Ejemplo: agrupar 500 incidentes por similitud semántica."
    ),
    parameters={
        "items_json": "JSON array de items a procesar (string)",
        "map_prompt_template": "Template de prompt por batch. Debe contener {items} como placeholder.",
        "proyecto_id": "UUID del proyecto (para logging)",
        "reduce_strategy": "Estrategia: 'merge_json' | 'union' | 'vote' | 'concat' (default: 'merge_json')",
        "max_tokens_per_batch": "Tokens máximos por batch (default: usa context_config)",
        "text_keys": "Keys del item con texto a contar, separadas por coma (opcional)",
    },
)
def batch_map_reduce(
    items_json: str = "[]",
    map_prompt_template: str = "",
    proyecto_id: str = "",
    reduce_strategy: str = "merge_json",
    max_tokens_per_batch: int = 0,
    text_keys: str = "",
) -> dict:
    """Tool: Map-Reduce sobre batches que caben en contexto.

    Wrapper sobre ContextWindowManager.batch_map_reduce().
    """
    items = json.loads(items_json) if isinstance(items_json, str) else items_json
    keys = [k.strip() for k in text_keys.split(",") if k.strip()] if text_keys else None

    manager = ContextWindowManager()
    return manager.batch_map_reduce(
        items=items,
        map_prompt_template=map_prompt_template,
        proyecto_id=UUID(proyecto_id) if proyecto_id else None,
        reduce_strategy=reduce_strategy,
        max_tokens_per_batch=max_tokens_per_batch if max_tokens_per_batch > 0 else None,
        text_keys=keys or None,
    )
