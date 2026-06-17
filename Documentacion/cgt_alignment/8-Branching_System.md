# 8 — Sistema de Branching de Memos (Pseudocódigo)

> **Diseño conceptual.** No implementar aún — analizar viabilidad y dependencias primero.

---

## 1. Modelo de Datos

```sql
-- Tabla existente (columnas nuevas)
ALTER TABLE memos ADD COLUMN branch_id UUID;
-- NULL = tronco principal (main). NOT NULL = pertenece a un branch.

ALTER TABLE memos ADD COLUMN branch_parent_id UUID REFERENCES memos(id);
-- memo del que este se derivó. NULL = memo original.

ALTER TABLE memos ADD COLUMN edit_summary TEXT;
-- Resumen del cambio (commit message). NULL si no fue editado.

ALTER TABLE memos ADD COLUMN edited_by_user BOOLEAN DEFAULT false;
-- true si el contenido fue modificado manualmente por el investigador.

-- Nueva tabla: branches
CREATE TABLE memo_branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proyecto_id UUID REFERENCES proyectos(id),
    name VARCHAR(200),                          -- "Análisis alternativo del core"
    root_memo_id UUID REFERENCES memos(id),      -- memo del que parte el branch
    created_by UUID REFERENCES usuarios(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    status VARCHAR(20) DEFAULT 'active',         -- 'active' | 'merged' | 'abandoned'
    description TEXT                              -- razón del branch
);

-- Nueva tabla: merge_log
CREATE TABLE memo_merge_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID REFERENCES memo_branches(id),
    source_memo_id UUID REFERENCES memos(id),
    target_memo_id UUID REFERENCES memos(id),
    merged_by UUID REFERENCES usuarios(id),
    merged_at TIMESTAMPTZ DEFAULT now(),
    conflict_resolution TEXT                      -- cómo se resolvieron conflictos
);
```

---

## 2. Pseudocódigo: Core Operations

### 2.1 Editar memo (con commit message)

```
FUNCTION edit_memo(memo_id, new_content, edit_summary, user_id):
    memo = SELECT * FROM memos WHERE id = memo_id
    
    IF memo IS NULL:
        RETURN error("Memo not found")
    
    -- Guardar snapshot de la versión anterior
    INSERT INTO memo_versions (memo_id, content, edited_by, edited_at, summary)
    VALUES (memo_id, memo.contenido, user_id, now(), edit_summary)
    
    -- Actualizar memo
    UPDATE memos SET
        contenido = new_content,
        edited_by_user = TRUE,
        edit_summary = edit_summary,
        version = version + 1
    WHERE id = memo_id
    
    -- Si el memo alimenta una entidad derivada (categoria, theoretical_code),
    -- sincronizar (ver 7-AddMemo_System_DeepDive.md P4)
    IF memo.tipo == "CATEGORIA" AND memo.source_memo_id:
        UPDATE categorias SET definicion = new_content
        WHERE source_memo_id = memo_id
    
    RETURN {memo_id, new_version: memo.version + 1}
```

### 2.2 Crear branch desde un memo

```
FUNCTION branch_memo(memo_id, branch_name, branch_reason, user_id):
    memo = SELECT * FROM memos WHERE id = memo_id
    
    IF memo IS NULL:
        RETURN error("Memo not found")
    
    -- 1. Crear el branch
    branch_id = UUID()
    INSERT INTO memo_branches (id, proyecto_id, name, root_memo_id, created_by, description)
    VALUES (branch_id, memo.proyecto_id, branch_name, memo_id, user_id, branch_reason)
    
    -- 2. Clonar el memo como raíz del branch
    branched_memo_id = UUID()
    INSERT INTO memos (
        id, proyecto_id, autor_id, tipo, estado, contenido,
        branch_id, branch_parent_id, version, user_created,
        stage_at_creation, edit_summary
    ) VALUES (
        branched_memo_id,
        memo.proyecto_id,
        user_id,                    -- el autor del branch es el usuario
        memo.tipo,
        'ABIERTO',
        memo.contenido,             -- hereda el contenido del padre
        branch_id,
        memo_id,                    -- branch_parent → memo original
        1,                          -- versión 1 del branch
        TRUE,                       -- user_created = true (es manual)
        memo.stage_at_creation,
        'Branched from memo ' || memo_id || ': ' || branch_reason
    )
    
    -- 3. Si el memo padre tenía entidad derivada, NO se clona.
    --    La entidad derivada del branch se crea cuando el branch
    --    se mergea o cuando el usuario explícitamente la crea.
    
    RETURN {branch_id, branched_memo_id}
```

### 2.3 Mergear branch al tronco principal

```
FUNCTION merge_branch(branch_id, user_id, conflict_strategy):
    branch = SELECT * FROM memo_branches WHERE id = branch_id
    
    IF branch IS NULL OR branch.status != 'active':
        RETURN error("Branch not found or not active")
    
    -- 1. Encontrar todos los memos del branch
    branch_memos = SELECT * FROM memos WHERE branch_id = branch_id
    
    conflicts = []
    
    FOR EACH branch_memo IN branch_memos:
        -- 2. Encontrar el memo original del tronco
        original = SELECT * FROM memos WHERE id = branch_memo.branch_parent_id
        
        IF original.contenido != branch_memo.contenido:
            -- 3. El tronco también cambió → conflicto
            IF original.version > 1:
                conflicts.append({
                    branch_memo: branch_memo.id,
                    original_memo: original.id,
                    branch_content: branch_memo.contenido,
                    trunk_content: original.contenido
                })
            ELSE:
                -- 4. Solo el branch cambió → merge limpio
                UPDATE memos SET
                    contenido = branch_memo.contenido,
                    edit_summary = 'Merged from branch ' || branch.name,
                    edited_by_user = TRUE,
                    version = version + 1
                WHERE id = original.id
                
                INSERT INTO memo_merge_log (branch_id, source_memo_id, target_memo_id, merged_by, conflict_resolution)
                VALUES (branch_id, branch_memo.id, original.id, user_id, 'clean')
    
    -- 5. Resolver conflictos
    IF conflicts.length > 0:
        IF conflict_strategy == 'keep_branch':
            FOR EACH conflict IN conflicts:
                UPDATE memos SET contenido = conflict.branch_content
                WHERE id = conflict.original_memo
        ELIF conflict_strategy == 'keep_trunk':
            -- No hacer nada, el tronco gana
            pass
        ELIF conflict_strategy == 'manual':
            -- Devolver conflictos para que el usuario decida uno por uno
            RETURN {status: 'conflicts', conflicts}
    
    -- 6. Marcar branch como mergeado
    UPDATE memo_branches SET status = 'merged' WHERE id = branch_id
    
    RETURN {status: 'merged', conflicts_resolved: conflicts.length}
```

### 2.4 Mostrar historial de versiones de un memo

```
FUNCTION get_memo_history(memo_id):
    -- Versiones anteriores (snapshots)
    versions = SELECT * FROM memo_versions
               WHERE memo_id = memo_id
               ORDER BY edited_at DESC
    
    -- Branches que parten de este memo
    branches = SELECT * FROM memo_branches
               WHERE root_memo_id = memo_id
    
    -- Si este memo ES un branch, mostrar su padre
    memo = SELECT * FROM memos WHERE id = memo_id
    parent = NULL
    IF memo.branch_parent_id IS NOT NULL:
        parent = SELECT * FROM memos WHERE id = memo.branch_parent_id
    
    RETURN {
        current: memo,
        versions: versions,
        branches: branches,
        parent: parent
    }
```

---

## 3. Cambios en el Frontend

### 3.1 Badge de edición

```
COMPONENT MemoCard(memo):
    badge_origin = IF memo.edited_by_user:
        "🤖 IA (edit)"      -- púrpura con borde naranja
    ELIF memo.user_created:
        "👤 Manual"          -- verde
    ELSE:
        "🤖 IA"              -- púrpura
    
    -- Si tiene edit_summary, mostrar tooltip al hover
    IF memo.edit_summary:
        badge_origin.TOOLTIP = memo.edit_summary
```

### 3.2 Indicador de branch

```
COMPONENT MemoCard(memo):
    IF memo.branch_id IS NOT NULL:
        RENDER <span style="color: #FF6B35">↳ {branch_name}</span>
```

### 3.3 Modal de edición con commit

```
COMPONENT EditMemoModal(memo):
    textarea = memo.contenido
    input_summary = ""  -- commit message
    
    BUTTON "Guardar (sobrescribir)":
        CALL edit_memo(memo.id, textarea.value, input_summary.value)
        -- badge cambia a "🤖 IA (edit)"
    
    BUTTON "Guardar como branch":
        CALL branch_memo(memo.id, "Branch: " + input_summary.value, input_summary.value)
        -- aparece nuevo memo en el historial con badge ↳
```

### 3.4 Panel de branches en Project.tsx

```
COMPONENT BranchPanel(projectId):
    branches = FETCH GET /projects/{projectId}/branches
    
    FOR EACH branch IN branches:
        RENDER card:
            name: branch.name
            memos: count
            status: badge (active/merged/abandoned)
            BUTTON "Merge" (si active)
            BUTTON "Abandon" (si active)
```

---

## 4. Dependencias para implementar

| # | Dependencia | Estado |
|---|-------------|--------|
| 1 | `memos.version` (ya existe — F0.3.1) | ✅ |
| 2 | `memos.parent_memo_id` (ya existe — F0.3.1) | ✅ |
| 3 | `memos.user_created` (implementado) | ✅ |
| 4 | `memos.edit_summary` (nuevo — este diseño) | 🔴 |
| 5 | `memos.edited_by_user` (nuevo — este diseño) | 🔴 |
| 6 | `memos.branch_id` (nuevo — este diseño) | 🔴 |
| 7 | `memos.branch_parent_id` (nuevo — este diseño) | 🔴 |
| 8 | Tabla `memo_branches` (nueva) | 🔴 |
| 9 | Tabla `memo_merge_log` (nueva) | 🔴 |
| 10 | Endpoint `PATCH /memos/{id}` con commit message | 🔴 |
| 11 | Endpoint `POST /memos/{id}/branch` | 🔴 |
| 12 | Endpoint `POST /branches/{id}/merge` | 🔴 |
| 13 | Modal de edición con commit | 🔴 |
| 14 | Panel de branches en frontend | 🔴 |

---

## 5. Lo que NO se implementa aún

- **Regeneración automática post-merge**: cuando se mergea un branch, los agentes no re-corren automáticamente. El usuario decide si re-ejecutar.
- **Conflictos automáticos**: la resolución de conflictos es manual. No hay merge automático inteligente.
- **Branches anidados**: un branch solo puede partir del tronco principal, no de otro branch.
- **Rebase**: no hay operación de rebase. Solo merge.
