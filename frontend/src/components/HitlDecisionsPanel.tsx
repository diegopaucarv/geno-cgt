import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  bulkDeleteHitlDecisions,
  createHitlDecision,
  deleteHitlDecision,
  listHitlDecisions,
  updateHitlDecision,
  type HitlDecisionFull,
  type HitlDecisionList,
  type HitlStatus,
} from "../api/client";
import { useI18n } from "../i18n";

// ── Helpers ─────────────────────────────────────────────────────────

const STATUS_COLORS: Record<HitlStatus, string> = {
  pending: "#D29922",
  accepted: "#3FB950",
  modified: "#58A6FF",
  rejected: "#F85149",
};

const STATUS_ORDER: HitlStatus[] = [
  "pending",
  "accepted",
  "modified",
  "rejected",
];

const KNOWN_GATES = [
  "pattern_of_interest",
  "pattern_convergence",
  "core_category",
  "selective_reduction",
  "core_saturation",
  "database_a",
  "database_b",
];

function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function pretty(value: Record<string, unknown>): string {
  if (!value || Object.keys(value).length === 0) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function statusLabel(t: (k: string) => string, status: HitlStatus): string {
  return t(
    `hitlCrud.status${status.charAt(0).toUpperCase()}${status.slice(1)}`,
  );
}

// ── Small building blocks ───────────────────────────────────────────

function Pill({
  active,
  color,
  onClick,
  children,
  title,
}: {
  active: boolean;
  color: string;
  onClick: () => void;
  children: ReactNode;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      style={{
        padding: "3px 9px",
        borderRadius: 999,
        border: `1px solid ${active ? color : "#30363D"}`,
        background: active ? `${color}22` : "transparent",
        color: active ? color : "#8B949E",
        fontSize: 10,
        fontWeight: 600,
        cursor: "pointer",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

function JsonBlock({
  label,
  value,
}: {
  label: string;
  value: Record<string, unknown>;
}) {
  const text = pretty(value);
  return (
    <div style={{ marginTop: 6 }}>
      <div style={{ fontSize: 10, color: "#8B949E", marginBottom: 2 }}>
        {label}
      </div>
      {text ? (
        <pre
          style={{
            margin: 0,
            padding: 8,
            borderRadius: 6,
            background: "#0D1117",
            border: "1px solid #30363D",
            color: "#C9D1D9",
            fontSize: 10,
            lineHeight: 1.45,
            maxHeight: 240,
            overflow: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {text}
        </pre>
      ) : (
        <span style={{ fontSize: 10, color: "#484F58" }}>—</span>
      )}
    </div>
  );
}

// ── Panel ───────────────────────────────────────────────────────────

export default function HitlDecisionsPanel({
  projectId,
}: {
  projectId?: string;
}) {
  const { t } = useI18n();

  const [data, setData] = useState<HitlDecisionList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<HitlStatus | "all">("all");
  const [gateFilter, setGateFilter] = useState<string>("all");

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirmBulk, setConfirmBulk] = useState(false);
  const [confirmFilter, setConfirmFilter] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [editingNote, setEditingNote] = useState<{
    id: string;
    value: string;
  } | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [createGate, setCreateGate] = useState("");
  const [createNote, setCreateNote] = useState("");
  const [createStatus, setCreateStatus] = useState<HitlStatus>("pending");

  const load = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const result = await listHitlDecisions(projectId, { limit: 500 });
      setData(result);
      setSelected((prev) => {
        const alive = new Set(result.items.map((item) => item.id));
        const next = new Set<string>();
        prev.forEach((id) => {
          if (alive.has(id)) next.add(id);
        });
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const items = data?.items ?? [];
  const counts = data?.counts;

  const gates = useMemo(() => {
    const found = new Set<string>(KNOWN_GATES);
    items.forEach((item) => found.add(item.gate_name));
    return Array.from(found).sort();
  }, [items]);

  const visible = useMemo(
    () =>
      items.filter(
        (item) =>
          (statusFilter === "all" || item.status === statusFilter) &&
          (gateFilter === "all" || item.gate_name === gateFilter),
      ),
    [items, statusFilter, gateFilter],
  );

  const filterActive = statusFilter !== "all" || gateFilter !== "all";
  const selectedVisible = visible.filter((item) => selected.has(item.id));
  const selectedCount = selectedVisible.length;
  const allSelected = visible.length > 0 && selectedCount === visible.length;

  useEffect(() => {
    if (selectedCount === 0) setConfirmBulk(false);
  }, [selectedCount]);

  useEffect(() => {
    if (!filterActive) setConfirmFilter(false);
  }, [filterActive]);

  function toggleAllVisible(checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      visible.forEach((item) => {
        if (checked) next.add(item.id);
        else next.delete(item.id);
      });
      return next;
    });
  }

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleExpanded(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleBulkDelete() {
    if (!projectId || selectedCount === 0) return;
    setBusy("bulk");
    try {
      await bulkDeleteHitlDecisions(projectId, {
        ids: selectedVisible.map((item) => item.id),
      });
      setSelected(new Set());
      setConfirmBulk(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleDeleteFiltered() {
    if (!projectId || !filterActive) return;
    setBusy("filter");
    try {
      await bulkDeleteHitlDecisions(projectId, {
        ...(statusFilter !== "all" ? { status: statusFilter } : {}),
        ...(gateFilter !== "all" ? { gate_name: gateFilter } : {}),
      });
      setConfirmFilter(false);
      setSelected(new Set());
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleDeleteOne(id: string) {
    if (!projectId) return;
    setBusy(id);
    try {
      await deleteHitlDecision(projectId, id);
      setConfirmDeleteId(null);
      setEditingNote(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveNote(id: string, value: string) {
    if (!projectId) return;
    setBusy(id);
    try {
      await updateHitlDecision(projectId, id, { note: value });
      setEditingNote(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleChangeStatus(id: string, status: HitlStatus) {
    if (!projectId) return;
    setBusy(id);
    try {
      await updateHitlDecision(projectId, id, { status });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  async function handleCreate() {
    if (!projectId || createGate.trim().length === 0) return;
    setBusy("create");
    try {
      await createHitlDecision(projectId, {
        gate_name: createGate.trim(),
        note: createNote,
        status: createStatus,
      });
      setShowCreate(false);
      setCreateGate("");
      setCreateNote("");
      setCreateStatus("pending");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(null);
    }
  }

  if (!projectId) return null;

  const totalCount = items.length;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: "2px 0 12px",
        minHeight: 0,
        overflow: "auto",
      }}
    >
      {/* Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: "#C9D1D9" }}>
          {t("hitlCrud.title")}
        </span>
        <span style={{ fontSize: 10, color: "#8B949E" }}>
          {t("hitlCrud.total", { n: totalCount })}
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <button
            onClick={() => void load()}
            disabled={loading}
            style={{
              padding: "3px 9px",
              borderRadius: 6,
              border: "1px solid #30363D",
              background: "#21262D",
              color: "#8B949E",
              fontSize: 10,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? t("hitlCrud.loading") : t("hitlCrud.refresh")}
          </button>
          <button
            onClick={() => setShowCreate((prev) => !prev)}
            style={{
              padding: "3px 9px",
              borderRadius: 6,
              border: `1px solid ${showCreate ? "#A371F7" : "#30363D"}`,
              background: showCreate ? "#A371F722" : "#21262D",
              color: showCreate ? "#A371F7" : "#8B949E",
              fontSize: 10,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {t("hitlCrud.newDecision")}
          </button>
        </div>
      </div>

      {/* Create form */}
      {showCreate && (
        <div
          style={{
            padding: 10,
            borderRadius: 8,
            background: "#161B22",
            border: "1px solid #30363D",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <label
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 3,
                flex: 1,
                minWidth: 160,
              }}
            >
              <span style={{ fontSize: 10, color: "#8B949E" }}>
                {t("hitlCrud.gateName")}
              </span>
              <input
                list="hitl-gate-options"
                value={createGate}
                onChange={(e) => setCreateGate(e.target.value)}
                placeholder={t("hitlCrud.gateNamePlaceholder")}
                style={{
                  padding: "4px 8px",
                  borderRadius: 6,
                  border: "1px solid #30363D",
                  background: "#0D1117",
                  color: "#C9D1D9",
                  fontSize: 11,
                }}
              />
              <datalist id="hitl-gate-options">
                {gates.map((gate) => (
                  <option key={gate} value={gate} />
                ))}
              </datalist>
            </label>
            <label
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 3,
                minWidth: 120,
              }}
            >
              <span style={{ fontSize: 10, color: "#8B949E" }}>
                {t("hitlCrud.status")}
              </span>
              <select
                value={createStatus}
                onChange={(e) => setCreateStatus(e.target.value as HitlStatus)}
                style={{
                  padding: "4px 8px",
                  borderRadius: 6,
                  border: "1px solid #30363D",
                  background: "#0D1117",
                  color: "#C9D1D9",
                  fontSize: 11,
                }}
              >
                {STATUS_ORDER.map((status) => (
                  <option key={status} value={status}>
                    {statusLabel(t, status)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <textarea
            value={createNote}
            onChange={(e) => setCreateNote(e.target.value)}
            placeholder={t("hitlCrud.notePlaceholder")}
            rows={2}
            style={{
              padding: "6px 8px",
              borderRadius: 6,
              border: "1px solid #30363D",
              background: "#0D1117",
              color: "#C9D1D9",
              fontSize: 11,
              resize: "vertical",
            }}
          />
          <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
            <button
              onClick={() => setShowCreate(false)}
              style={{
                padding: "3px 10px",
                borderRadius: 6,
                border: "1px solid #30363D",
                background: "#21262D",
                color: "#8B949E",
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              {t("hitlCrud.cancel")}
            </button>
            <button
              onClick={() => void handleCreate()}
              disabled={busy === "create" || createGate.trim().length === 0}
              style={{
                padding: "3px 10px",
                borderRadius: 6,
                border: "none",
                background: "#A371F7",
                color: "#fff",
                fontSize: 10,
                fontWeight: 600,
                cursor:
                  busy === "create" || createGate.trim().length === 0
                    ? "not-allowed"
                    : "pointer",
                opacity:
                  busy === "create" || createGate.trim().length === 0 ? 0.6 : 1,
              }}
            >
              {busy === "create" ? t("hitlCrud.saving") : t("hitlCrud.create")}
            </button>
          </div>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        <Pill
          active={statusFilter === "all"}
          color="#A371F7"
          onClick={() => setStatusFilter("all")}
        >
          {t("hitlCrud.filterAll")}
        </Pill>
        {STATUS_ORDER.map((status) => (
          <Pill
            key={status}
            active={statusFilter === status}
            color={STATUS_COLORS[status]}
            onClick={() =>
              setStatusFilter((prev) => (prev === status ? "all" : status))
            }
          >
            {statusLabel(t, status)}
            {counts ? ` ${counts[status]}` : ""}
          </Pill>
        ))}
        <select
          value={gateFilter}
          onChange={(e) => setGateFilter(e.target.value)}
          style={{
            marginLeft: "auto",
            padding: "3px 8px",
            borderRadius: 6,
            border: "1px solid #30363D",
            background: "#21262D",
            color: gateFilter === "all" ? "#8B949E" : "#C9D1D9",
            fontSize: 10,
            maxWidth: 180,
          }}
        >
          <option value="all">{t("hitlCrud.gateFilterAll")}</option>
          {gates.map((gate) => (
            <option key={gate} value={gate}>
              {gate}
            </option>
          ))}
        </select>
      </div>

      {/* Selection / bulk bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          minHeight: 22,
          flexWrap: "wrap",
        }}
      >
        {visible.length > 0 && (
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
              style={{ margin: 0, cursor: "pointer", accentColor: "#A371F7" }}
            />
            <span style={{ fontSize: 10, color: "#8B949E" }}>
              {t("hitlCrud.selectAll")}
            </span>
          </label>
        )}

        {selectedCount > 0 && !confirmBulk && (
          <button
            onClick={() => setConfirmBulk(true)}
            style={{
              padding: "2px 8px",
              borderRadius: 999,
              border: "1px solid #F8514933",
              background: "#F8514918",
              color: "#F85149",
              fontSize: 10,
              cursor: "pointer",
            }}
          >
            {`🗑 ${t("hitlCrud.deleteSelected", { n: selectedCount })}`}
          </button>
        )}

        {confirmBulk && selectedCount > 0 && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 8px",
              borderRadius: 999,
              border: "1px solid #F8514944",
              background: "#F8514922",
              fontSize: 10,
              color: "#F85149",
            }}
          >
            <span>
              {t("hitlCrud.deleteSelectedConfirm", { n: selectedCount })}
            </span>
            <button
              onClick={() => void handleBulkDelete()}
              disabled={busy === "bulk"}
              style={{
                padding: "1px 6px",
                borderRadius: 4,
                border: "none",
                background: "#F85149",
                color: "#fff",
                fontSize: 9,
                fontWeight: 600,
                cursor: busy === "bulk" ? "not-allowed" : "pointer",
              }}
            >
              {busy === "bulk" ? t("hitlCrud.deleting") : t("hitlCrud.yes")}
            </button>
            <button
              onClick={() => setConfirmBulk(false)}
              style={{
                padding: "1px 6px",
                borderRadius: 4,
                border: "none",
                background: "#21262D",
                color: "#8B949E",
                fontSize: 9,
                cursor: "pointer",
              }}
            >
              {t("hitlCrud.no")}
            </button>
          </span>
        )}

        {filterActive &&
          visible.length > 0 &&
          selectedCount === 0 &&
          !confirmFilter && (
            <button
              onClick={() => setConfirmFilter(true)}
              title={t("hitlCrud.deleteFilteredHint")}
              style={{
                padding: "2px 8px",
                borderRadius: 999,
                border: "1px solid #D2992233",
                background: "#D2992218",
                color: "#D29922",
                fontSize: 10,
                cursor: "pointer",
              }}
            >
              {`🗑 ${t("hitlCrud.deleteFiltered", { n: visible.length })}`}
            </button>
          )}

        {confirmFilter && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              padding: "2px 8px",
              borderRadius: 999,
              border: "1px solid #D2992244",
              background: "#D2992222",
              fontSize: 10,
              color: "#D29922",
            }}
          >
            <span>
              {t("hitlCrud.deleteFilteredConfirm", { n: visible.length })}
            </span>
            <button
              onClick={() => void handleDeleteFiltered()}
              disabled={busy === "filter"}
              style={{
                padding: "1px 6px",
                borderRadius: 4,
                border: "none",
                background: "#D29922",
                color: "#0D1117",
                fontSize: 9,
                fontWeight: 600,
                cursor: busy === "filter" ? "not-allowed" : "pointer",
              }}
            >
              {busy === "filter" ? t("hitlCrud.deleting") : t("hitlCrud.yes")}
            </button>
            <button
              onClick={() => setConfirmFilter(false)}
              style={{
                padding: "1px 6px",
                borderRadius: 4,
                border: "none",
                background: "#21262D",
                color: "#8B949E",
                fontSize: 9,
                cursor: "pointer",
              }}
            >
              {t("hitlCrud.no")}
            </button>
          </span>
        )}

        {visible.length !== totalCount && (
          <span style={{ fontSize: 10, color: "#484F58", marginLeft: "auto" }}>
            {t("hitlCrud.shownOf", {
              shown: visible.length,
              total: totalCount,
            })}
          </span>
        )}
      </div>

      {error && (
        <div
          style={{
            padding: "6px 10px",
            borderRadius: 6,
            background: "#F8514922",
            border: "1px solid #F8514944",
            color: "#F85149",
            fontSize: 10,
          }}
        >
          {error}
        </div>
      )}

      {/* List */}
      {visible.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: 24,
            color: "#484F58",
            fontSize: 11,
          }}
        >
          {loading ? t("hitlCrud.loading") : t("hitlCrud.empty")}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {visible.map((decision) => (
            <DecisionRow
              key={decision.id}
              decision={decision}
              t={t}
              selected={selected.has(decision.id)}
              expanded={expanded.has(decision.id)}
              busy={busy === decision.id}
              confirmDelete={confirmDeleteId === decision.id}
              editingNote={
                editingNote?.id === decision.id ? editingNote.value : null
              }
              onToggleSelect={() => toggleSelect(decision.id)}
              onToggleExpand={() => toggleExpanded(decision.id)}
              onStartEditNote={() =>
                setEditingNote({
                  id: decision.id,
                  value: decision.researcher_note ?? "",
                })
              }
              onChangeNote={(value) =>
                setEditingNote((prev) =>
                  prev && prev.id === decision.id ? { ...prev, value } : prev,
                )
              }
              onCancelEditNote={() => setEditingNote(null)}
              onSaveNote={(value) => void handleSaveNote(decision.id, value)}
              onChangeStatus={(status) =>
                void handleChangeStatus(decision.id, status)
              }
              onAskDelete={() => setConfirmDeleteId(decision.id)}
              onCancelDelete={() => setConfirmDeleteId(null)}
              onConfirmDelete={() => void handleDeleteOne(decision.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Row ─────────────────────────────────────────────────────────────

function DecisionRow({
  decision,
  t,
  selected,
  expanded,
  busy,
  confirmDelete,
  editingNote,
  onToggleSelect,
  onToggleExpand,
  onStartEditNote,
  onChangeNote,
  onCancelEditNote,
  onSaveNote,
  onChangeStatus,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: {
  decision: HitlDecisionFull;
  t: (key: string, replacements?: Record<string, string | number>) => string;
  selected: boolean;
  expanded: boolean;
  busy: boolean;
  confirmDelete: boolean;
  editingNote: string | null;
  onToggleSelect: () => void;
  onToggleExpand: () => void;
  onStartEditNote: () => void;
  onChangeNote: (value: string) => void;
  onCancelEditNote: () => void;
  onSaveNote: (value: string) => void;
  onChangeStatus: (status: HitlStatus) => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}) {
  const color = STATUS_COLORS[decision.status] ?? "#8B949E";

  return (
    <div
      style={{
        borderRadius: 8,
        border: `1px solid ${selected ? "#A371F7" : "#30363D"}`,
        background: selected ? "#A371F70D" : "#161B22",
        padding: 8,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          style={{ margin: 0, cursor: "pointer", accentColor: "#A371F7" }}
          aria-label={t("hitlCrud.selectAll")}
        />
        <button
          onClick={onToggleExpand}
          title={expanded ? t("hitlCrud.hideDetails") : t("hitlCrud.details")}
          style={{
            border: "none",
            background: "transparent",
            color: "#8B949E",
            fontSize: 10,
            cursor: "pointer",
            padding: 0,
            width: 12,
            flexShrink: 0,
          }}
        >
          {expanded ? "▾" : "▸"}
        </button>
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 10,
            color: "#C9D1D9",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
            minWidth: 40,
          }}
          title={decision.gate_name}
        >
          {decision.gate_name}
        </span>
        <span
          style={{
            padding: "1px 7px",
            borderRadius: 999,
            border: `1px solid ${color}44`,
            background: `${color}18`,
            color,
            fontSize: 9,
            fontWeight: 600,
            flexShrink: 0,
          }}
        >
          {statusLabel(t, decision.status)}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginTop: 4,
          marginLeft: 20,
        }}
      >
        <span style={{ fontSize: 9, color: "#484F58", flex: 1 }}>
          {formatDate(decision.created_at)}
        </span>

        <select
          value={decision.status}
          onChange={(e) => onChangeStatus(e.target.value as HitlStatus)}
          disabled={busy}
          title={t("hitlCrud.redecide")}
          style={{
            padding: "1px 4px",
            borderRadius: 4,
            border: "1px solid #30363D",
            background: "#0D1117",
            color: "#8B949E",
            fontSize: 9,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          {STATUS_ORDER.map((status) => (
            <option key={status} value={status}>
              {statusLabel(t, status)}
            </option>
          ))}
        </select>
        <button
          onClick={onStartEditNote}
          disabled={busy}
          title={t("hitlCrud.editNote")}
          style={{
            padding: "1px 6px",
            borderRadius: 4,
            border: "1px solid #30363D",
            background: "#21262D",
            color: "#8B949E",
            fontSize: 9,
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          ✎
        </button>
        {!confirmDelete ? (
          <button
            onClick={onAskDelete}
            disabled={busy}
            title={t("hitlCrud.delete")}
            style={{
              padding: "1px 6px",
              borderRadius: 4,
              border: "1px solid #F8514933",
              background: "#F8514918",
              color: "#F85149",
              fontSize: 9,
              cursor: busy ? "not-allowed" : "pointer",
            }}
          >
            🗑
          </button>
        ) : (
          <span
            style={{ display: "inline-flex", gap: 3, alignItems: "center" }}
          >
            <button
              onClick={onConfirmDelete}
              disabled={busy}
              style={{
                padding: "1px 6px",
                borderRadius: 4,
                border: "none",
                background: "#F85149",
                color: "#fff",
                fontSize: 9,
                fontWeight: 600,
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              {t("hitlCrud.yes")}
            </button>
            <button
              onClick={onCancelDelete}
              style={{
                padding: "1px 6px",
                borderRadius: 4,
                border: "none",
                background: "#21262D",
                color: "#8B949E",
                fontSize: 9,
                cursor: "pointer",
              }}
            >
              {t("hitlCrud.no")}
            </button>
          </span>
        )}
      </div>

      {decision.researcher_note && editingNote === null && (
        <div
          style={{
            marginTop: 6,
            marginLeft: 32,
            fontSize: 10,
            color: "#8B949E",
            fontStyle: "italic",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {decision.researcher_note}
        </div>
      )}

      {editingNote !== null && (
        <div
          style={{
            marginTop: 6,
            marginLeft: 32,
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <textarea
            value={editingNote}
            onChange={(e) => onChangeNote(e.target.value)}
            rows={2}
            style={{
              padding: "5px 7px",
              borderRadius: 6,
              border: "1px solid #A371F7",
              background: "#0D1117",
              color: "#C9D1D9",
              fontSize: 10,
              resize: "vertical",
            }}
          />
          <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
            <button
              onClick={onCancelEditNote}
              style={{
                padding: "1px 8px",
                borderRadius: 4,
                border: "1px solid #30363D",
                background: "#21262D",
                color: "#8B949E",
                fontSize: 9,
                cursor: "pointer",
              }}
            >
              {t("hitlCrud.cancel")}
            </button>
            <button
              onClick={() => onSaveNote(editingNote)}
              disabled={busy}
              style={{
                padding: "1px 8px",
                borderRadius: 4,
                border: "none",
                background: "#A371F7",
                color: "#fff",
                fontSize: 9,
                fontWeight: 600,
                cursor: busy ? "not-allowed" : "pointer",
              }}
            >
              {busy ? t("hitlCrud.saving") : t("hitlCrud.save")}
            </button>
          </div>
        </div>
      )}

      {expanded && (
        <div style={{ marginTop: 6, marginLeft: 32 }}>
          <JsonBlock label={t("hitlCrud.proposal")} value={decision.proposal} />
          <JsonBlock
            label={t("hitlCrud.criticVerdict")}
            value={decision.critic_verdict}
          />
          <div
            style={{
              marginTop: 6,
              display: "flex",
              gap: 12,
              flexWrap: "wrap",
              fontSize: 9,
              color: "#484F58",
            }}
          >
            <span>
              {t("hitlCrud.researcherDecision")}:{" "}
              {decision.researcher_decision ?? "—"}
            </span>
            <span>
              {t("hitlCrud.decidedAt")}: {formatDate(decision.decided_at)}
            </span>
            <span>
              {t("hitlCrud.updatedAt")}: {formatDate(decision.updated_at)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
