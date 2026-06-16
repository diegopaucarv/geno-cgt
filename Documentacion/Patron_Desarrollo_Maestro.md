# Patrón de Desarrollo Maestro — Sistema GT

> **Principios arquitectónicos y metodológicos que toda etapa del pipeline debe seguir.**
>
> Versión 2.0 — 2026-06-16

---

## 0. REGLA 0 — Metodológica (precede a todas las demás)

Antes de las reglas de ingeniería, todo componente del pipeline debe cumplir **3 principios CGT**:

```
┌─────────────────────────────────────────────────────────────────┐
│              REGLA 0 — PRINCIPIOS METODOLÓGICOS CGT              │
│                                                                  │
│  R0.1: Proposer → Critic → HITL en toda decisión teórica        │
│  ─────────────────────────────────────────────────────          │
│  Ningún agente puede FINALIZAR una decisión teórica sin          │
│  pasar por el investigador. El flujo es:                         │
│    Proposer (IA propone) → Critic (IA evalúa SAT/MOD/FORCED)     │
│    → HITL (investigador confirma/rechaza/modifica).              │
│  Esto aplica a: core concern, core category, reducción           │
│  selectiva, expansiones de saturación, cierre de saturación.     │
│                                                                  │
│  R0.2: Dependencias metodológicas seriales, no paralelas         │
│  ────────────────────────────────────────────────────           │
│  Core concern → Core emergence → Selective reduction →           │
│  Core saturation. Cada fase consume el output de la anterior.    │
│  No se puede integrar paradigmas antes de saber qué categorías   │
│  importan. No se puede hacer muestreo teórico antes de saber     │
│  qué propiedades necesitan más datos.                            │
│                                                                  │
│  R0.3: Separación estricta open coding / selective coding        │
│  ────────────────────────────────────────────────────           │
│  La codificación selectiva NO recodifica desde cero. Opera       │
│  sobre el sistema de códigos ya existente, DELIMITANDO           │
│  (descartando lo no relacionado al core) y SATURANDO             │
│  (elaborando propiedades de lo que sobrevive).                   │
│  Invocar nodos de open coding (batch_code, map_synthesize)       │
│  dentro de la fase selectiva es metodológicamente incorrecto.    │
└─────────────────────────────────────────────────────────────────┘
```

### 0.1 Grafo de dependencias metodológicas (post open coding)

```
Fase 3-4: Open Coding + Síntesis Cross-Document
  │
  │  Output: all_open_codes, all_memos, categories, population_context
  │
  ▼
┌─ FASE 5b: CODIFICACIÓN SELECTIVA ──────────────────────────────┐
│                                                                  │
│  A. CORE CATEGORY DETECTION (serial, con HITL)                   │
│  ─────────────────────────────────────────                       │
│  A1. main_concern_proposer (PRO)                                  │
│       → A2. main_concern_critic (PRO)                             │
│       → 🛑 HITL: researcher confirms main concern                │
│  A3. core_emergence_proposer (PRO)                                │
│       → A4. core_emergence_critic (FLASH)                         │
│       → 🛑 HITL: researcher confirms core category               │
│       │                                                          │
│       ▼                                                          │
│  B. SELECTIVE REDUCTION (serial, con HITL)                       │
│  ───────────────────────────────────────                         │
│  B1. selective_reduction_proposer (PRO)                           │
│       → B2. selective_reduction_critic (PRO)                      │
│       → 🛑 HITL: researcher confirms reduced code system         │
│       │                                                          │
│       ▼                                                          │
│  C. CORE SATURATION (loop cat×doc, con HITL)                     │
│  ─────────────────────────────────────────                       │
│  For each category with score ≥ 4:                               │
│    For each document:                                             │
│      C1. core_saturation_proposer (PRO)                           │
│           → C2. core_saturation_critic (FLASH)                    │
│           → if did_state_expand=false for 3 iterations:           │
│               → 🛑 HITL: confirm saturation                      │
│           → if properties still undocumented:                    │
│               → TheoSampler (demand-driven, not pre-emptive)     │
│               → fetch new docs → repeat loop                     │
│       │                                                          │
│       ▼                                                          │
│  D. DATABASE A/B (serial, con HITL)                              │
│  ───────────────────────────────                                 │
│  D1. database_a_proposer (PRO) → nodes planos + entity_type      │
│       → D2. database_a_critic (PRO)                               │
│       → 🛑 HITL: researcher confirms node system                 │
│  D3. database_b_proposer (PRO) → edges + relationship_type       │
│       → D4. database_b_critic (PRO)                               │
│       → 🛑 HITL: researcher confirms relationship system         │
│       │                                                          │
│       ▼                                                          │
│  E. GLOBAL SATURATION CHECK                                      │
│  ─────────────────────────                                       │
│  Verify 3 conditions:                                             │
│    1. All categories ≥4 are saturated                             │
│    2. All inter-category relationships saturated (5 docs, 0 CE) │
│    3. Residual buffer reviewed (anomalies documented)             │
│  → 🛑 HITL: researcher closes selective coding                   │
└──────────────────────────────────────────────────────────────────┘
```

### 0.2 El patrón Proposer→Critic→HITL en detalle

```
┌──────────────────────────────────────────────────────────────┐
│           PATRÓN PROPOSER → CRITIC → HITL                     │
│                                                               │
│  ┌──────────┐    ┌──────────┐    ┌───────────┐               │
│  │ PROPOSER │───▶│  CRITIC  │───▶│   HITL    │               │
│  │ (PRO)    │    │ (PRO o   │    │ (frontend │               │
│  │ propone  │    │  FLASH)  │    │  modal)   │               │
│  │ opciones │    │ evalúa   │    │ investig. │               │
│  │          │    │SAT/MOD/  │    │ decide    │               │
│  │          │    │FORCED    │    │           │               │
│  └──────────┘    └──────────┘    └─────┬─────┘               │
│                                        │                     │
│                          ┌─────────────┼─────────────┐       │
│                          ▼             ▼             ▼       │
│                       ACCEPT       MODIFY        REJECT      │
│                       (avanzar)   (re-ejecutar  (archivar    │
│                                    proposer      decisión    │
│                                    con feedback)  con nota)  │
└──────────────────────────────────────────────────────────────┘

PROPOSER siempre es PRO (generación teórica requiere razonamiento).
CRITIC es PRO si evalúa grounding metodológico complejo (fusión de
códigos, calidad de abstracción) o FLASH si es diff estructurado
(intercambiabilidad, expansión de propiedades vs paradigm_state).

HITL no es opcional. Es un gate metodológico. El pipeline no avanza
sin confirmación humana en decisiones teóricas.
```

### 0.3 Theoretical Coding — Principios específicos

El theoretical coding opera bajo un paradigma distinto al selective coding.
Mientras que el selective coding DELIMITA y SATURA (filtra categorías, las densifica),
el theoretical coding INTEGRA y ELEVA (conecta categorías, las renombra).

**R0.4: Elaboración, no ejecución**
En theoretical coding no hay "tareas" con `success/failure`. Hay
**elaboraciones** con `converge/diverge/expand`. Un dato divergente
NO es un error — es una oportunidad de expansión conceptual.

**R0.5: Los códigos teóricos son herramientas del investigador, no config del sistema**
Los 12 códigos teóricos (`theoretical_codes`) son visibles, modificables
y extensibles por el investigador. Cada uno tiene `evaluation_logic` que
el investigador puede inspeccionar (botón "▶ VER LÓGICA") y ajustar.
El investigador puede crear nuevos códigos user-defined. El sistema
no elige qué código aplicar — el investigador decide.

**R0.6: Sesión persistente, no estado terminal**
El Theoretical Playground no es un paso del pipeline que termina en
`playground_ready`. Es un **workspace persistente** que evoluciona a
través de sesiones. El `EcosystemLayout` persiste posiciones entre
sesiones. El `ElaborationMemo` registra cada iteración. El investigador
puede cerrar el navegador y volver días después — el ecosistema está
como lo dejó.

**R0.7: La divergencia EXPANDE, no rompe**
Cuando `conceptual_elaborator` encuentra datos que no encajan en una
relación, NO emite "error" ni "failure". Emite `diverging_evidence`
con `expansion_suggestion`. El tendril muestra **fisuras doradas** —
el investigador hace clic para expandir la relación con una condición,
subtipo, o ruta alternativa. La relación se vuelve MÁS RICA, no se descarta.

**R0.8: Sorting Log y homeless memos**
Glaser insiste en que el sorting físico produce montones, montones
delgados, memos sin hogar, y colocaciones forzadas. El `ElaborationMemo`
captura cada iteración. El `RecommendationEngine` detecta categorías
huérfanas y capas sin cubrir. El sistema debe hacer visible lo que
NO encaja — es tan informativo como lo que sí.

**R0.9: No linealidad — el investigador puede volver**
El investigador, en medio del Playground, puede detectar que una relación
necesita más evidencia → volver a selective coding → muestrear →
re-codificar → regresar al Playground con el concepto densificado.
Esto no es un bug. Es el método. El StateGraph lo soporta con
`after_gap_review → segment_and_index`.

**R0.10: Renombres como elevación teórica**
Cuando una categoría crece (≥3 versiones de definición, ≥2x propiedades,
≥3x incidentes), `rename_detector` sugiere renombre a 3 niveles de
abstracción (conservador, moderado, transformador). El investigador
decide. El renombre no es cosmético — es **elevación teórica**:
el concepto se vuelve más abstracto y más potente.

---

## 1. El Patrón Maestro (Ingeniería)

Todo componente del pipeline (worker, endpoint, agente) debe cumplir **5 reglas de ingeniería** (además de REGLA 0):

```
┌─────────────────────────────────────────────────────────────────┐
│                  PATRÓN MAESTRO DE PIPELINE                      │
│                                                                  │
│  REGLA 1: Transiciones centralizadas                             │
│  ─────────────────────────────────                              │
│  SOLO agents/transitions.py modifica documentos.estado.          │
│  SOLO agents/transitions.py despacha la siguiente tarea.         │
│  Los workers llaman transition() al terminar.                    │
│                                                                  │
│  REGLA 2: Tracking obligatorio                                   │
│  ─────────────────────────                                      │
│  Toda tarea despachada crea un registro en pipeline_tasks.       │
│  Campos obligatorios: celery_task_id, task_name, queue,          │
│  status, doc_estado_before.                                      │
│                                                                  │
│  REGLA 3: Cancelabilidad                                         │
│  ──────────────────────                                          │
│  Toda tarea Celery usa base=AbortableTask.                       │
│  Todo worker respeta SIGTERM (cleanup en finally).               │
│  Toda tarea es revocable vía admin.py.                           │
│                                                                  │
│  REGLA 4: Resumibilidad (opcional pero recomendado)              │
│  ─────────────────────────────────────────                      │
│  Tareas multi-step deben usar task_step_checkpoints.             │
│  Al resumir: limpiar pasos in_progress, saltar completados.     │
│                                                                  │
│  REGLA 5: Optimistic locking en estado                           │
│  ───────────────────────────────────                            │
│  UPDATE documentos SET estado = :next                            │
│  WHERE id = :did AND estado = :current                           │
│  Si rowcount=0 → otro proceso ya transicionó.                    │
└─────────────────────────────────────────────────────────────────┘
```

### 1.1 Anatomía de un worker que cumple el patrón

```python
@app.task(name="mi_tarea", base=AbortableTask, bind=True)
def mi_tarea(self, doc_id: str, project_id: str) -> dict:
    session = SessionLocal()
    try:
        # 1. Check abort
        if self._aborted:
            raise TaskCancelledError()

        # 2. Ejecutar lógica de negocio
        resultado = hacer_el_trabajo(session, doc_id)

        # 3. Transicionar (REGLA 1)
        from agents.transitions import transition
        transition(session, doc_id, project_id,
                   from_state="estado_actual",
                   task_name="mi_tarea",
                   success=True)

        return {"status": "completed", "doc_id": doc_id}

    except TaskCancelledError:
        return {"status": "cancelled", "doc_id": doc_id}
    except Exception as e:
        from agents.transitions import transition
        transition(session, doc_id, project_id,
                   from_state="estado_actual",
                   task_name="mi_tarea",
                   success=False)
        raise
    finally:
        session.close()
```

### 1.2 Anatomía del despachador (orchestrator o transition)

```python
def despachar_siguiente_tarea(session, doc_id, project_id):
    """REGLA 2 + REGLA 5"""
    result = session.execute(
        text("UPDATE documentos SET estado = :next WHERE id = :did AND estado = :current"),
        {"next": next_state, "did": doc_id, "current": current_state}
    )
    if result.rowcount == 0:
        return None

    task = celery_app.send_task(task_name, args=[...], queue=queue)

    run_id = _get_active_run(session, project_id)
    if run_id:
        session.execute(
            text("INSERT INTO pipeline_tasks (...) VALUES (...)"),
            {"rid": run_id, "did": doc_id, "tid": task.id, ...}
        )
        session.commit()

    return {"next_task": task_name, "task_id": task.id}
```

### 1.3 Anatomía de un paso HITL (Human-in-the-Loop)

```python
def hitl_gate(session, project_id: str, gate_name: str,
              proposal: dict, critic_verdict: dict) -> str:
    """
    REGLA 0.1 — Todo paso de decisión teórica requiere HITL.

    El pipeline se PAUSA aquí. El frontend muestra la propuesta
    y el veredicto del critic. El investigador decide:
      - ACCEPT → continuar al siguiente paso
      - MODIFY → re-ejecutar proposer con feedback del investigador
      - REJECT → archivar decisión con nota, intentar alternativa

    Returns: "accepted", "modify", o "rejected"
    """
    # 1. Guardar proposal + critic_verdict en DB
    session.execute(
        text("""
            INSERT INTO hitl_decisions
            (project_id, gate_name, proposal, critic_verdict, status)
            VALUES (:pid, :gate, :prop, :verdict, 'pending')
        """),
        {"pid": project_id, "gate": gate_name,
         "prop": json.dumps(proposal),
         "verdict": json.dumps(critic_verdict)}
    )
    session.commit()

    # 2. Notificar frontend vía WebSocket/SSE
    notify_frontend(project_id, {
        "type": "hitl_required",
        "gate": gate_name,
        "proposal": proposal,
        "critic_verdict": critic_verdict
    })

    # 3. Bloquear hasta que el investigador responda
    #    (implementado como polling desde el frontend o callback)
    decision = wait_for_hitl_decision(session, project_id, gate_name)
    return decision
```

---

## 2. La Máquina de Estados Completa

### 2.1 Estados de documento (nivel documento)

```
                    ┌──────────┐
                    │  crudo   │ (doc subido, sin procesar)
                    └────┬─────┘
                         │ segmentar_documento
                    ┌────▼─────┐
                    │segmentando│ (NLP trabajando)
                    └────┬─────┘
                         │ NLP termina
                    ┌────▼─────┐
                    │segmentado │ (segmentos listos)
                    └────┬─────┘
                         │ process_document_agents_a
                    ┌────▼──────┐
                    │procesando │ (A1→A2→A3 corriendo)
                    └────┬──────┘
                         │ agentes terminan
                    ┌────▼─────┐
                    │  listo   │ (doc individual completado)
                    └────┬─────┘
                         │ process_synthesis_agents_b (auto, >=3 docs)
                    ┌────▼──────┐
                    │sintetizado│ (cross-doc synthesis completada)
                    └───────────┘

   ┌──────────┐
   │  error   │ (cualquier etapa puede fallar)
   └────┬─────┘
        │ restart / resume
        ▼
   vuelve al estado anterior
```

### 2.2 Estados de proyecto (nivel proyecto — post open coding)

```
   ┌──────────────┐
   │  collecting  │ (subiendo docs, fase inicial)
   └──────┬───────┘
          │ >=3 docs con estado 'listo'
   ┌──────▼───────┐
   │    coding    │ (open coding + cross-doc synthesis en curso)
   └──────┬───────┘
          │ todos los docs 'sintetizado'
   ┌──────▼───────────┐
   │ finding_cc        │ (Fase A: core category detection)
   │  ├─ proposing_mc  │ (A1+A2 ejecutándose)
   │  ├─ hitl_mc       │ 🛑 esperando decisión del investigador
   │  ├─ proposing_cc  │ (A3+A4 ejecutándose)
   │  └─ hitl_cc       │ 🛑 esperando decisión del investigador
   └──────┬───────────┘
          │ core concern + core category confirmados
   ┌──────▼───────────┐
   │ reducing          │ (Fase B: selective reduction)
   │  ├─ proposing     │ (B1+B2 ejecutándose)
   │  └─ hitl          │ 🛑 esperando decisión del investigador
   └──────┬───────────┘
          │ reduced_code_system confirmado
   ┌──────▼───────────┐
   │ saturating        │ (Fase C: core saturation loop)
   │  ├─ loop_active   │ (C1+C2 iterando cat×doc)
   │  ├─ hitl_cat      │ 🛑 confirmar saturación por categoría
   │  ├─ theo_sampling │ (TheoSampler buscando nuevos docs)
   │  └─ all_saturated │ (todas las cats ≥4 saturadas)
   └──────┬───────────┘
          │ todas las categorías saturadas
   ┌──────▼───────────┐
   │ building_db       │ (Fase D: Database A/B)
   │  ├─ nodes         │ (D1+D2: nodos planos)
   │  ├─ hitl_nodes    │ 🛑 confirmar sistema de nodos
   │  ├─ edges         │ (D3+D4: relaciones)
   │  └─ hitl_edges    │ 🛑 confirmar sistema de relaciones
   └──────┬───────────┘
          │ global saturation check (Fase E)
   ┌──────▼───────────┐
   │ playground_ready  │ (listo para theoretical playground)
   └──────┬───────────┘
          │ prepare_playground
   ┌──────▼───────────┐
   │    completed      │ (estudio cerrado)
   └──────────────────┘
```

### 2.3 Estados actuales vs necesarios

| Estado | Nivel | ¿Existe? | ¿Cumple R0? | ¿Cumple R1-R5? |
|--------|-------|----------|-------------|----------------|
| `crudo` | doc | ✅ | N/A (pre-teórico) | ✅ |
| `segmentando` | doc | ✅ | N/A | ✅ |
| `segmentado` | doc | ✅ | N/A | ✅ |
| `procesando` | doc | ✅ | N/A | ✅ |
| `listo` | doc | ✅ | N/A | ✅ |
| `error` | doc | ✅ | N/A | ✅ |
| `sintetizado` | doc | ❌ | N/A | ❌ |
| `collecting` | proyecto | ❌ | — | — |
| `coding` | proyecto | ❌ | — | — |
| `finding_cc` | proyecto | ❌ | ❌ (sin HITL) | ❌ |
| `reducing` | proyecto | ❌ | ❌ (sin HITL) | ❌ |
| `saturating` | proyecto | ❌ | ❌ (sin loop) | ❌ |
| `building_db` | proyecto | ❌ | ❌ (no existe) | ❌ |
| `playground_ready` | proyecto | ❌ | — | ❌ |
| `completed` | proyecto | ❌ | — | ❌ |

---

## 3. Etapas del Pipeline — Auditoría de Coherencia

Cada etapa se audita en **dos dimensiones**: metodológica (R0) y de ingeniería (R1-R5).

### 3.1 ✅ Segmentación — CUMPLE

| Dimensión | Regla | Estado |
|-----------|-------|--------|
| Metodológica | R0 | N/A (pre-teórico) |
| Ingeniería | R1 Transiciones | ✅ NLP worker → `transitions.transition("segmentado", ...)` |
| Ingeniería | R2 Tracking | ✅ `_dispatch_next()` crea PipelineTask |
| Ingeniería | R3 Cancelabilidad | ✅ `AbortableTask` en NLP worker |
| Ingeniería | R4 Resumibilidad | ⬜ Pendiente (checkpoints en NLP) |
| Ingeniería | R5 Optimistic lock | ✅ `transition()` usa `WHERE estado = current` |

### 3.2 ✅ Agentes A — CUMPLE

| Dimensión | Regla | Estado |
|-----------|-------|--------|
| Metodológica | R0 | N/A (open coding individual) |
| Ingeniería | R1-R5 | ✅ Completo |

### 3.3 ⚠️ Phase B (Síntesis Cross-Document) — PARCIAL

| Dimensión | Regla | Estado |
|-----------|-------|--------|
| Metodológica | R0.2 Dependencias | ✅ Ejecuta después de ≥3 docs 'listo' |
| Metodológica | R0.3 Separación | ✅ Opera sobre códigos existentes, no recodifica |
| Ingeniería | R1 Transiciones | ❌ No actualiza estado de docs |
| Ingeniería | R2 Tracking | ❌ Sin PipelineTask |
| Ingeniería | R3 Cancelabilidad | ✅ `AbortableTask` |
| Ingeniería | R4 Resumibilidad | ❌ Sin checkpoints |
| Ingeniería | R5 Optimistic lock | ❌ Sin optimistic lock |

### 3.4 ❌ Main Concern / Core Category Detection — NO CUMPLE

| Dimensión | Regla | Estado |
|-----------|-------|--------|
| **Metodológica** | **R0.1 HITL** | **❌ CRÍTICO. `task_a14_main_concern` ejecuta proposer+critic sin pausa HITL. El investigador no confirma el main concern.** |
| **Metodológica** | **R0.2 Dependencias** | **❌ CRÍTICO. `task_a15_core_emergence` corre en paralelo con `task_a14` en lugar de serial.** |
| Metodológica | R0.3 Separación | ✅ No invoca open coding |
| Ingeniería | R1 Transiciones | ❌ Sin `transitions.transition()` |
| Ingeniería | R2 Tracking | ❌ Sin PipelineTask |
| Ingeniería | R3 Cancelabilidad | ❌ Sin `AbortableTask` |
| Ingeniería | R4 Resumibilidad | ❌ Sin checkpoints |
| Ingeniería | R5 Optimistic lock | ❌ Sin optimistic lock |

**Problema de fondo:** El core concern es la decisión teórica más importante del estudio CGT. Automatizarla sin HITL viola el principio fundamental de que el investigador debe "ganarse" la categoría central mediante comparación constante. Ningún algoritmo puede finalizar esta decisión.

### 3.5 ❌ Selective Elaboration — NO CUMPLE

| Dimensión | Regla | Estado |
|-----------|-------|--------|
| **Metodológica** | **R0.1 HITL** | **❌ CRÍTICO. `trigger_selective_elaboration` ejecuta todas las tareas sin gates HITL.** |
| **Metodológica** | **R0.2 Dependencias** | **❌ CRÍTICO. Las tareas se ejecutan como grupo paralelo ignorando dependencias seriales.** |
| **Metodológica** | **R0.3 Separación** | **❌ CRÍTICO. Invoca `invoke_graph()` que contiene nodos de open coding (`node_batch_code`, `node_map_synthesize`) dentro de fase selectiva.** |
| Metodológica | **Selective Reduction** | **❌ AUSENTE. No hay paso de delimitación/reducción entre core concern y elaboración.** |
| Metodológica | **Saturation Loop** | **❌ AUSENTE. No hay loop iterativo cat×doc con criterio de término.** |
| Metodológica | **TheoSampler** | **❌ Pre-emptive. Se ejecuta al inicio en lugar de bajo demanda.** |
| Metodológica | **Database A/B** | **❌ AUSENTE. No se construyen nodos planos ni edges.** |
| Ingeniería | R1-R5 | ❌ Ninguna regla cumplida |

### 3.6 ❌ LangGraph (invoke_graph) — NO CUMPLE

| Dimensión | Regla | Estado |
|-----------|-------|--------|
| **Metodológica** | **R0.3 Separación** | **❌ El grafo mezcla nodos de open coding y selective coding en el mismo workflow.** |
| Metodológica | R0.1 HITL | ⚠️ Parcial: `node_hitl_review` existe pero no está integrado con los gates del pipeline principal |
| Ingeniería | R1 Transiciones | ❌ Opera con `AnalysisState`, no `documentos.estado` |
| Ingeniería | R2 Tracking | ❌ Sin PipelineTask |
| Ingeniería | R3 Cancelabilidad | ❌ Sin `AbortableTask` |
| Ingeniería | R4 Resumibilidad | ✅ LangGraph PostgresSaver |
| Ingeniería | R5 Optimistic lock | ❌ N/A |

### 3.7 ❌ Theoretical Playground — AUDITORÍA COMPLETA

**La auditoría original trataba el Playground como "fase post-selectiva sin decisiones teóricas". Esto es incorrecto. El Theoretical Playground TOMA decisiones teóricas constantemente — solo que no son del tipo "ejecutar tarea → terminar". Son del tipo "elaborar → expandir → iterar".**

| Dimensión | Regla | Estado | Corrección |
|-----------|-------|--------|------------|
| **Metodológica** | **R0.1 HITL** | **❌** | El HITL es ubicuo: arrastrar blobs (propone relación), clic en fisuras (expande divergencia), confirmar renombres, absorber ghosts. Son **interacciones directas** con el ecosistema. |
| **Metodológica** | **R0.4 Elaboración** | **❌** | No "ejecuta tareas". Elabora relaciones.  emite , no . |
| **Metodológica** | **R0.5 Herramientas** | **❌** | Los 12 códigos teóricos son visibles y modificables. El investigador inspecciona , ajusta umbrales, crea nuevos. |
| **Metodológica** | **R0.6 Sesión** | **❌** | Es un workspace persistente, no un paso.  y  persisten el estado entre sesiones. |
| **Metodológica** | **R0.7 Divergencia** | **❌** | La evidencia divergente NO es error. Fisuras doradas = oportunidades de expansión. |
| **Metodológica** | **R0.8 Sorting** | **❌** |  +  = sorting log: homeless memos, montones delgados, capas sin cubrir. |
| **Metodológica** | **R0.9 No linealidad** | **❌** | El investigador puede volver a selective coding (). |
| **Metodológica** | **R0.10 Renombres** | **❌** |  +  = elevación teórica. No es cosmético. |
| Ingeniería | R1 Transiciones | N/A | Solo aplica a tareas deterministas. Las elaboraciones usan . |
| Ingeniería | R2 Tracking | ⚠️ |  +  +  = trazabilidad completa (distinta a PipelineTask pero equivalente). |
| Ingeniería | R3 Cancelabilidad | N/A | No hay "cancelar" una sesión interactiva. El estado se persiste automáticamente. |
| Ingeniería | R4 Resumibilidad | ✅ |  persiste posiciones. El investigador retoma donde dejó. |
| Ingeniería | R5 Optimistic lock | ⚠️ |  se incrementa en cada save. |

---

## 4. Plan de Modificaciones Pendientes

### PRE-FASE: Refactor metodológico del pipeline selectivo

**Antes de aplicar reglas de ingeniería, el flujo debe corregirse metodológicamente.**

**Archivos:** `workers/heavy/tasks.py`, `backend/app/core/workflow.py`, `agents/transitions.py`

- [ ] **Eliminar `trigger_selective_elaboration` actual** — reemplazar por `selective_coding_coordinator` que implemente el pipeline A→B→C→D→E con gates HITL
- [ ] **Eliminar ejecución paralela** de tareas en selective — reemplazar por ejecución serial con dependencias explícitas
- [ ] **Separar LangGraph**: `invoke_graph()` solo debe contener nodos de open coding (`node_segment_and_index`, `node_extract_entities`, `node_batch_code`, `node_map_synthesize`, `node_reduce_synthesize`). Los nodos de selective coding (`node_find_core_concern`, `node_theosampler_evaluate`, `node_prepare_playground`) deben migrarse al coordinator.
- [ ] **Implementar HITL gates**: nuevo modelo `hitl_decisions` + endpoint `POST /projects/{id}/hitl/decide` + frontend modal
- [ ] **TheoSampler → demanda**: mover de posición inicial a dentro del saturation loop, solo cuando `did_state_expand=false` por 3 iteraciones

---

### Fase 5: Extender el patrón a Phase B
**Archivos:** `workers/heavy/tasks.py`, `workers/heavy/agents_b.py`, `agents/transitions.py`

- [ ] `process_synthesis_agents_b` → `base=AbortableTask, bind=True`
- [ ] Agregar tracking: PipelineTask con `document_id=NULL` (tarea de proyecto)
- [ ] Agregar `task_step_checkpoints` para B1, B2, B2.5, B3
- [ ] Al terminar, llamar `transitions._maybe_trigger_phase_b` → dispatch next
- [ ] Nuevo estado: `sintetizado`

### Fase 6: Implementar Fase A — Core Category Detection (con HITL)
**Archivos:** `workers/heavy/tasks.py`, `agents/transitions.py`, `backend/app/api/v1/projects.py`

- [ ] **A1+A2**: `task_main_concern_pipeline` → `base=AbortableTask, bind=True`
  - Ejecuta `main_concern_proposer` → `main_concern_critic` serialmente
  - Al terminar critic: GUARDAR propuesta + veredicto, NOTIFICAR frontend, **PAUSAR**
  - Endpoint: `POST /projects/{id}/hitl/main-concern` → `{decision: "accept"|"modify"|"reject"}`
  - Si MODIFY → re-ejecutar proposer con feedback del investigador
  - Si ACCEPT → avanzar a A3
- [ ] **A3+A4**: `task_core_emergence_pipeline` → igual patrón
  - Depende de A1+A2 completado (no paralelo)
  - HITL gate para confirmar core category
- [ ] Nuevos estados de proyecto: `finding_cc` con sub-estados `proposing_mc`, `hitl_mc`, `proposing_cc`, `hitl_cc`

### Fase 7: Implementar Fase B — Selective Reduction (con HITL)
**Archivos:** `workers/heavy/tasks.py`, `agents/transitions.py`

- [ ] **B1+B2**: `task_selective_reduction_pipeline` → `base=AbortableTask, bind=True`
  - Ejecuta `selective_reduction_proposer` → `selective_reduction_critic` serialmente
  - HITL gate: investigador confirma/rechaza descartes y fusiones
  - Los códigos descartados se ARCHIVAN (no se eliminan) con `discard_rationale`
- [ ] Nuevo estado de proyecto: `reducing` con sub-estados `proposing`, `hitl`

### Fase 8: Implementar Fase C — Core Saturation Loop (con HITL)
**Archivos:** `workers/heavy/tasks.py`, `agents/transitions.py`

- [ ] **C1+C2**: `task_core_saturation_loop` → `base=AbortableTask, bind=True`
  - Itera sobre categorías con score ≥4 × documentos
  - Por cada iteración: `core_saturation_proposer` → `core_saturation_critic`
  - Si `did_state_expand=true`: continuar loop con siguiente doc
  - Si `did_state_expand=false` por 3 iteraciones consecutivas: HITL gate para confirmar saturación de esta categoría
  - Si categoría no satura y no hay más docs: TheoSampler (buscar nuevos) → repetir
- [ ] **TheoSampler reactivo**: mover de posición inicial a dentro del loop
- [ ] **MemoMaker integrado**: después de saturar cada categoría, ejecutar nodo Generate → Simplificación → Correlaciones
- [ ] Agregar `task_step_checkpoints` por categoría
- [ ] Nuevo estado de proyecto: `saturating` con sub-estados `loop_active`, `hitl_cat`, `theo_sampling`, `all_saturated`

### Fase 9: Implementar Fase D — Database A/B (con HITL)
**Archivos:** `workers/heavy/tasks.py`, `agents/transitions.py`

- [ ] **D1+D2**: `task_database_a_pipeline` → nodos planos
- [ ] **D3+D4**: `task_database_b_pipeline` → edges con relationship_type
- [ ] Ambos con HITL gates para confirmación del investigador
- [ ] Nuevo estado de proyecto: `building_db`

### Fase 10: Implementar Fase E — Global Saturation Check
**Archivos:** `workers/heavy/tasks.py`, `agents/transitions.py`

- [ ] Verificar 3 condiciones:
  1. Todas las cats ≥4 saturadas
  2. Relaciones inter-categoriales saturadas (5 docs, 0 contraejemplos)
  3. Buffer de residuos revisado
- [ ] HITL gate final: investigador cierra codificación selectiva
- [ ] Transicionar a `playground_ready`

### Fase 11: Unificar estados de proyecto
**Archivos:** `models/domain/project.py`, `agents/transitions.py`

- [ ] Agregar estados de proyecto: `collecting`, `coding`, `finding_cc`, `reducing`, `saturating`, `building_db`, `playground_ready`, `completed`
- [ ] `transitions.py` debe manejar transiciones de proyecto (no solo de documento)
- [ ] Modelo `hitl_decisions`: `project_id`, `gate_name`, `proposal`, `critic_verdict`, `status`, `researcher_decision`, `researcher_note`, `created_at`, `decided_at`

### Fase 12: Theoretical Playground — Infraestructura y sesión

**Archivos:** `workers/heavy/tasks.py`, `backend/app/core/workflow.py`, `backend/app/services/elaboration_engine.py`, `backend/app/services/ghost_connector.py`

#### 12.1 Entrada al Playground (T25)

- [ ] `node_prepare_playground` → seed de 12 códigos teóricos (`theory_seeder`)
- [ ] Crear `EcosystemLayout` inicial con `physics_params` default
- [ ] `GhostConnector.generate_ghost_blobs()` → clasificar memos huérfanos con `ghost_blob_mapper` (PRO)
- [ ] Generar `RecommendationEngine.generate_recommendations()` inicial
- [ ] Transicionar proyecto a `playground_ready`
- [ ] Frontend: cargar ruta `/projects/:id/theory` → `PlaygroundPage`

#### 12.2 Sesión interactiva (no es pipeline, es workspace)

El Playground NO sigue el patrón de tareas Celery. Es una sesión interactiva con:

- **Estado persistente:** `EcosystemLayout` (posiciones, ghosts, fog zones, physics)
- **Registro de acciones:** `ElaborationMemo` (cada iteración: relationship_proposed, divergence_expanded, ghost_absorbed, rename_applied)
- **Relaciones:** `ConceptualRelationship` (converging/diverging evidence, elaboration_status, position_tension)
- **Historial de categorías:** `CategoryDefinitionVersion` (versiones, triggers, renombres)

#### 12.3 HITL en el Playground (R0.1, R0.4-R0.10)

A diferencia del selective coding (gates formales Proposer→Critic→HITL), el HITL en el Playground es **interacción directa**:

| Acción del investigador | Sistema responde | Regla |
|------------------------|-----------------|-------|
| Arrastrar dos blobs juntos | Menú contextual de código teórico → `conceptual_elaborator` (PRO) → tendril con evidencia convergente/divergente | R0.1, R0.4 |
| Clic en fisura dorada | Popup con opciones de expansión (condición, subtipo, ruta alternativa) → `elaborate_divergence()` | R0.7 |
| Arrastrar ghost-blob a blob | Confirmación de absorción → `absorb_ghost_blob()` → blob crece, posible shimmer de renombre | R0.1 |
| Clic en shimmer (✦) | `RenameModal` con 3 niveles de abstracción → `apply_rename()` → blob cambia de color | R0.10 |
| Clic en neblina | Recomendación de muestreo → opción de volver a selective coding | R0.9 |
| Clic en "Sync gaps" | `SaturationGapAnalyzer.full_analysis()` → recomendaciones actualizadas | R0.8 |

#### 12.4 ElaborationEngine (T12)

- [ ] `elaborate_relationship()`: carga categorías + código teórico → invoca `conceptual_elaborator` (PRO) → persiste `ConceptualRelationship` + `ElaborationMemo`
- [ ] `elaborate_divergence()`: aplica `divergence_resolution` → `elaboration_status='expanded'` → `position_tension=0`
- [ ] `absorb_ghost_blob()`: crea `CategoryDefinitionVersion` (trigger='ghost_absorbed') → crea `ElaborationMemo`
- [ ] `_get_lens_instruction()`: construye instrucción específica desde `evaluation_logic` del código teórico

#### 12.5 Sorting Log (R0.8)

- [ ] El `RecommendationEngine` evalúa 5 dimensiones: conexiones sugeridas, ghosts sin absorber, renombres sugeridos, zonas de neblina, tensiones sin resolver
- [ ] El `ElaborationMemo` registra cada iteración con `ecosystem_snapshot`
- [ ] Las categorías huérfanas y capas sin cubrir son visibles en el frontend
- [ ] Los "homeless memos" (ghost-blobs no absorbidos) persisten en los márgenes del canvas

#### 12.6 No linealidad (R0.9)

- [ ] El StateGraph soporta `after_gap_review → segment_and_index` (volver a selective coding)
- [ ] El `process_new_data` re-ejecuta Fases 1-5b sobre documentos nuevos
- [ ] Después de re-codificar, el investigador puede volver al Playground con `node_prepare_playground`
- [ ] Las relaciones elaboradas previamente se preservan (no se pierden al re-samplear)

### Fase 13: Frontend — Overlay coherente
**Archivos:** `frontend/src/pages/Project.tsx`, `frontend/src/components/pipeline/`

- [ ] Reemplazar PIPELINE_STAGES con etapas reales:
  ```
  segment → agents → synthesis → find_cc → reduce → saturate → build_db → playground
  ```
- [ ] Componente `HITLModal`: muestra propuesta + veredicto del critic + opciones ACCEPT/MODIFY/REJECT
- [ ] Vista `PlaygroundPage` (`/projects/:id/theory`): layout de 3 columnas (GuidePanel 280px | EcosystemCanvas flex | ElaborationPanel 340px)
- [ ] `EcosystemCanvas`: SVG 800×600 con fondo oscuro, física d3-force, blobs arrastrables, tendriles con fisuras, ghost-blobs, neblina
- [ ] `CategoryBlob`: gradiente radial con shimmer, pulse, glow, drag & drop
- [ ] `RelationshipTendril`: curvas Bézier con grosor variable y fisuras doradas (#FFD700)
- [ ] `GhostBlob`: círculos translúcidos arrastrables hacia blobs
- [ ] `ElaborationPanel`: BlobDetail (nombre, definición, propiedades, timeline) + TendrilDetail (evidencia, ajuste conceptual)
- [ ] `RecommendationGuide`: 5 secciones colapsables (conexiones, ghosts, renombres, neblina, tensiones)
- [ ] `RenameModal`: 3 niveles de abstracción + custom input
- [ ] `CategoryEvolutionPanel`: timeline de versiones con triggers y fechas
- [ ] WebSocket/SSE para notificaciones HITL en tiempo real
- [ ] Cada etapa se actualiza vía `getPipelineLog`
- [ ] Mostrar progreso por documento/categoría dentro de cada etapa
- [ ] Botones de stop/cancel/resume conscientes de la etapa actual

---

## 5. Reglas de Delegación PRO vs FLASH

Basado en el análisis de los 34 prompts existentes y los 8 nuevos:

| Tipo de tarea | Modelo | Criterio |
|---------------|--------|----------|
| Generación teórica (proposers) | **PRO** | Requiere razonamiento cualitativo, sensibilidad teórica, juicio metodológico |
| Evaluación metodológica compleja (critics de fusión, grounding, abstracción) | **PRO** | Requiere entender CGT en profundidad |
| Comparación estructurada (interchangeability, diff paradigm_state) | **FLASH** | Criterios explícitos, tarea de matching |
| Extracción de datos (incidentes, entidades) | **FLASH** | Tarea mecánica, sin juicio teórico |
| Síntesis y resumen | **FLASH** | Compresión de información, no generación |

### 5.1 Matriz PRO/FLASH del pipeline selectivo

| Agente | Modelo | Razón |
|--------|--------|-------|
| `main_concern_proposer` | PRO | Sensado cualitativo de preocupación latente |
| `main_concern_critic` | PRO | Evaluación de grounding empírico y abstracción |
| `core_emergence_proposer` | PRO | Juicio cualitativo sobre centralidad y theoretical grab |
| `core_emergence_critic` | **FLASH** | Interchangeability test: criterios claros (valid/refine/split) |
| `selective_reduction_proposer` | PRO | Requiere entender el core y evaluar relación de cada código |
| `selective_reduction_critic` | PRO | Juicio sobre uniformidad subyacente (análogo a batch_coder_critic) |
| `core_saturation_proposer` | PRO | Síntesis compleja integrando incidentes con paradigm_state |
| `core_saturation_critic` | **FLASH** | Diff estructurado: new_incident vs existing_paradigm_state. Corre frecuentemente (cat×doc) — ahorro significativo |

---

## 6. Registro de Prompts y Contrato de Agentes

### 6.1 Prompts existentes (Era 1 — `.txt`, Era 2 — `.md`)

| Directorio | Formato | Agentes | Estado |
|------------|---------|---------|--------|
| `deepseek_pro/` | `.txt` con `-- headers` | a1, a2, a3, b1, b2, b3 | Legacy — mantener como referencia |
| `deepseek_flash/` | `.txt` con `-- headers` + few-shot | a1, a2, a3, b1, b2, b3 | Legacy |
| `pro/` | `.md` con YAML frontmatter | batch_coder_producer, batch_coder_critic, clusterizador_informado, core_concern_finder, final_report, hypothesis_generation, map_synthesis, reduce_synthesis | **Activo** |
| `flash/` | `.md` con YAML frontmatter | context_synthesizer, document_summarizer, entity_extraction, incident_extractor | **Activo** |

### 6.2 Prompts nuevos (Selective Coding — Fase 5b)

| Archivo | Carpeta | Modelo | Agente | Paso |
|---------|---------|--------|--------|------|
| `main_concern_proposer.md` | `pro/` | PRO | A14 | A1 |
| `main_concern_critic.md` | `pro/` | PRO | — | A2 |
| `core_emergence_proposer.md` | `pro/` | PRO | A15 | A3 |
| `core_emergence_critic.md` | `flash/` | FLASH | A16 | A4 |
| `selective_reduction_proposer.md` | `pro/` | PRO | NEW_SR | B1 |
| `selective_reduction_critic.md` | `pro/` | PRO | — | B2 |
| `core_saturation_proposer.md` | `pro/` | PRO | A25 | C1 |
| `core_saturation_critic.md` | `flash/` | FLASH | — | C2 |

### 6.3 Prompts pendientes (Database A/B — Fase D)

| Archivo | Carpeta | Modelo | Paso |
|---------|---------|--------|------|
| `database_a_proposer.md` | `pro/` | PRO | D1 |
| `database_a_critic.md` | `pro/` | PRO | D2 |
| `database_b_proposer.md` | `pro/` | PRO | D3 |
| `database_b_critic.md` | `pro/` | PRO | D4 |

### 6.4 Contrato de un agente `.md`

Todo prompt nuevo debe seguir este formato exacto:

```markdown
---
prompt_id: nombre_unico
version: 1.0.0
model_profile: pro | flash
description: Una oración describiendo qué hace.
langgraph_node: nombre_del_nodo_si_aplica
execution_order: "posición en el pipeline"
input_state: variable1, variable2
output_state: variable_output
depends_on: prompt_id_del_que_depende
prerequisite_for: prompt_id_que_requiere_esto
agent_id: AXX
triggers_on: Condición que dispara este agente
note: Notas para developers (no visible al LLM)
---

## System

[ROL]
...

[OBJETIVO]
...

[RESTRICCIONES]
...

## User

[SECCIÓN DE DATOS]
{variable}

## Output Schema

```json
{...}
```
```

---

## 7. Principios de Diseño para Futuras Extensiones

1. **Nunca automatizar una decisión teórica sin HITL.** Si el output del agente modifica la teoría (nuevo código, fusión, core concern, propiedad, relación), el investigador debe confirmar.

2. **El critic no reemplaza al investigador.** El critic evalúa con criterios CGT, pero su veredicto es una recomendación, no una decisión final.

3. **PRO para generar, FLASH para comparar.** Si la tarea es "crea algo nuevo" → PRO. Si es "¿esto es igual a esto otro?" → FLASH.

4. **El pipeline es un diálogo, no una línea de ensamblaje.** Cada gate HITL es una oportunidad para que el investigador refine, cuestione, o redirija el análisis. El sistema propone; el investigador dispone.

5. **La delimitación es tan importante como la generación.** Descartar un código con justificación metodológica es un output valioso, no un fracaso. El sistema debe tratar los descartes como ciudadanos de primera clase (archivados con rationale, recuperables).

6. **La saturación se demuestra, no se declara.** El sistema debe mostrar evidencia concreta (3 iteraciones sin `did_state_expand`, 5 documentos sin contraejemplos para relaciones) antes de afirmar saturación.
