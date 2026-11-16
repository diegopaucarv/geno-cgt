import { useEffect, useRef, useState } from "react";
import ModificationPanel from "./theory/ModificationPanel";
import { getEntityTypeColors, type MemoTypeItem } from "../api/client";
import { useI18n } from "../i18n";

// ── Types ───────────────────────────────────────────────────────────

export interface MemoEntry {
  id: string;
  family: string; // agent_families.family key (system memos) or entity_type (user memos)
  agentId: string;
  isFinal: boolean;
  documentName: string;
  timestamp: string;
  data: Record<string, unknown>;
  user_created?: boolean;
  entity_type?: string;
}

// Re-export MemoTypeItem as EntityTypeInfo for convenience
export type EntityTypeInfo = MemoTypeItem;

// ── Family colors ────────────────────────────────────────────────────

const FAMILY_COLORS: Record<
  string,
  { bg: string; border: string; text: string }
> = {
  descriptive_data: { bg: "#58A6FF18", border: "#58A6FF44", text: "#58A6FF" },
  inductive_data: { bg: "#A371F718", border: "#A371F744", text: "#A371F7" },
  inductive_concepts: { bg: "#D2992218", border: "#D2992244", text: "#D29922" },
  elaborative: { bg: "#3FB95018", border: "#3FB95044", text: "#3FB950" },
  evaluative: { bg: "#F8514918", border: "#F8514944", text: "#F85149" },
  structural: { bg: "#79C0FF18", border: "#79C0FF44", text: "#79C0FF" },
};

const FAMILY_LABELS: Record<string, string> = {
  descriptive_data: "memo.descriptive",
  inductive_data: "memo.inductiveData",
  inductive_concepts: "memo.inductiveConcepts",
  elaborative: "memo.elaborative",
  evaluative: "memo.evaluative",
  structural: "memo.structural",
};

function getFamilyColor(family: string) {
  return (
    FAMILY_COLORS[family] || {
      bg: "#8B949E18",
      border: "#8B949E44",
      text: "#8B949E",
    }
  );
}

// ── Family → Entity Type mapping (frontend mirror of memo_types.py) ─

const FAMILY_TO_ENTITY_TYPE: Record<string, string> = {
  inductive_data: "CATEGORIA",
  inductive_concepts: "HIPOTESIS",
  descriptive_data: "METODOLOGICO",
  evaluative: "CATEGORIA",
  structural: "DATABASE_NODE",
  elaborative: "RELACION",
};

function getMemoEntityType(memo: MemoEntry): string {
  if (memo.user_created && memo.entity_type) return memo.entity_type;
  return FAMILY_TO_ENTITY_TYPE[memo.family] || "GENERAL";
}

function getUserMemoFamily(memo: MemoEntry): string {
  if (!memo.user_created) return memo.family;
  const map: Record<string, string> = {
    CATEGORIA: "inductive_data",
    HIPOTESIS: "inductive_concepts",
    PROPIEDAD: "inductive_data",
    RELACION: "elaborative",
    METODOLOGICO: "descriptive_data",
    MUESTREO: "descriptive_data",
    TEORICO: "structural",
    DATABASE_NODE: "structural",
    DATABASE_EDGE: "structural",
    GENERAL: "descriptive_data",
  };
  return map[memo.entity_type || ""] || "descriptive_data";
}

function getFamilyLabel(memo: MemoEntry): string {
  const family = getUserMemoFamily(memo);
  return FAMILY_LABELS[family] || family;
}

// ── JsonViewer ──────────────────────────────────────────────────────

function JsonViewer({
  data,
  depth = 0,
  onEdit,
  fieldPath = "",
}: {
  data: unknown;
  depth?: number;
  onEdit?: (field: string, value: string) => void;
  fieldPath?: string;
}) {
  if (data === null || data === undefined) {
    return <span style={{ color: "#484F58" }}>—</span>;
  }

  if (typeof data === "boolean") {
    return (
      <span
        style={{
          padding: "1px 6px",
          borderRadius: 4,
          fontSize: 11,
          background: data ? "#3FB95022" : "#F8514922",
          color: data ? "#3FB950" : "#F85149",
          border: `1px solid ${data ? "#3FB95044" : "#F8514944"}`,
        }}
      >
        {String(data)}
      </span>
    );
  }

  if (typeof data === "number") {
    return (
      <span style={{ fontFamily: "monospace", color: "#79C0FF" }}>{data}</span>
    );
  }

  if (typeof data === "string") {
    if (data.length > 120 && onEdit) {
      return (
        <div style={{ position: "relative" }}>
          <div
            onDoubleClick={() => onEdit(fieldPath, data)}
            title="Doble click para editar"
            style={{
              background: "#0D1117",
              border: "1px solid #21262D",
              borderRadius: 6,
              padding: "8px 10px",
              fontFamily: "monospace",
              fontSize: 11,
              color: "#E6EDF3",
              lineHeight: 1.5,
              whiteSpace: "pre-wrap",
              cursor: "text",
            }}
          >
            {data}
          </div>
          <span
            onClick={(e) => {
              e.stopPropagation();
              onEdit(fieldPath, data);
            }}
            style={{
              position: "absolute",
              top: 4,
              right: 6,
              fontSize: 10,
              color: "#58A6FF",
              cursor: "pointer",
              opacity: 0.6,
            }}
            title="Editar"
          >
            ✎
          </span>
        </div>
      );
    }
    if (data.length > 120) {
      return (
        <div
          style={{
            background: "#0D1117",
            border: "1px solid #21262D",
            borderRadius: 6,
            padding: "8px 10px",
            fontFamily: "monospace",
            fontSize: 11,
            color: "#E6EDF3",
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
          }}
        >
          {data}
        </div>
      );
    }
    if (data.length <= 120 && onEdit) {
      return (
        <span
          onDoubleClick={() => onEdit(fieldPath, data)}
          title="Doble click para editar"
          style={{
            color: "#A5D6FF",
            fontFamily: "monospace",
            cursor: "text",
            borderBottom: "1px dashed #30363D",
          }}
        >
          "{data}"
        </span>
      );
    }
    return (
      <span style={{ color: "#E6EDF3", fontFamily: "monospace" }}>
        "{data}"
      </span>
    );
  }

  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <span style={{ color: "#484F58" }}>[]</span>;
    }
    return (
      <div style={{ paddingLeft: depth > 0 ? 16 : 0 }}>
        {data.map((item, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              gap: 8,
              padding: "2px 0",
              borderLeft: depth > 0 ? "1px solid #21262D" : "none",
              paddingLeft: depth > 0 ? 12 : 0,
            }}
          >
            <span style={{ color: "#484F58", fontSize: 10, minWidth: 16 }}>
              {i}
            </span>
            <JsonViewer
              data={item}
              depth={depth + 1}
              onEdit={onEdit}
              fieldPath={fieldPath ? `${fieldPath}[${i}]` : `[${i}]`}
            />
          </div>
        ))}
      </div>
    );
  }

  if (typeof data === "object") {
    const entries = Object.entries(data as Record<string, unknown>);
    if (entries.length === 0) {
      return <span style={{ color: "#484F58" }}>{`{}`}</span>;
    }
    return (
      <div
        style={{
          borderLeft: depth > 0 ? "1px solid #21262D" : "none",
          paddingLeft: depth > 0 ? 12 : 0,
        }}
      >
        {entries.map(([key, value]) => (
          <div
            key={key}
            style={{
              padding: "3px 0",
              display: "flex",
              gap: 8,
              alignItems:
                typeof value === "object" && value !== null
                  ? "flex-start"
                  : "center",
            }}
          >
            <span
              style={{
                color: "#A371F7",
                fontSize: 11,
                fontFamily: "monospace",
                fontWeight: 600,
                minWidth: 120,
                flexShrink: 0,
              }}
            >
              {key}:
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <JsonViewer
                data={value}
                depth={depth + 1}
                onEdit={onEdit}
                fieldPath={fieldPath ? `${fieldPath}.${key}` : key}
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return <span style={{ color: "#8B949E" }}>{String(data)}</span>;
}

// ── MemoCard ────────────────────────────────────────────────────────

export function MemoCard({
  memo,
  onDelete,
  onUpdate,
  projectId,
  originalPrompt,
  onMemoModified,
  entityTypes,
  onToggleSelect,
  selected,
}: {
  memo: MemoEntry;
  onDelete: (id: string) => Promise<void> | void;
  onUpdate: (id: string, field: string, value: string) => void;
  projectId: string;
  originalPrompt?: string;
  onMemoModified?: () => void;
  entityTypes: EntityTypeInfo[];
  /** Renders the selection checkbox when provided. */
  onToggleSelect?: (id: string) => void;
  selected?: boolean;
}) {
  const { t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const [confirmDel, setConfirmDel] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editingField, setEditingField] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const entityTypeKey = getMemoEntityType(memo);
  const entityTypeInfo = entityTypes.find((t) => t.key === entityTypeKey);
  const typeColor = entityTypeInfo?.color || "#8B949E";
  const typeLabel = entityTypeInfo
    ? `${entityTypeInfo.icon} ${entityTypeInfo.label}`
    : entityTypeKey;

  function handleDblClick(field: string, currentValue: unknown) {
    setEditingField(field);
    setEditValue(typeof currentValue === "string" ? currentValue : "");
  }

  function handleSave(field: string) {
    if (editValue.trim()) {
      onUpdate(memo.id, field, editValue.trim());
    }
    setEditingField(null);
  }

  async function handleConfirmDelete() {
    setDeleting(true);
    try {
      await onDelete(memo.id);
    } catch {
      // The parent reports the failure with a toast; keep the card visible.
    } finally {
      setDeleting(false);
      setConfirmDel(false);
    }
  }

  return (
    <div
      style={{
        background: selected ? "#58A6FF0D" : "#161B22",
        border: selected ? "1px solid #58A6FF" : `1px solid ${typeColor}33`,
        borderRadius: 8,
        marginBottom: 8,
        overflow: "hidden",
        cursor: "pointer",
      }}
      onClick={(e) => {
        // No expandir/colapsar si el click viene de un elemento interactivo
        const target = e.target as HTMLElement;
        if (
          target.closest(
            "button, textarea, input, select, a, [contenteditable='true'], [role='button']",
          )
        )
          return;

        // Si ya hay un timer pendiente (posible doble-click), cancelar toggle
        if (clickTimerRef.current) {
          clearTimeout(clickTimerRef.current);
          clickTimerRef.current = null;
          return;
        }

        // Esperar 250ms antes de toggle — si llega un 2º click (dblclick) se cancela
        clickTimerRef.current = setTimeout(() => {
          setExpanded(!expanded);
          clickTimerRef.current = null;
        }, 250);
      }}
      onDoubleClick={() => {
        // Cancelar cualquier toggle pendiente al hacer doble-click
        if (clickTimerRef.current) {
          clearTimeout(clickTimerRef.current);
          clickTimerRef.current = null;
        }
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          padding: "8px 12px",
          borderBottom: expanded ? "1px solid #21262D" : "none",
        }}
      >
        {onToggleSelect && (
          <input
            type="checkbox"
            checked={!!selected}
            onChange={() => onToggleSelect(memo.id)}
            onClick={(e) => e.stopPropagation()}
            title={t("memo.selectMemo")}
            aria-label={t("memo.selectMemo")}
            style={{
              cursor: "pointer",
              accentColor: "#58A6FF",
              flexShrink: 0,
            }}
          />
        )}
        <span
          style={{
            fontSize: 10,
            padding: "2px 6px",
            borderRadius: 4,
            background: typeColor + "18",
            color: typeColor,
            border: `1px solid ${typeColor}44`,
            fontWeight: 600,
          }}
        >
          {typeLabel}
        </span>
        <span
          style={{
            fontSize: 10,
            padding: "2px 6px",
            borderRadius: 4,
            background: "#8B949E18",
            color: "#8B949E",
            border: "1px solid #8B949E33",
            fontWeight: 500,
          }}
        >
          {t(getFamilyLabel(memo))}
        </span>
        <span
          style={{
            fontSize: 10,
            padding: "2px 6px",
            borderRadius: 4,
            background: memo.user_created ? "#3FB95018" : "#A371F718",
            color: memo.user_created ? "#3FB950" : "#A371F7",
            border: memo.user_created
              ? "1px solid #3FB95033"
              : "1px solid #A371F744",
            fontWeight: 500,
          }}
        >
          {memo.user_created ? t("memo.manual") : t("memo.ai")}
        </span>
        <span
          style={{
            fontSize: 11,
            color: "#E6EDF3",
            fontWeight: 500,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
        >
          {memo.documentName}
        </span>
        <span style={{ fontSize: 9, color: "#484F58" }}>{memo.timestamp}</span>
        {confirmDel ? (
          <span
            onClick={(e) => e.stopPropagation()}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 6px",
              borderRadius: 999,
              border: "1px solid #F8514944",
              background: "#F8514922",
              fontSize: 10,
              color: "#F85149",
            }}
          >
            <span>{t("memo.deleteOutputConfirm")}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleConfirmDelete();
              }}
              disabled={deleting}
              style={{
                padding: "1px 5px",
                borderRadius: 4,
                border: "none",
                background: "#F85149",
                color: "#fff",
                fontSize: 9,
                fontWeight: 600,
                cursor: deleting ? "not-allowed" : "pointer",
                opacity: deleting ? 0.6 : 1,
              }}
            >
              {deleting ? t("memo.deleting") : t("memo.confirmYes")}
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setConfirmDel(false);
              }}
              style={{
                padding: "1px 5px",
                borderRadius: 4,
                border: "none",
                background: "#21262D",
                color: "#8B949E",
                fontSize: 9,
                cursor: "pointer",
              }}
            >
              {t("memo.confirmNo")}
            </button>
          </span>
        ) : (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setConfirmDel(true);
            }}
            style={{
              background: "transparent",
              border: "1px solid #F8514944",
              borderRadius: 4,
              color: "#F85149",
              fontSize: 10,
              padding: "2px 6px",
              cursor: "pointer",
              opacity: 0.7,
            }}
            title={t("memo.deletePermanentlyTitle")}
          >
            ✕
          </button>
        )}
        <span style={{ fontSize: 11, color: "#484F58" }}>
          {expanded ? "▲" : "▼"}
        </span>
      </div>

      {/* Collapsed preview */}
      {!expanded && (
        <div style={{ padding: "6px 12px 10px" }}>
          {Object.entries(memo.data)
            .slice(0, 3)
            .map(([key, value]) => (
              <div
                key={key}
                style={{
                  display: "flex",
                  gap: 6,
                  padding: "1px 0",
                  fontSize: 11,
                }}
              >
                <span
                  style={{
                    color: "#8B949E",
                    fontFamily: "monospace",
                    flexShrink: 0,
                  }}
                >
                  {key}:
                </span>
                <span
                  style={{
                    color: "#E6EDF3",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {typeof value === "string"
                    ? value.slice(0, 80) + (value.length > 80 ? "…" : "")
                    : String(value)}
                </span>
              </div>
            ))}
          {Object.keys(memo.data).length > 3 && (
            <span style={{ fontSize: 10, color: "#58A6FF", marginTop: 4 }}>
              {t("memo.moreCount", { n: Object.keys(memo.data).length - 3 })}
            </span>
          )}
        </div>
      )}

      {/* Expanded full content */}
      {expanded && (
        <div style={{ padding: "10px 12px 14px" }}>
          {editingField ? (
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                background: "#0D1117",
                border: "1px solid #58A6FF",
                borderRadius: 6,
                padding: 8,
              }}
            >
              {/* ── Field label ── */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  marginBottom: 6,
                }}
              >
                <span
                  style={{
                    color: "#A371F7",
                    fontSize: 10,
                    fontFamily: "monospace",
                    fontWeight: 600,
                  }}
                >
                  {editingField}
                </span>
              </div>

              {/* ── Input: single-line para strings cortos, textarea para largos ── */}
              {editValue.length <= 120 ? (
                <input
                  autoFocus
                  type="text"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setEditingField(null);
                    if (e.key === "Enter") handleSave(editingField);
                  }}
                  style={{
                    width: "100%",
                    background: "#161B22",
                    color: "#E6EDF3",
                    border: "1px solid #30363D",
                    borderRadius: 4,
                    padding: "6px 8px",
                    fontFamily: "monospace",
                    fontSize: 12,
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              ) : (
                <textarea
                  autoFocus
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") setEditingField(null);
                    if (e.key === "Enter" && e.ctrlKey)
                      handleSave(editingField);
                  }}
                  rows={Math.min(
                    Math.max(Math.ceil(editValue.length / 55), 3),
                    10,
                  )}
                  style={{
                    width: "100%",
                    minHeight: 48,
                    background: "#161B22",
                    color: "#E6EDF3",
                    border: "1px solid #30363D",
                    borderRadius: 4,
                    padding: "6px 8px",
                    fontFamily: "monospace",
                    fontSize: 11,
                    lineHeight: 1.5,
                    resize: "vertical",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              )}

              {/* ── Actions ── */}
              <div
                style={{
                  display: "flex",
                  gap: 6,
                  marginTop: 6,
                  alignItems: "center",
                }}
              >
                <button
                  onClick={() => handleSave(editingField)}
                  style={{
                    padding: "3px 10px",
                    borderRadius: 4,
                    border: "none",
                    background: "#3FB950",
                    color: "#FFF",
                    fontSize: 11,
                    cursor: "pointer",
                    fontWeight: 500,
                  }}
                >
                  {t("common.save")}
                  {editValue.length <= 120
                    ? ` ${t("memo.saveShortcut")}`
                    : ` ${t("memo.saveShortcutCtrl")}`}
                </button>
                <button
                  onClick={() => setEditingField(null)}
                  style={{
                    padding: "3px 10px",
                    borderRadius: 4,
                    border: "1px solid #30363D",
                    background: "#1C2333",
                    color: "#8B949E",
                    fontSize: 11,
                    cursor: "pointer",
                  }}
                >
                  {t("memo.cancelShortcut")}
                </button>
              </div>
            </div>
          ) : (
            <JsonViewer
              data={memo.data}
              onEdit={(field, value) => {
                setEditingField(field);
                setEditValue(value);
              }}
            />
          )}

          {/* ── Modification Panel ───────────────────── */}
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              marginTop: 12,
              paddingTop: 12,
              borderTop: "1px solid #21262D",
            }}
          >
            <ModificationPanel
              projectId={projectId}
              agentId={memo.agentId}
              currentMemo={memo.data}
              memoId={memo.id}
              originalPrompt={originalPrompt || ""}
              agentFamily={memo.family}
              onApplied={onMemoModified}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ── ConfirmDeleteButton ────────────────────────────────────────────────
// Pill → inline "confirm / cancel" step. No native confirm(): the inline
// step is the only way to confirm, so it works when `window.confirm` is
// blocked.

export function ConfirmDeleteButton({
  label,
  title,
  confirmText,
  disabled,
  busyText,
  onConfirm,
}: {
  label: string;
  title?: string;
  confirmText: string;
  disabled?: boolean;
  busyText?: string;
  onConfirm: () => Promise<void> | void;
}) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  // A disabled trigger must not leave an armed confirmation behind.
  useEffect(() => {
    if (disabled) setConfirming(false);
  }, [disabled]);

  const handleConfirm = async () => {
    setBusy(true);
    try {
      await onConfirm();
    } catch {
      // The parent already reports the failure with a toast.
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  if (!confirming) {
    return (
      <button
        onClick={(e) => {
          e.stopPropagation();
          if (!disabled) setConfirming(true);
        }}
        disabled={disabled}
        title={title ?? label}
        style={{
          padding: "3px 8px",
          borderRadius: 999,
          border: "1px solid #F8514933",
          background: "#F8514918",
          color: "#F85149",
          fontSize: 10,
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.5 : 1,
        }}
      >
        {`${t("memo.deleteButtonIcon")}${label}`}
      </button>
    );
  }

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "3px 8px",
        borderRadius: 999,
        border: "1px solid #F8514944",
        background: "#F8514922",
        fontSize: 10,
        color: "#F85149",
      }}
    >
      <span>{confirmText}</span>
      <button
        onClick={(e) => {
          e.stopPropagation();
          handleConfirm();
        }}
        disabled={busy || disabled}
        style={{
          padding: "1px 5px",
          borderRadius: 4,
          border: "none",
          background: "#F85149",
          color: "#fff",
          fontSize: 9,
          fontWeight: 600,
          cursor: busy ? "not-allowed" : "pointer",
          opacity: busy ? 0.6 : 1,
        }}
      >
        {busy ? (busyText ?? t("memo.deleting")) : t("memo.confirmYes")}
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setConfirming(false);
        }}
        style={{
          padding: "1px 5px",
          borderRadius: 4,
          border: "none",
          background: "#21262D",
          color: "#8B949E",
          fontSize: 9,
          cursor: "pointer",
        }}
      >
        {t("memo.confirmNo")}
      </button>
    </span>
  );
}

// ── MemoHistory ─────────────────────────────────────────────────────

interface MemoHistoryProps {
  memos: MemoEntry[];
  activeFilter: string;
  onFilterChange: (typeKey: string) => void;
  onDeleteMemo: (id: string) => Promise<void> | void;
  /** Batch delete. Falls back to sequential `onDeleteMemo` when absent. */
  onDeleteMemos?: (ids: string[]) => Promise<void>;
  /** Disables batch deletion (e.g. while the pipeline is running). */
  deleteDisabled?: boolean;
  onUpdateMemo: (id: string, field: string, value: string) => void;
  projectId: string;
  originalPrompt?: string;
  onMemoModified?: () => void;
}

export function MemoHistory({
  memos,
  activeFilter,
  onFilterChange,
  onDeleteMemo,
  onDeleteMemos,
  deleteDisabled,
  onUpdateMemo,
  projectId,
  originalPrompt,
  onMemoModified,
}: MemoHistoryProps) {
  const { t, language } = useI18n();
  const [entityTypes, setEntityTypes] = useState<EntityTypeInfo[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmBulk, setBulkConfirm] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);

  // The catalogue is resolved in the UI language, so reload it on language change.
  useEffect(() => {
    getEntityTypeColors(language)
      .then((r) => setEntityTypes(r.types))
      .catch(() => {});
  }, [language]);

  // A deleted memo leaves its id behind in the selection; drop ghosts only
  // when the set actually changes, to avoid a re-render loop.
  useEffect(() => {
    setSelected((prev) => {
      if (prev.size === 0) return prev;
      const alive = new Set(memos.map((m) => m.id));
      const next = new Set([...prev].filter((memoId) => alive.has(memoId)));
      return next.size === prev.size ? prev : next;
    });
  }, [memos]);

  const filtered = memos.filter((m) => {
    if (activeFilter !== "all" && getMemoEntityType(m) !== activeFilter)
      return false;
    return true;
  });

  // Deletion only ever touches what is on screen: a selection left over from
  // another filter must not be deleted behind the user's back.
  const selectedVisible = filtered.filter((m) => selected.has(m.id));
  const selectedCount = selectedVisible.length;

  const allSelected =
    filtered.length > 0 && filtered.every((m) => selected.has(m.id));

  // The confirm panel is hidden when nothing visible is selected; without this
  // it would reappear already armed if the user selects something later.
  useEffect(() => {
    if (selectedCount === 0) setBulkConfirm(false);
  }, [selectedCount]);

  function toggleMemo(memoId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(memoId)) next.delete(memoId);
      else next.add(memoId);
      return next;
    });
  }

  // "Select all" acts on the visible (filtered) memos only.
  function toggleAllVisible(checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) filtered.forEach((m) => next.add(m.id));
      else filtered.forEach((m) => next.delete(m.id));
      return next;
    });
  }

  async function handleBulkDelete() {
    const ids = selectedVisible.map((m) => m.id);
    if (ids.length === 0) {
      setBulkConfirm(false);
      return;
    }
    setBulkDeleting(true);
    try {
      if (onDeleteMemos) await onDeleteMemos(ids);
      else for (const memoId of ids) await onDeleteMemo(memoId);
      // Do not clear the selection here: the purge effect drops the ids that
      // really disappeared, so a failed memo stays selected for a retry.
    } catch {
      // The parent reports the failure with a toast.
    } finally {
      setBulkDeleting(false);
      setBulkConfirm(false);
    }
  }

  return (
    <div>
      {/* Filter bar — entity types */}
      <div
        style={{
          display: "flex",
          gap: 4,
          marginBottom: 10,
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        {/* Filter dropdown — one compact control instead of a pill per category */}
        <select
          value={activeFilter}
          onChange={(e) => onFilterChange(e.target.value)}
          title={t("memo.filterByType")}
          aria-label={t("memo.filterByType")}
          style={{
            padding: "4px 8px",
            borderRadius: 6,
            border: "1px solid #21262D",
            background: "#161B22",
            color: "#E6EDF3",
            fontSize: 11,
            cursor: "pointer",
            maxWidth: 260,
          }}
        >
          <option value="all">
            {`${t("memo.allCategories")} (${memos.length})`}
          </option>
          {entityTypes.map((et) => {
            const count = memos.filter(
              (m) => getMemoEntityType(m) === et.key,
            ).length;
            return (
              <option key={et.key} value={et.key}>
                {`${et.icon} ${et.label} (${count})`}
              </option>
            );
          })}
        </select>
        {/* Selection + batch delete (right side of the filter row) */}
        <div
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: 8,
          }}
        >
          {filtered.length > 0 && (
            <label
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={allSelected}
                ref={(el) => {
                  if (el) el.indeterminate = selectedCount > 0 && !allSelected;
                }}
                onChange={(e) => toggleAllVisible(e.target.checked)}
                onClick={(e) => e.stopPropagation()}
                title={t("memo.selectAll")}
                aria-label={t("memo.selectAll")}
                style={{
                  margin: 0,
                  cursor: "pointer",
                  accentColor: "#58A6FF",
                }}
              />
              <span style={{ fontSize: 11, color: "#8B949E" }}>
                {t("memo.selectAll")}
              </span>
            </label>
          )}
          {selectedCount > 0 && !confirmBulk && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                if (!deleteDisabled) setBulkConfirm(true);
              }}
              disabled={deleteDisabled}
              title={deleteDisabled ? t("memo.pipelineBusy") : undefined}
              style={{
                padding: "3px 8px",
                borderRadius: 999,
                border: "1px solid #F8514933",
                background: "#F8514918",
                color: "#F85149",
                fontSize: 10,
                cursor: deleteDisabled ? "not-allowed" : "pointer",
                opacity: deleteDisabled ? 0.5 : 1,
              }}
            >
              {`🗑 ${t("memo.deleteSelected", { n: selectedCount })}`}
            </button>
          )}
          {confirmBulk && selectedCount > 0 && (
            <span
              onClick={(e) => e.stopPropagation()}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 4,
                padding: "3px 8px",
                borderRadius: 999,
                border: "1px solid #F8514944",
                background: "#F8514922",
                fontSize: 10,
                color: "#F85149",
              }}
            >
              <span>
                {t("memo.deleteSelectedConfirm", { n: selectedCount })}
              </span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleBulkDelete();
                }}
                disabled={bulkDeleting}
                style={{
                  padding: "1px 5px",
                  borderRadius: 4,
                  border: "none",
                  background: "#F85149",
                  color: "#fff",
                  fontSize: 9,
                  fontWeight: 600,
                  cursor: bulkDeleting ? "not-allowed" : "pointer",
                  opacity: bulkDeleting ? 0.6 : 1,
                }}
              >
                {bulkDeleting ? t("memo.deleting") : t("memo.confirmYes")}
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setBulkConfirm(false);
                }}
                style={{
                  padding: "1px 5px",
                  borderRadius: 4,
                  border: "none",
                  background: "#21262D",
                  color: "#8B949E",
                  fontSize: 9,
                  cursor: "pointer",
                }}
              >
                {t("memo.confirmNo")}
              </button>
            </span>
          )}
        </div>
      </div>

      {/* Memo list */}
      {filtered.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: 24,
            color: "#484F58",
            fontSize: 12,
          }}
        >
          {t("memo.noMemos")}
        </div>
      ) : (
        filtered.map((memo) => (
          <MemoCard
            key={memo.id}
            memo={memo}
            onDelete={onDeleteMemo}
            onUpdate={onUpdateMemo}
            projectId={projectId}
            originalPrompt={originalPrompt}
            onMemoModified={onMemoModified}
            entityTypes={entityTypes}
            selected={selected.has(memo.id)}
            onToggleSelect={toggleMemo}
          />
        ))
      )}
    </div>
  );
}
