# Translation Pattern — Sistema de Idiomas para Prompts CGT

> **Principio:** DeepSeek V4 PRO razona exclusivamente en inglés. Nemotron FLASH rinde mejor con prompts en inglés. El LLM es el traductor — solo necesita saber a qué idioma traducir.
>
> **Regla de oro:** System prompt en inglés. Output en el idioma del usuario. El LLM traduce.

---

## 1. El Patrón

```
┌──────────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT: 🇬🇧 Inglés                                    │
│   [ROL], [OBJETIVO], [RESTRICCIONES] en inglés               │
│   JSON Schema descriptions: Inglés                           │
│   JSON Schema enum codes: Language-neutral (SAT, MOD, etc.)  │
├──────────────────────────────────────────────────────────────┤
│ USER MESSAGE: Inglés (instrucciones) + datos originales      │
│   Instrucción final explícita:                               │
│   "Respond in {user_language}. Output values must be in      │
│    {user_language}. Source quotes stay in original language." │
├──────────────────────────────────────────────────────────────┤
│ LLM: Razona en inglés, traduce output al {user_language}     │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Clasificación de Campos de Output

| Tipo | Ejemplos | Idioma | Quién decide |
|------|---------|--------|-------------|
| **Códigos de sistema** | `SAT`, `MOD`, `FORCED`, `baseline_data`, `properline_data`, `collecting`, `coding` | 🌐 Neutro (inglés) | Sistema |
| **Valores naturales** | Nombres de categorías, definiciones, jots, descripciones, rationale, justification | 🇪🇸/🇬🇧/🇩🇪/🇵🇹 Idioma del usuario | LLM traduce |
| **Texto fuente** | Segmentos, citas, contenido de documentos | Idioma original | Dato inmutable |
| **Scores** | `confidence`, `similarity_score`, `conceptual_fit` | 🌐 Neutro (números) | Sistema |

---

## 3. Variable `{user_language}`

### Fuente
- Leer de `proyectos.population_assumption->>'language'` (nuevo campo F0.3.6)
- Default: `"es"` (Spanish)
- Valores válidos: `"es"`, `"en"`, `"de"`, `"pt"` (matching frontend i18n)

### Inyección
- `loader.py` lee `user_language` del contexto global
- Cada `build_messages()` agrega automáticamente: `f"Respond in {user_language}. Output values (names, definitions, descriptions, jots, rationale) must be in {user_language}. Source quotes stay in original language."`
- Workers pasan `user_language` como variable extra en `run_agent()`

---

## 4. Instrucciones por Tier

### PRO (DeepSeek V4)
```markdown
[ROL]
You are a [role] for Classic Grounded Theory analysis.

[OBJETIVO]
1. [Concrete step]
2. [Concrete step]

[RESTRICCIONES]
- Work exclusively with the provided data.
- DO NOT use external tools or search for additional information.
- Output language: {user_language}. All natural language values (names, definitions,
  descriptions, jots, rationale) must be in {user_language}.
- Source quotes from segments MUST stay in their original language — never translate them.
- System codes (SAT, MOD, FORCED, baseline_data, etc.) are language-neutral.
```

### FLASH (Nemotron)
```markdown
## System
You are a [role]. [One sentence].

## Rules
- EXTRACT [what] from the provided data.
- CLASSIFY each item into [categories].
- RETURN results in {user_language}.
- KEEP source quotes in original language.

## Task
<data>{input_data}</data>

Respond EXCLUSIVELY in JSON format. Output values in {user_language}.
```

---

## 5. Agentes Legacy (.txt)

Los siguientes prompts legacy en `.txt` **no se usarán** en el nuevo sistema. Sus agentes han sido reemplazados:

| Legacy .txt | Reemplazado por | Estado |
|-------------|----------------|--------|
| `a1_population_context.txt` | `a1_population_context.md` (PRO) | Deprecado |
| `a3_sense_maker.txt` | `a3_sense_maker.md` (PRO) | Deprecado |
| `b1_sampling_distiller.txt` | `incident_comparator.md` (PRO) | Deprecado |
| `b3_hypothesis_generator.txt` | `b3_hypothesis_generator.md` (PRO) | Deprecado |
| `b2a_extract_indicators.txt` | `incident_extractor.md` (FLASH) | Deprecado |
| `b2b_generate_codes.txt` | `pattern_labeler.md` (PRO) | Deprecado |

---

## 6. Plan de Migración

| Fase | Tarea | Archivos |
|------|-------|----------|
| **T0** | Agregar `language` a `proyectos` (columna + default "es") | `project.py`, migración |
| **T1** | Modificar `loader.py` para inyectar `{user_language}` | `loader.py` |
| **T2** | Workers pasan `user_language` en cada `run_agent()` | `tasks.py` (heavy + fast) |
| **T3** | Traducir system prompts a inglés (6 PRO críticos primero) | `deepseek_pro/*.md` |
| **T4** | Traducir FLASH prompts (4 críticos) | `deepseek_flash/*.md` |
| **T5** | Traducir resto de prompts | `deepseek_pro/*.md`, `deepseek_flash/*.md` |
| **T6** | Eliminar/archivar legacy `.txt` | `prompts/*.txt` |

---

## 7. Verificación

Para cada prompt migrado:
1. El system prompt está en inglés
2. Las JSON schema `description` están en inglés
3. El user template incluye `{user_language}` o el loader lo inyecta
4. Los `enum` de códigos de sistema no cambiaron
5. El output mantiene el idioma del usuario para valores naturales
