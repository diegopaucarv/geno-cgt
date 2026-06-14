import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";

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
      <h1>GT · Crear cuenta</h1>
      <form onSubmit={handleSubmit}>
        <input
          placeholder="Nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          required
          style={{ width: "100%", marginBottom: 8, padding: 8 }}
        />
        <input
          type="email"
          placeholder="Correo"
          value={correo}
          onChange={(e) => setCorreo(e.target.value)}
          required
          style={{ width: "100%", marginBottom: 8, padding: 8 }}
        />
        <input
          type="password"
          placeholder="Contraseña"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={6}
          style={{ width: "100%", marginBottom: 8, padding: 8 }}
        />
        {error && <p style={{ color: "red" }}>{error}</p>}
        <button type="submit" style={{ width: "100%", padding: 10 }}>
          Crear cuenta
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
        🚀 Crear demo (demo@gt.com / demo123)
      </button>
      <p style={{ marginTop: 16, textAlign: "center" }}>
        ¿Ya tienes cuenta? <Link to="/login">Inicia sesión</Link>
      </p>
    </div>
  );
}
