import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useI18n } from "../i18n";

const BG = "#0D1117";
const CARD = "#161B22";
const BORDER = "#30363D";
const TEXT = "#E6EDF3";
const MUTED = "#8B949E";
const PURPLE = "#A371F7";
const GREEN = "#3FB950";
const RED = "#F85149";

async function registerUser(nombre: string, correo: string, password: string) {
  const res = await fetch("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nombre, correo, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Error" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export default function Register() {
  const { t } = useI18n();
  const [nombre, setNombre] = useState("");
  const [correo, setCorreo] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await registerUser(nombre, correo, password);
      localStorage.setItem("access_token", data.access_token);
      navigate("/setup");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 14px",
    background: BG,
    border: `1px solid ${BORDER}`,
    borderRadius: 8,
    color: TEXT,
    fontSize: 14,
    boxSizing: "border-box",
    outline: "none",
    transition: "border-color 0.2s",
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: BG,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <div
        style={{
          width: 380,
          padding: "40px 32px",
          background: CARD,
          border: `1px solid ${BORDER}`,
          borderRadius: 12,
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: 14,
              background: `linear-gradient(135deg, ${PURPLE}, #7C3AED)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px",
              fontSize: 24,
            }}
          >
            🧬
          </div>
          <h1
            style={{
              color: TEXT,
              fontSize: 22,
              fontWeight: 700,
              margin: 0,
              marginBottom: 4,
            }}
          >
            {t("auth.registerTitle")}
          </h1>
          <p style={{ color: MUTED, fontSize: 13, margin: 0 }}>
            Create your account
          </p>
        </div>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label
              style={{
                display: "block",
                fontSize: 12,
                color: MUTED,
                marginBottom: 6,
                fontWeight: 500,
              }}
            >
              {t("auth.nameLabel") || "Name"}
            </label>
            <input
              placeholder={t("auth.namePlaceholder")}
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              required
              style={inputStyle}
              onFocus={(e) => (e.target.style.borderColor = PURPLE)}
              onBlur={(e) => (e.target.style.borderColor = BORDER)}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label
              style={{
                display: "block",
                fontSize: 12,
                color: MUTED,
                marginBottom: 6,
                fontWeight: 500,
              }}
            >
              {t("auth.emailLabel") || "Email"}
            </label>
            <input
              type="email"
              placeholder={t("auth.emailPlaceholder")}
              value={correo}
              onChange={(e) => setCorreo(e.target.value)}
              required
              style={inputStyle}
              onFocus={(e) => (e.target.style.borderColor = PURPLE)}
              onBlur={(e) => (e.target.style.borderColor = BORDER)}
            />
          </div>

          <div style={{ marginBottom: 20 }}>
            <label
              style={{
                display: "block",
                fontSize: 12,
                color: MUTED,
                marginBottom: 6,
                fontWeight: 500,
              }}
            >
              {t("auth.passwordLabel") || "Password"}
            </label>
            <input
              type="password"
              placeholder={t("auth.passwordPlaceholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={inputStyle}
              onFocus={(e) => (e.target.style.borderColor = PURPLE)}
              onBlur={(e) => (e.target.style.borderColor = BORDER)}
            />
          </div>

          {error && (
            <div
              style={{
                padding: "10px 14px",
                marginBottom: 16,
                background: "rgba(248,81,73,0.1)",
                border: `1px solid ${RED}33`,
                borderRadius: 8,
                color: RED,
                fontSize: 13,
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "12px 16px",
              background: loading ? `${PURPLE}88` : GREEN,
              border: "none",
              borderRadius: 8,
              color: "#FFF",
              fontSize: 15,
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "..." : t("auth.registerButton")}
          </button>
        </form>

        <p
          style={{
            marginTop: 20,
            textAlign: "center",
            color: MUTED,
            fontSize: 13,
          }}
        >
          {t("auth.hasAccount")}{" "}
          <Link
            to="/login"
            style={{ color: PURPLE, textDecoration: "none", fontWeight: 600 }}
          >
            {t("auth.loginLink")}
          </Link>
        </p>
      </div>
    </div>
  );
}
