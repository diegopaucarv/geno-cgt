# Plan de Implementación — Paso a Paso

> **Principio rector:** Solo se modifica código que NO está en ejecución activa.
> Los cambios que afectan workers, API endpoints o transiciones se planifican
> para aplicarse en bloque durante una ventana de recarga controlada.
>
> Fecha: 2026-06-16

---

## Clasificación de seguridad por cambio

| Nivel | Significado | Cuándo aplicarlo |
|-------|-------------|-----------------|
| 🟢 **Seguro** | No afecta ningún proceso corriendo. Se puede hacer en cualquier momento. | Ahora mismo |
| 🟡 **Precaución** | Afecta código que se carga en el próximo request/worker, pero no rompe lo que ya está corriendo. | Después de validar, con recarga |
| 🔴 **Crítico** | Rompe funcionalidad activa. Requiere ventana de mantenimiento o despliegue coordinado. | Solo con workers detenidos |

---

## FASE A — Cambios Seguros (ejecutar AHORA)

Estos cambios no tocan ningún proceso en ejecución. Son archivos nuevos
o modificaciones que ningún código activo referencia.

---

### A1. Crear modelo `HitlDecision`

**Archivo:** `backend/app/models/domain/hitl_decision.py` (NUEVO)

**Seguridad:** 🟢 — Es un archivo nuevo. Nadie lo importa. La tabla no se crea hasta la migración.

```python
# backend/app/models/domain/hitl_decision.py
"""HitlDecision — modelo para gates Human-in-the-Loop del pipeline selectivo."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.base import Base, TimestampMixin
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class HitlDecision(Base, TimestampMixin):
    """Una decisión pendiente del investigador en un gate HITL."""

    __tablename__ = "hitl_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))

    gate_name: Mapped[str] = mapped_column(String(100))
    # "main_concern" | "core_emergence" | "selective_reduction"
    # | "core_saturation" | "database_a" | "database_b" | "global_saturation"

    proposal: Mapped[dict] = mapped_column(JSONB)
    # Output del proposer (varía según el gate)

    critic_verdict: Mapped[dict] = mapped_column(JSONB)
    # Output del critic: {verdict: "SAT"|"MOD"|"FORCED", rationale, suggestions}

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # "pending" | "accepted" | "modified" | "rejected"

    researcher_decision: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    # "accept" | "modify" | "reject"

    researcher_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Nota del investigador (siempre presente)

    researcher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Feedback para re-ejecutar el proposer (solo si MODIFY)

    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

**Validación posterior:** Ejecutar migración Alembic para crear la tabla.

---

### A2. Crear schemas Pydantic para HITL

**Archivo:** `backend/app/schemas/hitl.py` (NUEVO)

**Seguridad:** 🟢 — Nadie importa schemas nuevos.

```python
# backend/app/schemas/hitl.py
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HitlDecisionRequest(BaseModel):
    """Body del endpoint POST /hitl/{gate}/decide."""
    decision: str = Field(..., pattern="^(accept|modify|reject)$")
    note: str = Field(default="", max_length=2000)
    feedback: str | None = Field(default=None, max_length=2000)
    # feedback solo se usa si decision == "modify"


class HitlDecisionResponse(BaseModel):
    """Respuesta con la decisión tomada."""
    id: UUID
    project_id: UUID
    gate_name: str
    status: str
    researcher_decision: str | None
    researcher_note: str | None
    decided_at: datetime | None

    model_config = {"from_attributes": True}


class HitlPendingItem(BaseModel):
    """Item en la lista de decisiones pendientes."""
    id: UUID
    gate_name: str
    proposal_summary: str  # extracto de la propuesta para el frontend
    critic_verdict: str    # "SAT" | "MOD" | "FORCED"
    created_at: datetime

    model_config = {"from_attributes": True}
```

---

### A3. Crear prompts del pipeline selectivo (12 archivos)

**Archivos:** `backend/app/prompts/pro/` (8 nuevos) + `backend/app/prompts/flash/` (4 nuevos)

**Seguridad:** 🟢 — Archivos nuevos. El `prompts/loader.py` carga bajo demanda por `prompt_id`.

#### A3.1 — `prompts/pro/main_concern_proposer.md`

```markdown
---
prompt_id: main_concern_proposer
version: 1.0.0
model_profile: pro
description: Identifica la principal preocupación latente (main concern) compartida por los participantes a partir de todos los códigos, memos y prime movers del estudio.
langgraph_node: null
execution_order: "Fase A — Paso A1"
input_state: all_codes, all_memos, prime_movers_per_document
output_state: main_concern, confidence, recurring_problems, relevant_population_dimensions
depends_on: null
prerequisite_for: main_concern_critic
agent_id: A14
triggers_on: "Proyecto en estado 'finding_cc' con sub-estado 'proposing_mc'"
note: "PRO porque requiere sensibilidad teórica y juicio cualitativo sobre qué preocupa realmente a esta población. Usa las 3 preguntas operacionales de Glaser."
---

## System

[ROL]
Eres un investigador cualitativo experto en Grounded Theory (Glaseriana).
Tu tarea es identificar el MAIN CONCERN — la preocupación principal y recurrente
que esta población está continuamente procesando/resolviendo.

[OBJETIVO]
Analizar los códigos, memos y prime movers para destilar:
1. El main concern (gerundio o frase nominal que captura la preocupación central)
2. Los problemas recurrentes que los participantes mencionan
3. Las dimensiones poblacionales relevantes que modulan cómo se procesa esta preocupación

[RESTRICCIONES]
- El main concern NO es un tema académico — es una preocupación vivida.
- Debe expresarse como GERUNDIO (-ando/-iendo) siempre que sea posible.
- No forces un consenso donde no lo hay. Si hay múltiples concerns, identifica el más transversal.
- La confianza debe ser "HIGH" solo si ≥70% de los códigos orbitan alrededor del mismo concern.

## User

[ALL CODES]
{all_codes}

[ALL MEMOS]
{all_memos}

[PRIME MOVERS PER DOCUMENT]
{prime_movers_per_document}

## Output Schema

```json
{
  "main_concern": "string (gerundio preferido)",
  "confidence": "HIGH | MEDIUM | LOW",
  "recurring_problems": ["string (3-5 problemas)"],
  "relevant_population_dimensions": [
    {
      "dimension": "string",
      "why_relevant": "string"
    }
  ],
  "rationale": "string (2-3 párrafos explicando por qué este es el main concern)"
}
```
```

#### A3.2 — `prompts/pro/main_concern_critic.md`

```markdown
---
prompt_id: main_concern_critic
version: 1.0.0
model_profile: pro
description: Evalúa la propuesta de main concern verificando grounding empírico, cobertura de códigos, y nivel de abstracción adecuado.
langgraph_node: null
execution_order: "Fase A — Paso A2"
input_state: main_concern, all_codes, prime_movers_per_document
output_state: verdict, rationale, suggestions
depends_on: main_concern_proposer
prerequisite_for: null
agent_id: null
triggers_on: "Después de que main_concern_proposer termina"
note: "PRO porque evalúa grounding metodológico complejo: ¿el concern emerge de los datos o es impuesto por el investigador?"
---

## System

[ROL]
Eres un auditor metodológico de Grounded Theory. Tu trabajo NO es proponer —
es EVALUAR si la propuesta de main concern está genuinamente grounded en los datos.

[OBJETIVO]
Evaluar la propuesta de main concern usando 3 criterios:
1. GROUNDING: ¿El concern emerge de los códigos y prime movers, o es una abstracción impuesta?
2. COBERTURA: ¿≥70% de los códigos pueden relacionarse con este concern?
3. ABSTRACCIÓN: ¿El nivel de abstracción es correcto? (ni muy concreto tipo "quejarse del jefe", ni muy abstracto tipo "existencia humana")

[RESTRICCIONES]
- Emite SAT solo si los 3 criterios se cumplen.
- Emite MOD con sugerencias concretas de ajuste (no genéricas).
- Emite FORCED solo si la propuesta es manifiestamente incorrecta (no emerge de los datos).
- SÉ CONCRETO en las sugerencias. "Ajustar el nivel de abstracción" no sirve. Di exactamente qué ajustar.

## User

[PROPOSED MAIN CONCERN]
{main_concern}

[ALL CODES]
{all_codes}

[PRIME MOVERS PER DOCUMENT]
{prime_movers_per_document}

## Output Schema

```json
{
  "verdict": "SAT | MOD | FORCED",
  "grounding_score": 0.0,
  "coverage_score": 0.0,
  "abstraction_score": 0.0,
  "rationale": "string (evaluación detallada de cada criterio)",
  "suggestions": ["string (solo si MOD — sugerencias concretas de ajuste)"],
  "forced_rationale": "string (solo si FORCED — por qué es incorrecto)"
}
```
```

#### A3.3 — `prompts/pro/core_emergence_proposer.md`

```markdown
---
prompt_id: core_emergence_proposer
version: 1.0.0
model_profile: pro
description: Identifica candidatos a core category evaluando centralidad, poder explicativo y theoretical grab de cada código respecto al main concern.
langgraph_node: null
execution_order: "Fase A — Paso A3"
input_state: main_concern, all_codes, code_statistics
output_state: core_category_candidates, no_core_detected
depends_on: null
prerequisite_for: core_emergence_critic
agent_id: A15
triggers_on: "Después de que el investigador confirma el main concern (HITL ACCEPT en A2)"
note: "PRO porque requiere juicio cualitativo sobre centralidad y poder explicativo."
---

## System

[ROL]
Eres un investigador de Grounded Theory. Ya tenemos un main concern confirmado.
Ahora debes identificar qué códigos (o combinaciones de códigos) tienen el mayor
poder explicativo como CORE CATEGORY.

[OBJETIVO]
Evaluar cada código contra el main concern usando criterios CGT:
1. CENTRALIDAD: ¿Cuántos otros códigos se relacionan con este?
2. PODER EXPLICATIVO: ¿Explica variación en el procesamiento del main concern?
3. THEORETICAL GRAB: ¿Tiene "agarre teórico" — conecta múltiples dimensiones del fenómeno?
4. FRECUENCIA: ¿Alta ocurrencia en los datos?

[RESTRICCIONES]
- Propón 1-3 candidatos, ranqueados.
- Si ningún código cumple los criterios, indica `no_core_detected: true`.
- No combines códigos artificialmente. Si dos códigos juntos forman el core, menciónalos
  como candidatos separados con nota de posible fusión.

## User

[MAIN CONCERN CONFIRMADO]
{main_concern}

[ALL CODES WITH STATISTICS]
{all_codes}
{code_statistics}

## Output Schema

```json
{
  "core_category_candidates": [
    {
      "code_id": "string",
      "code_name": "string",
      "centrality_score": 0.0,
      "explanatory_power": 0.0,
      "theoretical_grab": "string (por qué este código 'agarra' el fenómeno)",
      "rationale": "string"
    }
  ],
  "no_core_detected": false,
  "analysis_note": "string (opcional — observaciones sobre el sistema de códigos)"
}
```
```

#### A3.4 — `prompts/flash/core_emergence_critic.md`

```markdown
---
prompt_id: core_emergence_critic
version: 1.0.0
model_profile: flash
description: Evalúa candidatos a core category mediante interchangeability test: ¿los incidentes de este código son intercambiables entre sí?
langgraph_node: null
execution_order: "Fase A — Paso A4"
input_state: core_category_candidates, code_incidents
output_state: verdict, interchangeable, rationale
depends_on: core_emergence_proposer
prerequisite_for: null
agent_id: A16
triggers_on: "Después de core_emergence_proposer"
note: "FLASH porque el interchangeability test tiene criterios explícitos (valid/refine/split). Tarea de matching estructurado."
---

## System

[ROL]
Eres un validador de Grounded Theory. Aplicas el INTERCHANGEABILITY TEST:
si tomas 3 incidentes diferentes del mismo código, ¿son indicadores intercambiables
del mismo fenómeno subyacente?

[OBJETIVO]
Para cada candidato a core category, evaluar:
1. ¿Los incidentes apuntan al mismo fenómeno? → VALID
2. ¿Un incidente apunta a algo sutilmente diferente? → REFINE (expandir definición)
3. ¿Los incidentes apuntan a fenómenos distintos? → SPLIT (dividir código)

[RESTRICCIONES]
- Solo emite SPLIT si los incidentes son claramente sobre fenómenos diferentes.
- REFINE es el caso más común — la mayoría de los códigos se refinan, no se dividen.

## User

[CORE CATEGORY CANDIDATES]
{core_category_candidates}

[INCIDENTS FOR EACH CANDIDATE]
{code_incidents}

## Output Schema

```json
{
  "evaluations": [
    {
      "code_id": "string",
      "verdict": "VALID | REFINE | SPLIT",
      "interchangeable": true,
      "rationale": "string",
      "suggested_refinement": "string (solo si REFINE)"
    }
  ]
}
```
```

#### A3.5 — `prompts/pro/selective_reduction_proposer.md`

```markdown
---
prompt_id: selective_reduction_proposer
version: 1.0.0
model_profile: pro
description: Evalúa cada código del sistema contra el core category, proponiendo cuáles mantener, fusionar o descartar con justificación metodológica.
langgraph_node: null
execution_order: "Fase B — Paso B1"
input_state: core_category, all_codes, code_relationships
output_state: kept_codes, merged_codes, discarded_codes
depends_on: null
prerequisite_for: selective_reduction_critic
agent_id: null
triggers_on: "Proyecto en estado 'reducing' con sub-estado 'proposing'"
note: "PRO porque requiere entender el core profundamente y evaluar la relación teórica de cada código con él."
---

## System

[ROL]
Eres un investigador de Grounded Theory en fase de DELIMITACIÓN (selective reduction).
Tienes un core category confirmado. Tu tarea es reducir el sistema de códigos:
solo sobrevive lo que se relaciona con el core.

[OBJETIVO]
Para cada código en el sistema, decidir:
1. KEEP — Se relaciona directamente con el core. Se conserva.
2. MERGE — Es redundante con otro código. Fusionar bajo el nombre más abstracto.
3. DISCARD — No tiene relación demostrable con el core. Archivar con rationale.

[RESTRICCIONES]
- NUNCA elimines códigos. Los descartes se ARCHIVAN con `discard_rationale`.
- Si un código tiene relación ambigua con el core, consérvalo (KEEP conservador).
- Las fusiones deben preservar el nombre más abstracto (el de mayor theoretical grab).

## User

[CORE CATEGORY]
{core_category}

[ALL CODES WITH DEFINITIONS]
{all_codes}

[CODE CO-OCCURRENCE MATRIX]
{code_relationships}

## Output Schema

```json
{
  "kept_codes": ["code_id"],
  "merged_codes": [
    {
      "survivor_code_id": "string",
      "absorbed_code_ids": ["string"],
      "new_name": "string (opcional — solo si la fusión eleva la abstracción)",
      "rationale": "string"
    }
  ],
  "discarded_codes": [
    {
      "code_id": "string",
      "code_name": "string",
      "discard_rationale": "string (por qué no se relaciona con el core)"
    }
  ],
  "reduction_summary": "string (resumen de la reducción: X mantenidos, Y fusionados, Z descartados)"
}
```
```

#### A3.6 — `prompts/pro/selective_reduction_critic.md`

```markdown
---
prompt_id: selective_reduction_critic
version: 1.0.0
model_profile: pro
description: Audita la reducción selectiva propuesta, verificando que cada descarte y fusión esté justificado y que no se haya descartado nada relevante al core.
langgraph_node: null
execution_order: "Fase B — Paso B2"
input_state: reduction_proposal, core_category, all_codes
output_state: verdict, disputed_items, suggestions
depends_on: selective_reduction_proposer
prerequisite_for: null
agent_id: null
triggers_on: "Después de selective_reduction_proposer"
note: "PRO porque evalúa juicio de uniformidad subyacente — requiere entender si dos códigos son realmente el mismo fenómeno."
---

## System

[ROL]
Eres un auditor de Grounded Theory. Revisas la reducción selectiva propuesta
buscando errores: códigos relevantes descartados incorrectamente, fusiones
que ocultan diferencias importantes, o códigos irrelevantes que sobrevivieron.

[OBJETIVO]
Para cada decisión en la propuesta de reducción:
1. Verificar que los descartes realmente no se relacionan con el core
2. Verificar que las fusiones no colapsan fenómenos distintos
3. Verificar que no quedaron códigos huérfanos sin evaluar

[RESTRICCIONES]
- Emite SAT solo si ≥90% de las decisiones son correctas.
- Para cada ítem disputado, explica POR QUÉ y sugiere la acción correcta.

## User

[REDUCTION PROPOSAL]
{reduction_proposal}

[CORE CATEGORY]
{core_category}

[ALL CODES]
{all_codes}

## Output Schema

```json
{
  "verdict": "SAT | MOD | FORCED",
  "agreement_percentage": 0.0,
  "disputed_items": [
    {
      "code_id": "string",
      "current_decision": "KEEP | MERGE | DISCARD",
      "suggested_decision": "KEEP | MERGE | DISCARD",
      "rationale": "string"
    }
  ],
  "overall_assessment": "string"
}
```
```

#### A3.7 — `prompts/pro/core_saturation_proposer.md`

```markdown
---
prompt_id: core_saturation_proposer
version: 1.0.0
model_profile: pro
description: Evalúa un nuevo incidente contra una categoría del core, determinando si converge (sin expansión) o diverge (expande propiedades, dimensiones o condiciones).
langgraph_node: null
execution_order: "Fase C — Paso C1"
input_state: category_label, category_definition, current_properties, incident_text, document_name
output_state: elaboration_type, description, expanded_definition, new_properties, did_state_expand
depends_on: null
prerequisite_for: core_saturation_critic
agent_id: A25
triggers_on: "Loop de saturación: para cada categoría (score≥4) × cada documento"
note: "PRO porque requiere integrar información nueva con el estado paradigmático existente de la categoría — no es solo matching."
---

## System

[ROL]
Eres un investigador de Grounded Theory en fase de SATURACIÓN TEÓRICA.
Evalúas si un nuevo incidente expande o no el estado actual de una categoría.

[OBJETIVO]
Comparar el incidente contra la definición y propiedades actuales de la categoría:
1. CONVERGE — El incidente es otro ejemplo de lo mismo. No expande.
2. DIVERGE (propiedad) — El incidente revela una propiedad nueva o expande un gradiente existente.
3. DIVERGE (dimensión) — El incidente añade una dimensión completamente nueva.
4. DIVERGE (condición) — El incidente revela una condición bajo la cual la categoría se comporta diferente.

[RESTRICCIONES]
- La divergencia NO es un error. Es información valiosa que densifica la categoría.
- Si el incidente no encaja en absoluto, indica `diverges_strong` — puede requerir re-categorización.

## User

[CATEGORY]
Name: {category_label}
Definition: {category_definition}
Version: {version}

[CURRENT PROPERTIES]
{current_properties}

[NEW INCIDENT]
Document: {document_name}
Text: {incident_text}

## Output Schema

```json
{
  "elaboration_type": "converges | diverges_property | diverges_dimension | diverges_condition | diverges_strong",
  "description": "string (qué aporta este incidente)",
  "expanded_definition": "string (solo si la definición debe actualizarse)",
  "new_or_expanded_properties": [
    {
      "name": "string",
      "gradient": "string (polos del gradiente: 'extremo A ↔ extremo B')",
      "incident_position": "string (dónde se ubica este incidente en el gradiente)"
    }
  ],
  "did_state_expand": true,
  "elaboration_note": "string (nota metodológica para el memo)"
}
```
```

#### A3.8 — `prompts/flash/core_saturation_critic.md`

```markdown
---
prompt_id: core_saturation_critic
version: 1.0.0
model_profile: flash
description: Verifica si el elaborator identificó correctamente convergencia/divergencia comparando el incidente contra el paradigm_state actual de la categoría.
langgraph_node: null
execution_order: "Fase C — Paso C2"
input_state: elaboration_result, category_definition, incident_text, paradigm_state
output_state: verdict, agree, rationale
depends_on: core_saturation_proposer
prerequisite_for: null
agent_id: null
triggers_on: "Después de core_saturation_proposer, para cada iteración cat×doc"
note: "FLASH porque es un diff estructurado. Corre frecuentemente (cada cat×doc) — ahorro significativo vs PRO."
---

## System

[ROL]
Eres un verificador rápido de Grounded Theory. Tu trabajo es confirmar o corregir
la evaluación de convergencia/divergencia hecha por el elaborator.

[OBJETIVO]
Dado el incidente, la definición de la categoría, y el paradigm_state actual:
- ¿El elaborator clasificó correctamente el tipo de elaboración?
- ¿La expansión de propiedades sugerida es válida?

[RESTRICCIONES]
- Solo corrige si hay error claro. Si hay ambigüedad, confía en el elaborator.
- Sé rápido. Esto corre para cada categoría × cada documento.

## User

[ELABORATION RESULT]
{elaboration_result}

[CATEGORY DEFINITION]
{category_definition}

[PARADIGM STATE]
{paradigm_state}

[INCIDENT TEXT]
{incident_text}

## Output Schema

```json
{
  "verdict": "AGREE | DISAGREE",
  "corrected_type": "string (solo si DISAGREE — el tipo correcto)",
  "rationale": "string (breve — 1-2 oraciones)"
}
```
```

#### A3.9-A3.12 — Database A/B prompts (4 archivos)

> **Nota:** Estos prompts son para la Fase D y se implementarán cuando lleguemos a E2.5.
> Los creamos ahora (seguro, son archivos nuevos) pero su contenido detallado se refinará
> al llegar a esa etapa. Por ahora, creamos el esqueleto con el contrato mínimo.

**`prompts/pro/database_a_proposer.md`:**
```markdown
---
prompt_id: database_a_proposer
version: 1.0.0
model_profile: pro
description: Genera nodos planos (entidades) con entity_type desde el sistema de categorías saturado.
langgraph_node: null
execution_order: "Fase D — Paso D1"
input_state: saturated_categories, core_category
output_state: nodes
depends_on: null
prerequisite_for: database_a_critic
agent_id: null
triggers_on: "Proyecto en estado 'building_db' con sub-estado 'nodes'"
note: "PRO — requiere razonamiento ontológico para decidir qué categorías se convierten en nodos y con qué entity_type."
---

## System
[ROL] Eres un modelador ontológico para Grounded Theory.
[OBJETIVO] Convertir el sistema de categorías saturado en nodos planos con entity_type.
[RESTRICCIONES] Solo categorías con score ≥ 4 y saturadas. entity_type debe ser uno de: PROCESS, ACTOR, CONDITION, CONSEQUENCE, CONTEXT, STRATEGY.

## User
[SATURATED CATEGORIES] {saturated_categories}
[CORE CATEGORY] {core_category}

## Output Schema
```json
{
  "nodes": [
    {
      "category_id": "string",
      "label": "string",
      "entity_type": "PROCESS | ACTOR | CONDITION | CONSEQUENCE | CONTEXT | STRATEGY",
      "definition": "string"
    }
  ]
}
```
```

**`prompts/pro/database_a_critic.md`:**
```markdown
---
prompt_id: database_a_critic
version: 1.0.0
model_profile: pro
description: Audita el sistema de nodos planos verificando entity_types correctos y que no falten entidades.
langgraph_node: null
execution_order: "Fase D — Paso D2"
input_state: nodes, saturated_categories
output_state: verdict, corrections
depends_on: database_a_proposer
prerequisite_for: null
agent_id: null
triggers_on: "Después de database_a_proposer"
note: "PRO — evaluar estructura ontológica requiere juicio."
---
## System
[ROL] Auditor ontológico para Grounded Theory.
[OBJETIVO] Verificar que los entity_type asignados son correctos y que no faltan entidades del sistema de categorías.
## User
[NODES] {nodes}
[SATURATED CATEGORIES] {saturated_categories}
## Output Schema
```json
{
  "verdict": "SAT | MOD | FORCED",
  "corrections": [{"node_label": "string", "current_type": "string", "suggested_type": "string", "rationale": "string"}]
}
```
```

**`prompts/pro/database_b_proposer.md`:**
```markdown
---
prompt_id: database_b_proposer
version: 1.0.0
model_profile: pro
description: Genera edges (relaciones) con relationship_type entre los nodos planos del sistema.
langgraph_node: null
execution_order: "Fase D — Paso D3"
input_state: nodes, conceptual_relationships, hypotheses
output_state: edges
depends_on: database_a_proposer
prerequisite_for: database_b_critic
agent_id: null
triggers_on: "Después de HITL ACCEPT en database_a"
note: "PRO — requiere razonamiento para inferir relaciones tipadas entre entidades."
---
## System
[ROL] Eres un modelador de relaciones para Grounded Theory.
[OBJETIVO] Generar edges tipados entre los nodos del sistema, basados en relaciones conceptuales elaboradas e hipótesis.
[RESTRICCIONES] relationship_type debe ser uno de: CAUSES, ENABLES, CONSTRAINS, MODULATES, IS_A, PART_OF, CO_OCCURS_WITH, RESOLVES.
## User
[NODES] {nodes}
[CONCEPTUAL RELATIONSHIPS] {conceptual_relationships}
[HYPOTHESES] {hypotheses}
## Output Schema
```json
{
  "edges": [
    {
      "source_node_label": "string",
      "target_node_label": "string",
      "relationship_type": "CAUSES | ENABLES | CONSTRAINS | MODULATES | IS_A | PART_OF | CO_OCCURS_WITH | RESOLVES",
      "evidence": "string",
      "direction": "unidirectional | bidirectional"
    }
  ]
}
```
```

**`prompts/pro/database_b_critic.md`:**
```markdown
---
prompt_id: database_b_critic
version: 1.0.0
model_profile: pro
description: Audita el sistema de relaciones verificando tipos correctos, direcciones, y relaciones faltantes.
langgraph_node: null
execution_order: "Fase D — Paso D4"
input_state: edges, nodes, hypotheses
output_state: verdict, corrections
depends_on: database_b_proposer
prerequisite_for: null
agent_id: null
triggers_on: "Después de database_b_proposer"
note: "PRO — validar sistema de relaciones requiere juicio teórico."
---
## System
[ROL] Auditor de relaciones para Grounded Theory.
[OBJETIVO] Verificar tipos de relación, direcciones, y detectar relaciones faltantes entre nodos.
## User
[EDGES] {edges}
[NODES] {nodes}
[HYPOTHESES] {hypotheses}
## Output Schema
```json
{
  "verdict": "SAT | MOD | FORCED",
  "corrections": [{"source": "string", "target": "string", "issue": "string", "suggestion": "string"}]
}
```
```

---

### A4. Crear router HITL (sin registrarlo aún)

**Archivo:** `backend/app/api/v1/hitl.py` (NUEVO)

**Seguridad:** 🟢 — El archivo existe pero `main.py` no lo importa todavía. Sin registrar = sin exponer.

```python
# backend/app/api/v1/hitl.py
"""HITL decision endpoint — gates del pipeline selectivo."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.schemas.hitl import (
    HitlDecisionRequest,
    HitlDecisionResponse,
    HitlPendingItem,
)
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["hitl"])


@router.get("/projects/{project_id}/hitl/pending")
async def get_pending_decisions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> list[HitlPendingItem]:
    """Devuelve las decisiones HITL pendientes para un proyecto."""
    rows = await db.execute(
        text(
            "SELECT id, gate_name, proposal, critic_verdict, creado_en "
            "FROM hitl_decisions "
            "WHERE project_id = :pid AND status = 'pending' "
            "ORDER BY creado_en ASC"
        ),
        {"pid": project_id},
    )
    results = []
    for row in rows:
        proposal = row[2] if isinstance(row[2], dict) else {}
        critic = row[3] if isinstance(row[3], dict) else {}
        results.append(
            HitlPendingItem(
                id=row[0],
                gate_name=row[1],
                proposal_summary=proposal.get("main_concern", "")
                or proposal.get("rationale", "")[:200],
                critic_verdict=critic.get("verdict", "SAT"),
                created_at=row[4],
            )
        )
    return results


@router.post(
    "/projects/{project_id}/hitl/{gate_name}/decide",
    response_model=HitlDecisionResponse,
)
async def decide_hitl(
    project_id: UUID,
    gate_name: str,
    body: HitlDecisionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """ACCEPT → avanzar pipeline. MODIFY → re-ejecutar proposer. REJECT → archivar."""
    # 1. Buscar la decisión pendiente más reciente para este gate
    row = await db.execute(
        text(
            "SELECT id, proposal FROM hitl_decisions "
            "WHERE project_id = :pid AND gate_name = :gate AND status = 'pending' "
            "ORDER BY creado_en DESC LIMIT 1"
        ),
        {"pid": project_id, "gate": gate_name},
    )
    decision_row = row.fetchone()
    if not decision_row:
        raise HTTPException(404, f"No pending decision for gate '{gate_name}'")

    decision_id = decision_row[0]

    # 2. Actualizar la decisión
    now = datetime.now(timezone.utc)
    await db.execute(
        text(
            "UPDATE hitl_decisions SET "
            "status = :status, "
            "researcher_decision = :dec, "
            "researcher_note = :note, "
            "researcher_feedback = :fb, "
            "decided_at = :now "
            "WHERE id = :did"
        ),
        {
            "status": body.decision + "ed" if body.decision != "accept" else "accepted",
            "dec": body.decision,
            "note": body.note,
            "fb": body.feedback,
            "now": now,
            "did": decision_id,
        },
    )
    await db.commit()

    # 3. TODO (E2): Si ACCEPT → disparar siguiente fase del coordinator
    #    Esto se implementa cuando el coordinator exista.
    #    Por ahora, solo registramos la decisión.

    logger.info(
        "HITL decision: gate=%s decision=%s by user=%s",
        gate_name,
        body.decision,
        current_user.id,
    )

    return HitlDecisionResponse(
        id=decision_id,
        project_id=project_id,
        gate_name=gate_name,
        status="accepted" if body.decision == "accept" else body.decision + "ed",
        researcher_decision=body.decision,
        researcher_note=body.note,
        decided_at=now,
    )
```

---

### A5. Crear componente HITLModal (frontend)

**Archivo:** `frontend/src/components/HITLModal.tsx` (NUEVO)

**Seguridad:** 🟢 — Componente nuevo. No se renderiza hasta que se importe en Project.tsx.

```tsx
// frontend/src/components/HITLModal.tsx
import { useState } from "react";

interface HITLModalProps {
  open: boolean;
  gateName: string;
  proposal: Record<string, unknown>;
  criticVerdict: {
    verdict: string;
    rationale?: string;
    suggestions?: string[];
    grounding_score?: number;
    coverage_score?: number;
    abstraction_score?: number;
  };
  onClose: () => void;
  onSubmit: (decision: "accept" | "modify" | "reject", note: string, feedback?: string) => void;
}

const GATE_LABELS: Record<string, string> = {
  main_concern: "Main Concern Detection",
  core_emergence: "Core Category Emergence",
  selective_reduction: "Selective Reduction",
  core_saturation: "Core Saturation",
  database_a: "Database A — Nodes",
  database_b: "Database B — Edges",
  global_saturation: "Global Saturation Check",
};

const VERDICT_COLORS: Record<string, string> = {
  SAT: "#2EA043",
  MOD: "#D29922",
  FORCED: "#F85149",
  AGREE: "#2EA043",
  DISAGREE: "#F85149",
};

export default function HITLModal({ open, gateName, proposal, criticVerdict, onClose, onSubmit }: HITLModalProps) {
  const [decision, setDecision] = useState<"accept" | "modify" | "reject" | null>(null);
  const [note, setNote] = useState("");
  const [feedback, setFeedback] = useState("");

  if (!open) return null;

  const handleSubmit = () => {
    if (!decision) return;
    onSubmit(decision, note, decision === "modify" ? feedback : undefined);
  };

  const gateLabel = GATE_LABELS[gateName] || gateName;

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.7)",
    }}>
      <div style={{
        background: "#161B22", borderRadius: 12, border: "1px solid #30363D",
        width: 640, maxHeight: "85vh", overflow: "auto", padding: 24,
        color: "#E6EDF3",
      }}>
        {/* Header */}
        <h2 style={{ margin: "0 0 4px 0", fontSize: 18 }}>
          🛑 HITL Decision Required
        </h2>
        <p style={{ margin: "0 0 16px 0", color: "#8B949E", fontSize: 13 }}>
          Gate: <strong>{gateLabel}</strong>
        </p>

        {/* Critic Verdict Banner */}
        <div style={{
          padding: "12px 16px", borderRadius: 8, marginBottom: 16,
          background: "#1C2333", border: `1px solid ${VERDICT_COLORS[criticVerdict.verdict] || "#30363D"}`,
        }}>
          <span style={{
            fontWeight: 700, fontSize: 14,
            color: VERDICT_COLORS[criticVerdict.verdict] || "#E6EDF3",
          }}>
            Critic Verdict: {criticVerdict.verdict}
          </span>
          {criticVerdict.rationale && (
            <p style={{ margin: "8px 0 0 0", fontSize: 13, color: "#8B949E", lineHeight: 1.5 }}>
              {criticVerdict.rationale}
            </p>
          )}
          {criticVerdict.suggestions && criticVerdict.suggestions.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <strong style={{ fontSize: 12, color: "#D29922" }}>Suggestions:</strong>
              <ul style={{ margin: "4px 0 0 0", paddingLeft: 20, fontSize: 12, color: "#8B949E" }}>
                {criticVerdict.suggestions.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {/* Scores (for main_concern gate) */}
          {(criticVerdict.grounding_score !== undefined) && (
            <div style={{ marginTop: 8, display: "flex", gap: 16, fontSize: 12 }}>
              <span style={{ color: "#8B949E" }}>Grounding: {(criticVerdict.grounding_score! * 100).toFixed(0)}%</span>
              <span style={{ color: "#8B949E" }}>Coverage: {(criticVerdict.coverage_score! * 100).toFixed(0)}%</span>
              <span style={{ color: "#8B949E" }}>Abstraction: {(criticVerdict.abstraction_score! * 100).toFixed(0)}%</span>
            </div>
          )}
        </div>

        {/* Proposal Summary */}
        <div style={{
          padding: "12px 16px", borderRadius: 8, marginBottom: 16,
          background: "#0D1117", border: "1px solid #21262D",
          maxHeight: 200, overflow: "auto",
        }}>
          <strong style={{ fontSize: 12, color: "#58A6FF" }}>Proposer Output:</strong>
          <pre style={{
            margin: "8px 0 0 0", fontSize: 12, color: "#C9D1D9",
            whiteSpace: "pre-wrap", fontFamily: "monospace",
          }}>
            {JSON.stringify(proposal, null, 2)}
          </pre>
        </div>

        {/* Decision Buttons */}
        <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
          {(["accept", "modify", "reject"] as const).map((d) => (
            <button
              key={d}
              onClick={() => setDecision(d)}
              style={{
                flex: 1, padding: "10px 0", borderRadius: 8, border: "none",
                fontSize: 14, fontWeight: 600, cursor: "pointer",
                background: decision === d
                  ? d === "accept" ? "#1F6FEB" : d === "modify" ? "#9E6A03" : "#DA3633"
                  : "#21262D",
                color: decision === d ? "#FFF" : "#8B949E",
                border: decision === d ? "none" : "1px solid #30363D",
              }}
            >
              {d === "accept" ? "✓ ACCEPT" : d === "modify" ? "✎ MODIFY" : "✗ REJECT"}
            </button>
          ))}
        </div>

        {/* Note (always shown) */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ fontSize: 12, color: "#8B949E", display: "block", marginBottom: 4 }}>
            Note {decision === "reject" ? "(required — explain why)" : "(optional)"}:
          </label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder={
              decision === "reject"
                ? "Why are you rejecting this proposal?"
                : "Any observations for the methodology log..."
            }
            style={{
              width: "100%", padding: "8px 12px", borderRadius: 6,
              background: "#0D1117", border: "1px solid #30363D",
              color: "#E6EDF3", fontSize: 12, resize: "vertical",
              fontFamily: "inherit",
            }}
          />
        </div>

        {/* Feedback (only for MODIFY) */}
        {decision === "modify" && (
          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 12, color: "#D29922", display: "block", marginBottom: 4 }}>
              Feedback for re-execution (what should the proposer do differently?):
            </label>
            <textarea
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              rows={3}
              placeholder="Be specific: what should change in the proposal?"
              style={{
                width: "100%", padding: "8px 12px", borderRadius: 6,
                background: "#0D1117", border: "1px solid #D29922",
                color: "#E6EDF3", fontSize: 12, resize: "vertical",
                fontFamily: "inherit",
              }}
            />
          </div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button
            onClick={onClose}
            style={{
              padding: "8px 16px", borderRadius: 6, border: "1px solid #30363D",
              background: "#21262D", color: "#E6EDF3", fontSize: 13, cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!decision || (decision === "reject" && !note.trim())}
            style={{
              padding: "8px 16px", borderRadius: 6, border: "none",
              background: !decision ? "#21262D" : "#1F6FEB",
              color: !decision ? "#484F58" : "#FFF",
              fontSize: 13, fontWeight: 600, cursor: !decision ? "not-allowed" : "pointer",
            }}
          >
            Submit Decision
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

### A6. Agregar funciones al API client del frontend

**Archivo:** `frontend/src/api/client.ts` (MODIFICAR — agregar al final)

**Seguridad:** 🟢 — Agregar exports nuevos no rompe imports existentes.

```typescript
// ── HITL Types ────────────────────────────────────────────────

export interface HitlPendingItem {
  id: string;
  gate_name: string;
  proposal_summary: string;
  critic_verdict: string;
  created_at: string;
}

export interface HitlDecisionResponse {
  id: string;
  project_id: string;
  gate_name: string;
  status: string;
  researcher_decision: string | null;
  researcher_note: string | null;
  decided_at: string | null;
}

// ── HITL API ──────────────────────────────────────────────────

export async function getPendingHitl(
  projectId: string,
): Promise<HitlPendingItem[]> {
  return apiGet(`/projects/${projectId}/hitl/pending`);
}

export async function decideHitl(
  projectId: string,
  gateName: string,
  decision: "accept" | "modify" | "reject",
  note: string,
  feedback?: string,
): Promise<HitlDecisionResponse> {
  return apiPost(`/projects/${projectId}/hitl/${gateName}/decide`, {
    decision,
    note,
    feedback,
  });
}
```

---

## FASE B — Cambios con Precaución (ejecutar con recarga controlada)

Estos cambios modifican código que se carga en runtime pero no rompen
procesos ya corriendo. Se aplican juntos y se recarga el backend.

---

### B1. Actualizar `document.py` (agregar `sintetizado` al docstring)

**Archivo:** `backend/app/models/domain/document.py` L31-32

**Seguridad:** 🟡 — Solo cambia un comentario. Pero el modelo se recarga al reiniciar.

```python
# Cambiar el docstring de la columna `estado`:
estado: Mapped[str] = mapped_column(String(50), default="crudo")
"""
crudo → segmentando → segmentado → procesando → listo → sintetizado
(error puede ocurrir en cualquier etapa)
"""
```

---

### B2. Actualizar `project.py` (cambiar default de estado)

**Archivo:** `backend/app/models/domain/project.py` L24

**Seguridad:** 🟡 — Cambia el default para NUEVOS proyectos. Proyectos existentes no se afectan hasta la migración.

```python
estado: Mapped[str] = mapped_column(String(50), default="collecting")
# "collecting" | "coding" | "finding_cc" | "reducing" |
# "saturating" | "building_db" | "playground_ready" | "completed"
```

**Migración requerida:**
```sql
-- Actualizar proyectos existentes
UPDATE proyectos SET estado = 'collecting' WHERE estado = 'ACTIVO';
```

---

### B3. Extender `events.py` (agregar tipo `hitl_required`)

**Archivo:** `backend/app/api/v1/events.py` (sin cambios — ya soporta cualquier `event_type`)

**Seguridad:** 🟡 — `publish_event()` acepta cualquier string como `event_type`. No hay que cambiar nada. Solo documentar que los workers llamarán:

```python
from app.api.v1.events import publish_event
publish_event(project_id, "hitl_required", {
    "gate": gate_name,
    "proposal": proposal,
    "critic_verdict": critic_verdict,
})
```

---

### B4. Generar migración Alembic

**Seguridad:** 🟡 — Crea la migración pero no la aplica hasta que se ejecute `alembic upgrade head`.

```bash
cd backend
alembic revision --autogenerate -m "add_hitl_decisions_and_project_states"
alembic upgrade head
```

---

## FASE C — Cambios Críticos (requieren workers detenidos)

Estos cambios rompen funcionalidad activa. Se planifican para una ventana
donde no haya workers procesando ni usuarios ejecutando el pipeline selectivo.

---

### C1. Actualizar `transitions.py`

**Archivo:** `backend/app/agents/transitions.py`

**Cambios:**
1. Agregar `"listo": ("sintetizado", None, None)` al dict `NEXT` (L36)
2. Agregar `"sintetizado": (None, None, None)` (nuevo estado terminal temporal)
3. Agregar `PROJECT_STATES` dict
4. Agregar función `transition_project()`
5. Agregar función `hitl_gate()`
6. Actualizar `_maybe_trigger_phase_b()` query: `WHERE estado='listo'` → `WHERE estado='sintetizado'`

**Seguridad:** 🔴 — Modifica las transiciones de estado de documentos. Si se cambia mientras hay workers corriendo, los documentos en estado `listo` podrían quedar en estado inconsistente.

---

### C2. Reducir `workflow.py`

**Archivo:** `backend/app/core/workflow.py`

**Cambios:**
1. Eliminar nodos del grafo: `find_core_concern`, `generate_hypotheses`, `calculate_saturation`, `hitl_review`, `final_report`
2. Eliminar `build_glaser_graph_with_feedback()` completa
3. Mantener solo open coding: `segment_and_index → extract_entities → batch_code → map_synthesize → reduce_synthesize → END`

**Seguridad:** 🔴 — `invoke_graph()` en `tasks.py` depende de `build_glaser_graph()`. Si se reduce el grafo antes de actualizar `invoke_graph()`, las invocaciones existentes fallarán.

---

### C3. Refactorizar `workers/heavy/tasks.py`

**Archivo:** `workers/heavy/tasks.py`

**Cambios:**
1. Eliminar `trigger_selective_elaboration()` (L1399-1440)
2. Refactorizar `process_synthesis_agents_b`: agregar `base=AbortableTask, bind=True`, checkpoints, transicionar docs a `sintetizado`
3. Refactorizar `task_a14_main_concern` → `task_main_concern_pipeline`
4. Refactorizar `task_a15_core_emergence` → `task_core_emergence_pipeline`
5. Crear `selective_coding_coordinator`
6. Crear `task_selective_reduction_pipeline`
7. Crear `task_core_saturation_loop`
8. Crear `task_database_a_pipeline`
9. Crear `task_database_b_pipeline`
10. Crear `task_global_saturation_check`

**Seguridad:** 🔴 — Elimina la tarea que actualmente ejecuta el pipeline selectivo. Si hay workers corriendo `trigger_selective_elaboration`, se interrumpirán.

---

### C4. Actualizar `pipeline.py` stages

**Archivo:** `backend/app/api/v1/pipeline.py` L87-108

**Seguridad:** 🔴 — Cambia los endpoints que el frontend usa para disparar stages. Si el frontend no se actualiza simultáneamente, los botones de pipeline fallarán.

---

### C5. Actualizar `Project.tsx` PIPELINE_STAGES

**Archivo:** `frontend/src/pages/Project.tsx` L44-50

**Seguridad:** 🟡 — Cambio de frontend puro. No afecta al backend. Pero mostrará stages incorrectos hasta que el backend esté actualizado.

---

## Resumen del Plan por Sesión de Trabajo

| Sesión | Pasos | Seguridad | Entregables |
|--------|-------|-----------|-------------|
| **Sesión 1** (AHORA) | A1, A2, A3.1-A3.12, A4, A5, A6 | 🟢 100% seguro | Modelo HITL + schemas + 12 prompts + router (sin registrar) + HITLModal + client.ts |
| **Sesión 2** (con recarga) | B1, B2, B3, B4 | 🟡 Precaución | Docstrings + project default + migración aplicada |
| **Sesión 3** (ventana) | C1, C2, C3, C4, C5 | 🔴 Crítico | Transiciones + workflow reducido + coordinator + pipeline stages + frontend |

---

## Checkpoint: ¿Qué tendremos al final de la Sesión 1?

Al terminar la Sesión 1 (AHORA), el sistema tendrá:

- ✅ Tabla `hitl_decisions` creada en la DB (vía migración)
- ✅ 12 nuevos prompts en `prompts/pro/` y `prompts/flash/`
- ✅ Router HITL listo (pero no registrado — sin exponer)
- ✅ Componente `HITLModal.tsx` listo (pero no integrado en Project.tsx)
- ✅ Funciones `getPendingHitl()` y `decideHitl()` en el API client
- ❌ El pipeline sigue funcionando exactamente igual que antes
- ❌ `trigger_selective_elaboration` sigue activo
- ❌ Los nuevos prompts no son llamados por nadie todavía
