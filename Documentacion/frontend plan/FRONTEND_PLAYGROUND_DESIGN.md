# GT Frontend — Theoretical Playground & Selective Coding UI

> Diseño de componentes para las Fases 5b (Selective Coding) y 6b (Theoretical Playground).
> Basado en el design system de `FRONTEND_PLAN.md`.

---

## 1. Análisis del estado actual

### Lo que existe
- **Framework:** React 19 + TypeScript + react-router-dom
- **Estilos:** inline styles (`style={{...}}`). Sin CSS modules ni styled-components.
- **API client:** `client.ts` con `request<T>()`, token JWT, tipos básicos (Project, Document, Category, Segment).
- **Páginas:** Login, Register, Projects, ProjectDetail.
- **Componentes:** carpeta `components/` vacía — no hay componentes reutilizables aún.

### Lo que NO existe
- Sistema de diseño implementado (solo documentado en `FRONTEND_PLAN.md`)
- Componentes reutilizables (Card, Pill, Blob)
- Canvas interactivo con física
- Paneles laterales
- Modales
- Animaciones CSS

### Decisión de implementación
Para mantener coherencia con el proyecto actual y minimizar dependencias:
- **Estilos:** CSS modules (`.module.css`). Un archivo por componente.
- **Física de blobs:** `d3-force` (ya en `package.json`).
- **Animaciones:** CSS `@keyframes` (shimmer, pulse, shake, breathe).
- **Estado global:** React Context (`PlaygroundContext`) para el ecosistema.
- **Renderizado:** SVG para blobs y tendriles (mejor performance que Canvas para <50 blobs).

---

## 2. Layout general — Theoretical Playground

```
┌──────────────────────────────────────────────────────────────────────────┐
│  TOP BAR: GT · Proyecto                              [◀ Volver] [···]   │
│  "Manteniendo relevancia profesional ante la IA"                          │
├──────────┬────────────────────────────────────────────┬──────────────────┤
│          │                                            │                  │
│  GUIDE   │          ECOSYSTEM CANVAS                  │   ELABORATION    │
│  PANEL   │                                            │   PANEL          │
│  (left)  │     ·  ·     ●●●●●      ·  ·              │   (right)        │
│  280px   │        ·   ●●●●●●●●●        ·             │   340px          │
│          │      ░░  ●●● CORE ●●●  ░░                │                  │
│  ┌────┐  │        ·   ●●●●●●●●●    ·                │  ┌────────────┐  │
│  │Recom│  │     ·  ───●●●●●───  ·                    │  │ Categoría  │  │
│  │endac│  │        ·  ││ tendril  ·  ·               │  │ selecc.    │  │
│  │iones│  │      ·  ───┘│  ·   ·                     │  │            │  │
│  │     │  │     ·  ●●●●●  ·  ░░ ghost                │  │ Definición │  │
│  └────┘  │        ·  ││ fisura                       │  │ Propiedades│  │
│          │     ·  ───┘│  ·                            │  │ Incidentes │  │
│  ┌────┐  │                                            │  │ Historial  │  │
│  │Gaps │  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  │            │  │
│  │aler-│  │  ▓▓ ZONA DE NEBLINA ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  │ [Renombrar]│  │
│  │tas  │  │  ▓▓ "Muestrear startups" ▓▓▓▓▓▓▓▓▓▓▓▓▓  │  │            │  │
│  └────┘  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │  └────────────┘  │
│          │                                            │                  │
│  ┌────┐  │  ┌──────────────────────────┐             │  ┌────────────┐  │
│  │Gap  │  │  │  Ghost-blobs (margin)   │             │  │ Relación   │  │
│  │Repo-│  │  │  ◌◌◌  ◌◌◌  ◌◌◌         │             │  │ selecc.    │  │
│  │rt   │  │  │  arrastrables →         │             │  │            │  │
│  └────┘  │  └──────────────────────────┘             │  │ Converg.   │  │
│          │                                            │  │ Diverg.    │  │
│          │                                            │  │ Código     │  │
│          │                                            │  └────────────┘  │
│          │                                            │                  │
│          │  BOTTOM BAR: [Sync gaps] [Layout auto]    │                  │
├──────────┴────────────────────────────────────────────┴──────────────────┤
│  STATUS BAR: 12 categorías · 5 relaciones · 3 gaps · Fase 6b             │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Jerarquía de componentes

```
PlaygroundPage                          ← nueva ruta /projects/:id/theory
├── PlaygroundProvider                  ← React Context (ecosystem state)
│   ├── TopBar
│   │   ├── Breadcrumb (Proyecto > Theoretical Playground)
│   │   ├── CoreConcernBadge
│   │   └── ActionButtons (Volver, Exportar)
│   │
│   ├── MainLayout (flex row)
│   │   ├── RecommendationGuide       ← panel izquierdo 280px
│   │   │   ├── GuideSection (Conexiones sugeridas)
│   │   │   │   └── GuideItem[]
│   │   │   ├── GuideSection (Ghost-blobs)
│   │   │   │   └── GuideItem[]
│   │   │   ├── GuideSection (Renombres)
│   │   │   │   └── GuideItem[]
│   │   │   ├── GuideSection (Zonas de neblina)
│   │   │   │   └── GuideItem[]
│   │   │   └── GuideSection (Tensiones)
│   │   │       └── GuideItem[]
│   │   │
│   │   ├── EcosystemCanvas            ← centro (flex: 1)
│   │   │   ├── <svg> (fondo oscuro, física d3-force)
│   │   │   │   ├── FogZone[]          ← overlays de neblina
│   │   │   │   ├── RelationshipTendril[] ← curvas Bézier
│   │   │   │   │   └── Fissure[]      ← zigzag dorado si divergencia
│   │   │   │   ├── CategoryBlob[]     ← círculos con gradiente
│   │   │   │   └── GhostBlob[]        ← círculos translúcidos
│   │   │   └── CanvasControls (zoom, reset layout)
│   │   │
│   │   └── ElaborationPanel           ← panel derecho 340px
│   │       ├── BlobDetail             ← cuando un blob está seleccionado
│   │       │   ├── CategoryHeader (nombre, capa, badge)
│   │       │   ├── DefinitionSection
│   │       │   ├── PropertiesList
│   │       │   ├── VersionTimeline
│   │       │   └── ActionButtons (Renombrar, Ver incidentes)
│   │       ├── TendrilDetail          ← cuando un tendril está seleccionado
│   │       │   ├── RelationshipHeader
│   │       │   ├── EvidenceList (convergente)
│   │       │   ├── DivergenceList (divergente)
│   │       │   └── TheoreticalCodeBadge
│   │       └── EmptyState             ← sin selección
│   │
│   ├── BottomBar
│   │   ├── SyncButton ("Sync gaps")
│   │   ├── AutoLayoutButton
│   │   └── StatusIndicator (categorías · relaciones · gaps · fase)
│   │
│   └── RenameModal                    ← overlay
│       ├── CurrentName
│       ├── SuggestionList (3 niveles)
│       └── CustomNameInput
```

---

## 4. Mockups detallados por componente

### 4.1 CategoryBlob

```
ESTADOS VISUALES:

  IDLE (estable, saturado)           DIVERGING (recién expandido)
       ●●●●●●●                            ●●●●●●●
     ●●●●●●●●●●●                        ●●●●●●●●●●●
    ●●●●●●●●●●●●        ──→            ●●●●●●●●●●●●   (tiembla 2s)
     ●●●●●●●●●●●                        ●●●●●●●●●●●
       ●●●●●●●                            ●●●●●●●
  borde: sólido, color capa           borde: pulsing ±4px

  SHIMMER (renombre sugerido)         NEEDS_SAMPLING (gap)
       ✦●●●●✦                             ·······
     ✦●●●●●●✦                           ···  ···
    ✦●●●●●●●●✦        ──→              ···    ···   (borde punteado)
     ✦●●●●●●✦                           ···  ···
       ✦●●●●✦                             ·······
  animación: hue-rotate 0→360 4s       borde: dashed 4 4

  DIVIDING (subdivide sugerido)
       ●●●    ●●●
     ●●●●●  ●●●●●
    ●●●●●●  ●●●●●●     (dos blobs separándose)
     ●●●●●  ●●●●●
       ●●●    ●●●
  animación: estrangulamiento

TAMAÑOS (radio en px):
  S  (1-5 inc):   32px    opacity: 0.55
  M  (6-15 inc):  44px    opacity: 0.70
  L  (16-30 inc): 58px    opacity: 0.85
  XL (31+ o core):72px    opacity: 0.95

RESPIRACIÓN (todos los blobs):
  radio += sin(t * 2.0 + phase) * 2.0
  fase aleatoria por blob.
```

### 4.2 RelationshipTendril

```
  TENDRIL ESTABLE (convergencia alta)     TENDRIL EMERGING (poca evidencia)
    ●━━━━━━━━━━━━━━━━━━●                    ● ┅ ┅ ┅ ┅ ┅ ┅ ┅ ●
    A     grosor 6px    B                    A  dashed 6 4    B
    color: layer                            color: layer, opacity 0.4

  TENDRIL CON FISURAS (divergencia)
    ●━━━━━━━━━━╱╲╱╲━━━━━━━━●
    A          fisura       B
    color fisura: #FFD700 (dorado)
    intensidad ∝ diverging_doc_count

  TENDRIL ACTIVO (evidencia recién añadida)
    ●━━━━━━━━━━━━━━━━━━━━●
    pulso: brillo 0→100%→0 en 1.5s
```

### 4.3 GhostBlob

```
  ◌◌◌◌◌◌◌
 ◌◌       ◌◌
◌◌   H31   ◌◌    opacity: 0.25
 ◌◌       ◌◌     borde: dashed 2 6
  ◌◌◌◌◌◌◌      radio: 20px fijo
                 label: hover
                 cursor: grab

  Al arrastrar hacia un blob → se agranda el blob destino (preview de absorción)
  Al soltar sobre un blob → animación de disolución + blob crece
  Al soltar en vacío → vuelve a su posición
```

### 4.4 FogZone

```
  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓
  ▓▓                         ▓▓
  ▓▓   Zona de muestreo      ▓▓    overlay radial
  ▓▓   "Buscar startups"     ▓▓    center: #FFF 10%
  ▓▓                         ▓▓    edge: transparent
  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓    cursor: pointer
```

### 4.5 ElaborationPanel

```
┌─────────────────────────────────┐
│ CATEGORÍA                       │
│                                 │
│ ┌─ Nombre ────────────────────┐ │
│ │ Analizando patrones    [✦]  │ │  ← [✦] = shimmer si rename pending
│ │ Capa: variación             │ │
│ └─────────────────────────────┘ │
│                                 │
│ ┌─ Definición ────────────────┐ │
│ │ Los periodistas examinan el │ │
│ │ impacto sistémico de la IA  │ │
│ │ más allá de la herramienta. │ │
│ │                   v3 [editar]│ │
│ └─────────────────────────────┘ │
│                                 │
│ ┌─ Propiedades (5) ───────────┐ │
│ │ Alcance: herramienta→sistema│ │
│ │ Profundidad: superficial→   │ │
│ │   profundo            ⚠️    │ │  ← ⚠️ = 0 casos en "superficial"
│ │ Motor: amenaza→curiosidad  │ │
│ │ Foco: tecnología→democracia│ │
│ │ Resultado: parálisis→acción│ │
│ └─────────────────────────────┘ │
│                                 │
│ ┌─ Historial ─────────────────┐ │
│ │ v1 (20 may) "Cuestionando   │ │
│ │   el impacto de la IA"      │ │
│ │ v2 (01 jun) "Analizando     │ │
│ │   efectos sociales de la IA"│ │
│ │ v3 (10 jun) actual          │ │
│ │   + propiedad "Resultado"   │ │
│ └─────────────────────────────┘ │
│                                 │
│ ┌─ Incidentes (18) ───────────┐ │
│ │ [ver 18 incidentes]    [→]  │ │
│ └─────────────────────────────┘ │
│                                 │
│ [✦ Sugerir renombre]           │
│ [🔄 Forzar re-saturación]      │
└─────────────────────────────────┘

CUANDO NO HAY SELECCIÓN:

┌─────────────────────────────────┐
│                                 │
│      (ninguna categoría        │
│       seleccionada)            │
│                                 │
│  Arrastrá dos blobs juntos     │
│  para explorar una relación.   │
│                                 │
│  Hacé clic en un blob para     │
│  ver sus propiedades.          │
│                                 │
└─────────────────────────────────┘
```

### 4.6 RecommendationGuide

```
┌────────────────────────────────┐
│ GUÍA DE ELABORACIÓN    [⟳]    │
├────────────────────────────────┤
│                                │
│ ▼ CONEXIONES SUGERIDAS (3)    │
│ ┌────────────────────────────┐ │
│ │ 'Percibir amenaza' y       │ │
│ │ 'Analizar patrones' co-    │ │
│ │ ocurren en 7 docs.         │ │
│ │                      [→]   │ │
│ └────────────────────────────┘ │
│ ┌────────────────────────────┐ │
│ │ 'Integrar' y 'Reforzar     │ │
│ │ identidad' comparten 5     │ │
│ │ docs sin relación.  [→]   │ │
│ └────────────────────────────┘ │
│                                │
│ ▼ GHOST-BLOBS (2)             │
│ ┌────────────────────────────┐ │
│ │ Memo H31: 'El análisis se  │ │
│ │ intensifica en gestores'   │ │
│ │ Arrastrar → Analizando  [→]│ │
│ └────────────────────────────┘ │
│                                │
│ ▼ RENOMBRES SUGERIDOS (1)    │
│ ┌────────────────────────────┐ │
│ │ 'Analizando patrones' —    │ │
│ │ 3 versiones de definición. │ │
│ │ Nombre sugerido:           │ │
│ │ 'Escaneando el horizonte   │ │
│ │ de amenazas'        [✦]   │ │
│ └────────────────────────────┘ │
│                                │
│ ▼ ZONAS DE NEBLINA (2)       │
│ ┌────────────────────────────┐ │
│ │ Capa 'consecuencias' sin   │ │
│ │ relaciones elaboradas.     │ │
│ │ Sugerido: explorar qué     │ │
│ │ produce Integrar.   [🔍]  │ │
│ └────────────────────────────┘ │
│                                │
│ ▼ TENSIONES (1)               │
│ ┌────────────────────────────┐ │
│ │ 'Analizar'—'Integrar'      │ │
│ │ 2 datos divergentes sin    │ │
│ │ resolver.           [↗]   │ │
│ └────────────────────────────┘ │
└────────────────────────────────┘
```

### 4.7 RenameModal

```
┌──────────────────────────────────────────┐
│            ✦ RENOMBRAR CATEGORÍA         │
│                                          │
│  Nombre actual: Analizando patrones      │
│  sociales                                │
│                                          │
│  ── CONSERVADOR ──────────────────────── │
│  ○ Analizando el impacto sistémico       │
│    de la tecnología                      │
│    → Mayor precisión, mantiene la esencia│
│                                          │
│  ── MODERADO ─────────────────────────── │
│  ○ Escaneando el horizonte de amenazas   │
│    → Captura la dimensión prospectiva    │
│      y el motor de amenaza profesional   │
│                                          │
│  ── TRANSFORMADOR ────────────────────── │
│  ○ Calibrando la percepción de riesgo    │
│    → Revela la función latente: ajustar  │
│      evaluación de amenaza profesional   │
│                                          │
│  ── PERSONALIZADO ────────────────────── │
│  ┌──────────────────────────────────────┐│
│  │ Escribí tu propio nombre...          ││
│  └──────────────────────────────────────┘│
│                                          │
│  Justificación del cambio:               │
│  ┌──────────────────────────────────────┐│
│  │ (opcional)                           ││
│  └──────────────────────────────────────┘│
│                                          │
│  [Cancelar]              [Aplicar nombre]│
└──────────────────────────────────────────┘
```

---

## 5. Flujos de interacción

### 5.1 Proponer relación (arrastrar blobs)

```
1. Usuario hace mousedown en Blob A
2. Blob A se eleva (z-index, sombra)
3. Usuario arrastra hacia Blob B
4. Blob B se ilumina (glow) cuando está en rango
5. Usuario suelta → aparece menú contextual:
   ┌─────────────────────────────┐
   │ ¿Qué tipo de relación?      │
   │                             │
   │ ○ Secuencia temporal        │
   │ ○ Causalidad                │
   │ ○ Oposición                 │
   │ ○ Variante / Tipo           │
   │ ○ Condición                 │
   │ ○ Consecuencia              │
   │ ○ No sé — sugerir           │
   │                             │
   │ [Cancelar]                  │
   └─────────────────────────────┘
6. Usuario elige → POST /elaboration/relationships
7. Tendril aparece (delgado, "emerging")
8. Tras respuesta del backend, tendril se actualiza (grosor, fisuras)
9. ElaborationPanel muestra resultado
```

### 5.2 Elaborar divergencia (clic en fisura)

```
1. Usuario hace clic en fisura dorada de un tendril
2. Fisura se expande mostrando incidentes divergentes:
   ┌──────────────────────────────────────┐
   │ Dato divergente (07_Carlos):         │
   │ "La empecé a usar y luego me di     │
   │  cuenta de los problemas"            │
   │                                      │
   │ Carlos integró ANTES de analizar.    │
   │                                      │
   │ ¿Cómo expandir la relación?          │
   │ ○ Agregar condición: "Bajo urgencia  │
   │   laboral, la secuencia se invierte" │
   │ ○ Crear ruta alternativa             │
   │ ○ Acotar la relación                 │
   │ ○ Registrar como excepción           │
   │                                      │
   │ [Aplicar]  [Ignorar]                │
   └──────────────────────────────────────┘
3. Usuario elige → PUT /elaboration/relationships/:id/diverge
4. Fisura desaparece, tendril se vuelve más complejo
   (aparece rama condicional)
```

### 5.3 Absorber ghost-blob

```
1. Usuario arrastra ghost-blob hacia un blob
2. Blob destino muestra glow de "absorción"
3. Usuario suelta → confirmación:
   ┌──────────────────────────────────────┐
   │ ¿Absorber Memo H31 en                │
   │ 'Analizando patrones sociales'?      │
   │                                      │
   │ Esto añadiría la propiedad:          │
   │ "Intensidad del análisis"            │
   │ con gradiente:                       │
   │ moderada ↔ intensa                   │
   │                                      │
   │ [Absorber]  [Cancelar]              │
   └──────────────────────────────────────┘
4. Usuario confirma → POST /elaboration/ghosts/:id/absorb
5. Ghost-blob se disuelve (animación fade-out)
6. Blob crece ligeramente, textura se vuelve más densa
7. Si la definición se expandió → aparece shimmer
```

### 5.4 Renombrar categoría

```
1. Usuario hace clic en [✦] del blob o en botón del panel
2. Se abre RenameModal con sugerencias del backend
   (GET /elaboration/rename-suggestions/:categoryId)
3. Usuario selecciona una sugerencia o escribe nombre propio
4. Usuario hace clic en "Aplicar nombre"
   → POST /elaboration/rename
5. Modal se cierra
6. Blob cambia de color gradualmente (transición 2s)
7. Label del blob se actualiza
8. Panel muestra nuevo nombre + entrada en historial
```

---

## 6. API endpoints requeridos (resumen)

Los componentes necesitan las siguientes funciones en `client.ts`:

```typescript
// Theoretical Codes
getTheoreticalCodes(projectId): Promise<TheoreticalCode[]>
createTheoreticalCode(projectId, body): Promise<void>

// Ecosystem
getEcosystem(projectId): Promise<EcosystemState>
saveEcosystemLayout(projectId, layout): Promise<void>

// Relationships
elaborateRelationship(projectId, body): Promise<Relationship>
getRelationships(projectId): Promise<Relationship[]>
getRelationship(projectId, relId): Promise<Relationship>
resolveDivergence(projectId, relId, body): Promise<void>

// Ghosts
getGhosts(projectId): Promise<GhostBlob[]>
absorbGhost(projectId, memoId, targetCategoryId): Promise<void>

// Renames
getRenameSuggestions(projectId, categoryId): Promise<RenameSuggestions>
applyRename(projectId, body): Promise<void>
getDefinitionHistory(projectId, categoryId): Promise<DefinitionVersion[]>

// Recommendations
getRecommendations(projectId): Promise<Recommendation[]>
getTheoreticalModel(projectId): Promise<ModelSummary>

// Saturation (ya existe en analysis.py)
getSaturationGaps(projectId): Promise<GapReport>
refreshSaturationGaps(projectId): Promise<void>
```

---

## 7. Plan de implementación

| # | Componente | Dependencias | Estimación |
|---|-----------|-------------|------------|
| 1 | Tipos + API functions en `client.ts` | Ninguna | 30 min |
| 2 | `PlaygroundContext` (estado global) | Tipos | 30 min |
| 3 | `CategoryBlob` + animaciones CSS | Context | 1 h |
| 4 | `RelationshipTendril` + fisuras | Context, CategoryBlob | 1 h |
| 5 | `GhostBlob` | Context | 30 min |
| 6 | `FogZone` | Context | 20 min |
| 7 | `EcosystemCanvas` (SVG + d3-force) | Blob, Tendril, Ghost, Fog | 2 h |
| 8 | `ElaborationPanel` (BlobDetail + TendrilDetail) | Context | 1.5 h |
| 9 | `RecommendationGuide` | Context | 1 h |
| 10 | `RenameModal` | Context | 45 min |
| 11 | `PlaygroundPage` (ensambla todo) | Todos los anteriores | 1 h |
| 12 | Ruta en `App.tsx` | PlaygroundPage | 5 min |

**Total estimado: ~10 horas.**
