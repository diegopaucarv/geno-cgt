import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useI18n } from "../i18n";

async function register(nombre: string, correo: string, password: string) {
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
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const data = await register(nombre, correo, password);
      localStorage.setItem("access_token", data.access_token);
      navigate("/projects");
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div style={{ maxWidth: 400, margin: "100px auto", padding: 24 }}>
      <h1>{t("auth.registerTitle")}</h1>
      <form onSubmit={handleSubmit}>
        <input
          placeholder={t("auth.namePlaceholder")}
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          required
          style={{ width: "100%", marginBottom: 8, padding: 8 }}
        />
        <input
          type="email"
          placeholder={t("auth.emailPlaceholder")}
          value={correo}
          onChange={(e) => setCorreo(e.target.value)}
          required
          style={{ width: "100%", marginBottom: 8, padding: 8 }}
        />
        <input
          type="password"
          placeholder={t("auth.passwordPlaceholder")}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={6}
          style={{ width: "100%", marginBottom: 8, padding: 8 }}
        />
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button type="submit" style={{ width: "100%", padding: 10 }}>
          {t("auth.registerButton")}
        </button>
      </form>
      <button
        onClick={() =>
          register("Investigador Demo", "demo@gt.com", "demo123")
            .then(() => navigate("/projects"))
            .catch((err: any) => setError(err.message))
        }
        style={{
          width: "100%",
          padding: 10,
          marginTop: 8,
          background: "#e0e0e0",
          border: "1px solid #aaa",
          cursor: "pointer",
        }}
      >
        {t("auth.demoButton")}
      </button>
      <p style={{ marginTop: 16, textAlign: "center" }}>
        {t("auth.hasAccount")} <Link to="/login">{t("auth.loginLink")}</Link>
      </p>
    </div>
  );
}
