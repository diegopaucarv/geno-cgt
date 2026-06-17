# backend/app/core/theoretical_families.py
"""
F1.3 — 12 Familias de Códigos Teóricos Glaserianos como módulo independiente.

Fuente única de verdad para los 12 códigos teóricos built-in.
Extraído de `backend/app/services/theory_seeder.py`.

Uso:
    from app.core.theoretical_families import THEORETICAL_FAMILIES, get_family, get_families_by_layer
"""

from __future__ import annotations

from typing import Any

# ═══════════════════════════════════════════════════════════════════════
# 12 familias de códigos teóricos glaserianos
# ═══════════════════════════════════════════════════════════════════════

THEORETICAL_FAMILIES: list[dict[str, Any]] = [
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


def get_family(family_key: str) -> dict[str, Any] | None:
    """Obtiene una familia por su key (ej. 'process', 'causal')."""
    for f in THEORETICAL_FAMILIES:
        if f["family"] == family_key:
            return f
    return None


def get_families_by_layer(layer: str) -> list[dict[str, Any]]:
    """Filtra familias por capa (ej. 'conditions', 'variation', 'structure')."""
    return [f for f in THEORETICAL_FAMILIES if f.get("layer") == layer]
