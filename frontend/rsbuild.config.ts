import { defineConfig } from "@rsbuild/core";
import { pluginReact } from "@rsbuild/plugin-react";

// ── Timeout global de un paso del pipeline ─────────────────────────
//
// Es el único mando a girar: alimenta (a) la ventana de sondeo del cliente
// (`src/config/timeouts.ts`) y (b) el tiempo máximo que el proxy de desarrollo
// deja viva una request. Antes eran dos valores sueltos que se quedaban cortos
// en máquinas lentas (la segmentación de entrevistas largas tarda minutos).
//
// Override: define `VITE_STEP_TIMEOUT_MS` en el `.env` raíz (el compose lo
// pasa al contenedor del frontend). Ej.: 7200000 = 2 h.
const DEFAULT_STEP_TIMEOUT_MS = 3_600_000; // 60 min
const STEP_TIMEOUT_MS =
  Number(process.env.VITE_STEP_TIMEOUT_MS) || DEFAULT_STEP_TIMEOUT_MS;

export default defineConfig({
  plugins: [pluginReact()],
  html: {
    template: "./index.html",
  },
  source: {
    entry: { index: "./src/main.tsx" },
    define: {
      // Rsbuild no expone `import.meta.env` por defecto; sin este define el
      // override del usuario nunca llegaría al bundle.
      "import.meta.env.VITE_STEP_TIMEOUT_MS": JSON.stringify(
        String(STEP_TIMEOUT_MS),
      ),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://fastapi:8000",
        changeOrigin: true,
        proxyTimeout: STEP_TIMEOUT_MS,
        timeout: STEP_TIMEOUT_MS,
      },
    },
  },
  tools: {
    rspack: {
      // Docker Desktop en Windows no propaga los eventos de inotify a los bind
      // mounts, así que sin polling el dev server no ve los cambios guardados
      // desde el host y la UI se queda con el build viejo hasta reiniciar el
      // contenedor. El sondeo cuesta poco: sólo vigila el grafo importado.
      watchOptions: { poll: 1000, aggregateTimeout: 500 },
    },
  },
  output: {
    assetPrefix: "/",
  },
});
