# Prompt Engineering Criteria — DeepSeek Pro & Gemma Flash

> Derivado de: `pro/` + `flash/` (viejo sistema) → `deepseek_pro/` + `deepseek_flash/` (nuevo)
> Aplica a todos los prompts del sistema CGT.
> Última actualización: 2026-06-15 — Refactor E4B y Promoción a PRO

---

## 1. Asignación de tier

| Tier | Modelo | Cuándo usarlo | Ejemplos |
|---|---|---|---|
| **FLASH** | Gemma 3n E4B (`google/gemma-3n-E4B-it`) | Extracción, clasificación, resumen. Tareas con input→output claro, baja ambigüedad. Textos cortos (<2000 chars). Sin razonamiento elaborado. | Extraer indicadores (b2a), clasificar tipo Glaser, clasificar evidencia, escanear corpus |
| **PRO** | DeepSeek V4 Pro (`deepseek-ai/DeepSeek-V4-Pro`) | Generación, síntesis, evaluación, puntuación de textos largos. Tareas con alta ambigüedad o inputs largos (>2000 chars). | Puntuación (punctuator), generar códigos (b2b), sintetizar cross-doc, main concern, hipótesis |

### Regla de quiebre (breakdown)

```
[FLASH] pre-procesamiento → [ALGORÍTMICO] filtrado → [PRO] razonamiento cualitativo
```

### Regla de longitud

- **Textos < 2000 caracteres** → FLASH puede manejar
- **Textos > 2000 caracteres** → PRO o dividir en chunks + overlap + paralelo
- **Puntuación de transcripciones** → SIEMPRE PRO. Es tarea de precisión sobre textos largos.

---

## 2. Estructura de archivo

### Formato YAML (.md)

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

## 3. Estrategias de prompting por tier

### PRO (DeepSeek V4)

Usar **staged context** (nunca "think step by step"):

```markdown
[Objetivo] → Qué debe lograr
[Contexto] → Datos y situación
[Restricciones] → Límites claros
[Razonamiento] → Qué analizar antes de responder
```

- `temperature`: 0.3
- `max_tokens`: 8192
- `json_object`: soportado nativamente
- NO usar instrucciones de "razonamiento paso a paso" — interfiere con CoT nativo

### FLASH (Gemma 3n E4B)

Usar **instrucciones positivas, few-shot, delimitadores XML**:

```markdown
## System — Rol directo sin adornos
## Reglas — Verbos en imperativo (INSERTA, CLASIFICA, DEVUELVE)
## Ejemplos — Siempre en formato JSON de salida
## Tarea — XML <datos> para aislar input
```

- `temperature`: 0.1
- `max_tokens`: 1500
- `repetition_penalty`: 1.1
- `frequency_penalty`: 1.15
- `top_p`: 0.9
- `json_object`: **NO USAR** con Gemma en Together.ai (respuestas vacías). El schema va inline en el prompt.
- Los ejemplos few-shot deben mostrar EXACTAMENTE el JSON de salida, no texto plano.
- Evitar negaciones ("NO hagas X"). Usar afirmaciones ("MANTÉN el texto igual").

### Fragmentación de textos largos

Cuando un texto excede `max_chars`:

1. **Corte semántico**: buscar el último `.`, `?`, `!`, o `\n\n` antes del límite. NUNCA cortar a ciegas en mitad de una palabra.
2. **Overlap**: incluir las últimas 2-3 oraciones del bloque N como prefijo del bloque N+1, con marcador `[CONTINÚA AQUÍ]`.
3. **Paralelismo**: despachar todos los bloques simultáneamente con `ThreadPoolExecutor`.
4. **Limpieza post-proceso**: eliminar el overlap del output final.

---

## 4. Auditoría de prompts FLASH (Junio 2026)

### Promovidos a PRO

| Prompt | Razón |
|--------|-------|
| `punctuator.md` | Textos largos (>2000 chars). Requiere precisión ortotipográfica que Gemma no entrega. DeepSeek V4 lo hace en 4s. |
| `a2_process_identifier.md` | Requiere razonamiento cualitativo (identificar proceso central de un entrevistado). Inputs de longitud variable. |

### Mantenidos como FLASH

| Prompt | Razón |
|--------|-------|
| `b2a_extract_indicators.md` | Extracción determinista de frases. Inputs acotados (segmentos individuales). |
| `evidence_classifier.md` | Clasificación binaria simple (POSITIVE/CONTRAST/NO_EVIDENCE). |
| `glaser_data_classifier.md` | Clasificación por segmento individual. Textos cortos. |
| `corpus_scanner.md` | Escaneo de presencia/ausencia. Baja ambigüedad. |

### Legacy (no usados por agentes)

| Prompt | Estado |
|--------|--------|
| `a1_population_context.txt` | Legacy .txt. Usa tier: PRO en metadata — correcto. Mantener. |
| `a3_sense_maker.txt` | Legacy .txt. Usa tier: PRO en metadata — correcto. Mantener. |
| `b1_sampling_distiller.txt` | Legacy .txt. Usa tier: PRO. Mantener. |
| `b3_hypothesis_generator.txt` | Legacy .txt. Usa tier: PRO. Mantener. |
| `context_synthesizer.md` | Usa `model_profile: flash` (sintaxis vieja). Legacy. |
| `core_saturation_critic.md` | Usa `model_profile: flash`. Legacy. |
| `document_summarizer.md` | Usa `model_profile: flash`. Legacy. |
| `entity_extraction.md` | Usa `model_profile: flash`. Legacy. |
| `incident_extractor.md` | Usa `model_profile: flash`. Legacy. |

---

## 5. Configuración de parámetros por tier

| Parámetro | FLASH (Gemma) | PRO (DeepSeek) |
|-----------|---------------|----------------|
| `temperature` | 0.1 | 0.3 |
| `max_tokens` | 1500 | 8192 |
| `repetition_penalty` | 1.1 | 1.0 |
| `frequency_penalty` | 1.15 | 0.0 |
| `top_p` | 0.9 | 1.0 |
| `json_object` | NO | SÍ |
| `timeout` API | 600s | 600s |

Todas las variables de entorno tienen defaults y se pueden sobreescribir:
- `MODEL_FLASH`, `MODEL_FLASH_MAX_TOKENS`, `MODEL_FLASH_TEMPERATURE`
- `MODEL_FLASH_REPETITION_PENALTY`, `MODEL_FLASH_FREQUENCY_PENALTY`, `MODEL_FLASH_TOP_P`
- `MODEL_PRO`, `MODEL_PRO_MAX_TOKENS`, `MODEL_PRO_TEMPERATURE`
