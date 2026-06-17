# 7-AddMemo System — Análisis Profundo de Problemas y Soluciones

> **Complementa:** `7-AddMemo_System.md` con diagnóstico de 11 problemas y soluciones diseñadas.

---

## 1. Matriz de Problemas

| # | Problema | Severidad | Impacto | Tipo |
|---|----------|-----------|---------|------|
| P1 | **Consistencia transaccional** — insert en `memos` + `categorias` no atómico | 🔴 Alta | Datos huérfanos si una tabla falla | Integridad |
| P2 | **Ambigüedad de re-procesamiento** — entidad añadida en etapa N no fue vista por agentes de etapas N+1 | 🟡 Media | El usuario cree que su entidad fue considerada pero no lo fue | UX/Semántica |
| P3 | **Gating demasiado grueso** — el dropdown muestra tipos por etapa, no por agentes ya ejecutados | 🟡 Media | Falsa sensación de completitud | UX |
| P4 | **Dualidad memo-entidad** — editar el memo no actualiza la entidad derivada | 🟡 Media | Inconsistencia silenciosa entre `memos.contenido` y `categorias.definicion` | Integridad |
| P5 | **Mezcla sistema/manual en el feed** — memos de agentes y de usuario en la misma lista sin distinción clara | 🟡 Media | Confusión visual | UX |
| P6 | **Filtros por familia de agente no mapean a tipos de entidad** — los botones actuales (`inductive_data`, `evaluative`) no sirven para memos de usuario | 🟡 Media | El filtro actual se vuelve inútil para memos manuales | UX |
| P7 | **Tipos complejos (TEORICO, DATABASE_*) no caben en `memos.contenido`** — necesitan campos estructurados | 🟡 Media | Datos incompletos o mal formados | Integridad |
| P8 | **Race condition** — el pipeline puede iniciar entre el check `pipeline_runs` y el INSERT | 🟢 Baja | Ventana de ~milisegundos, pero posible bajo carga | Integridad |
| P9 | **Conflicto de nombres** — categoría manual con mismo nombre que una del sistema | 🟢 Baja | Dos entidades distintas con nombres idénticos — confunde al investigador y a los agentes | Semántica |
| P10 | **Sección de categorías** — si se elimina, ¿dónde ve el usuario las categorías del sistema? | 🟡 Media | Pérdida de visibilidad del output principal de la síntesis | UX |
| P11 | **¿Qué entidad se crea realmente?** — el dropdown ofrece "CATEGORIA" pero el usuario podría esperar que también se creen `codigos_segmento` automáticamente | 🟢 Baja | Expectativa no alineada | UX |

---

## 2. Soluciones Diseñadas

### P1 — Consistencia Transaccional

**Problema:** Si `INSERT INTO memos` funciona pero `INSERT INTO categorias` falla, queda un memo huérfano que referencia una categoría inexistente.

**Solución:** Envolver ambas operaciones en una transacción con savepoint:

```python
async def create_user_memo(...):
    async with db.begin() as transaction:
        # 1. Insert memo
        await db.execute(text("INSERT INTO memos (...) VALUES (...)"))
        
        # 2. Si es CATEGORIA → insert en categorias (misma transacción)
        if body.tipo == "CATEGORIA":
            await db.execute(text("INSERT INTO categorias (...) VALUES (...)"))
        
        # 3. Si es TEORICO → insert en theoretical_codes
        if body.tipo == "TEORICO":
            await db.execute(text("INSERT INTO theoretical_codes (...) VALUES (...)"))
        
        # 4. Si es DATABASE_NODE → insert en database_nodes
        if body.tipo == "DATABASE_NODE":
            await db.execute(text("INSERT INTO database_nodes (...) VALUES (...)"))
        
        # Commit implícito al salir del context manager
    # Si algo falla → rollback automático de AMBAS tablas
```

**Riesgo residual:** Ninguno. La transacción de SQLAlchemy garantiza atomicidad.

---

### P2 — Ambigüedad de Re-procesamiento

**Problema:** Usuario añade CATEGORIA en `finding_cc`. El `main_concern_proposer` ya corrió → no la vio. El pipeline avanza a `reducing`, `saturating`. La categoría existe en la tabla pero ningún agente la procesó. El usuario asume que fue considerada.

**Solución — Banner de Stale Entities en el Frontend:**

```tsx
// En Project.tsx, antes de mostrar el botón "Continue Pipeline":

function StaleEntitiesWarning({ projectId, currentStage }: { projectId: string; currentStage: string }) {
  const [staleCount, setStaleCount] = useState(0);
  const [staleStages, setStaleStages] = useState<string[]>([]);
  
  useEffect(() => {
    // Fetch memos creados por usuario en etapas ANTERIORES a la actual
    request(`/projects/${projectId}/stale-user-entities?current_stage=${currentStage}`)
      .then(data => {
        setStaleCount(data.count);
        setStaleStages(data.affected_stages);
      });
  }, [projectId, currentStage]);
  
  if (staleCount === 0) return null;
  
  return (
    <Banner color="#D29922">
      ⚠️ Agregaste {staleCount} entidade{staleCount > 1 ? 's' : ''} en etapa{staleStages.length > 1 ? 's' : ''} anterior{staleStages.length > 1 ? 'es' : ''} ({staleStages.join(', ')}). 
      Algunos agentes ya corrieron sin verlas. 
      <LinkButton onClick={() => setShowReSpec(true)}>
        ¿Re-ejecutar desde la etapa afectada?
      </LinkButton>
    </Banner>
  );
}
```

**Endpoint de soporte:**
```python
@router.get("/projects/{project_id}/stale-user-entities")
async def get_stale_user_entities(
    project_id: UUID,
    current_stage: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Detecta memos de usuario creados en etapas anteriores a current_stage."""
    
    # Mapa de orden de etapas
    STAGE_ORDER = ["collecting", "coding", "finding_cc", "reducing", "saturating", "building_db", "playground_ready", "completed"]
    current_idx = STAGE_ORDER.index(current_stage) if current_stage in STAGE_ORDER else 0
    
    stale = await db.execute(
        text(
            "SELECT stage_at_creation, COUNT(*) FROM memos "
            "WHERE proyecto_id = :pid AND user_created = true "
            "AND stage_at_creation != :stage "
            "GROUP BY stage_at_creation"
        ),
        {"pid": project_id, "stage": current_stage},
    )
    
    stale_rows = stale.fetchall()
    affected_stages = []
    total = 0
    for row in stale_rows:
        stage = row[0]
        count = row[1]
        if stage in STAGE_ORDER and STAGE_ORDER.index(stage) < current_idx:
            affected_stages.append(stage)
            total += count
    
    return {
        "count": total,
        "affected_stages": affected_stages,
        "earliest_stage": affected_stages[0] if affected_stages else None,
    }
```

---

### P3 — Gating de Dos Niveles

**Problema:** El dropdown actual muestra tipos por etapa del proyecto, pero no informa qué agentes ya corrieron y por tanto no verán la nueva entidad.

**Solución — Marcadores de disponibilidad en el dropdown:**

```python
# En memo_types.py, agregar metadata de agente:

MEMO_TYPES_BY_STAGE: dict[str, list[dict]] = {
    "finding_cc": [
        {
            "key": "CATEGORIA", 
            "label": "Categoría", 
            "icon": "🏷️",
            "description": "Categoría de investigación manual.",
            "requires_agent": "main_concern_proposer",  # ← NUEVO
            "agent_status": "checking",  # ← NUEVO: 'pending', 'completed', 'checking'
        },
        {
            "key": "HIPOTESIS",
            "label": "Hipótesis",
            "icon": "💡",
            "requires_agent": None,  # ← no requiere agente específico
        },
        ...
    ],
}
```

El endpoint `GET /available-memo-types` enriquece cada tipo con el estado del agente asociado:

```python
# En el endpoint:
for t in types:
    if t.get("requires_agent"):
        # Verificar si el agente ya corrió
        agent_done = await db.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = :gate "
                "AND status = 'accepted' LIMIT 1"
            ),
            {"pid": project_id, "gate": t["requires_agent"]},
        )
        t["agent_status"] = "completed" if agent_done.fetchone() else "pending"
        if t["agent_status"] == "completed":
            t["warning"] = f"⚠️ El agente {t['requires_agent']} ya se ejecutó. Esta entidad no será considerada a menos que re-ejecutes."
```

El frontend muestra el warning como tooltip o badge en el dropdown:

```tsx
{types.map(t => (
  <option key={t.key} value={t.key}>
    {t.icon} {t.label}
    {t.warning && " ⚠️"}  {/* indicador visual */}
  </option>
))}
{selectedType?.warning && (
  <WarningBadge>{selectedType.warning}</WarningBadge>
)}
```

---

### P4 — Dualidad Memo-Entidad (Sincronización)

**Problema:** Si el usuario edita el contenido de un memo CATEGORIA, la tabla `categorias` no se actualiza.

**Solución — Trigger de sincronización en el endpoint de edición de memos:**

Ya existe `PATCH /api/v1/pipeline/memos/{memo_id}` (en `pipeline.py` L769-797). Extenderlo:

```python
@router.patch("/projects/{project_id}/pipeline/memos/{memo_id}")
async def patch_agent_output(...):
    # ... lógica existente de actualización del memo ...
    
    # ── Sincronizar entidad derivada si el memo es user_created ──
    memo_row = await db.execute(
        text("SELECT tipo, user_created FROM memos WHERE id = :mid"),
        {"mid": memo_id},
    )
    memo = memo_row.fetchone()
    
    if memo and memo[1]:  # user_created = true
        if memo[0] == "CATEGORIA":
            # Actualizar la categoría vinculada (por nombre o por FK futura)
            await db.execute(
                text(
                    "UPDATE categorias SET definicion = :content "
                    "WHERE proyecto_id = :pid AND nombre LIKE :prefix"
                ),
                {"content": body.nuevo_contenido, "pid": project_id, "prefix": "[Manual]%"},
            )
        elif memo[0] == "TEORICO":
            await db.execute(
                text(
                    "UPDATE theoretical_codes SET description = :content "
                    "WHERE project_id = :pid AND name LIKE :prefix"
                ),
                {"content": body.nuevo_contenido, "pid": project_id, "prefix": "[User]%"},
            )
```

**Alternativa más robusta:** Agregar FK opcional desde `categorias` → `memos` (`source_memo_id`). Así la sincronización es directa:

```sql
ALTER TABLE categorias ADD COLUMN source_memo_id UUID REFERENCES memos(id);
-- NULL = creada por el sistema (agentes)
-- NOT NULL = creada desde un memo manual
```

Esto permite:
- Update directo: `UPDATE categorias SET definicion = :new WHERE source_memo_id = :mid`
- Trazabilidad: desde cualquier categoría, saber si fue manual o del sistema
- Eliminación en cascada: si se borra el memo, se borra la categoría derivada

---

### P5 — Separación Visual Sistema vs Manual

**Solución — Dos secciones en MemoHistory o badges claros:**

Opción A (más simple): Badges de color en el feed unificado.

```tsx
function getMemoBadge(memo: MemoEntry) {
  if (memo.user_created) {
    return { label: `👤 ${memo.entity_type}`, color: "#3FB950", bg: "#3FB95018" };
  }
  // Sistema: usar el badge de familia de agente existente
  return { label: FAMILY_LABELS[memo.family], color: getFamilyColor(memo.family).text, bg: getFamilyColor(memo.family).bg };
}
```

Opción B (más clara): Tabs "🤖 Sistema" / "👤 Manual" en el historial.

```tsx
const [tab, setTab] = useState<"all" | "system" | "user">("all");

<TabBar>
  <Tab active={tab === "all"} onClick={() => setTab("all")}>Todo</Tab>
  <Tab active={tab === "system"} onClick={() => setTab("system")}>🤖 Sistema</Tab>
  <Tab active={tab === "user"} onClick={() => setTab("user")}>👤 Manual</Tab>
</TabBar>
```

**Recomendación: Opción A + B combinadas** — tabs para la separación gruesa, badges de color para la identificación fina.

---

### P6 — Rediseño de Filtros del Historial (de Familia de Agente → Tipo de Entidad)

**Problema:** Los filtros actuales usan `FAMILY_LABELS` (inductive_data, evaluative, etc.) que solo aplican a memos de agentes. Los memos de usuario tienen `memo.tipo` (CATEGORIA, HIPOTESIS, etc.) que no mapean a familias.

**Solución — Reemplazar la barra de filtros actual:**

```tsx
// NUEVOS filtros — reemplazan FAMILY_LABELS
const ENTITY_FILTERS = [
  { key: "all", label: "Todo", icon: "📋" },
  { key: "HIPOTESIS", label: "Hipótesis", icon: "💡" },
  { key: "CATEGORIA", label: "Categorías", icon: "🏷️" },
  { key: "PROPIEDAD", label: "Propiedades", icon: "📐" },
  { key: "RELACION", label: "Relaciones", icon: "🔗" },
  { key: "METODOLOGICO", label: "Metodológico", icon: "📋" },
  { key: "MUESTREO", label: "Muestreo", icon: "🎯" },
  { key: "GENERAL", label: "General", icon: "📝" },
  { key: "TEORICO", label: "Teóricos", icon: "🔬" },
  { key: "user", label: "👤 Manuales", icon: null },  // filtra user_created=true
  { key: "system", label: "🤖 Sistema", icon: null },  // filtra user_created=false
];

// Lógica de filtrado:
const filtered = memos.filter((m) => {
  // Filtro por tipo de entidad
  if (activeFilter !== "all") {
    if (activeFilter === "user") {
      if (!m.user_created) return false;
    } else if (activeFilter === "system") {
      if (m.user_created) return false;
    } else {
      // Para memos de usuario: comparar con memo.entity_type
      // Para memos de sistema: mapear family → entity_type
      const entityType = m.user_created ? m.entity_type : mapFamilyToType(m.family);
      if (entityType !== activeFilter) return false;
    }
  }
  
  // Toggle de intermedios (se mantiene)
  if (!showIntermediates && !m.isFinal) return false;
  
  return true;
});

// Mapeo family → entity_type para memos de sistema:
function mapFamilyToType(family: string): string {
  const map: Record<string, string> = {
    inductive_data: "CATEGORIA",       // b2b genera códigos → categorías
    inductive_concepts: "HIPOTESIS",   // b3 genera hipótesis
    descriptive_data: "METODOLOGICO",  // a1, a2 generan contexto
    evaluative: "CATEGORIA",           // b2.5 evalúa códigos → categorías
    structural: "DATABASE_NODE",       // database_a/b
    elaborative: "RELACION",           // elaboration engine
  };
  return map[family] || "GENERAL";
}
```

**Cambios en `MemoHistoryProps`:**

```tsx
// Antes:
interface MemoHistoryProps {
  activeFilter: string;          // family key o "all"
  showIntermediates: boolean;
  onFilterChange: (family: string) => void;
  onToggleIntermediates: (show: boolean) => void;
}

// Después:
interface MemoHistoryProps {
  activeFilter: string;          // entity type key, "all", "user", "system"
  showIntermediates: boolean;
  onFilterChange: (filter: string) => void;
  onToggleIntermediates: (show: boolean) => void;
}
```

**Cambios en `Project.tsx`:**

```tsx
// Antes:
const [memoFilter, setMemoFilter] = useState("all");

// Después (misma variable, diferente semántica):
const [memoFilter, setMemoFilter] = useState("all");
// Ahora "all" | "HIPOTESIS" | "CATEGORIA" | ... | "user" | "system"
```

---

### P7 — Tipos Complejos con `structured_fields`

**Problema:** TEORICO, DATABASE_NODE, DATABASE_EDGE requieren campos que no caben en `memos.contenido` plano.

**Solución — Formulario específico por tipo en el modal:**

```tsx
function AddMemoModal(...) {
  // ... estado común ...
  const [structuredData, setStructuredData] = useState<Record<string, any>>({});
  
  const needsStructure = ["TEORICO", "DATABASE_NODE", "DATABASE_EDGE"].includes(selectedType);
  
  return (
    <Overlay>
      <Card>
        {/* Selector de tipo (común) */}
        <TypeSelector ... />
        
        {/* Contenido (común para tipos simples) */}
        {!needsStructure && (
          <TextArea ... placeholder="Escribí el contenido del memo..." />
        )}
        
        {/* Campos estructurados (para tipos complejos) */}
        {selectedType === "TEORICO" && (
          <>
            <Label>Familia</Label>
            <Input value={structuredData.family} onChange={...} placeholder="custom" />
            <Label>Capa (layer)</Label>
            <Select value={structuredData.layer}>
              <option>process</option>
              <option>conditions</option>
              <option>variation</option>
              <option>structure</option>
              <option>consequences</option>
              <option>action</option>
              <option>fusion</option>
              <option>custom</option>
            </Select>
            <Label>Visualización</Label>
            <Select value={structuredData.visualization_hint}>
              <option>tendril</option>
              <option>arrow_diagram</option>
              <option>matrix</option>
              <option>cluster</option>
            </Select>
            <Label>Lógica de evaluación (opcional)</Label>
            <TextArea value={structuredData.evaluation_logic} placeholder='{"what_it_tests": "...", "how_it_tests": [...]}' />
          </>
        )}
        
        {selectedType === "DATABASE_NODE" && (
          <>
            <Label>Entity Type</Label>
            <Select value={structuredData.entity_type}>
              <option>PROCESS</option>
              <option>ACTOR</option>
              <option>CONDITION</option>
              <option>CONSEQUENCE</option>
              <option>CONTEXT</option>
              <option>STRATEGY</option>
            </Select>
            <Checkbox>¿Es core?</Checkbox>
          </>
        )}
        
        {selectedType === "DATABASE_EDGE" && (
          <>
            <Label>Nodo origen</Label>
            <Select value={structuredData.source_node_id}>
              {/* fetch database_nodes del proyecto */}
            </Select>
            <Label>Nodo destino</Label>
            <Select value={structuredData.target_node_id} />
            <Label>Tipo de relación</Label>
            <Select value={structuredData.relationship_type}>
              <option>CAUSES</option>
              <option>ENABLES</option>
              <option>CONSTRAINS</option>
              <option>MODULATES</option>
              <option>IS_A</option>
              <option>PART_OF</option>
              <option>CO_OCCURS_WITH</option>
              <option>RESOLVES</option>
            </Select>
            <Label>Dirección</Label>
            <Select value={structuredData.direction}>
              <option>unidirectional</option>
              <option>bidirectional</option>
            </Select>
            <Label>Fuerza</Label>
            <Select value={structuredData.strength}>
              <option>weak</option>
              <option>moderate</option>
              <option>strong</option>
            </Select>
          </>
        )}
        
        <ButtonRow>
          <Button secondary onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSubmit}>Guardar</Button>
        </ButtonRow>
      </Card>
    </Overlay>
  );
}
```

---

### P8 — Race Condition (Pipeline Inicia Durante el Check)

**Problema:** Ventana de tiempo entre el SELECT que verifica `pipeline_runs` y el INSERT del memo.

**Solución — SELECT ... FOR UPDATE sobre el proyecto:**

```python
async def create_user_memo(...):
    async with db.begin():
        # Bloquear la fila del proyecto para evitar que el orchestrator inicie
        row = await db.execute(
            text("SELECT estado FROM proyectos WHERE id = :pid FOR UPDATE"),
            {"pid": project_id},
        )
        proyecto = row.fetchone()
        
        # Verificar pipeline_runs (dentro de la misma transacción, con lock)
        active = await db.execute(
            text("SELECT id FROM pipeline_runs WHERE project_id = :pid AND status = 'running' FOR UPDATE LIMIT 1"),
            {"pid": project_id},
        )
        if active.fetchone():
            raise HTTPException(409, "Pipeline en ejecución")
        
        # Insertar memo (el lock previene que el orchestrator inicie)
        await db.execute(text("INSERT INTO memos ..."))
        
        # Insertar entidad derivada
        if body.tipo == "CATEGORIA":
            await db.execute(text("INSERT INTO categorias ..."))
```

`FOR UPDATE` bloquea la fila hasta el commit. Si el orchestrator intenta `UPDATE proyectos SET estado = 'coding'` durante esta transacción, esperará a que termine. Esto elimina la race condition.

---

### P9 — Conflicto de Nombres entre Manual y Sistema

**Problema:** Usuario crea categoría "Negociando visibilidad" manualmente. El sistema ya generó "Negociando visibilidad algorítmica" en Phase B. Son entidades distintas con nombres casi idénticos.

**Solución — Detección de similitud y prefijo [Manual]:**

1. **Prefijo automático:** Todas las categorías manuales se crean con prefijo `[Manual]`.
2. **Detección de similitud:** Al guardar, buscar categorías existentes con nombre similar (Levenshtein o embedding cosine). Si se detecta similitud > 0.8, mostrar warning: "Ya existe una categoría similar: 'Negociando visibilidad algorítmica'. ¿Estás seguro de crear una nueva?"
3. **El usuario decide:** Puede proceder (crea entidad separada) o cancelar (edita la existente vía P5 Modification).

```python
# En el endpoint POST /memos, antes de crear CATEGORIA:
if body.tipo == "CATEGORIA":
    # Buscar categorías con nombre similar
    similar = await db.execute(
        text(
            "SELECT nombre, similarity(nombre, :name) AS sim "
            "FROM categorias WHERE proyecto_id = :pid "
            "AND similarity(nombre, :name) > 0.3 "
            "ORDER BY sim DESC LIMIT 3"
        ),
        {"pid": project_id, "name": nombre_propuesto},
    )
    similars = similar.fetchall()
    if similars:
        return {
            "warning": "similar_exists",
            "similar_categories": [{"name": s[0], "similarity": float(s[1])} for s in similars],
            "message": f"Ya existen categorías con nombres similares. ¿Crear de todos modos?"
        }
```

El frontend muestra un diálogo de confirmación antes del POST real.

---

### P10 — ¿Eliminar o Transformar la Sección de Categorías?

**Problema:** Las categorías son el output principal de Phase B. Eliminar la sección las vuelve invisibles.

**Solución — Transformar, no eliminar:**

La sección actual de "Categorías" en `Project.tsx` se convierte en un **panel de entidades unificado** que muestra:

```
┌─────────────────────────────────────────┐
│ 🏷️ Entidades del Proyecto               │
│                                         │
│ [Todo] [Categorías] [Hipótesis] [Teóricos] │
│                                         │
│ 🏷️ Negociando visibilidad        🤖 sys │
│ 🏷️ [Manual] Mi categoría         👤 man │
│ 💡 La percepción modula el análisis 🤖   │
│ 🔬 Proceso / Secuencia            🔧 bt  │
│ ...                                     │
└─────────────────────────────────────────┘
```

- Badge `🤖 sys` = generada por agente del sistema
- Badge `👤 man` = creada manualmente (user_created=true)
- Badge `🔧 bt` = built-in (theoretical_code con glaserian=true)
- Cada entidad es clickeable → abre el memo asociado en el historial
- El botón "➕ Add Memo" está integrado en este panel

Esto **reemplaza** la tabla de categorías actual sin perder funcionalidad, y la **extiende** para incluir todos los tipos de entidad.

---

### P11 — Claridad sobre qué se crea

**Problema:** El usuario selecciona "CATEGORIA" en el dropdown pero no sabe si eso también crea automáticamente `codigos_segmento` o relaciones.

**Solución — Descripción explícita en el modal:**

```tsx
{selectedType && (
  <InfoBox>
    {selectedType === "CATEGORIA" && (
      <>
        <strong>Se creará:</strong> Una categoría en la tabla de entidades del proyecto.
        <br/>
        <strong>No se creará:</strong> Asignaciones a segmentos (codigos_segmento). 
        Para vincular esta categoría a segmentos, usá el panel de codificación.
      </>
    )}
    {selectedType === "TEORICO" && (
      <>
        <strong>Se creará:</strong> Un código teórico personalizado disponible en el Playground.
        <br/>
        <strong>No se creará:</strong> Relaciones conceptuales. 
        Para usar este código, arrastralo en el Playground.
      </>
    )}
  </InfoBox>
)}
```

---

## 3. Resumen de Cambios al Plan de Implementación

| # | Cambio | Tipo | Impacto |
|---|--------|------|---------|
| P1 | Transacción atómica para inserts multi-tabla | Nuevo | Endpoint POST /memos |
| P2 | Banner de stale entities + endpoint de detección | Nuevo | Frontend + Backend |
| P3 | Marcadores `requires_agent`/`agent_status` en memo_types | Extensión | memo_types.py + endpoint |
| P4 | FK `source_memo_id` en categorias + trigger de sync en PATCH | Nuevo | BD + endpoint |
| P5 | Badges/Tabs para separar sistema/manual | Nuevo | MemoHistory.tsx |
| P6 | **Rediseño completo de filtros:** FAMILY_LABELS → ENTITY_FILTERS | Refactor | MemoHistory.tsx + Project.tsx |
| P7 | Campos estructurados en el modal para tipos complejos | Extensión | AddMemoModal.tsx |
| P8 | `SELECT ... FOR UPDATE` anti-race-condition | Nuevo | Endpoint POST /memos |
| P9 | Detección de similitud + confirmación pre-creación | Nuevo | Endpoint POST /memos + Frontend |
| P10 | Panel de entidades unificado (reemplaza sección categorías) | Refactor | Project.tsx |
| P11 | InfoBox de "qué se crea / qué no se crea" | Nuevo | AddMemoModal.tsx |
