"""T28 — Seed de 12 códigos teóricos glaserianos built-in.

Se ejecuta al inicializar la BD o al crear un proyecto nuevo.
Los códigos con project_id=NULL son globales (disponibles para todos los proyectos).
"""

from __future__ import annotations

import json
import uuid
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

BUILT_IN_THEORETICAL_CODES: list[dict] = [
    # ── 1. Proceso / Secuencia ──
    {
        "id": "bbbbbbbb-0001-4000-8000-000000000001",
        "name": "Proceso / Secuencia",
        "family": "process",
        "glaserian": True,
        "layer": "process",
        "visualization_hint": "arrow_diagram",
        "description": "Evalúa si dos o más categorías forman una secuencia temporal o lógica (A → B → C).",
        "evaluation_logic": {
            "what_it_tests": "Precedencia temporal o lógica entre categorías dentro del mismo documento.",
            "how_it_tests": [
                "1. Identificar documentos que contienen incidentes de AMBAS categorías.",
                "2. Para cada documento, verificar el orden de aparición de los incidentes.",
                "3. Contar en cuántos documentos A aparece antes que B y viceversa.",
                "4. Buscar marcadores lingüísticos de secuencia.",
                "5. Evaluar si hay un mecanismo que explique la transición.",
            ],
            "evidence_thresholds": {
                "supported": "≥ 3 docs muestran la secuencia y ≤ 1 muestra secuencia inversa",
                "weak": "2 docs muestran la secuencia, o hay empate",
                "contradicted": "≥ 2 docs muestran secuencia inversa",
            },
            "what_it_cannot_test": [
                "No evalúa causalidad (usar Causal/Seis C's).",
                "No evalúa si las categorías son variantes de lo mismo (usar Oposición).",
            ],
        },
        "compatible_with": [
            "bbbbbbbb-0002-4000-8000-000000000002",
            "bbbbbbbb-0004-4000-8000-000000000004",
        ],
    },
    # ── 2. Causal / Seis C's ──
    {
        "id": "bbbbbbbb-0002-4000-8000-000000000002",
        "name": "Causal / Seis C's",
        "family": "causal",
        "glaserian": True,
        "layer": "conditions",
        "visualization_hint": "tendril",
        "description": "Identifica causas, efectos, condiciones mediadoras y variables intervinientes.",
        "evaluation_logic": {
            "what_it_tests": "Relaciones causales: ¿A produce B? ¿Bajo qué condiciones?",
            "how_it_tests": [
                "1. Identificar las Seis C: Causes, Conditions, Contingencies, Consequences, Covariances, Context.",
                "2. Para cada par, verificar precedencia temporal + mecanismo.",
                "3. Distinguir condiciones estructurales (siempre presentes) de contingentes (varían).",
            ],
            "evidence_thresholds": {
                "supported": "≥ 3 docs con precedencia A→B + mecanismo identificable",
                "weak": "2 docs o mecanismo no claro",
            },
            "what_it_cannot_test": [
                "No establece causalidad estadística.",
                "No prueba hipótesis nula.",
            ],
        },
        "compatible_with": [
            "bbbbbbbb-0001-4000-8000-000000000001",
            "bbbbbbbb-0009-4000-8000-000000000009",
        ],
    },
    # ── 3. Oposición / Gradiente ──
    {
        "id": "bbbbbbbb-0003-4000-8000-000000000003",
        "name": "Oposición / Gradiente",
        "family": "opposition",
        "glaserian": True,
        "layer": "variation",
        "visualization_hint": "matrix",
        "description": "Agrupa por polos opuestos o perfiles contrastantes de una misma dimensión.",
        "evaluation_logic": {
            "what_it_tests": "Si dos categorías forman polos opuestos de una misma dimensión subyacente.",
            "how_it_tests": [
                "1. Identificar la DIMENSIÓN que las enfrenta.",
                "2. Verificar que los incidentes de cada categoría se ubican en extremos opuestos.",
                "3. Verificar si hay casos intermedios (zona gris).",
            ],
        },
        "compatible_with": ["bbbbbbbb-0004-4000-8000-000000000004"],
    },
    # ── 4. Tipología ──
    {
        "id": "bbbbbbbb-0004-4000-8000-000000000004",
        "name": "Tipología",
        "family": "typology",
        "glaserian": True,
        "layer": "variation",
        "visualization_hint": "cluster",
        "description": "Identifica TIPOS o PERFILES mutuamente excluyentes que emergen de los datos.",
        "evaluation_logic": {
            "what_it_tests": "Si los incidentes se agrupan en configuraciones coherentes y mutuamente excluyentes.",
            "how_it_tests": [
                "1. Identificar propiedades distintivas de cada tipo.",
                "2. Verificar consistencia interna: los incidentes de un mismo tipo comparten propiedades.",
                "3. Verificar distinción externa: los tipos no se solapan.",
            ],
        },
        "compatible_with": [
            "bbbbbbbb-0003-4000-8000-000000000003",
            "bbbbbbbb-0006-4000-8000-000000000006",
        ],
    },
    # ── 5. Jerarquía / Centralidad ──
    {
        "id": "bbbbbbbb-0005-4000-8000-000000000005",
        "name": "Jerarquía / Centralidad",
        "family": "hierarchy",
        "glaserian": True,
        "layer": "structure",
        "visualization_hint": "tendril",
        "description": "Clasifica categorías como centrales, periféricas, condiciones o consecuencias.",
        "evaluation_logic": {
            "what_it_tests": "Qué categorías son más centrales que otras respecto al core concern.",
            "how_it_tests": [
                "1. Evaluar cuántas conexiones tiene cada categoría.",
                "2. Evaluar cuántos incidentes respaldan cada categoría.",
                "3. Evaluar cercanía semántica al core concern.",
            ],
        },
    },
    # ── 6. Matriz 2×2 ──
    {
        "id": "bbbbbbbb-0006-4000-8000-000000000006",
        "name": "Matriz 2×2",
        "family": "matrix",
        "glaserian": True,
        "layer": "structure",
        "visualization_hint": "matrix",
        "description": "Cruza dos dimensiones para producir 4 cuadrantes que organizan los datos.",
        "evaluation_logic": {
            "what_it_tests": "Si dos propiedades, al cruzarse, producen 4 cuadrantes significativos.",
            "how_it_tests": [
                "1. Identificar las DOS dimensiones más relevantes.",
                "2. Asignar categorías a cada cuadrante.",
                "3. Verificar que cada cuadrante tiene al menos un caso.",
            ],
        },
        "compatible_with": ["bbbbbbbb-0004-4000-8000-000000000004"],
    },
    # ── 7. Consecuencias ──
    {
        "id": "bbbbbbbb-0007-4000-8000-000000000007",
        "name": "Consecuencias",
        "family": "consequences",
        "glaserian": True,
        "layer": "consequences",
        "visualization_hint": "tendril",
        "description": "Evalúa qué produce actuar sobre una categoría. Efectos posteriores.",
        "evaluation_logic": {
            "what_it_tests": "Si una categoría produce efectos observables en los participantes.",
            "how_it_tests": [
                "1. Identificar incidentes que ocurren DESPUÉS de la categoría.",
                "2. Verificar si los participantes vinculan explícitamente causa y efecto.",
                "3. Distinguir consecuencias inmediatas de mediatas.",
            ],
        },
    },
    # ── 8. Estrategias ──
    {
        "id": "bbbbbbbb-0008-4000-8000-000000000008",
        "name": "Estrategias",
        "family": "strategies",
        "glaserian": True,
        "layer": "action",
        "visualization_hint": "tendril",
        "description": "Identifica qué estrategias comparten los participantes para resolver el core concern.",
        "evaluation_logic": {
            "what_it_tests": "Si los participantes usan patrones de acción similares.",
            "how_it_tests": [
                "1. Agrupar acciones concretas descritas por los participantes.",
                "2. Identificar condiciones bajo las cuales se elige cada estrategia.",
                "3. Verificar si hay estrategias opuestas para el mismo problema.",
            ],
        },
    },
    # ── 9. Condición estructural ──
    {
        "id": "bbbbbbbb-0009-4000-8000-000000000009",
        "name": "Condición estructural",
        "family": "structural_condition",
        "glaserian": True,
        "layer": "conditions",
        "visualization_hint": "tendril",
        "description": "Identifica condiciones del contexto que son estables y moldean el fenómeno.",
        "evaluation_logic": {
            "what_it_tests": "Si hay condiciones estables del entorno que afectan cómo se manifiesta la categoría.",
            "how_it_tests": [
                "1. Identificar factores contextuales que aparecen consistentemente.",
                "2. Distinguir de contingencias: las estructurales no varían entre casos.",
            ],
        },
        "compatible_with": ["bbbbbbbb-0010-4000-8000-000000000010"],
    },
    # ── 10. Contingencia ──
    {
        "id": "bbbbbbbb-0010-4000-8000-000000000010",
        "name": "Contingencia",
        "family": "contingency",
        "glaserian": True,
        "layer": "conditions",
        "visualization_hint": "tendril",
        "description": "Identifica condiciones variables que modifican el fenómeno entre casos.",
        "evaluation_logic": {
            "what_it_tests": "Si hay condiciones que varían entre casos y modifican la categoría.",
            "how_it_tests": [
                "1. Identificar factores que cambian entre documentos.",
                "2. Verificar si el cambio en el factor coincide con cambio en la categoría.",
            ],
        },
        "compatible_with": ["bbbbbbbb-0009-4000-8000-000000000009"],
    },
    # ── 11. Covarianza ──
    {
        "id": "bbbbbbbb-0011-4000-8000-000000000011",
        "name": "Covarianza",
        "family": "covariance",
        "glaserian": True,
        "layer": "variation",
        "visualization_hint": "tendril",
        "description": "Identifica qué categorías varían juntas sistemáticamente.",
        "evaluation_logic": {
            "what_it_tests": "Si dos categorías covarían: cuando una cambia, la otra también.",
            "how_it_tests": [
                "1. Identificar pares de categorías que aparecen y desaparecen juntas.",
                "2. Verificar si la relación es directa o inversa.",
            ],
        },
    },
    # ── 12. Intercambiabilidad ──
    {
        "id": "bbbbbbbb-0012-4000-8000-000000000012",
        "name": "Intercambiabilidad / Fusión",
        "family": "interchangeability",
        "glaserian": True,
        "layer": "fusion",
        "visualization_hint": "tendril",
        "description": "Evalúa si dos categorías son en realidad la misma (indicadores intercambiables).",
        "evaluation_logic": {
            "what_it_tests": "Si los incidentes de dos categorías son intercambiables (mismo patrón subyacente).",
            "how_it_tests": [
                "1. Comparar incidentes de ambas categorías.",
                "2. Si los incidentes podrían asignarse indistintamente a cualquiera → intercambiables.",
                "3. Si cada categoría tiene incidentes que no encajan en la otra → distintas.",
            ],
            "evidence_thresholds": {
                "supported": "> 80% de incidentes intercambiables",
                "weak": "50-80% intercambiables",
            },
        },
    },
]


def seed_theoretical_codes(session: Session) -> int:
    """Inserta los 12 códigos built-in si no existen. Retorna cantidad insertada."""
    existing = session.execute(
        text("SELECT COUNT(*) FROM theoretical_codes WHERE project_id IS NULL")
    ).fetchone()[0]

    if existing >= 12:
        return 0

    inserted = 0
    for code in BUILT_IN_THEORETICAL_CODES:
        row = session.execute(
            text("SELECT id FROM theoretical_codes WHERE id = :id"),
            {"id": code["id"]},
        ).fetchone()
        if row:
            continue

        session.execute(
            text(
                """INSERT INTO theoretical_codes
                (id, project_id, name, family, description, glaserian, user_defined,
                 evaluation_logic, output_schema, compatible_with, layer, visualization_hint)
                VALUES (:id, NULL, :name, :family, :desc, true, false,
                        :logic, :schema, :compat, :layer, :viz)"""
            ),
            {
                "id": code["id"],
                "name": code["name"],
                "family": code["family"],
                "desc": code["description"],
                "logic": json.dumps(code.get("evaluation_logic", {})),
                "schema": json.dumps(code.get("output_schema", {})),
                "compat": json.dumps(code.get("compatible_with", [])),
                "layer": code.get("layer", "undefined"),
                "viz": code.get("visualization_hint", "tendril"),
            },
        )
        inserted += 1

    session.commit()
    return inserted
