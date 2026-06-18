# REDISEÑO ARQUITECTÓNICO — Every-3-Doc Pause y Procesos Interconectados
# ============================================================================
# 
# Principios:
# 1. Cada 3 docs → pausa unificada con 4 pasos
# 2. Categorías vinculadas a población + concern
# 3. Core category se elige al FINAL, informada por hipótesis
# 4. Población puede tener múltiples concerns; usuario elige UNO al final
# 5. Coding style es recomendación del sistema, no imposición
# 6. Sin decisión del usuario cada 3 docs, no se avanza
# ============================================================================

# ═══════════════════════════════════════════════════════════════════════════
# CAMBIOS DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════════════════════

# TABLA NUEVA: concerns
# ─────────────────────
# id: UUID
# project_id: FK → proyectos
# label: TEXT           — gerundio del concern (ej: "Maintaining professional relevance")
# description: TEXT     — explicación
# status: TEXT          — candidate | confirmed | rejected
# identified_at_batch: INT — en qué batch (3, 6, 9...) se identificó
# created_at, updated_at

# COLUMNAS NUEVAS en categorias:
# ─────────────────────────────
# concern_label: TEXT   — a qué concern se vincula esta categoría
# population_label: TEXT — a qué variante poblacional

# COLUMNA NUEVA en hypotheses:
# ────────────────────────────
# concern_labels: JSONB  — array de concerns que esta hipótesis conecta
# batch_number: INT      — en qué batch se generó/actualizó

# ═══════════════════════════════════════════════════════════════════════════
# FLUJO EVERY-3-DOCS (corre después de Phase A para el batch actual)
# ═══════════════════════════════════════════════════════════════════════════

def every_3_doc_pause(proyecto_id, batch_start_doc_index):
    """
    Disparado cuando docs 1-3, 4-6, 7-9... están 'listo'.
    Para último batch con 1-2 docs, también corre.
    """

    # ── PASO 1: Category Synthesizer ──
    categories = synthesize_categories_v2(
        proyecto_id,
        batch_start=batch_start_doc_index,
        # Input: todas las categorías (previas + nuevas del batch)
        # Las nuevas NO vieron las viejas durante B1/B2
        # El sintetizador mergea, deduplica, renombra
    )
    # Output: unified_categories[] — set final de categorías

    # ── PASO 2: Hypothesis Synthesizer ──
    hypotheses = synthesize_hypotheses(
        proyecto_id,
        categories=categories,          # output del paso 1
        previous_hypotheses=load_previous_hypotheses(proyecto_id),
        # Las hipótesis conectan categorías entre sí
        # Crecen con cada batch: se refinan, no se reemplazan
    )
    # Output: updated_hypotheses[] — nota creciente con referencias precisas

    # ── PASO 3: Configuration Critic ──
    config_review = critique_configuration(
        proyecto_id,
        categories=categories,           # output del paso 1
        hypotheses=hypotheses,           # output del paso 2
        baseline_segments=load_baseline_segments_for_batch(proyecto_id, batch_start),
        current_population=load_population_assumption(proyecto_id),
        current_concern=load_current_concern(proyecto_id),
        current_coding_style=load_coding_style(proyecto_id),
    )
    # Output:
    #   concerns[] — posibles concerns subyacentes (gerundios)
    #     Ej: ["Sobreviviendo la burocracia", "Manteniendo autoridad en el aula", ...]
    #   population_variants[] — posibles reconfiguraciones poblacionales
    #     Ej: ["docentes veteranos (>10 años)", "docentes nuevos (<5 años)", ...]
    #   coding_style_recommendation — sugerencia o null
    #   rationale — explicación de cada recomendación

    # ── PASO 4: HITL Overlay ──
    hitl_overlay(
        proyecto_id,
        gate="batch_review",
        data={
            "batch_number": batch_start // 3 + 1,
            "categories": categories,       # nuevo set unificado
            "hypotheses": hypotheses,       # hipótesis actualizadas
            "concerns": config_review.concerns,         # opciones de concern
            "population_variants": config_review.population_variants,  # opciones de población
            "coding_style": config_review.coding_style_recommendation,
        },
        choices={
            "categories": "multi",       # puede elegir varias, una, o todas
            "concerns": "multi",         # puede elegir varias (hasta el final)
            "population": "multi",       # puede elegir varias
            "coding_style": "single",    # una o ninguna
        },
    )
    # BLOQUEANTE: no avanza hasta que el usuario decida

    # ── CASCADA post-decisión ──
    on_user_decision(decision):
        if decision.categories:
            persist_categories(decision.categories)
        if decision.concerns:
            persist_concerns(decision.concerns)
            # Actualiza categories.concern_label según elección
        if decision.population:
            update_population_assumption(decision.population)
        if decision.coding_style:
            update_coding_style(decision.coding_style)


# ═══════════════════════════════════════════════════════════════════════════
# FLUJO COMPLETO (por batch)
# ═══════════════════════════════════════════════════════════════════════════

def process_batch(proyecto_id, doc_ids):
    """
    Para cada batch de documentos:
    1. Phase A (open coding) por documento → clasificación + incidentes + patrones
    2. Phase B (cross-document) → agrupar incidentes → etiquetar → criticar
    3. Every-3-doc Pause → sintetizar + hipótesis + revisar config → HITL
    """

    # ── PHASE A: Open Coding (por documento, en secuencia) ──
    for doc_id in doc_ids:
        process_document_agents_a(doc_id, proyecto_id)
        # Produce: segmentos clasificados, incidentes, document_signals

    # ── PHASE B: Cross-Document Synthesis ──
    process_synthesis_agents_b(proyecto_id)
    # Produce: incident_groups, categorias (labels con gerundios)
    # NOTA: B1/B2 no ven categorías previas ni concerns previos
    #       Solo ven los incidentes del batch actual

    # ── EVERY-3-DOC PAUSE ──
    every_3_doc_pause(proyecto_id, batch_start_doc_index)
    # BLOQUEANTE hasta decisión del usuario


# ═══════════════════════════════════════════════════════════════════════════
# SELECCIÓN DE CORE CATEGORY (después de TODOS los batches)
# ═══════════════════════════════════════════════════════════════════════════

def select_core_category(proyecto_id):
    """
    Solo corre cuando:
    1. Todos los documentos están procesados
    2. Todos los batches tienen su every-3-doc pause resuelta
    3. El usuario ha elegido UN concern y UNA población

    El sistema recomienda categorías core basado en las hipótesis acumuladas.
    """

    # Guardrail 1: ¿Hay UN solo concern confirmado?
    confirmed_concerns = get_confirmed_concerns(proyecto_id)
    if len(confirmed_concerns) != 1:
        raise "Debe elegir exactamente UN concern antes de seleccionar core category"

    # Guardrail 2: ¿Todas las categorías tienen concern_label?
    unlinked = get_categories_without_concern(proyecto_id)
    if unlinked:
        raise f"Hay {len(unlinked)} categorías sin concern asignado"

    # Proposer: recomienda core categories basado en hipótesis
    core_candidates = propose_core_categories(
        proyecto_id,
        concern=confirmed_concerns[0],
        categories=get_all_categories(proyecto_id),
        hypotheses=get_all_hypotheses(proyecto_id),
        # Las hipótesis contienen relaciones entre categorías
        # → categorías más conectadas = candidatas a core
    )

    # Critic: evalúa intercambiabilidad de incidentes
    critic_result = critique_core_candidates(
        proyecto_id,
        candidates=core_candidates,
    )

    # HITL final: usuario elige UNA core category
    hitl_overlay(
        proyecto_id,
        gate="core_category_selection",
        data={
            "candidates": core_candidates,
            "critic_verdicts": critic_result,
            "hypothesis_evidence": relevant_hypotheses,
        },
        choices={"core_category": "single"},  # SOLO UNA
    )
