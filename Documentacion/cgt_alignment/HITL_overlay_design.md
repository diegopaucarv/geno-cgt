# HITL Overlay Design — Batch Review (Every-3-Doc Pause)

## Overview

After every 3 documents (including the last incomplete batch), the system pauses and shows the user a comprehensive review overlay. This overlay consolidates what used to be separate HITL gates into ONE unified decision moment.

## Flow

```
Phase A (3 docs) → Phase B (cross-doc) → Synthesizer 1 → Synthesizer 2 → Config Critic
                                                                              ↓
                                                                     🛑 HITL OVERLAY
                                                                              ↓
                                                                     User decides
                                                                              ↓
                                                                     Cascada updates
                                                                              ↓
                                                                     Next batch (or core category selection if final)
```

## Overlay Structure

```
┌─────────────────────────────────────────────────────────────┐
│  🧬 Revisión del Lote #2 (Documentos 4-6)                   │
│                                                             │
│  ─────────────────────────────────────────────────────────── │
│  📊 CATEGORÍAS UNIFICADAS                                   │
│  ─────────────────────────────────────────────────────────── │
│  ☑ Sobreviviendo la avalancha de iniciativas (13 incidents) │
│  ☑ Performando para la evaluación (6 incidents)              │
│  ☑ Aferrándose a los momentos significativos (9 incidents)   │
│  ☐ [NUEVA] Extendiendo la jornada laboral (5 incidents)     │
│  ☐ [NUEVA] Diagnosticando la desvinculación (5 incidents)   │
│                                                             │
│  [ Seleccionar todas ] [ Desseleccionar todas ]             │
│                                                             │
│  ─────────────────────────────────────────────────────────── │
│  🎯 CONCERNS (Patrones de Interés)                          │
│  ─────────────────────────────────────────────────────────── │
│  ● Sobreviviendo la burocracia escolar          ← ACTUAL    │
│  ○ Manteniendo autoridad en el aula             ← NUEVA     │
│  ○ Resistiendo la desprofesionalización         ← NUEVA     │
│  ○ Mantener selección actual (no cambiar)                   │
│                                                             │
│  ─────────────────────────────────────────────────────────── │
│  👥 POBLACIÓN                                               │
│  ─────────────────────────────────────────────────────────── │
│  ● Docentes de secundaria en Minnesota         ← ACTUAL    │
│  ○ Docentes veteranos (>10 años)               ← NUEVA     │
│  ○ Docentes nuevos (<5 años)                   ← NUEVA     │
│  ○ Mantener selección actual (no cambiar)                   │
│                                                             │
│  ─────────────────────────────────────────────────────────── │
│  ✏️ CODING STYLE                                            │
│  ─────────────────────────────────────────────────────────── │
│  ● Gerundio (actual)                                        │
│  ○ In-vivo (recomendado: captura mejor lenguaje nativo)     │
│  ○ Mantener selección actual (no cambiar)                   │
│                                                             │
│  ─────────────────────────────────────────────────────────── │
│  💡 HIPÓTESIS ACTUALIZADAS (crecimiento acumulativo)        │
│  ─────────────────────────────────────────────────────────── │
│  "Sobreviviendo la avalancha" conecta con "Extendiendo la   │
│   jornada" → ambos expresan carga laboral invisible         │
│  "Performando para la evaluación" es condición de           │
│   "Sobreviviendo la avalancha"                              │
│  [Ver todas las hipótesis]                                  │
│                                                             │
│  ─────────────────────────────────────────────────────────── │
│                                                             │
│  ☐ No volver a preguntar (bloquear selección actual)       │
│                                                             │
│  [ Cancelar ]  [ Aplicar cambios ]                          │
└─────────────────────────────────────────────────────────────┘
```

## Behavior Rules

### Categories
- **Multi-select**: user can accept any subset of unified categories
- Previously accepted categories are pre-checked (☑)
- New categories from this batch are unchecked (☐)
- User can deselect previously accepted categories
- Minimum: at least 2 categories must remain selected

### Concerns
- **Multi-select during early batches, single at final**
- Current selection shown with ● (filled circle) and "ACTUAL" label
- New AI proposals shown with ○ (empty circle) and "NUEVA" label
- "Mantener selección actual" = keep what's currently selected, ignore new proposals
- Can select multiple concerns during batches 1, 2, 3...
- After final batch: forced to choose exactly ONE

### Population
- **Multi-select during early batches, single at final**
- Same pattern as concerns: ● ACTUAL / ○ NUEVA / "Mantener selección actual"
- Population variants are conceptual, not demographic

### Coding Style
- **Single select**
- ● ACTUAL / ○ NUEVA / "Mantener selección actual"
- If user rejects recommendation, current style stays

### "No volver a preguntar"
- Checkbox at the bottom
- When checked: current selections for concern + population + style are LOCKED
- Remaining batches skip the config review portion of the HITL
- Categories and hypotheses still update (synthesizers still run)
- Can be UNCHECKED later if user changes mind

### Accumulative Selection
- User's CURRENT choices are NEVER removed by new AI proposals
- AI proposals are ADDED to the list, not replacing user's
- User sees: [current selection ●] + [new proposals ○] + [keep current]
- This applies to concerns, population, and coding style

## Final Batch Behavior

After the LAST batch:
- Concerns: forced to single select (radio buttons instead of checkboxes)
- Population: forced to single select
- "No volver a preguntar" is auto-selected (no more batches)
- After confirmation → triggers core category selection

## API Endpoint

```
POST /api/v1/projects/{id}/hitl/batch_review/decide
Body: {
  "categories": ["label1", "label2", ...],  // accepted category labels
  "concerns": ["concern1"],                   // selected concerns  
  "population": "population_label",           // selected population
  "coding_style": "gerundio",                 // selected style
  "no_more_questions": true                   // lock config
}
```

## Cascada Updates

On user decision:
1. Categories not selected → marked as rejected (soft delete or status change)
2. Selected concerns → upserted to `concerns` table (status = confirmed)
3. Population → updated in `population_assumption` JSONB
4. Coding style → updated, `coding_style_instruction` regenerated
5. If `no_more_questions` → `population_assumption.config_locked = true`
6. Categories updated with `concern_label` and `population_label`
