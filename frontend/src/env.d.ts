// Rsbuild inyecta las variables públicas vía `source.define`; declaramos aquí
// el subconjunto que consumimos para que `import.meta.env` esté tipado.
interface ImportMetaEnv {
  readonly VITE_STEP_TIMEOUT_MS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Rsbuild resuelve los CSS modules a un objeto de clases; sin esta declaración
// TypeScript no encuentra el módulo (y por tanto no tipa `styles.*`).
declare module "*.module.css" {
  const classes: { readonly [key: string]: string };
  export default classes;
}
