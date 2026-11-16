// Rsbuild inyecta las variables públicas vía `source.define`; declaramos aquí
// el subconjunto que consumimos para que `import.meta.env` esté tipado.
interface ImportMetaEnv {
  readonly VITE_STEP_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
