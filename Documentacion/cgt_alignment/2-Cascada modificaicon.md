# Mapa de Cascada de Modificaciones — P5 HITL

> **¿Qué pasa cuando un usuario aplica una modificación a un output de agente CGT?**

```mermaid
flowchart TD
    U["👤 Usuario aplica modificación"]
    U --> API["POST /modification/apply"]

    API --> UPDATE["✏️ UPDATE output_table SET field = new_value"]
    API --> WIPE["🗑️ DELETE FROM dependent_tables"]

    UPDATE --> DB1["categorias<br/>(o hypotheses, population_contexts, etc.)"]

    WIPE --> DB2["codigos_segmento"]
    WIPE --> DB3["code_document_summaries"]
    WIPE --> DB4["code_global_summaries"]
    WIPE --> DB5["conceptual_relationships"]
    WIPE --> DB6["elaboration_memos"]

    API --> CELERY["📤 Celery: send_task('process_synthesis_agents_b')"]
    CELERY --> REDIS["Redis queue: heavy"]
    REDIS --> WORKER["Worker Heavy"]

    WORKER --> B2["B2: Open Coding"]
    WORKER --> B3["B3: Hypothesis Generation"]
    WORKER --> MAP["Map Synthesis"]
    WORKER --> REDUCE["Reduce Synthesis"]

    B2 --> SSE["📡 SSE: project:{id}:events"]
    B3 --> SSE
    MAP --> SSE
    REDUCE --> SSE

    SSE --> UI["🖥️ Frontend: PipelineStatus se actualiza en tiempo real"]

    API --> LOG["📝 output_modifications table"]
    LOG --> TRACE["Trazabilidad: quién, qué, cuándo, veredicto"]

    style U fill:#58A6FF,color:#fff
    style API fill:#1C2333,color:#E6EDF3
    style UPDATE fill:#238636,color:#fff
    style WIPE fill:#F85149,color:#fff
    style CELERY fill:#D29922,color:#000
    style SSE fill:#3FB950,color:#000
    style UI fill:#161B22,color:#E6EDF3
```

## ¿Qué tablas se limpian según el agente modificado?

```mermaid
flowchart LR
    subgraph "🔍 Inductive Data"
        B2B["b2b_generate_codes"] --> W1["codigos_segmento<br/>code_document_summaries<br/>code_global_summaries"]
    end

    subgraph "🧠 Inductive Concepts"
        B3["b3_hypothesis_generator"] --> W2["conceptual_relationships<br/>elaboration_memos"]
        MC["main_concern_proposer"] --> W2B["hypotheses<br/>conceptual_relationships"]
    end

    subgraph "📋 Descriptive"
        A2["a2_process_identifier"] --> W3["hypotheses"]
    end

    subgraph "⚖️ Evaluative"
        CRT["batch_coder_critic"] --> W4["categorias"]
    end

    subgraph "🏗️ Structural"
        DBA["database_a_proposer"] --> W5["elaboration_memos<br/>ecosystem_layouts"]
    end

    subgraph "🔬 Elaborative"
        CE["conceptual_elaborator"] --> W6["elaboration_memos"]
    end

    style B2B fill:#FF6B3522,color:#FF6B35
    style B3 fill:#45B7D122,color:#45B7D1
    style MC fill:#45B7D122,color:#45B7D1
    style A2 fill:#8B949E22,color:#8B949E
    style CRT fill:#D2992222,color:#D29922
    style DBA fill:#3FB95022,color:#3FB950
    style CE fill:#58A6FF22,color:#58A6FF
```

## ¿Dónde se reinicia el pipeline?

```mermaid
flowchart TD
    subgraph "Pipeline Nodes"
        SEG["segment_and_index"] --> EXT["extract_entities"]
        EXT --> BATCH["batch_code"]
        BATCH --> MAP_S["map_synthesize"]
        MAP_S --> REDUCE_S["reduce_synthesize"]
        REDUCE_S --> CC["find_core_concern"]
        CC --> HYP["generate_hypotheses"]
        HYP --> SAT["calculate_saturation"]
        SAT --> TS["theosampler_evaluate"]
        TS --> PP["prepare_playground"]
    end

    B2B_MOD["Modificación B2b"] -.->|"restart_from"| BATCH
    A2_MOD["Modificación A2"] -.->|"restart_from"| SEG
    B3_MOD["Modificación B3"] -.->|"restart_from"| HYP
    MC_MOD["Modificación MainConcern"] -.->|"restart_from"| CC
    ELA_MOD["Modificación Elaboration"] -.->|"restart_from"| PP

    style B2B_MOD fill:#FF6B35,color:#fff
    style A2_MOD fill:#8B949E,color:#fff
    style B3_MOD fill:#45B7D1,color:#fff
    style MC_MOD fill:#45B7D1,color:#fff
    style ELA_MOD fill:#58A6FF,color:#fff
    style BATCH fill:#3FB950,color:#000
    style SEG fill:#3FB950,color:#000
    style HYP fill:#3FB950,color:#000
    style CC fill:#3FB950,color:#000
    style PP fill:#3FB950,color:#000
```
