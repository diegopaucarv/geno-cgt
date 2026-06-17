# 7 — Add Memo: Sistema de Adición Manual de Entidades por Etapa

> **Diseño:** Botón "➕ Add Memo" con dropdown contextual de entity types según la etapa del pipeline.
> El historial de memos absorbe la sección de categorías como fuente central de entidades.

---

## 1. Filosofía

El investigador debe poder añadir entidades manualmente en cualquier momento en que el pipeline **no esté ejecutándose**. El tipo de entidad disponible depende de la etapa actual del proyecto — no se pueden añadir códigos teóricos durante open coding, ni categorías antes de la síntesis.

El **historial de memos** se convierte en la fuente central de todas las entidades del proyecto. Las categorías, hipótesis, propiedades, relaciones, y códigos teóricos son todos **tipos de memo**. Esto unifica la UI y simplifica el modelo mental del investigador.

---

## 2. Cambios en Capa de Datos

### 2.1 Nueva columna en `memos`

```sql
ALTER TABLE memos ADD COLUMN user_created BOOLEAN DEFAULT false;
-- false = creado por el sistema (agentes)
-- true  = creado manualmente por el investigador

ALTER TABLE memos ADD COLUMN stage_at_creation VARCHAR(50);
-- Etapa del proyecto cuando se creó el memo
-- Útil para trazabilidad y para determinar si un memo es relevante al reanudar
```

### 2.2 Tipos de memo por etapa

```python
# backend/app/core/memo_types.py (nuevo)

MEMO_TYPES_BY_STAGE: dict[str, list[dict]] = {
    "collecting": [
        {"key": "METODOLOGICO", "label": "Metodológico", "icon": "📋", "description": "Nota sobre el método, decisiones de muestreo, ajustes al diseño"},
        {"key": "MUESTREO", "label": "Muestreo", "icon": "🎯", "description": "Criterios de inclusión/exclusión, dimensiones de muestreo teórico"},
        {"key": "GENERAL", "label": "General", "icon": "📝", "description": "Observación, idea, o reflexión no categorizada"},
    ],
    "coding": [
        {"key": "HIPOTESIS", "label": "Hipótesis", "icon": "💡", "description": "Hipótesis emergente sobre relaciones entre conceptos"},
        {"key": "METODOLOGICO", "label": "Metodológico", "icon": "📋"},
        {"key": "MUESTREO", "label": "Muestreo", "icon": "🎯"},
        {"key": "PROPIEDAD", "label": "Propiedad", "icon": "📐", "description": "Propiedad o dimensión de una categoría existente"},
        {"key": "GENERAL", "label": "General", "icon": "📝"},
    ],
    "finding_cc": [
        {"key": "HIPOTESIS", "label": "Hipótesis", "icon": "💡"},
        {"key": "CATEGORIA", "label": "Categoría", "icon": "🏷️", "description": "Categoría de investigación. Se persistirá en la tabla categorias como categoría manual."},
        {"key": "PROPIEDAD", "label": "Propiedad", "icon": "📐"},
        {"key": "RELACION", "label": "Relación", "icon": "🔗", "description": "Relación conceptual entre categorías"},
        {"key": "METODOLOGICO", "label": "Metodológico", "icon": "📋"},
        {"key": "MUESTREO", "label": "Muestreo", "icon": "🎯"},
        {"key": "GENERAL", "label": "General", "icon": "📝"},
    ],
    "reducing": "finding_cc",   # hereda los mismos tipos
    "saturating": "finding_cc", # hereda los mismos tipos
    "building_db": [
        {"key": "HIPOTESIS", "label": "Hipótesis", "icon": "💡"},
        {"key": "CATEGORIA", "label": "Categoría", "icon": "🏷️"},
        {"key": "PROPIEDAD", "label": "Propiedad", "icon": "📐"},
        {"key": "RELACION", "label": "Relación", "icon": "🔗"},
        {"key": "DATABASE_NODE", "label": "Nodo (DB A)", "icon": "🟦", "description": "Nodo del modelo teórico plano"},
        {"key": "DATABASE_EDGE", "label": "Edge (DB B)", "icon": "➡️", "description": "Relación del modelo teórico"},
        {"key": "METODOLOGICO", "label": "Metodológico", "icon": "📋"},
        {"key": "MUESTREO", "label": "Muestreo", "icon": "🎯"},
        {"key": "GENERAL", "label": "General", "icon": "📝"},
    ],
    "playground_ready": [
        {"key": "HIPOTESIS", "label": "Hipótesis", "icon": "💡"},
        {"key": "CATEGORIA", "label": "Categoría", "icon": "🏷️"},
        {"key": "PROPIEDAD", "label": "Propiedad", "icon": "📐"},
        {"key": "RELACION", "label": "Relación", "icon": "🔗"},
        {"key": "DATABASE_NODE", "label": "Nodo (DB A)", "icon": "🟦"},
        {"key": "DATABASE_EDGE", "label": "Edge (DB B)", "icon": "➡️"},
        {"key": "TEORICO", "label": "Código Teórico", "icon": "🔬", "description": "Familia teórica personalizada (las 12 built-in no se tocan)"},
        {"key": "METODOLOGICO", "label": "Metodológico", "icon": "📋"},
        {"key": "MUESTREO", "label": "Muestreo", "icon": "🎯"},
        {"key": "GENERAL", "label": "General", "icon": "📝"},
    ],
    "completed": "playground_ready",
}
```

---

## 3. Cambios en Backend

### 3.1 Nuevo endpoint: `GET /api/v1/projects/{id}/available-memo-types`

```python
# backend/app/api/v1/memos.py (nuevo archivo o agregar a pipeline.py)

@router.get("/projects/{project_id}/available-memo-types")
async def get_available_memo_types(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve los tipos de memo disponibles según la etapa actual del proyecto."""
    from app.core.memo_types import MEMO_TYPES_BY_STAGE

    # 1. Obtener etapa del proyecto
    row = await db.execute(
        text("SELECT estado FROM proyectos WHERE id = :pid"),
        {"pid": project_id},
    )
    proyecto = row.fetchone()
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    stage = proyecto[0]

    # 2. Verificar si el pipeline está corriendo
    active_run = await db.execute(
        text("SELECT id FROM pipeline_runs WHERE project_id = :pid AND status = 'running' LIMIT 1"),
        {"pid": project_id},
    )
    is_running = active_run.fetchone() is not None

    # 3. Resolver tipos (soporta herencia con alias de string)
    types = MEMO_TYPES_BY_STAGE.get(stage, MEMO_TYPES_BY_STAGE["collecting"])
    if isinstance(types, str):
        types = MEMO_TYPES_BY_STAGE[types]

    return {
        "stage": stage,
        "pipeline_running": is_running,
        "can_add_memo": not is_running,
        "available_types": types,
    }
```

### 3.2 Nuevo endpoint: `POST /api/v1/projects/{id}/memos`

```python
@router.post("/projects/{project_id}/memos")
async def create_user_memo(
    project_id: UUID,
    body: CreateMemoRequest,  # {tipo: str, contenido: str, es_confidencial: bool}
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Crea un memo manual. Solo permitido si el pipeline NO está corriendo."""

    # 1. Verificar que el pipeline no esté corriendo
    active_run = await db.execute(
        text("SELECT id FROM pipeline_runs WHERE project_id = :pid AND status = 'running' LIMIT 1"),
        {"pid": project_id},
    )
    if active_run.fetchone():
        raise HTTPException(409, "No se pueden añadir entidades mientras el pipeline está ejecutándose. Pausalo primero.")

    # 2. Obtener etapa actual
    row = await db.execute(
        text("SELECT estado FROM proyectos WHERE id = :pid"),
        {"pid": project_id},
    )
    proyecto = row.fetchone()
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    stage = proyecto[0]

    # 3. Validar que el tipo esté permitido en esta etapa
    from app.core.memo_types import MEMO_TYPES_BY_STAGE
    types = MEMO_TYPES_BY_STAGE.get(stage, MEMO_TYPES_BY_STAGE["collecting"])
    if isinstance(types, str):
        types = MEMO_TYPES_BY_STAGE[types]
    allowed_keys = [t["key"] for t in types]

    if body.tipo not in allowed_keys:
        raise HTTPException(400, f"Tipo '{body.tipo}' no disponible en etapa '{stage}'. Disponibles: {allowed_keys}")

    # 4. Crear memo
    memo_id = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO memos (id, proyecto_id, autor_id, tipo, estado, contenido, es_confidencial, user_created, stage_at_creation) "
            "VALUES (:id, :pid, :uid, :tipo, 'ABIERTO', :contenido, :conf, true, :stage)"
        ),
        {
            "id": memo_id,
            "pid": project_id,
            "uid": current_user.id,
            "tipo": body.tipo,
            "contenido": body.contenido,
            "conf": body.es_confidencial,
            "stage": stage,
        },
    )

    # 5. Si es tipo CATEGORIA, también crear en tabla categorias
    if body.tipo == "CATEGORIA":
        await db.execute(
            text(
                "INSERT INTO categorias (id, proyecto_id, nombre, definicion, estado_saturacion, puntaje_relevancia, version) "
                "VALUES (gen_random_uuid(), :pid, :nombre, :def, 'ABIERTO', 1, 1)"
            ),
            {"pid": project_id, "nombre": f"[Manual] {body.contenido[:100]}", "def": body.contenido},
        )

    # 6. Si es tipo TEORICO, crear en theoretical_codes
    if body.tipo == "TEORICO":
        await db.execute(
            text(
                "INSERT INTO theoretical_codes (id, project_id, name, family, description, glaserian, user_defined, layer) "
                "VALUES (gen_random_uuid(), :pid, :name, 'custom', :desc, false, true, 'custom')"
            ),
            {"pid": project_id, "name": f"[User] {body.contenido[:100]}", "desc": body.contenido},
        )

    await db.commit()

    return {"id": str(memo_id), "tipo": body.tipo, "stage": stage, "user_created": True}
```

### 3.3 Continuación del pipeline con entidades de usuario

```python
# En selective_coding_coordinator (tasks.py L1738), agregar al inicio:

# Detectar memos creados por el usuario desde la última ejecución
user_memos = s.execute(
    text(
        "SELECT tipo, COUNT(*) FROM memos "
        "WHERE proyecto_id = :pid AND user_created = true "
        "AND stage_at_creation = :stage "
        "AND creado_en > COALESCE("
        "  (SELECT MAX(creado_en) FROM pipeline_tasks WHERE run_id IN "
        "    (SELECT id FROM pipeline_runs WHERE project_id = :pid2 ORDER BY creado_en DESC LIMIT 1)"
        "  ), '1970-01-01'::timestamp)"
        "GROUP BY tipo"
    ),
    {"pid": proyecto_id, "stage": current_state, "pid2": proyecto_id},
).fetchall()

if user_memos:
    logger.info(
        "Detected %d user-created memos since last run. They will be included in the current stage.",
        sum(row[1] for row in user_memos),
    )
    # No se necesita flag especial: los agentes consultan memos naturalmente.
    # Las categorías manuales ya están en la tabla categorias.
    # Los códigos teóricos manuales ya están en theoretical_codes.
```

**Conclusión sobre `user_added_entities` flag:** **No se necesita un flag especial.** El sistema ya es re-entrante por diseño:
- Los agentes de selective coding consultan `memos`, `categorias`, y `theoretical_codes` al iniciar
- Si el usuario añadió entidades durante la pausa, los agentes las ven naturalmente
- El `selective_coding_coordinator` solo necesita registrar el hecho (para trazabilidad), no cambiar su lógica
- El caso extremo (usuario añade CATEGORIA en `finding_cc` y luego espera que el `main_concern_proposer` la considere) se resuelve solo: el proposer consulta `categorias` al ejecutarse

---

## 4. Cambios en Frontend

### 4.1 Componente: `AddMemoModal.tsx`

```tsx
// frontend/src/components/AddMemoModal.tsx (nuevo)

interface MemoType {
  key: string;
  label: string;
  icon: string;
  description: string;
}

interface AddMemoModalProps {
  projectId: string;
  onClose: () => void;
  onCreated: () => void;  // callback para refrescar historial
}

function AddMemoModal({ projectId, onClose, onCreated }: AddMemoModalProps) {
  const [types, setTypes] = useState<MemoType[]>([]);
  const [selectedType, setSelectedType] = useState<string>("");
  const [content, setContent] = useState("");
  const [isConfidential, setIsConfidential] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [stage, setStage] = useState("");
  const [pipelineRunning, setPipelineRunning] = useState(false);

  useEffect(() => {
    // Fetch available types
    request(`/projects/${projectId}/available-memo-types`)
      .then((data) => {
        setTypes(data.available_types);
        setStage(data.stage);
        setPipelineRunning(data.pipeline_running);
        if (data.available_types.length > 0) {
          setSelectedType(data.available_types[0].key);
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [projectId]);

  const handleSubmit = async () => {
    if (!selectedType || !content.trim()) return;
    setSubmitting(true);
    try {
      await request(`/projects/${projectId}/memos`, {
        method: "POST",
        body: JSON.stringify({
          tipo: selectedType,
          contenido: content,
          es_confidencial: isConfidential,
        }),
      });
      onCreated();
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (pipelineRunning) {
    return (
      <Overlay>
        <Card>
          <Title>🚫 Pipeline en ejecución</Title>
          <Text>Pausá el pipeline antes de añadir entidades manualmente.</Text>
          <Button onClick={onClose}>Cerrar</Button>
        </Card>
      </Overlay>
    );
  }

  return (
    <Overlay>
      <Card>
        <Title>➕ Add Memo — Etapa: {stage}</Title>

        {/* Type selector */}
        <Label>Tipo de entidad</Label>
        <Select value={selectedType} onChange={(e) => setSelectedType(e.target.value)}>
          {types.map((t) => (
            <option key={t.key} value={t.key}>
              {t.icon} {t.label}
            </option>
          ))}
        </Select>
        {selectedType && (
          <TypeDescription>
            {types.find((t) => t.key === selectedType)?.description}
          </TypeDescription>
        )}

        {/* Content */}
        <Label>Contenido</Label>
        <TextArea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder="Escribí el contenido del memo..."
          rows={8}
        />

        {/* Confidential toggle */}
        <Checkbox>
          <input
            type="checkbox"
            checked={isConfidential}
            onChange={(e) => setIsConfidential(e.target.checked)}
          />
          🔒 Confidencial
        </Checkbox>

        {error && <Error>{error}</Error>}

        <ButtonRow>
          <Button secondary onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSubmit} disabled={submitting || !content.trim()}>
            {submitting ? "Guardando..." : "Guardar Memo"}
          </Button>
        </ButtonRow>
      </Card>
    </Overlay>
  );
}
```

### 4.2 Botón en `Project.tsx`

Agregar después del botón "Ejecutar Pipeline":

```tsx
{/* Add Memo button — visible cuando el pipeline NO está corriendo */}
{!pipelineRunning && (
  <button
    onClick={() => setShowAddMemo(true)}
    style={{
      padding: "5px 14px",
      borderRadius: 6,
      border: "1px solid #3FB95044",
      background: "#3FB95018",
      color: "#3FB950",
      fontSize: 12,
      fontWeight: 600,
      cursor: "pointer",
    }}
  >
    ➕ Add Memo
  </button>
)}

{/* Modal */}
{showAddMemo && (
  <AddMemoModal
    projectId={id}
    onClose={() => setShowAddMemo(false)}
    onCreated={() => {
      toastMsg && showToast("Memo creado");
      refreshDocs();  // refrescar el historial de memos
    }}
  />
)}
```

### 4.3 Historial de Memos — Mostrar todos los tipos

El `MemoHistory.tsx` actual filtra por `agentMemos`. Debe ampliarse para incluir memos `user_created=true` con badges visuales distintos:

```tsx
// En MemoHistory, agregar badge para memos de usuario:
const isUserMemo = memo.user_created === true;
const badgeColor = isUserMemo ? "#3FB950" : FAMILY_COLORS[memo.family]?.text;
const badgeLabel = isUserMemo ? `👤 ${memo.tipo}` : memo.agentId;
```

### 4.4 Sección de Categorías

La sección de categorías en `Project.tsx` se **mantiene** pero se marca como "generadas por el sistema". Las categorías creadas manualmente (tipo `CATEGORIA`) aparecen tanto en el historial de memos como en la tabla de categorías con un badge `[Manual]`.

---

## 5. Plan de Implementación

| # | Qué | Archivo | Esfuerzo |
|---|-----|---------|----------|
| 1 | Agregar columnas `user_created`, `stage_at_creation` a `memos` | `backend/app/models/domain/memo.py` + migración | Bajo |
| 2 | Crear `memo_types.py` con matriz de tipos por etapa | `backend/app/core/memo_types.py` | Bajo |
| 3 | Crear endpoint `GET /available-memo-types` | `backend/app/api/v1/memos.py` (o `pipeline.py`) | Medio |
| 4 | Crear endpoint `POST /memos` | `backend/app/api/v1/memos.py` | Medio |
| 5 | Agregar detección de user memos en coordinator | `workers/heavy/tasks.py` L1738 | Bajo |
| 6 | Crear `AddMemoModal.tsx` | `frontend/src/components/AddMemoModal.tsx` | Medio |
| 7 | Agregar botón "➕ Add Memo" en Project.tsx | `frontend/src/pages/Project.tsx` | Bajo |
| 8 | Actualizar `MemoHistory.tsx` para mostrar memos de usuario | `frontend/src/components/MemoHistory.tsx` | Bajo |
| 9 | Agregar `getAvailableMemoTypes`, `createMemo` a client.ts | `frontend/src/api/client.ts` | Bajo |

---

## 6. Ramificaciones del Flag de Continuación

**Conclusión:** No se necesita un `user_added_entities` flag explícito. Razones:

1. **Re-entrancia natural**: Los agentes del coordinator (`task_main_concern_pipeline`, `task_core_saturation_loop`, etc.) consultan las tablas (`categorias`, `memos`, `theoretical_codes`) al iniciar. Si el usuario añadió entidades, las ven.

2. **Cascada de modificaciones**: Si el usuario añade una entidad que invalida resultados anteriores (ej. añade una CATEGORIA que debería ser considerada por `main_concern_proposer`), el sistema ya tiene el botón "Re-especificar" (Stage-Gate Review) para re-ejecutar desde el nodo correcto.

3. **Trazabilidad**: La combinación `user_created=true` + `stage_at_creation` + `creado_en` es suficiente para que el frontend muestre "Agregaste 3 memos durante la pausa. ¿Querés re-ejecutar la detección de core category?"

4. **El caso problemático**: Usuario añade CATEGORIA en `finding_cc` → espera que `main_concern_proposer` la vea → pero el proposer ya corrió. Solución: el frontend detecta `user_created=true` memos con `stage_at_creation='finding_cc'` y muestra un warning: "Agregaste categorías manualmente. ¿Re-ejecutar Main Concern Detection?" → dispatchea `task_main_concern_pipeline` de nuevo. Esto es UI, no backend.
