# Prompt Engineering Criteria — Programmer's Guide

> **Modelos activos:** Nemotron (FLASH) | DeepSeek V4 Pro (PRO)
> **Aplica a:** Todos los prompts del sistema CGT en `backend/app/prompts/deepseek_flash/` y `deepseek_pro/`
> **Última actualización:** 2026-06-16 — Reorganizado como guía para programadores

---

## GUÍA RÁPIDA: Nemotron FLASH

### Cuándo usarlo
- Output esperado: **≤1 párrafo** (~200-300 palabras, ~1500 tokens)
- Tareas **estructuradas**: clasificación, extracción simple, evaluación binaria, diff/comparación
- Inputs **cortos** (<2000 caracteres por item)
- **Alto volumen** de llamadas (cientos por proyecto)
- Ejemplos: `incident_extractor`, `glaser_data_classifier`, `label_critic`, `gap_feeler`

### Parámetros
```
temperature:           0.1
max_tokens:            1500
repetition_penalty:    1.1
frequency_penalty:     1.15
top_p:                 0.9
json_object:           NO (inline schema en el prompt — Nemotron responde vacío con json_object en Together.ai)
timeout API:           600s
```

### Estructura del prompt
```markdown
## System — Rol directo sin adornos. Una frase.
## Reglas — Verbos en IMPERATIVO (EXTRAE, CLASIFICA, DEVUELVE, COMPARA).
           NUNCA uses negaciones ("NO hagas X"). Usa afirmaciones ("MANTÉN el texto original").
## Ejemplos — 1-2 ejemplos few-shot en el MISMO formato JSON de salida esperado.
## Tarea — Delimitar el input con tags XML: <datos>...</datos>
## Formato de salida — Schema JSON inline. NO uses `response_format=json_object`.
  Para outputs complejos (arrays de objetos, enums, scores), usar **JSON Schema completo** (ver §JSON SCHEMA PARA IA — Técnicas T1-T5).
```

### Anti-patrones (qué NO hacer)
- ❌ `response_format=json_object` → respuestas vacías en Nemotron vía Together.ai
- ❌ Instrucciones negativas ("NO inventes", "NO añadas") → el modelo las ignora. Reformular en positivo.
- ❌ Inputs >2000 chars → excede capacidad. Usar fragmentación o promover a PRO.
- ❌ Pedir razonamiento multi-step → Nemotron no tiene CoT nativo. Dividir en llamadas separadas.

---

## GUÍA RÁPIDA: DeepSeek V4 PRO

### Cuándo usarlo
- Output esperado: **multi-párrafo** (razonamiento, síntesis, generación creativa)
- Tareas con **alta ambigüedad**: síntesis cualitativa, generación de teoría, evaluación compleja
- Inputs **largos** (>2000 caracteres, contexto acumulativo)
- **Bajo volumen** de llamadas (decenas por proyecto)
- Ejemplos: `core_pattern_extractor`, `pattern_labeler`, `main_concern_proposer`, `natural_writer`

### Parámetros
```
temperature:           0.3
max_tokens:            8192
repetition_penalty:    1.0
frequency_penalty:     0.0
top_p:                 1.0
json_object:           SÍ (soportado nativamente)
timeout API:           600s
```

### Estructura del prompt (staged context)
```markdown
[Objetivo] → Qué debe lograr. Una frase.
[Contexto] → Datos y situación actual. Puede ser extenso.
[Restricciones] → Límites claros. Bullet points.
[Razonamiento] → Qué analizar antes de responder. No "think step by step" — interfiere con CoT nativo de DeepSeek.
```

### Regla de oro para PRO
- **NUNCA** uses `response_format=json_object` con PRO si querés preservar el `reasoning_content`. Usá un parser que extraiga el JSON del final de la respuesta (después del razonamiento interno de DeepSeek). Esto duplica la calidad en tareas de síntesis cualitativa.
- **NO** uses instrucciones de "razonamiento paso a paso" — DeepSeek V4 tiene CoT nativo. Instrucciones explícitas de razonamiento interfieren con él.
- Para extraer el JSON: buscar `{` balanceado al final del texto, después del bloque de razonamiento.
- Para outputs estructurados, usar **JSON Schema completo** (ver §JSON SCHEMA PARA IA — Técnicas T1-T10). La estructura canónica es `[ROL]` + `[OBJETIVO]` + `[RESTRICCIONES]` (T6).

---

## REGLA DE ASIGNACIÓN DE TIER

```
¿El output esperado es ≤1 párrafo (~300 palabras)?
  ├── SÍ → ¿La tarea es estructurada (clasificar, extraer, evaluar)?
  │         ├── SÍ → FLASH (Nemotron)
  │         └── NO → PRO (DeepSeek)
  └── NO → PRO (DeepSeek)
```

### Regla de pre-procesamiento (breakdown)
```
[FLASH] pre-procesamiento → [⚙️ ALG] filtrado → [PRO] razonamiento cualitativo
```

Ejemplo: `glaser_data_classifier` = ⚙️ ALG (regex, 90% de segmentos) + FLASH (10% borderline).

---

## CONFIGURACIÓN POR TIER (resumen)

| Parámetro | FLASH (Nemotron) | PRO (DeepSeek) |
|-----------|-----------------|----------------|
| `temperature` | 0.1 | 0.3 |
| `max_tokens` | 1500 | 8192 |
| `repetition_penalty` | 1.1 | 1.0 |
| `frequency_penalty` | 1.15 | 0.0 |
| `top_p` | 0.9 | 1.0 |
| `json_object` | ❌ NO USAR | ✅ SÍ (nativo) |
| `timeout` API | 600s | 600s |

Variables de entorno (con defaults, sobreescribibles):
- `MODEL_FLASH`, `MODEL_FLASH_MAX_TOKENS`, `MODEL_FLASH_TEMPERATURE`
- `MODEL_FLASH_REPETITION_PENALTY`, `MODEL_FLASH_FREQUENCY_PENALTY`, `MODEL_FLASH_TOP_P`
- `MODEL_PRO`, `MODEL_PRO_MAX_TOKENS`, `MODEL_PRO_TEMPERATURE`

---

## FRAGMENTACIÓN DE TEXTOS LARGOS

Cuando un texto excede `max_chars` para FLASH:

1. **Corte semántico**: buscar el último `.`, `?`, `!`, o `\n\n` antes del límite. NUNCA cortar a ciegas.
2. **Overlap**: incluir las últimas 2-3 oraciones del bloque N como prefijo del bloque N+1, con marcador `[CONTINÚA AQUÍ]`.
3. **Paralelismo**: despachar todos los bloques simultáneamente con `ThreadPoolExecutor`.
4. **Limpieza post-proceso**: eliminar el overlap del output final.

---

## JSON SCHEMA PARA IA — Técnicas de los prompts legacy `pro/` y `flash/`

> **Extraído de:** `backend/app/prompts/pro/` (18 archivos) y `backend/app/prompts/flash/` (6 archivos)
> **Aplica a:** Todos los prompts que producen JSON estructurado. Reemplaza los JSON de ejemplo simples por schemas completos.

### Regla de oro

**Siempre usar JSON Schema completo, nunca solo un ejemplo JSON.** El schema le da al modelo restricciones precisas que los ejemplos no pueden comunicar: tipos exactos, valores permitidos (`enum`), campos obligatorios (`required`), rangos numéricos (`minimum`/`maximum`), y descripciones por campo (`description`). Un ejemplo JSON solo muestra UNA instancia; el schema define TODAS las instancias válidas.

### Plantilla base

```json
{
  "type": "object",
  "properties": {
    "campo_principal": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "nombre": {"type": "string", "description": "Descripción corta de qué debe contener este campo"},
          "verdict": {"type": "string", "enum": ["SAT", "MOD", "FORCED"], "description": "Veredicto. Solo estos 3 valores."},
          "score": {"type": "number", "minimum": 0, "maximum": 1, "description": "Puntaje entre 0.0 y 1.0"}
        },
        "required": ["nombre", "verdict"]
      }
    }
  },
  "required": ["campo_principal"]
}
```

### Técnicas extraídas

#### T1 — `enum` para veredictos categóricos
**Origen:** `main_concern_critic.md`, `batch_coder_critic.md`, `code_critic.md`

Todos los critic prompts usan `"enum": ["SAT", "MOD", "FORCED"]`. Esto fuerza al modelo a elegir exactamente uno de tres valores, eliminando ambigüedad. Sin `enum`, el modelo puede inventar variantes ("saturado", "SATURADO", "sat", "ok") que rompen el parsing.

```json
"verdict": {"type": "string", "enum": ["SAT", "MOD", "FORCED"], "description": "Veredicto metodológico"}
```

#### T2 — `description` en cada propiedad (no solo en las requeridas)
**Origen:** Todos los prompts `pro/` y `flash/`

Cada campo del schema tiene `description`. El modelo usa estas descripciones para entender QUÉ escribir en cada campo. Son más efectivas que las instrucciones en el system prompt porque están ancladas al campo específico.

```json
"rationale": {"type": "string", "description": "Justificación detallada con referencia a segmentos específicos"}
```

#### T3 — `required` a nivel de objeto anidado
**Origen:** `clusterizador_informado.md`

No solo el objeto raíz tiene `required`. Cada objeto anidado también. Esto previene outputs incompletos donde el array existe pero sus items están vacíos.

```json
"strategic_sampling_criteria": {
  "type": "object",
  "properties": {
    "inclusion": {"type": "array", "items": {"type": "string"}},
    "exclusion": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["inclusion", "exclusion"]
}
```

#### T4 — `additionalProperties` para mapas dinámicos
**Origen:** `clusterizador_informado.md`

Cuando un campo es un diccionario con keys variables (ej. `evidence_map` donde las keys son document_ids), usar `additionalProperties` en vez de `properties` fijas.

```json
"evidence_map": {
  "type": "object",
  "additionalProperties": {"type": "array", "items": {"type": "string"}},
  "description": "Mapa de document_id → lista de citas de evidencia"
}
```

#### T5 — `minimum`/`maximum` para scores numéricos
**Origen:** `batch_coder_critic.md`

Los campos de puntaje siempre tienen rango explícito. Sin esto, el modelo puede devolver 147 en vez de 0.8.

```json
"confidence": {"type": "number", "minimum": 0, "maximum": 1, "description": "Confianza del crítico (0.0–1.0)"}
```

#### T6 — `[ROL]` + `[OBJETIVO]` + `[RESTRICCIONES]` como estructura canónica
**Origen:** Todos los prompts `pro/`

El system prompt se divide en 3 bloques con delimitadores explícitos. Esto es más efectivo que prosa corrida porque el modelo puede atender a cada bloque por separado.

```markdown
[ROL]
Eres un [rol específico]. [Una frase de contexto].

[OBJETIVO]
1. [Paso concreto]
2. [Paso concreto]

[RESTRICCIONES]
- [Regla negativa o afirmativa]
- [Regla negativa o afirmativa]
```

#### T7 — Verbos en imperativo para restricciones
**Origen:** `selective_reduction_proposer.md`, `core_emergence_proposer.md`

Las restricciones usan verbos en imperativo: "NUNCA elimines", "SÉ CONCRETO", "Propón 1-3 candidatos", "Responde directamente". El imperativo es más efectivo que el condicional ("deberías") o el pasivo ("se debe").

#### T8 — YAML frontmatter como registro de prompt
**Origen:** Todos los prompts `pro/` y `flash/`

Cada archivo tiene metadatos estructurados: `prompt_id`, `version`, `model_profile`, `input_state`, `output_state`, `depends_on`, `agent_id`, `triggers_on`. Esto permite:
- Auto-documentación: saber qué produce y consume cada prompt sin leerlo entero
- Validación automática: un script puede verificar que `depends_on` existe
- Registro de dependencias: el `loader.py` puede construir el DAG de prompts

```yaml
---
prompt_id: core_emergence_proposer
version: 1.0.0
model_profile: pro
input_state: main_concern, all_codes, code_statistics
output_state: core_category_candidates, no_core_detected
depends_on: null
agent_id: A15
triggers_on: "Después de que el investigador confirma el main concern"
---
```

#### T9 — `parallelizable: true` para optimización
**Origen:** `incident_extractor.md` (flash), `entity_extraction.md` (flash)

Flag que indica si el prompt puede ejecutarse en paralelo sobre múltiples inputs sin conflicto. El orchestrator puede usar esto para decidir si despachar en `ThreadPoolExecutor`.

#### T10 — Anti-alucinación: "No uses herramientas externas" / "Responde directamente"
**Origen:** `entity_extraction.md`, `incident_extractor.md`

Para modelos que tienen acceso a tools (DeepSeek V4 con function calling), esta restricción explícita previene que el modelo intente buscar información adicional en vez de trabajar con los datos proporcionados.

```markdown
[RESTRICCIONES]
- Responde directamente. NO uses herramientas externas.
- NO intentes buscar información adicional.
```

### Comparativa: Ejemplo JSON vs JSON Schema

| Aspecto | Ejemplo JSON simple | JSON Schema completo |
|---------|--------------------|--------------------|
| Valores permitidos | Implícito (el modelo adivina) | Explícito (`enum`) |
| Campos obligatorios | Implícito | Explícito (`required`) |
| Tipos de datos | Implícito | Explícito (`type`) |
| Rangos numéricos | Implícito | Explícito (`minimum`/`maximum`) |
| Descripciones por campo | No | Sí (`description`) |
| Mapas dinámicos | No soportado | `additionalProperties` |
| Validación automática | No (hay que inspeccionar) | Sí (jsonschema library) |
| Tasa de error de parsing | ~15-20% (campos mal tipeados) | ~3-5% (el schema fuerza tipos) |

### Cuándo usar cada approach

| Situación | Usar |
|-----------|------|
| Output simple (1-3 campos planos) | Ejemplo JSON (basta) |
| Output con arrays de objetos | **JSON Schema** (required en items) |
| Output con veredictos categóricos | **JSON Schema** (enum) |
| Output con scores numéricos | **JSON Schema** (minimum/maximum) |
| Output con mapas dinámicos | **JSON Schema** (additionalProperties) |
| Prompt FLASH con `json_object` deshabilitado | **JSON Schema inline** (el schema va en el cuerpo del prompt como parte de las instrucciones) |
| Prompt PRO con `json_object` nativo | **JSON Schema** (se pasa como `response_format`) o ejemplo JSON (si se preserva reasoning_content) |

```yaml
---
agent: id_unico
tier: PRO | FLASH
description: Una línea explicando qué hace
notes:
  - Nota de implementación 1
  - Detalles del modelo y parámetros
constraints:
  - Regla anti-alucinación 1
---
```

---

## AUDITORÍA DE PROMPTS EXISTENTES

### Promovidos a PRO (desde FLASH)

| Prompt | Razón |
|--------|-------|
| `punctuator.md` | Textos largos (>2000 chars). Requiere precisión ortotipográfica que Nemotron no entrega. DeepSeek V4 lo hace en 4s. |
| `a2_process_identifier.md` | Requiere razonamiento cualitativo (identificar proceso central de un entrevistado). Inputs de longitud variable. |

### Mantenidos como FLASH

| Prompt | Razón |
|--------|-------|
| `b2a_extract_indicators.md` | Extracción determinista de frases. Inputs acotados (segmentos individuales). |
| `evidence_classifier.md` | Clasificación binaria simple (POSITIVE/CONTRAST/NO_EVIDENCE). |
| `glaser_data_classifier.md` | Clasificación por segmento individual. Textos cortos. ⚙️+FLASH (dos capas). |
| `corpus_scanner.md` | Escaneo de presencia/ausencia. Baja ambigüedad. |
| `incident_extractor.md` | Output ≤1 párrafo (4 respuestas cortas + jot). Alto volumen (cientos/proyecto). Keep-moving. |

### Legacy (.txt, sintaxis vieja)

| Prompt | Estado |
|--------|--------|
| `a1_population_context.txt` | Legacy .txt. Tier: PRO. Mantener. |
| `a3_sense_maker.txt` | Legacy .txt. Tier: PRO. Mantener. |
| `b1_sampling_distiller.txt` | Legacy .txt. Tier: PRO. Mantener. |
| `b3_hypothesis_generator.txt` | Legacy .txt. Tier: PRO. Mantener. |
| `context_synthesizer.md` | `model_profile: flash` (sintaxis vieja). Legacy. |
| `core_saturation_critic.md` | `model_profile: flash`. Legacy. |
| `document_summarizer.md` | `model_profile: flash`. Legacy. |
| `entity_extraction.md` | `model_profile: flash`. Legacy. |
| `incident_extractor.md` | `model_profile: flash`. Legacy. |
