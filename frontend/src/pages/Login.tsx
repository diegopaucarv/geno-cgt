import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login } from "../api/client";
import { useI18n } from "../i18n";

const BG = "#0D1117";
const CARD = "#161B22";
const BORDER = "#30363D";
const TEXT = "#E6EDF3";
const MUTED = "#8B949E";
const PURPLE = "#A371F7";
const GREEN = "#3FB950";
const RED = "#F85149";

export default function Login() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/projects");
    } catch (err: any) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  }

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
        {/* Logo / Title */}
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
            {t("auth.loginTitle")}
          </h1>
          <p style={{ color: MUTED, fontSize: 13, margin: 0 }}>
            {t("auth.loginSubtitle") || "Sign in to continue"}
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
              {t("auth.emailLabel") || "Email"}
            </label>
            <input
              type="email"
              placeholder={t("auth.emailPlaceholder")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{
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
              }}
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
              style={{
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
              }}
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
              transition: "background 0.2s",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "..." : t("auth.loginButton")}
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
          {t("auth.noAccount")}{" "}
          <Link
            to="/register"
            style={{ color: PURPLE, textDecoration: "none", fontWeight: 600 }}
          >
            {t("auth.registerLink")}
          </Link>
        </p>
      </div>
    </div>
  );
}
