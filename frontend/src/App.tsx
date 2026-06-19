import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
} from "react-router-dom";
import { useState } from "react";
import Login from "./pages/Login";
import Projects from "./pages/Projects";
import ProjectDetail from "./pages/Project";
import PlaygroundPage from "./pages/Playground";
import Register from "./pages/Register";
import Setup from "./pages/Setup";
import ConfigModal, { ConfigButton } from "./components/ConfigModal";

/** Layout que envuelve las vistas principales con el botón de configuración */
function MainLayout() {
  const [configOpen, setConfigOpen] = useState(false);

  return (
    <>
      <Outlet />
      <ConfigButton onClick={() => setConfigOpen(true)} />
      <ConfigModal open={configOpen} onClose={() => setConfigOpen(false)} />
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div style={{ minHeight: "100vh", background: "#0D1117" }}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          {/* Vistas principales con config persistente */}
          <Route element={<MainLayout />}>
            <Route path="/setup" element={<Setup />} />
            <Route path="/projects" element={<Projects />} />
            <Route path="/projects/:id" element={<ProjectDetail />} />
            <Route path="/projects/:id/theory" element={<PlaygroundPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}
