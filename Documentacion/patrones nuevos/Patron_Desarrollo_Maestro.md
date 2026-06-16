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

---

## 8. Análisis de Alineación — Código Actual vs Patrón

> **Auditoría archivo-por-archivo del código existente (2026-06-16).**
>
> Cada componente se audita en 3 dimensiones: qué EXISTE (con número de línea), qué FALTA, y qué SPILLOVERS produce modificarlo.

### 8.0 Resumen de Alineación por Componente

| Componente | Estado | Brecha principal |
|------------|--------|------------------|
| `agents/transitions.py` | ⚠️ Parcial | Solo maneja estados de documento, no de proyecto. Sin `sintetizado`. |
| `core/workflow.py` | ❌ Desalineado | Mezcla open/selective coding. Sin Proposer→Critic→HITL. |
| `workers/heavy/tasks.py` | ❌ Desalineado | `trigger_selective_elaboration` viola R0.1, R0.2, R0.3. |
| `models/domain/` | ⚠️ Parcial | Theory models ✅. Falta `HitlDecision`. Project sin estados pipeline. |
| `api/v1/pipeline.py` | ⚠️ Parcial | Dispara stages antiguos. Sin endpoint HITL. |
| `api/v1/events.py` | ✅ Alineado | SSE + Redis pub/sub listo para HITL. |
| `services/` | ✅ Alineado | Todos los engines existen y cumplen el contrato. |
| `prompts/` | ❌ Incompleto | Faltan 12 prompts del pipeline selectivo. |
| `frontend/` | ⚠️ Parcial | Playground ✅. Pipeline stages antiguos. Sin HITLModal. |

---

### 8.1 `backend/app/agents/transitions.py` — Análisis Detallado

#### Lo que EXISTE ✅

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 26-41 | `NEXT` dict con estados doc: crudo→segmentando→segmentado→procesando→listo | ✅ Correcto |
| 44-107 | `transition()` con optimistic locking (`WHERE estado=current`) | ✅ Cumple REGLA 5 |
| 115-121 | `_to_error()` | ✅ Correcto |
| 124-177 | `_dispatch_next()` con PipelineTask tracking | ✅ Cumple REGLA 2 |
| 180-232 | `_maybe_trigger_phase_b()` con deduplicación vía `processing_states` | ✅ Correcto pero limitado |
| 235-257 | `_get_active_run()`, `_get_texto()` | ✅ Correcto |

#### Lo que FALTA ❌

| Elemento | Gravedad | Detalle |
|----------|----------|--------|
| Estado `sintetizado` | 🔴 | `NEXT` dict no tiene transición `listo → sintetizado`. Phase B debe actualizar docs a `sintetizado`. |
| Estados de proyecto | 🔴 | Solo maneja `documentos.estado`. No existe `proyectos.estado` con valores `collecting\|coding\|finding_cc\|reducing\|saturating\|building_db\|playground_ready\|completed`. |
| HITL gate | 🔴 | No hay función `hitl_gate()` que pause el pipeline, guarde proposal+verdict en DB, y espere confirmación. |
| `_maybe_trigger_phase_b` no usa `sintetizado` | 🟠 | Actualmente verifica `COUNT(*) WHERE estado='listo'`. Debería verificar `estado='sintetizado'`. |

#### Cambios requeridos

```python
# 1. Agregar 'sintetizado' al NEXT dict
NEXT: dict[str, tuple[str, str | None, str | None]] = {
    ...
    "listo": ("sintetizado", None, None),   # Phase B transiciona
    "sintetizado": (None, None, None),       # Terminal (espera selective coding)
    "error": ("crudo", None, None),
}

# 2. Agregar manejo de estados de proyecto
PROJECT_STATES = {
    "collecting": "coding",
    "coding": "finding_cc",
    "finding_cc": "reducing",
    "reducing": "saturating",
    "saturating": "building_db",
    "building_db": "playground_ready",
    "playground_ready": "completed",
}

def transition_project(session, proyecto_id, from_state, to_state) -> bool:
    """Transiciona el estado de un proyecto con optimistic locking."""
    result = session.execute(
        text("UPDATE proyectos SET estado = :next WHERE id = :pid AND estado = :current"),
        {"next": to_state, "pid": proyecto_id, "current": from_state},
    )
    session.commit()
    return result.rowcount > 0

# 3. Agregar hitl_gate()
def hitl_gate(session, project_id, gate_name, proposal, critic_verdict) -> str:
    """Inserta en hitl_decisions, notifica frontend vía Redis, espera decisión."""
    session.execute(
        text("""
            INSERT INTO hitl_decisions
            (id, project_id, gate_name, proposal, critic_verdict, status)
            VALUES (gen_random_uuid(), :pid, :gate, :prop, :verdict, 'pending')
        """),
        {"pid": project_id, "gate": gate_name,
         "prop": json.dumps(proposal), "verdict": json.dumps(critic_verdict)}
    )
    session.commit()
    from app.api.v1.events import publish_event
    publish_event(project_id, "hitl_required", {
        "gate": gate_name, "proposal": proposal, "critic_verdict": critic_verdict
    })
    decision = wait_for_hitl_decision(session, project_id, gate_name)
    return decision

# 4. Actualizar _maybe_trigger_phase_b
# SELECT COUNT(*) WHERE estado = 'sintetizado'  # antes: estado = 'listo'
```

#### Spillovers

- **`_maybe_trigger_phase_b`** se dispara cuando un doc llega a `listo` (L104). Con `sintetizado`, `process_synthesis_agents_b` debe llamar `transition(session, doc_id, ..., "listo", "process_synthesis_agents_b", True)` para cada doc → eso transiciona a `sintetizado`. **Spillover:** `process_synthesis_agents_b` en `workers/heavy/tasks.py` debe iterar docs y transicionarlos.

---

### 8.2 `backend/app/core/workflow.py` — Análisis Detallado

#### Lo que EXISTE ✅

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 34-91 | `AnalysisState` TypedDict | ✅ Cubre campos necesarios |
| 99-130 | `node_segment_and_index` | ✅ Open coding (conservar) |
| 133-150 | `node_extract_entities` | ✅ Open coding (conservar) |
| 153-179 | `node_batch_code` | ✅ Open coding (conservar) |
| 182-209 | `node_map_synthesize` | ✅ Open coding (conservar) |
| 212-216 | `node_reduce_synthesize` | ✅ Open coding (conservar) |
| 287-310 | `node_hitl_review` | ⚠️ Solo hipótesis, no es suficiente |
| 359-433 | `build_glaser_graph()` | ❌ Mezcla open + selective coding |
| 531-582 | `node_theosampler_evaluate` | ⚠️ Pre-emptive, debe ser reactivo |
| 585-618 | `node_hitl_gap_review` | ✅ Correcto pero aislado |
| 660-721 | `node_prepare_playground` | ✅ Correcto |
| 767-853 | `build_glaser_graph_with_feedback()` | ❌ Mismo problema que el grafo base |

#### Lo que FALTA ❌

| Elemento | Gravedad | Detalle |
|----------|----------|--------|
| `node_find_core_concern` (L219-235) viola R0.1 | 🔴 | Llama `task_a14_main_concern()` directamente, sin Proposer→Critic→HITL. |
| `node_find_core_concern` viola R0.2 | 🔴 | No ejecuta A1+A2 serialmente, ni A3+A4 después. Es una sola llamada. |
| Sin `node_selective_reduction` | 🔴 | Fase B del selective coding no existe en el grafo. |
| Sin `node_core_saturation` | 🔴 | Fase C no existe. |
| Sin `node_database_a` / `node_database_b` | 🔴 | Fase D no existe. |
| Sin `node_global_saturation_check` | 🔴 | Fase E no existe. |
| `build_glaser_graph()` mezcla nodos | 🔴 | `find_core_concern`, `theosampler_evaluate`, `prepare_playground` son selective coding, en el mismo grafo que `batch_code` (open coding). |
| El grafo no usa `transitions.py` | 🟠 | Opera con `AnalysisState`, no con `documentos.estado`. Sin optimistic locking ni PipelineTask. |

#### Decisión arquitectónica

El grafo actual debe dividirse en **DOS componentes separados:**

1. **Grafo A — Open Coding:** `segment_and_index → extract_entities → batch_code → map_synthesize → reduce_synthesize` (determinista, sin HITL)
2. **Pipeline B — Selective Coding:** No necesita un StateGraph de LangGraph. Es un **orchestrator secuencial** (`selective_coding_coordinator`) que despacha tareas Celery una tras otra con gates HITL entre fases.

Los nodos extraídos (`node_find_core_concern`, `node_theosampler_evaluate`, `node_hitl_gap_review`, `node_process_new_data`, `node_prepare_playground`) se convierten en funciones standalone invocadas desde el coordinator.

#### Cambios requeridos

```python
# workflow.py — El grafo se reduce a solo open coding
builder.add_node("segment_and_index", node_segment_and_index)
builder.add_node("extract_entities", node_extract_entities)
builder.add_node("batch_code", node_batch_code)
builder.add_node("map_synthesize", node_map_synthesize)
builder.add_node("reduce_synthesize", node_reduce_synthesize)
# El grafo termina en reduce_synthesize → END

# build_glaser_graph_with_feedback() se elimina.
# Los nodos E07-E08 + T25 migran al coordinator en workers/heavy/tasks.py.
```

#### Spillovers

- **`invoke_graph()` en `workers/heavy/tasks.py`** (L1453-1518): Invoca `build_glaser_graph()`. Después del split, solo debe invocar el grafo reducido de open coding.
- **`trigger_selective_elaboration`** (L1399): Llama `invoke_graph()`. Al eliminarse, `invoke_graph()` solo se usa para open coding.
- **`node_find_core_concern`** importa `task_a14_main_concern` de `workers.heavy.tasks`. Esta dependencia circular implícita desaparece.

---

### 8.3 `workers/heavy/tasks.py` — Análisis Detallado

#### Lo que EXISTE ✅

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 1181-1232 | `task_a14_main_concern` | ⚠️ Existe pero sin critic ni HITL |
| 1236-1278 | `task_a15_core_emergence` | ⚠️ Existe pero paralelo (no serial) |
| 1282-1323 | `task_a16_interchangeability` | ✅ Correcto como utilidad |
| 1327-1390 | `task_a04_group_constructs` | ✅ Correcto |
| 929-1002 | `task_a06_theoretical_sample` | ⚠️ Pre-emptive, debe ser reactivo |
| 1006-1082 | `task_a01_integrate_paradigm` | ✅ Correcto como utilidad |
| 1086-1172 | `task_a07_build_evidence_map` | ✅ Correcto |
| 641-806 | `process_document_agents_a` | ✅ Cumple R1-R5 |
| 841-864 | `process_synthesis_agents_b` | ⚠️ Sin AbortableTask, sin checkpoints |
| 1453-1518 | `invoke_graph` | ⚠️ Usa grafo mixto |
| 1522-1536 | `task_seed_theoretical_codes` | ✅ Correcto |

#### `trigger_selective_elaboration` (L1399-1440) — EL PROBLEMA CENTRAL

La función actual:
1. Itera sobre todas las categorías del proyecto
2. Para cada una, llama `task_a01_integrate_paradigm()` (elaboración por código)
3. No hay Proposer→Critic→HITL en ninguna decisión teórica
4. Las tareas A06, A01, A07, A14, A15, A16, A04, invoke_graph se ejecutan como grupo paralelo

**Violaciones detectadas:**

| Regla | Violación |
|-------|-----------|
| R0.1 | Sin HITL. `task_a14_main_concern` decide el core concern automáticamente. |
| R0.2 | `task_a15` corre en paralelo con `task_a14` en lugar de serial. |
| R0.3 | `invoke_graph()` contiene nodos de open coding (`batch_code`, `map_synthesize`) dentro de fase selectiva. |
| R1 | Sin `transitions.transition()`. |
| R2 | Sin PipelineTask tracking. |
| R3 | Sin `AbortableTask`. |

#### Cambios requeridos

```python
# ── ELIMINAR ──
# trigger_selective_elaboration()  # L1399-1440

# ── REFACTORIZAR ──
# task_a14_main_concern → task_main_concern_pipeline(self, proyecto_id):
#   Proposer (PRO) → Critic (PRO) → GUARDA hitl_decisions → PAUSA

# task_a15_core_emergence → task_core_emergence_pipeline(self, proyecto_id):
#   Serial después de A1+A2. Mismo patrón Proposer→Critic(FLASH)→HITL.

# process_synthesis_agents_b → base=AbortableTask, bind=True
#   task_step_checkpoints para B1, B2, B2.5, B3
#   Al terminar: transicionar docs a 'sintetizado'

# task_a06_theoretical_sample → reactivo: solo dentro de core_saturation_loop
#   cuando did_state_expand=false por 3 iteraciones

# ── CREAR ──
# selective_coding_coordinator(self, proyecto_id):
#   base=AbortableTask, bind=True
#   Fase A → HITL → Fase B → HITL → Fase C → HITL → Fase D → HITL → Fase E → HITL

# task_main_concern_pipeline(self, proyecto_id)
# task_core_emergence_pipeline(self, proyecto_id)
# task_selective_reduction_pipeline(self, proyecto_id)
# task_core_saturation_loop(self, proyecto_id)
# task_database_a_pipeline(self, proyecto_id)
# task_database_b_pipeline(self, proyecto_id)
# task_global_saturation_check(self, proyecto_id)
```

#### Spillovers

- **`pipeline.py` L97-99**: `stage_name == "selective"` → debe cambiar a `selective_coding_coordinator`.
- **`pipeline.py` L87-93**: `stage_name == "main_concern"` → debe redirigir al coordinator o eliminarse.
- **`invoke_graph` (L1453)**: Después del refactor, solo se usa para open coding.

---

### 8.4 `backend/app/models/domain/` — Análisis Detallado

#### Lo que EXISTE ✅

| Archivo | Modelos | Estado |
|---------|---------|--------|
| `theory.py` | `TheoreticalCode`, `ConceptualRelationship`, `ElaborationMemo`, `EcosystemLayout`, `CategoryDefinitionVersion` | ✅ Completo |
| `canvas.py` | `LienzoDelPlanDeAnalisis`, `NodoDeLienzo`, `BordeDeLienzo` | ✅ Completo |
| `pipeline_run.py` | `PipelineRun`, `PipelineTask`, `TaskStepCheckpoint` | ✅ Completo |
| `project.py` | `Proyecto` | ⚠️ `estado` solo tiene "ACTIVO" |
| `document.py` | `Documento` | ⚠️ `estado` no incluye "sintetizado" |
| `enums.py` | `RolDeUsuario`, `TipoPlanSuscripcion`, etc. | ✅ Completo |

#### Lo que FALTA ❌

| Elemento | Gravedad | Detalle |
|----------|----------|--------|
| Modelo `HitlDecision` | 🔴 | No existe. Necesita tabla `hitl_decisions`. |
| `Proyecto.estado` sin valores pipeline | 🔴 | Solo "ACTIVO". Necesita: `collecting\|coding\|finding_cc\|reducing\|saturating\|building_db\|playground_ready\|completed`. |
| `Documento.estado` sin "sintetizado" | 🟠 | Docstring L31-32 lista `crudo → ... → listo → error`. Falta `sintetizado`. |

#### Cambios requeridos — Modelo `HitlDecision`

```python
# Nuevo archivo: models/domain/hitl_decision.py
class HitlDecision(Base, TimestampMixin):
    __tablename__ = "hitl_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    gate_name: Mapped[str] = mapped_column(String(100))
    # "main_concern" | "core_emergence" | "selective_reduction"
    # | "core_saturation" | "database_a" | "database_b" | "global_saturation"

    proposal: Mapped[dict] = mapped_column(JSONB)        # output del proposer
    critic_verdict: Mapped[dict] = mapped_column(JSONB)  # output del critic

    status: Mapped[str] = mapped_column(String(20), default="pending")
    # "pending" | "accepted" | "modified" | "rejected"

    researcher_decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    researcher_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    researcher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

#### Cambios requeridos — `project.py`

```python
# Cambiar default de estado
estado: Mapped[str] = mapped_column(String(50), default="collecting")
# "collecting" | "coding" | "finding_cc" | "reducing" |
# "saturating" | "building_db" | "playground_ready" | "completed"
```

#### Cambios requeridos — `document.py`

```python
# Docstring actualizado:
# crudo → segmentando → segmentado → procesando → listo → sintetizado
# (error puede ocurrir en cualquier etapa)
```

#### Spillovers

- **Migración Alembic**: `alembic revision --autogenerate -m "add_hitl_decisions"`.
- **`Proyecto.estado` default cambia**: "ACTIVO" → "collecting". Código que verifique `estado == "ACTIVO"` debe actualizarse.
- **`_maybe_trigger_phase_b`**: Query cambia `WHERE estado='listo'` → `WHERE estado='sintetizado'`.

---

### 8.5 `backend/app/api/v1/` — Análisis Detallado

#### `pipeline.py` — Estado actual

| Línea(s) | Elemento | Estado |
|----------|----------|--------|
| 38-56 | `stage_name == "upload"` | ✅ |
| 58-62 | `stage_name == "precoding"` | ✅ |
| 64-76 | `stage_name == "open_coding"` | ✅ |
| 78-85 | `stage_name == "cross_doc"` | ✅ |
| 87-94 | `stage_name == "main_concern"` → `a14_find_main_concern` | ❌ Debe apuntar al coordinator |
| 96-103 | `stage_name == "selective"` → `trigger_selective_elaboration` | ❌ Debe apuntar al coordinator |
| 105-108 | `stage_name == "saturation"` | ⚠️ Placeholder |
| 116-200+ | `getPipelineLog` | ⚠️ No incluye nuevos estados |

#### Cambios requeridos

```python
# pipeline.py — Nuevos stage names
elif stage_name == "main_concern":
    task = celery_app.send_task("selective_coding_coordinator",
        args=[str(project_id), "main_concern"], queue="heavy")
elif stage_name == "selective":
    task = celery_app.send_task("selective_coding_coordinator",
        args=[str(project_id)], queue="heavy")
elif stage_name == "reduce":
    task = celery_app.send_task("selective_coding_coordinator",
        args=[str(project_id), "reduce"], queue="heavy")
elif stage_name == "saturate":
    task = celery_app.send_task("selective_coding_coordinator",
        args=[str(project_id), "saturate"], queue="heavy")
elif stage_name == "build_db":
    task = celery_app.send_task("selective_coding_coordinator",
        args=[str(project_id), "build_db"], queue="heavy")
```

#### `hitl.py` — Nuevo router requerido

```python
# Nuevo archivo: backend/app/api/v1/hitl.py
router = APIRouter(prefix="/api/v1", tags=["hitl"])

@router.post("/projects/{project_id}/hitl/{gate_name}/decide")
async def hitl_decide(project_id, gate_name, body: HitlDecisionRequest):
    """ACCEPT → avanzar pipeline. MODIFY → re-ejecutar proposer. REJECT → archivar."""

@router.get("/projects/{project_id}/hitl/pending")
async def hitl_pending(project_id):
    """Devuelve decisiones pendientes para el frontend."""
```

#### `events.py` — Extensión mínima

```python
# Ya tiene SSE + publish_event. Solo agregar tipo de evento:
def publish_event(proyecto_id, event_type, data):
    ...
# Los workers llamarán:
# publish_event(pid, "hitl_required", {"gate": "main_concern", ...})
```

#### Spillovers

- **`main.py`**: Registrar nuevo router `hitl.py`.
- **`frontend/src/api/client.ts`**: Nuevas funciones `decideHitl()` y `getPendingHitl()`.
- **`getPipelineLog`**: Reflejar nuevos estados `sintetizado`, `finding_cc`, etc.

---

### 8.6 `backend/app/services/` — Análisis Detallado

#### Estado: ✅ ALTAMENTE ALINEADO — 0 cambios necesarios

| Archivo | Clase/Función | Estado | Nota |
|---------|--------------|--------|------|
| `elaboration_engine.py` | `ElaborationEngine` | ✅ | `elaborate_relationship()`, `elaborate_divergence()`, `absorb_ghost_blob()`, `_get_lens_instruction()` — todo implementado |
| `selective_elaborator.py` | `SelectiveElaborator` | ✅ | `elaborate_incident()`, `get_category_evolution()` — listo para saturation loop |
| `emergent_sampler.py` | `EmergentSampler` | ✅ | `detect_emergent_dimensions()`, `sample_for_property_extreme()` — reemplazo del viejo TheoSampler |
| `ghost_connector.py` | `GhostConnector` | ✅ | `generate_ghost_blobs()`, `absorb_ghost()` |
| `rename_detector.py` | `RenameDetector` | ✅ | `get_rename_candidates()`, `should_suggest_rename()` |
| `recommendation_engine.py` | `RecommendationEngine` | ✅ | 5 dimensiones de recomendación |
| `saturation_gap_analyzer.py` | `SaturationGapAnalyzer` | ✅ | `full_analysis()` con 4 fuentes de gap |
| `theory_seeder.py` | `seed_theoretical_codes()` | ✅ | 12 códigos built-in |

Los services existentes ya implementan las capacidades que el pipeline selectivo y el playground necesitan. Solo hay que **conectarlos** desde el `selective_coding_coordinator` y desde los endpoints del Playground.

---

### 8.7 `backend/app/prompts/` — Análisis Detallado

#### Estado: ❌ INCOMPLETO — Faltan 12 prompts

| # | Prompt | Archivo | Estado |
|---|--------|---------|--------|
| 1 | `batch_coder_producer` | `prompts/pro/batch_coder_producer.md` | ✅ |
| 2 | `batch_coder_critic` | `prompts/pro/batch_coder_critic.md` | ✅ |
| 3 | `map_synthesis` | `prompts/pro/map_synthesis.md` | ✅ |
| 4 | `reduce_synthesis` | `prompts/pro/reduce_synthesis.md` | ✅ |
| 5 | `core_concern_finder` | `prompts/pro/core_concern_finder.md` | ✅ (legacy) |
| 6 | `hypothesis_generation` | `prompts/pro/hypothesis_generation.md` | ✅ |
| 7 | `final_report` | `prompts/pro/final_report.md` | ✅ |
| 8 | `main_concern_proposer` | — | ❌ CREAR |
| 9 | `main_concern_critic` | — | ❌ CREAR |
| 10 | `core_emergence_proposer` | — | ❌ CREAR |
| 11 | `core_emergence_critic` | — | ❌ CREAR |
| 12 | `selective_reduction_proposer` | — | ❌ CREAR |
| 13 | `selective_reduction_critic` | — | ❌ CREAR |
| 14 | `core_saturation_proposer` | — | ❌ CREAR |
| 15 | `core_saturation_critic` | — | ❌ CREAR |
| 16 | `database_a_proposer` | — | ❌ CREAR |
| 17 | `database_a_critic` | — | ❌ CREAR |
| 18 | `database_b_proposer` | — | ❌ CREAR |
| 19 | `database_b_critic` | — | ❌ CREAR |

Cada prompt nuevo debe seguir el contrato de agente `.md` definido en §6.4.

---

### 8.8 `frontend/` — Análisis Detallado

#### Estado: ⚠️ PARCIAL

| Componente | Archivo | Estado |
|-----------|---------|--------|
| `Project.tsx` | `frontend/src/pages/Project.tsx` | ⚠️ Pipeline stages antiguos (L44-50) |
| `Playground.tsx` | `frontend/src/pages/Playground.tsx` | ✅ Layout 3 columnas completo |
| `EcosystemCanvas` | `components/theory/EcosystemCanvas.tsx` | ✅ |
| `ElaborationPanel` | `components/theory/ElaborationPanel.tsx` | ✅ |
| `RecommendationGuide` | `components/theory/RecommendationGuide.tsx` | ✅ |
| `RenameModal` | `components/theory/RenameModal.tsx` | ✅ |
| `GhostBlob` | `components/theory/GhostBlob.tsx` | ✅ |
| `CategoryBlob` | `components/theory/CategoryBlob.tsx` | ✅ |
| `RelationshipTendril` | `components/theory/RelationshipTendril.tsx` | ✅ |
| `PlaygroundContext` | `components/theory/PlaygroundContext.tsx` | ✅ |
| `CategoryEvolutionPanel` | `components/selective/CategoryEvolutionPanel.tsx` | ✅ |
| **HITLModal** | — | ❌ CREAR |

#### Cambios requeridos — `Project.tsx` PIPELINE_STAGES

```typescript
// Reemplazar L44-50:
const PIPELINE_STAGES: StageDef[] = [
  { key: "segment", icon: "✂️", label: "Segmentación" },
  { key: "agents", icon: "🧠", label: "Open Coding (Agentes A)" },
  { key: "synthesis", icon: "🔗", label: "Síntesis Cross-Doc (Phase B)" },
  { key: "find_cc", icon: "🎯", label: "Core Category Detection" },
  { key: "reduce", icon: "✂️", label: "Selective Reduction" },
  { key: "saturate", icon: "🔄", label: "Core Saturation" },
  { key: "build_db", icon: "🗄️", label: "Database A/B" },
  { key: "playground", icon: "🎨", label: "Theoretical Playground" },
];
```

Este cambio requiere actualizar la lógica de `stageStatuses` para mapear los nuevos keys.

#### Cambios requeridos — `HITLModal.tsx` (NUEVO)

```tsx
// Componente modal que muestra:
// - Nombre del gate (main_concern, core_emergence, etc.)
// - Propuesta del Proposer (formateada)
// - Veredicto del Critic (SAT/MOD/FORCED con rationale)
// - Botones: ACCEPT | MODIFY (con campo de texto) | REJECT (con nota)
// - Llama a POST /api/v1/projects/{id}/hitl/{gate}/decide
```

#### Cambios requeridos — `client.ts`

```typescript
// Nuevas funciones:
decideHitl(projectId: string, gateName: string, decision: HitlDecision): Promise<void>
getPendingHitl(projectId: string): Promise<HitlPending[]>
```

---

## 9. Matriz de Spillovers (Efectos en Cascada)

Cada cambio en el sistema produce efectos en otros archivos. Esta matriz los documenta para que ninguna modificación se haga de forma aislada.

| Acción | Archivos afectados directamente | Archivos afectados indirectamente |
|--------|-------------------------------|----------------------------------|
| **Eliminar `trigger_selective_elaboration`** | `workers/heavy/tasks.py` L1399-1440 | `pipeline.py` L97-99, tests que lo invoquen |
| **Separar open/selective en workflow.py** | `workflow.py` (reducir grafo) | `invoke_graph()` en `tasks.py`, `node_find_core_concern` |
| **Agregar `HitlDecision` model** | `models/domain/hitl_decision.py` (nuevo), `project.py` | `alembic/versions/`, `main.py` (import), `api/v1/hitl.py` (nuevo router) |
| **Agregar `sintetizado` a doc.estado** | `document.py` L29-32 | `transitions.py` NEXT dict, `_maybe_trigger_phase_b` query, `pipeline.py` getPipelineLog |
| **Cambiar `Proyecto.estado` default** | `project.py` L24 | Código que verifique `estado == "ACTIVO"`, seeders, tests |
| **Agregar `transition_project()`** | `transitions.py` | `selective_coding_coordinator` (tasks.py), `pipeline.py` |
| **Crear `selective_coding_coordinator`** | `workers/heavy/tasks.py` (nuevo) | `pipeline.py` stages, `events.py` (publica eventos de progreso) |
| **Mover TheoSampler a reactivo** | `tasks.py` task_a06 | `emergent_sampler.py` (ya existe), `selective_coding_coordinator` |
| **Crear 12 prompts nuevos** | `prompts/pro/*.md` (8), `prompts/flash/*.md` (4) | `prompts/loader.py` (si requiere registro), `core/llm_config.py` PROMPT_TIER_MAP |
| **Cambiar PIPELINE_STAGES** | `Project.tsx` L44-50 | Componentes que lean `stageStatuses` keys |
| **Crear HITLModal** | `components/HITLModal.tsx` (nuevo) | `Project.tsx` (integración), `client.ts` (nuevas funciones API) |
| **Agregar endpoint HITL** | `api/v1/hitl.py` (nuevo) | `main.py` (registro router) |

---

## 10. Riesgos Identificados

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|--------|------------|
| **Romper el pipeline actual al eliminar `trigger_selective_elaboration`** | Alta | Medio | E0 es deliberadamente destructiva. El frontend mostrará "selective" como no disponible hasta que E2 implemente el coordinator. |
| **Migración de `Proyecto.estado` rompe datos existentes** | Media | Alto | Usar migración con valor default `collecting`. Proyectos existentes en "ACTIVO" se migran a "collecting". |
| **Dependencia circular `transitions.py` ↔ `tasks.py`** | Media | Medio | El coordinator llama a `transition_project()`; `transition_project()` no debe importar tareas. |
| **SSE HITL no funciona sin Redis** | Baja | Medio | El endpoint SSE ya tiene fallback (heartbeat sin Redis). El polling vía `GET /hitl/pending` sirve como backup. |
| **12 prompts nuevos requieren ajuste iterativo** | Alta | Bajo | Los prompts son el componente más fácil de iterar. Se crean con el contrato mínimo y se refinan con uso. |
| **El coordinator es una tarea Celery de larga duración** | Media | Alto | Con gates HITL, el coordinator puede estar vivo días. Usar `task_step_checkpoints` y `soft_time_limit` generoso (o ilimitado con `time_limit=None`). |
| **`invoke_graph()` se rompe al reducir el grafo** | Media | Medio | Solo se usa para open coding. Reducir el grafo a solo nodos open coding mantiene su funcionalidad intacta. |

---

## 11. Orden de Ejecución Validado (contra Spillovers)

Cada paso depende de los anteriores. Este orden minimiza el riesgo de dejar el sistema en estado inconsistente.

```
Paso 1: models/domain/hitl_decision.py (nuevo) + migración
        → Sin dependencias. Nadie lo importa aún.

Paso 2: project.py (cambiar default estado) + document.py (agregar 'sintetizado')
        → Sin dependencias críticas. Migración incluida.

Paso 3: agents/transitions.py (agregar 'sintetizado', hitl_gate, transition_project)
        → Depende de paso 1 (HitlDecision) y paso 2 (nuevo default estado).

Paso 4: api/v1/hitl.py (nuevo router) + extender events.py
        → Depende de paso 1 (modelo). Usa transition_project del paso 3.

Paso 5: prompts/ (12 nuevos archivos .md)
        → Sin dependencias de código. Se pueden crear en paralelo con pasos 1-4.

Paso 6: workflow.py (reducir grafo a solo open coding)
        → Depende de paso 5 conceptualmente (los nodos extraídos van al coordinator).

Paso 7: workers/heavy/tasks.py (eliminar trigger_selective, crear coordinator + 6 pipelines)
        → Depende de pasos 1-6.

Paso 8: api/v1/pipeline.py (actualizar stages)
        → Depende de paso 7 (nuevos task names).

Paso 9: frontend/ (HITLModal + actualizar PIPELINE_STAGES + client.ts)
        → Depende de paso 4 (endpoint HITL) y paso 8 (stages).
```

---

## 12. Inventario de Componentes que NO Requieren Cambios

Estos componentes ya están implementados y cumplen el contrato metodológico y de ingeniería. Se documentan aquí para evitar trabajo innecesario.

### 12.1 Services — 8 archivos, 0 cambios

| Archivo | Funciones clave | Usado por |
|---------|----------------|-----------|
| `elaboration_engine.py` | `elaborate_relationship()`, `elaborate_divergence()`, `absorb_ghost_blob()` | Playground, E3 |
| `selective_elaborator.py` | `elaborate_incident()`, `get_category_evolution()` | Saturation Loop (E2.4) |
| `emergent_sampler.py` | `detect_emergent_dimensions()`, `sample_for_property_extreme()` | TheoSampler reactivo (E2.4.5) |
| `ghost_connector.py` | `generate_ghost_blobs()` | Playground Entry (E3.1.3) |
| `rename_detector.py` | `get_rename_candidates()`, `should_suggest_rename()` | Playground (E3.4.6) |
| `recommendation_engine.py` | `generate_recommendations()` (5 dimensiones) | Playground (E3.4.4) |
| `saturation_gap_analyzer.py` | `full_analysis()` (4 fuentes de gap) | Saturation Loop (E2.4) |
| `theory_seeder.py` | `seed_theoretical_codes()` | Playground Entry (E3.1.1) |

### 12.2 Frontend Theory Components — 10 archivos, 0 cambios

| Componente | Archivo | Función |
|-----------|---------|--------|
| `PlaygroundPage` | `pages/Playground.tsx` | Layout 3 columnas (GuidePanel \| Canvas \| ElaborationPanel) |
| `EcosystemCanvas` | `components/theory/EcosystemCanvas.tsx` | SVG d3-force con blobs, tendriles, ghosts, neblina |
| `CategoryBlob` | `components/theory/CategoryBlob.tsx` | Gradiente radial con shimmer, pulse, glow, drag & drop |
| `RelationshipTendril` | `components/theory/RelationshipTendril.tsx` | Curvas Bézier con fisuras doradas |
| `GhostBlob` | `components/theory/GhostBlob.tsx` | Círculos translúcidos arrastrables |
| `ElaborationPanel` | `components/theory/ElaborationPanel.tsx` | BlobDetail + TendrilDetail |
| `RecommendationGuide` | `components/theory/RecommendationGuide.tsx` | 5 secciones colapsables |
| `RenameModal` | `components/theory/RenameModal.tsx` | 3 niveles de abstracción + custom input |
| `PlaygroundContext` | `components/theory/PlaygroundContext.tsx` | Estado global del ecosistema |
| `CategoryEvolutionPanel` | `components/selective/CategoryEvolutionPanel.tsx` | Timeline de versiones |

### 12.3 Infraestructura — 3 archivos, cambios mínimos

| Archivo | Ya implementado | Cambio necesario |
|---------|----------------|-----------------|
| `events.py` | SSE stream + `publish_event()` + Redis pub/sub | Agregar tipo de evento `hitl_required` |
| `pipeline_run.py` | `PipelineRun`, `PipelineTask`, `TaskStepCheckpoint` | Ninguno (ya soporta el nuevo pipeline) |
| `celery_app.py` | Configuración de Celery con Redis broker | Ninguno |

---

## 13. Notas Finales para el Implementador

1. **Los services NO necesitan cambios.** `ElaborationEngine`, `SelectiveElaborator`, `EmergentSampler`, `GhostConnector`, `RenameDetector`, `RecommendationEngine`, `SaturationGapAnalyzer`, `TheorySeeder` ya están implementados y cumplen el contrato metodológico.

2. **El frontend del Playground YA EXISTE.** Solo falta el `HITLModal` y actualizar los `PIPELINE_STAGES` en `Project.tsx`.

3. **El SSE YA EXISTE.** `events.py` tiene `publish_event()` y `stream_events()`. Solo hay que agregar el tipo de evento `hitl_required` y publicarlo desde los workers.

4. **La arquitectura de transiciones YA CUMPLE R1-R5.** `transitions.py` tiene optimistic locking, PipelineTask tracking, y AbortableTask. Solo hay que extenderlo a nivel proyecto y agregar el gate HITL.

5. **El cambio más disruptivo es eliminar `trigger_selective_elaboration` y dividir el grafo de LangGraph.** Esto dejará el pipeline selectivo inoperativo hasta que el `selective_coding_coordinator` esté completo. Es aceptable porque el pipeline actual ya es metodológicamente incorrecto.

6. **No avances a la siguiente etapa sin validar la anterior.** Cada etapa desbloquea dependencias reales (ver §11).

7. **PRO para generar, FLASH para comparar.** Si la tarea es "crea algo nuevo" → PRO. Si es "¿esto es igual a esto otro?" → FLASH (ver §5.1).

8. **Todos los prompts nuevos deben seguir el contrato de agente `.md`** definido en §6.4.
