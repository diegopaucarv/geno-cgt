import { useState, useEffect } from "react";
import { usePlayground } from "./PlaygroundContext";
import {
  getRenameSuggestions,
  applyRename,
  type RenameSuggestion,
} from "../../api/client";
import { useI18n } from "../../i18n";

export default function RenameModal() {
  const pg = usePlayground();
  const { t } = useI18n();
  const [suggestions, setSuggestions] = useState<RenameSuggestion[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [custom, setCustom] = useState("");
  const [rationale, setRationale] = useState("");
  const [loading, setLoading] = useState(false);

  const blob = pg.renameTarget;
  if (!blob) return null;

  useEffect(() => {
    getRenameSuggestions(pg.projectId, blob.id)
      .then((s) => setSuggestions(s.suggestions || []))
      .catch(() => {});
  }, [blob.id]);

  const handleApply = async () => {
    const newName = custom || selected;
    if (!newName) return;
    setLoading(true);
    try {
      await applyRename(pg.projectId, {
        category_id: blob.id,
        new_name: newName,
        rationale,
      });
      pg.closeRename();
      pg.refreshEcosystem();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const levels = [
    { key: "conservative", label: t("theory.levelConservative") },
    { key: "moderate", label: t("theory.levelModerate") },
    { key: "transformative", label: t("theory.levelTransformer") },
  ];

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        <h3 style={{ margin: 0, fontSize: 16, color: "#E6EDF3" }}>
          {t("theory.renameTitle")}
        </h3>
        <p style={{ fontSize: 12, color: "#8B949E", marginTop: 4 }}>
          {t("theory.currentNameLabel")}
          <strong style={{ color: "#E6EDF3" }}>{blob.name}</strong>
        </p>

        {levels.map(({ key, label }) => {
          const items = suggestions.filter((s) => s.level === key);
          if (!items.length) return null;
          return (
            <div key={key} style={{ marginTop: 16 }}>
              <div style={{ fontSize: 11, color: "#484F58", fontWeight: 500 }}>
                {t("theory.sectionDividerPrefix")}
                {label}
                {t("theory.sectionDividerSuffix")}
              </div>
              {items.map((s, i) => (
                <label
                  key={i}
                  style={{
                    display: "block",
                    padding: "8px 12px",
                    marginTop: 6,
                    background: selected === s.name ? "#1C2333" : "transparent",
                    border: `1px solid ${selected === s.name ? "#58A6FF" : "#21262D"}`,
                    borderRadius: 6,
                    cursor: "pointer",
                    color: "#E6EDF3",
                    fontSize: 13,
                  }}
                >
                  <input
                    type="radio"
                    name="rename"
                    value={s.name}
                    checked={selected === s.name}
                    onChange={() => {
                      setSelected(s.name);
                      setCustom("");
                    }}
                    style={{ marginRight: 8 }}
                  />
                  {s.name}
                  <div
                    style={{
                      fontSize: 11,
                      color: "#8B949E",
                      marginTop: 2,
                      marginLeft: 22,
                    }}
                  >
                    {t("theory.arrowPrefix")}
                    {s.what_it_gains}
                  </div>
                </label>
              ))}
            </div>
          );
        })}

        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, color: "#484F58", fontWeight: 500 }}>
            {t("theory.customSection")}
          </div>
          <input
            placeholder={t("theory.customNamePlaceholder")}
            value={custom}
            onChange={(e) => {
              setCustom(e.target.value);
              setSelected("");
            }}
            style={inputStyle}
          />
        </div>

        <input
          placeholder={t("theory.justificationPlaceholder")}
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          style={{ ...inputStyle, marginTop: 8 }}
        />

        <div
          style={{
            marginTop: 20,
            display: "flex",
            gap: 8,
            justifyContent: "flex-end",
          }}
        >
          <button onClick={pg.closeRename} style={cancelBtn}>
            {t("theory.cancelButton")}
          </button>
          <button
            onClick={handleApply}
            disabled={loading || (!selected && !custom)}
            style={{
              ...applyBtn,
              opacity: loading || (!selected && !custom) ? 0.5 : 1,
            }}
          >
            {loading ? t("theory.applying") : t("theory.applyName")}
          </button>
        </div>
      </div>
    </div>
  );
}

const overlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.6)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 100,
};

const modalStyle: React.CSSProperties = {
  background: "#161B22",
  border: "1px solid #21262D",
  borderRadius: 12,
  padding: 24,
  maxWidth: 520,
  width: "90%",
  maxHeight: "80vh",
  overflow: "auto",
};

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 12px",
  borderRadius: 6,
  border: "1px solid #21262D",
  background: "#0D1117",
  color: "#E6EDF3",
  fontSize: 13,
  marginTop: 6,
  boxSizing: "border-box",
};

const cancelBtn: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: 6,
  border: "1px solid #21262D",
  background: "#0D1117",
  color: "#8B949E",
  cursor: "pointer",
  fontSize: 13,
};

const applyBtn: React.CSSProperties = {
  padding: "8px 16px",
  borderRadius: 6,
  border: "none",
  background: "#A371F7",
  color: "#FFF",
  cursor: "pointer",
  fontSize: 13,
};
