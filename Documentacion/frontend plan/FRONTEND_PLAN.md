# GT Frontend — Design System & Views

> Lenguaje visual para el sistema CGT. Coherencia completa entre paneles.
> Tema: oscuro azulado/púrpura. Fondo grisáceo claro para contraste suave.

---

## 🎨 Design Tokens

```
┌─ Colors ─────────────────────────────────────────────────────────┐
│                                                                   │
│  Surface                                                        │
│  ┌───────┬───────┬───────┬───────┬───────┐                      │
│  │ #0D1117│ #161B22│ #1C2333│ #21262D│ #2A1A3A│                 │
│  │ bg-base│ bg-elev│ bg-card│border │accent │                   │
│  │ negro  │ated   │       │       │púrpura│                      │
│  │ azulado│       │       │       │       │                      │
│  └───────┴───────┴───────┴───────┴───────┘                      │
│                                                                   │
│  Text                                                            │
│  ┌───────┬───────┬───────┬───────┐                              │
│  │ #E6EDF3│ #8B949E│ #484F58│ #58A6FF│                          │
│  │ text-p │ text-s │ text-d │ link   │                          │
│  │ rimary │ econdar│ isabled│        │                          │
│  └───────┴───────┴───────┴───────┘                              │
│                                                                   │
│  Semantic                                                        │
│  ┌───────┬───────┬───────┬───────┬───────┬───────┐             │
│  │ #3FB950│ #D29922│ #F85149│ #A371F7│ #79C0FF│ #56D364│        │
│  │ satura │ warning│ error  │ elabora│ info   │ conver │        │
│  │ ted    │        │        │ tion   │        │ gence  │        │
│  └───────┴───────┴───────┴───────┴───────┴───────┘             │
│                                                                   │
│  Saturation gradient:  #F85149 → #D29922 → #3FB950 → #A371F7    │
│  (unsaturated)      (warning)     (saturated)   (elaborated)     │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘

┌─ Typography ──────────────────────────────────────────────────────┐
│                                                                   │
│  Font: Inter (UI), JetBrains Mono (code/segment text)            │
│                                                                   │
│  Scale:                                                           │
│    xs: 11px · sm: 13px · base: 15px · lg: 18px                   │
│    xl: 24px · 2xl: 32px · 3xl: 48px                              │
│                                                                   │
│  Weights: 400 (body), 500 (label), 600 (heading), 700 (title)    │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘

┌─ Spacing & Radius ────────────────────────────────────────────────┐
│                                                                   │
│  Spacing: 4px grid (4, 8, 12, 16, 24, 32, 48, 64)               │
│  Radius: 6px (cards), 8px (modals), 12px (blobs), 999px (pills)  │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Component Library

### Card
```
┌──────────────────────────────────────────┐
│ ┌─ header (optional) ──────────────────┐ │
│ │ Title                        [action]│ │
│ └──────────────────────────────────────┘ │
│                                          │
│ Content area                             │
│                                          │
│ ┌─ footer (optional) ──────────────────┐ │
│ │ Meta info                             │ │
│ └──────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```
- bg: `#1C2333`, border: `#21262D`, radius: 6px
- padding: 16px, gap: 12px

### Pill / Badge
```
┌──────────────┐
│ ● label      │
└──────────────┘
```
- radius: 999px, padding: 2px 10px, font: 11px/500
- Colors: green (SAT), yellow (WARN), red (ERR), purple (elaborating)

### Blob (categoría viva)
```
     ●●●●●●●
   ●●●●●●●●●●●   Color = fase de saturación
  ●●●●●●●●●●●●   Tamaño = incident_count
   ●●●●●●●●●●●   Borde = estado (sólido=estable, punteado=gap, tembloroso=divergence)
     ●●●●●●●
```
- CSS: radial-gradient + box-shadow + animation
- States: idle, converging (pulse green), diverging (shake), rename (shimmer)

### Hypothesis Card
```
┌──────────────────────────────────────────┐
│ 🟡 emergent                    0.5      │
│                                          │
│ Micro-resistencia adaptativa             │
│                                          │
│ Evidence: Docs 1 y 3.                    │
│                                          │
│ [✓ Accept] [✎ Modify] [✗ Reject] [🔀]  │
└──────────────────────────────────────────┘
```
- bg: `#1C2333`, accent left border by level (emergent=yellow, specific=blue, general=green)

### Gap Row
```
┌──────────────────────────────────────────┐
│ 🔴 CRÍTICO                               │
│ "Analizando patrones" — saturada pero    │
│ vacía en extremo "superficial"          │
│ → Muestrear casos de integración     [→] │
└──────────────────────────────────────────┘
```
- Left accent: severity color
- Hover: bg lightens slightly

---

## 📱 View 1: Project Dashboard

```
┌──────────────────────────────────────────────────────────────────┐
│  GT · Proyecto                                   [Config] [···] │
│  Adaptación a plataformas digitales                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐│
│  │    12      │  │     8      │  │     3      │  │    85%     ││
│  │ Documentos │  │ Categorías │  │ Hipótesis  │  │ Saturación ││
│  │   subidos  │  │  abiertas  │  │ candidatas │  │   global   ││
│  └────────────┘  └────────────┘  └────────────┘  └────────────┘│
│                                                                   │
│  ┌─ Pipeline Activity ─────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  📄 entrevista_03.txt                                       │ │
│  │  ████████████████████████████████░░░░░░░ 85%                 │ │
│  │  A1✓ A2✓ A3✓ B1✓ B2⟳ B2.5...                               │ │
│  │                                                              │ │
│  │  📄 entrevista_02.txt                                       │ │
│  │  ████████████████████████████████████████ 100% ✓            │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Saturation Overview ───────────────────────────────────────┐ │
│  │                                                              │ │
│  │  ●●●●●●●  ●●●      ●        ●●●●●●●●●●                     │ │
│  │  Percib-   Negoc-    Evad-    Balance-                       │ │
│  │  iendo     iando     iendo    ando                           │ │
│  │  SAT ✓     ≈ media   ⚠ alta   SAT ✓                         │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Population Context (A1) ───────────────────────────────────┐ │
│  │ v3 · Tensión autonomía-dependencia. Metáforas espaciales.   │ │
│  │                                        [Ver historial →]    │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📱 View 2: Document Upload + Progress

```
┌──────────────────────────────────────────────────────────────────┐
│  📄 Documents                                    [+ Upload]      │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Upload Area ───────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │              ┌──────────────────────┐                        │ │
│  │              │     📤  Drop files    │                        │ │
│  │              │   or click to browse  │                        │ │
│  │              │                      │                        │ │
│  │              │  PDF · TXT · DOCX    │                        │ │
│  │              │  MP3 · MP4 · JPG     │                        │ │
│  │              │  Max 50 MB           │                        │ │
│  │              └──────────────────────┘                        │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Filter ─────────────────────────────────────────────────────┐ │
│  │ [All] [Processing] [Ready] [Error]          🔍 Search...    │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Document List ──────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  📄 entrevista_01.txt                         3m ago  ✓     │ │
│  │  ████████████████████████████████████████ 100%              │ │
│  │  23 segmentos · 5 códigos asignados                         │ │
│  │                                                              │ │
│  │  📄 entrevista_02.txt                         8m ago  ✓     │ │
│  │  ████████████████████████████████████████ 100%              │ │
│  │  18 segmentos · 3 códigos asignados                         │ │
│  │                                                              │ │
│  │  📄 grupo_focal_01.mp3                       12m ago  ⟳     │ │
│  │  ████████████████░░░░░░░░░░░░░░░░░░░░ 52%                   │ │
│  │  Transcribiendo...                                           │ │
│  │                                                              │ │
│  │  📄 entrevista_03.txt                         2m ago  ✗     │ │
│  │  ██████████░░░░░░░░░░░░░░░░░░░░░░░░░░ 30%                   │ │
│  │  Error: texto extraído vacío                      [Retry]   │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📱 View 3: Coding View

```
┌──────────────────────────────────────────────────────────────────┐
│  🏷 Coding · entrevista_01.txt                   [← Back]        │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Segment List ───────────────────┬─ Code Panel ──────────────┐│
│  │                                  │                            ││
│  │ [baseline] [properline] [all]   │  Categorías (8)            ││
│  │                                  │                            ││
│  │ ┌────────────────────────────┐  │  ┌──────────────────────┐  ││
│  │ │ #1                         │  │  │ Evadiendo control    │  ││
│  │ │ "Bueno, yo creo que la     │  │  │ 12 segmentos · 0.92 │  ││
│  │ │  verdad es que el sistema  │  │  │ [Asignar]            │  ││
│  │ │  no funciona como debería" │  │  └──────────────────────┘  ││
│  │ │                            │  │                            ││
│  │ │ properline_data            │  │  ┌──────────────────────┐  ││
│  │ │ [Asignar código ▾]        │  │  │ Negociando permanen- │  ││
│  │ └────────────────────────────┘  │  │ cia                  │  ││
│  │                                  │  │ 8 segmentos · 0.85  │  ││
│  │ ┌────────────────────────────┐  │  │ [Asignar]            │  ││
│  │ │ #2                         │  │  └──────────────────────┘  ││
│  │ │ "Siempre tengo que estar   │  │                            ││
│  │ │  pendiente de que no me    │  │  ┌──────────────────────┐  ││
│  │ │  bajen los pedidos."       │  │  │ + Nuevo código       │  ││
│  │ │                            │  │  │                      │  ││
│  │ │ baseline_data ⬤            │  │  │ Nombre: ___________  │  ││
│  │ │ [Asignar código ▾]        │  │  │ Def: _______________ │  ││
│  │ └────────────────────────────┘  │  └──────────────────────┘  ││
│  │                                  │                            ││
│  │ ┌────────────────────────────┐  │  💡 Sugerencias IA         ││
│  │ │ #3                         │  │  ┌──────────────────────┐  ││
│  │ │ "A veces acepto los que    │  │  │ "Evadiendo control"   │  ││
│  │ │  salen aunque no valgan    │  │  │  score: 0.89          │  ││
│  │ │  la pena"                  │  │  │  [Aceptar] [Ignorar]  │  ││
│  │ │                            │  │  └──────────────────────┘  ││
│  │ │ baseline_data ⬤            │  │                            ││
│  │ │ [Asignar código ▾]        │  │                            ││
│  │ └────────────────────────────┘  │                            ││
│  │                                  │                            ││
│  └──────────────────────────────────┴────────────────────────────┘│
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

**Estados de segmento:**
- ⬤ verde = baseline_data (oro)
- 🟡 amarillo = properline_data
- 🟠 naranja = interpreted_data
- ⚪ gris = vague_data

**Interacciones:**
- Click en segmento → expande texto completo
- Drag de segmento a código → asigna
- Click en sugerencia IA → auto-asigna con confirmación
- Filter tabs: baseline primero (default)

---

## 📱 View 4: Saturation Dashboard

```
┌──────────────────────────────────────────────────────────────────┐
│  📊 Saturation                          [Sync Analysis] [···]    │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Global Stats ───────────────────────────────────────────────┐ │
│  │  85% saturated · 3 warnings · 2 critical                    │ │
│  │  ████████████████████████████████░░░░░░░                     │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Blob Grid ──────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │ │
│  │  │ ●●●●●●●  │  │ ●●●●●    │  │ ●●●      │  │ ●        │    │ │
│  │  │Percibien-│  │Balancean-│  │Negociando│  │Evadiendo │    │ │
│  │  │do amenaza│  │do riesgo │  │permanenci│  │control   │    │ │
│  │  │          │  │          │  │a         │  │          │    │ │
│  │  │ 12 docs  │  │ 8 docs   │  │ 5 docs   │  │ 2 docs   │    │ │
│  │  │ std:0.04 │  │ std:0.09 │  │ std:0.15 │  │ std:0.28 │    │ │
│  │  │ ✓ SAT    │  │ ✓ SAT    │  │ ≈ media  │  │ ⚠ alta   │    │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Gap Report ─────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  🔴 CRÍTICO (2)                                              │ │
│  │  ┌──────────────────────────────────────────────────────────┐│ │
│  │  │ MATH · "Analizando patrones"                             ││ │
│  │  │ Saturada matemáticamente pero vacía en extremo           ││ │
│  │  │ "superficial" de PROFUNDIDAD.                            ││ │
│  │  │ → Muestrear casos de integración superficial.     [→]   ││ │
│  │  ├──────────────────────────────────────────────────────────┤│ │
│  │  │ AXES · ROL_ORGANIZACIONAL="fundador"                     ││ │
│  │  │ 0 documentos en esta categoría de muestreo.              ││ │
│  │  │ → ¿Existen fundadores? Recolectar o marcar límite. [→]  ││ │
│  │  └──────────────────────────────────────────────────────────┘│ │
│  │                                                              │ │
│  │  🟡 WARNING (3)                                              │ │
│  │  ┌──────────────────────────────────────────────────────────┐│ │
│  │  │ MATH · "Resistiendo adopción" — std:0.32                ││ │
│  │  │ → Continuar codificación selectiva.                      ││ │
│  │  ├──────────────────────────────────────────────────────────┤│ │
│  │  │ PARADIGM · "Negociando permanencia" — expandió           ││ │
│  │  │ → 3/5 iteraciones para saturación paradigmática.        ││ │
│  │  ├──────────────────────────────────────────────────────────┤│ │
│  │  │ DENSITY · "Balanceando riesgo" — sin relaciones         ││ │
│  │  │ → Conectar en el Theoretical Playground.                ││ │
│  │  └──────────────────────────────────────────────────────────┘│ │
│  │                                                              │ │
│  │  🟢 SATURADO (4)                                             │ │
│  │  ┌──────────────────────────────────────────────────────────┐│ │
│  │  │ Percibiendo amenaza · Balanceando riesgo                 ││ │
│  │  │ Construyendo confianza · Adaptando estrategia            ││ │
│  │  └──────────────────────────────────────────────────────────┘│ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📱 View 5: Hypothesis Panel (HITL)

```
┌──────────────────────────────────────────────────────────────────┐
│  💡 Hypothesis Review                          3 candidates      │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Filter ─────────────────────────────────────────────────────┐ │
│  │ [All] [Candidate] [Accepted] [Rejected] [Split]              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ 🟡 emergent                                   0.5 ⬤          │ │
│  │                                                              │ │
│  │ Micro-resistencia adaptativa                                 │ │
│  │                                                              │ │
│  │ [MOCK] Micro-resistencia adaptativa.                         │ │
│  │ Evidence: Docs 1 y 3.                                        │ │
│  │                                                              │ │
│  │ ┌─ Evidence Preview ───────────────────────────────────┐    │ │
│  │ │ Doc 1: "Siempre tengo que estar pendiente de que     │    │ │
│  │ │ no me bajen los pedidos."                            │    │ │
│  │ │ Doc 3: "Mis compañeros hacen lo mismo, cada uno      │    │ │
│  │ │ tiene su estrategia."                                │    │ │
│  │ └──────────────────────────────────────────────────────┘    │ │
│  │                                                              │ │
│  │  [✓ Accept]    [✎ Modify]    [✗ Reject]    [🔀 Split]     │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Modify Modal ───────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  New text:                                                   │ │
│  │  ┌──────────────────────────────────────────────────────┐    │ │
│  │  │ La experiencia acumulada en la plataforma incrementa │    │ │
│  │  │ la sofisticación de estrategias de evasión del       │    │ │
│  │  │ control algorítmico, especialmente entre veteranos.  │    │ │
│  │  └──────────────────────────────────────────────────────┘    │ │
│  │                                                              │ │
│  │  Level: [emergent ▾]    Confidence: [0.5 ▾]                 │ │
│  │                                                              │ │
│  │  Justification:                                              │ │
│  │  ┌──────────────────────────────────────────────────────┐    │ │
│  │  │ Añadido matiz de "especialmente entre veteranos"     │    │ │
│  │  │ basado en Doc2.                                      │    │ │
│  │  └──────────────────────────────────────────────────────┘    │ │
│  │                                                              │ │
│  │               [Save]          [Cancel]                       │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📱 View 6: Elaboration View (Categoría viva)

```
┌──────────────────────────────────────────────────────────────────┐
│  🔬 "Negociando permanencia"                      [← Categories] │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Blob ───────────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │              ●●●●●●●●●●●●●                                  │ │
│  │           ●●●●●●●●●●●●●●●●●●                                │ │
│  │         ●●●●●●●●●●●●●●●●●●●●●●                              │ │
│  │       ●●●●●●●●●●●●●●●●●●●●●●●●●●                            │ │
│  │     ●●●●●●●●●●●●●●●●●●●●●●●●●●●●●●                          │ │
│  │       ●●●●●●●●●●●●●●●●●●●●●●●●●●                            │ │
│  │         ●●●●●●●●●●●●●●●●●●●●●●                              │ │
│  │           ●●●●●●●●●●●●●●●●●●                                │ │
│  │              ●●●●●●●●●●●●●                                  │ │
│  │                                                              │ │
│  │       12 incidentes · 5 sin expandir                         │ │
│  │       ████████████████████████████░░░░ 85% → SATURADO       │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Latest Incident ────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  Doc 3 · "A veces acepto los que salen aunque no valgan     │ │
│  │  la pena, porque si no me quedo sin nada."                  │ │
│  │                                                              │ │
│  │  ┌─ Elaboration ───────────────────────────────────────┐    │ │
│  │  │ 🟢 CONVERGE                                          │    │ │
│  │  │                                                      │    │ │
│  │  │ Confirma propiedad "intensidad: alta".               │    │ │
│  │  │ El entrevistado acepta pedidos no rentables para     │    │ │
│  │  │ mantener presencia en la plataforma.                 │    │ │
│  │  │                                                      │    │ │
│  │  │ Action: none                                         │    │ │
│  │  └──────────────────────────────────────────────────────┘    │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Definition History ─────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  v4 ← diverges_dimension (nueva propiedad "contexto")       │ │
│  │  ┌──────────────────────────────────────────────────────┐   │ │
│  │  │ Patrón de comportamiento donde el participante       │   │ │
│  │  │ ajusta su presencia y estrategia en la plataforma    │   │ │
│  │  │ para mantener viabilidad económica.                  │   │ │
│  │  │                                                      │   │ │
│  │  │ Propiedades:                                         │   │ │
│  │  │  • intensidad: baja ⟶ alta                          │   │ │
│  │  │  • temporalidad: esporádica ⟶ constante              │   │ │
│  │  │  • contexto: horas pico, zonas periféricas           │   │ │
│  │  └──────────────────────────────────────────────────────┘   │ │
│  │                                                              │ │
│  │  v3 ← convergence × 3                                       │ │
│  │  v2 ← diverges_dimension (gradiente "intensidad")           │ │
│  │  v1 ← initial definition                                    │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Actions ────────────────────────────────────────────────────┐ │
│  │  [✎ Rename]  [🔀 Subdivide]  [↔ Merge with...]             │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

**Estados del blob:**
- `idle`: gradiente suave del color de saturación
- `converging`: pulso verde (#56D364), 2s ease-in-out
- `diverging_dimension`: borde naranja (#D29922), ligero shake
- `diverging_property`: borde púrpura (#A371F7), crecimiento animado
- `diverging_strong`: borde rojo (#F85149), shake fuerte, botón HITL
- `rename_pending`: shimmer dorado sobre el nombre

---

## 📱 View 7: Coding Style Selector

```
┌──────────────────────────────────────────────────────────────────┐
│  🎨 Coding Styles · Project Config                               │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Choose coding styles for this project. You can select multiple.  │
│  The system will use any of the selected styles for each code.    │
│                                                                   │
│  ┌─ Active ─────────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────┐ [×]   │ │
│  │  │ 🟢 Gerundios (Glaser)                            │       │ │
│  │  │ "Negociando límites", "Evadiendo control"        │       │ │
│  │  │ Process Coding — default CGT                      │       │ │
│  │  └──────────────────────────────────────────────────┘       │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────┐ [×]   │ │
│  │  │ 💬 In Vivo (citas literales)                     │       │ │
│  │  │ '"cada uno tiene su maña"', '"acepto las que     │       │ │
│  │  │ valen"'                                           │       │ │
│  │  │ In Vivo Coding — expresiones nativas              │       │ │
│  │  └──────────────────────────────────────────────────┘       │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Available ──────────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────┐ [+]   │ │
│  │  │ 📝 Verbos nominalizados (-ción, -miento)         │       │ │
│  │  │ "Negociación", "Evitación", "Construcción"       │       │ │
│  │  └──────────────────────────────────────────────────┘       │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────┐ [+]   │ │
│  │  │ 📄 Paráfrasis descriptiva                        │       │ │
│  │  │ "El algoritmo decide sin consultar"              │       │ │
│  │  └──────────────────────────────────────────────────┘       │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────┐ [+]   │ │
│  │  │ 🏷 TEMA → subtema                                │       │ │
│  │  │ "Control algorítmico → Resistencia"              │       │ │
│  │  └──────────────────────────────────────────────────┘       │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────┐ [+]   │ │
│  │  │ 🔗 Cadenas causales (A → B)                      │       │ │
│  │  │ "Falta de transparencia → Desconfianza"          │       │ │
│  │  └──────────────────────────────────────────────────┘       │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Combined instruction preview:                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ Puedes usar CUALQUIERA de estos estilos:                     │ │
│  │   • Nombra cada código con un GERUNDIO (-ando/-iendo)...    │ │
│  │   • Nombra cada código con una CITA TEXTUAL...              │ │
│  │                                                              │ │
│  │ Elige el más adecuado para cada código.                     │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│                              [Save]                               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 📱 View 8: Population Context

```
┌──────────────────────────────────────────────────────────────────┐
│  🧠 Population Context · v3                       [← Dashboard]  │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─ Surprising Details ─────────────────────────────────────────┐ │
│  │ Tensión autonomía-dependencia. Los entrevistados oscilan     │ │
│  │ entre querer control total sobre su trabajo y depender       │ │
│  │ completamente del algoritmo para obtener ingresos.           │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Language Patterns ──────────────────────────────────────────┐ │
│  │ Metáforas espaciales: "estar en la zona", "moverse",        │ │
│  │ "quedarse parado". Lenguaje de juego: "ganar", "perder",     │ │
│  │ "vale la pena", "no rinde".                                  │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Data Production Context ────────────────────────────────────┐ │
│  │ Entrevistas realizadas en zonas de espera de repartidores.   │ │
│  │ Algunos entrevistados mostraban fatiga (entrevistados al     │ │
│  │ final de su jornada). Posible deseabilidad social en         │ │
│  │ críticas a la plataforma.                                    │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌─ Version History ────────────────────────────────────────────┐ │
│  │                                                              │ │
│  │  ● v3 — Doc 3 añadió "metáforas espaciales"         2m ago  │ │
│  │  ● v2 — Doc 2 confirmó "tensión autonomía-dependencia" 8m   │ │
│  │  ● v1 — Doc 1 — initial context                      12m ago │ │
│  │                                                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  Source documents: Doc 1 · Doc 2 · Doc 3                          │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🧭 Navigation Structure

```
┌──────────────────────────────────────────────────────────────────┐
│  GT                                          [🔔] [👤 User]     │
├──────────────────────────────────────────────────────────────────┤
│  [📊 Dashboard] [📄 Docs] [🏷 Coding] [💡 Hypotheses] [🔬 Elab] │
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│                        CONTENT AREA                               │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

**Sidebar (collapsible):**
```
┌──────────────┐
│ GT           │
├──────────────┤
│ 📊 Dashboard │
│ 📄 Documents │
│ 🏷 Coding    │
│ 💡 Hypotheses│
│ 🔬 Elaborat..│
│ 📊 Saturation│
│ 🧠 Context   │
│ 🎨 Styles    │
├──────────────┤
│ ⚙ Settings   │
└──────────────┘
```

---

## 🔄 Real-time Updates (SSE → UI)

| SSE Event | UI Reaction |
|---|---|
| `doc_status` | Progress bar updates, badge changes color |
| `incident_elaborated` | Blob pulses/grows/shakes based on elaboration_type |
| `hypotheses_ready` | Badge counter increments, notification dot |
| `phase_complete` | Pipeline step checkmarks fill in |
| `saturation_update` | Blob color transitions on gradient |
| `action_suggested` | HITL notification with action button |
| `rename_suggested` | Blob name shimmers, rename prompt appears |

---

## 📐 Responsive Breakpoints

```
Mobile:       < 768px   — single column, cards stack, sidebar → bottom nav
Tablet:    768-1024px   — two columns where useful (segment list + code panel)
Desktop:    > 1024px    — full layout with sidebar
```
