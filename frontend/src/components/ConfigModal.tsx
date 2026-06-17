import { useEffect, useState, useCallback } from "react";
import { getToken, clearToken } from "../api/client";

/* ── Types ─────────────────────────────────────────────────────────── */

interface BackendConfig {
  environment: string;
  models: {
    pro: {
      tier: string;
      model_id: string;
      display_name: string;
      max_tokens: number;
      temperature: number;
    };
    flash: {
      tier: string;
      model_id: string;
      display_name: string;
      max_tokens: number;
      temperature: number;
    };
  };
  segmentation: {
    mode: string;
  };
  auth: {
    algorithm: string;
    token_type: string;
  };
}

interface UserInfo {
  user_id: string;
  email?: string;
  name?: string;
}

/* ── Styles ────────────────────────────────────────────────────────── */

const OVERLAY: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.65)",
  zIndex: 1000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const MODAL: React.CSSProperties = {
  background: "#161B22",
  border: "1px solid #30363D",
  borderRadius: 12,
  width: 520,
  maxHeight: "80vh",
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
  boxShadow: "0 8px 40px rgba(0,0,0,0.5)",
};

const HEADER: React.CSSProperties = {
  padding: "16px 20px",
  borderBottom: "1px solid #21262D",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const TAB_ROW: React.CSSProperties = {
  display: "flex",
  borderBottom: "1px solid #21262D",
  padding: "0 20px",
};

const TAB: React.CSSProperties = {
  padding: "10px 16px",
  fontSize: 13,
  cursor: "pointer",
  borderBottom: "2px solid transparent",
  background: "none",
  color: "#8B949E",
  transition: "all 0.15s",
};

const TAB_ACTIVE: React.CSSProperties = {
  ...TAB,
  color: "#E6EDF3",
  borderBottom: "2px solid #A371F7",
};

const BODY: React.CSSProperties = {
  padding: "20px",
  overflowY: "auto",
  flex: 1,
};

const SECTION: React.CSSProperties = {
  marginBottom: 20,
};

const SECTION_TITLE: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  color: "#8B949E",
  marginBottom: 10,
};

const KV_ROW: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  padding: "6px 0",
  borderBottom: "1px solid #21262D22",
  fontSize: 13,
};

const KV_KEY: React.CSSProperties = {
  color: "#8B949E",
};

const KV_VAL: React.CSSProperties = {
  color: "#E6EDF3",
  fontFamily: "monospace",
  fontSize: 12,
};

const BADGE: React.CSSProperties = {
  padding: "2px 8px",
  borderRadius: 999,
  fontSize: 11,
  fontWeight: 600,
};

const FLOAT_BTN: React.CSSProperties = {
  position: "fixed",
  bottom: 20,
  right: 20,
  zIndex: 999,
  width: 44,
  height: 44,
  borderRadius: "50%",
  background: "#21262D",
  border: "1px solid #30363D",
  color: "#8B949E",
  fontSize: 20,
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  boxShadow: "0 2px 12px rgba(0,0,0,0.4)",
  transition: "all 0.2s",
};

/* ── Floating config button ────────────────────────────────────────── */

export function ConfigButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={FLOAT_BTN}
      title="Configuración"
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "#30363D";
        e.currentTarget.style.color = "#E6EDF3";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "#21262D";
        e.currentTarget.style.color = "#8B949E";
      }}
    >
      ⚙
    </button>
  );
}

/* ── Config Modal ──────────────────────────────────────────────────── */

interface ConfigModalProps {
  open: boolean;
  onClose: () => void;
}

export default function ConfigModal({ open, onClose }: ConfigModalProps) {
  const [tab, setTab] = useState<"general" | "session">("general");
  const [config, setConfig] = useState<BackendConfig | null>(null);
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const token = getToken();

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/v1/config");
      if (res.ok) {
        setConfig(await res.json());
      } else {
        setError("No se pudo cargar la configuración del backend");
      }
    } catch {
      setError("Backend no disponible");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchSession = useCallback(async () => {
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const res = await fetch("/api/v1/ping", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUser({ user_id: data.user_id, email: data.email, name: data.name });
      }
    } catch {
      // ignore
    }
  }, [token]);

  useEffect(() => {
    if (!open) return;
    fetchConfig();
    if (token) fetchSession();
  }, [open, fetchConfig, fetchSession, token]);

  if (!open) return null;

  function handleLogout() {
    clearToken();
    onClose();
    window.location.href = "/login";
  }

  const envBadge =
    config?.environment === "dev"
      ? { ...BADGE, background: "#D2992222", color: "#D29922" }
      : config?.environment === "prod"
        ? { ...BADGE, background: "#2EA04322", color: "#2EA043" }
        : { ...BADGE, background: "#8B949E22", color: "#8B949E" };

  return (
    <div style={OVERLAY} onClick={onClose}>
      <div style={MODAL} onClick={(e) => e.stopPropagation()}>
        {/* ── Header ── */}
        <div style={HEADER}>
          <span style={{ fontSize: 16, fontWeight: 600, color: "#E6EDF3" }}>
            ⚙ Configuración
          </span>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#8B949E",
              fontSize: 18,
              cursor: "pointer",
            }}
          >
            ✕
          </button>
        </div>

        {/* ── Tabs ── */}
        <div style={TAB_ROW}>
          <button
            style={tab === "general" ? TAB_ACTIVE : TAB}
            onClick={() => setTab("general")}
          >
            🖥 General
          </button>
          <button
            style={tab === "session" ? TAB_ACTIVE : TAB}
            onClick={() => setTab("session")}
          >
            {token ? "🔐 Sesión" : "🔓 Sesión"}
          </button>
        </div>

        {/* ── Body ── */}
        <div style={BODY}>
          {tab === "general" && (
            <>
              {loading && (
                <p style={{ color: "#8B949E", fontSize: 13 }}>
                  Cargando configuración…
                </p>
              )}
              {error && (
                <p style={{ color: "#F85149", fontSize: 13 }}>{error}</p>
              )}

              {config && (
                <>
                  {/* Environment */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Entorno</div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Environment</span>
                      <span style={envBadge}>{config.environment}</span>
                    </div>
                  </div>

                  {/* Pro Model */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Modelo PRO (razonamiento)</div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Model ID</span>
                      <span style={KV_VAL}>{config.models.pro.model_id}</span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Display</span>
                      <span style={KV_VAL}>
                        {config.models.pro.display_name}
                      </span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Max tokens</span>
                      <span style={KV_VAL}>{config.models.pro.max_tokens}</span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Temperature</span>
                      <span style={KV_VAL}>
                        {config.models.pro.temperature}
                      </span>
                    </div>
                  </div>

                  {/* Flash Model */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Modelo FLASH (extracción)</div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Model ID</span>
                      <span style={KV_VAL}>{config.models.flash.model_id}</span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Display</span>
                      <span style={KV_VAL}>
                        {config.models.flash.display_name}
                      </span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Max tokens</span>
                      <span style={KV_VAL}>
                        {config.models.flash.max_tokens}
                      </span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Temperature</span>
                      <span style={KV_VAL}>
                        {config.models.flash.temperature}
                      </span>
                    </div>
                  </div>

                  {/* Segmentation */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Segmentación</div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Modo</span>
                      <span style={KV_VAL}>{config.segmentation.mode}</span>
                    </div>
                  </div>

                  {/* Auth */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Autenticación</div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Algoritmo</span>
                      <span style={KV_VAL}>{config.auth.algorithm}</span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Tipo de token</span>
                      <span style={KV_VAL}>{config.auth.token_type}</span>
                    </div>
                  </div>
                </>
              )}
            </>
          )}

          {tab === "session" && (
            <>
              {!token ? (
                <div style={{ textAlign: "center", padding: "20px 0" }}>
                  <p style={{ fontSize: 36, marginBottom: 12 }}>🔓</p>
                  <p style={{ color: "#8B949E", fontSize: 13 }}>
                    No has iniciado sesión.
                  </p>
                  <p style={{ color: "#484F58", fontSize: 12, marginTop: 8 }}>
                    Inicia sesión para ver la información de tu sesión.
                  </p>
                </div>
              ) : (
                <>
                  {/* User Info */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Usuario</div>
                    {user ? (
                      <>
                        <div style={KV_ROW}>
                          <span style={KV_KEY}>User ID</span>
                          <span style={KV_VAL}>
                            {user.user_id.slice(0, 12)}…
                          </span>
                        </div>
                        {user.email && (
                          <div style={KV_ROW}>
                            <span style={KV_KEY}>Email</span>
                            <span style={KV_VAL}>{user.email}</span>
                          </div>
                        )}
                        {user.name && (
                          <div style={KV_ROW}>
                            <span style={KV_KEY}>Nombre</span>
                            <span style={KV_VAL}>{user.name}</span>
                          </div>
                        )}
                      </>
                    ) : (
                      <p style={{ color: "#8B949E", fontSize: 13 }}>
                        Cargando info del usuario…
                      </p>
                    )}
                  </div>

                  {/* Token Info */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Token JWT</div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Almacenado en</span>
                      <span style={KV_VAL}>localStorage</span>
                    </div>
                    <div style={KV_ROW}>
                      <span style={KV_KEY}>Tipo</span>
                      <span style={KV_VAL}>Bearer (HS256)</span>
                    </div>
                    <div style={{ marginTop: 10 }}>
                      <span style={{ ...KV_KEY, fontSize: 11 }}>
                        Token preview:
                      </span>
                      <div
                        style={{
                          marginTop: 4,
                          padding: 8,
                          background: "#0D1117",
                          borderRadius: 6,
                          border: "1px solid #21262D",
                          fontSize: 11,
                          fontFamily: "monospace",
                          color: "#484F58",
                          wordBreak: "break-all",
                          maxHeight: 60,
                          overflow: "hidden",
                        }}
                      >
                        {token.slice(0, 60)}…
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div style={SECTION}>
                    <div style={SECTION_TITLE}>Acciones</div>
                    <button
                      onClick={handleLogout}
                      style={{
                        padding: "8px 20px",
                        borderRadius: 6,
                        border: "1px solid #F8514933",
                        background: "#F8514918",
                        color: "#F85149",
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Cerrar sesión
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
