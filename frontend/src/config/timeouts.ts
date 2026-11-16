// ── Timeouts globales de los pasos del pipeline ────────────────────
//
// El worker no impone `task_time_limit`, así que el único techo real era la
// ventana de sondeo del cliente: 6 minutos fijos por paso, que en una máquina
// lenta se queda corta (la segmentación con worker-nlp tarda varios minutos en
// entrevistas largas).
//
// El valor vive ahora en `rsbuild.config.ts`, que lo inyecta aquí y además lo
// aplica al proxy de desarrollo. Se configura con `VITE_STEP_TIMEOUT_MS` en el
// `.env` raíz (el compose lo pasa al contenedor) y su default es 60 min.
//
// Debe quedar siempre en paridad con `DEFAULT_STEP_TIMEOUT_MS` del config.
const DEFAULT_STEP_TIMEOUT_MS = 3_600_000; // 60 min

const configured = Number(import.meta.env.VITE_STEP_TIMEOUT_MS);

/** Espera máxima de un paso (encolado incluido) antes de declararlo timeout. */
export const STEP_TIMEOUT_MS =
  Number.isFinite(configured) && configured > 0
    ? configured
    : DEFAULT_STEP_TIMEOUT_MS;

/** El mismo valor en minutos, para los mensajes al usuario. */
export const STEP_TIMEOUT_MINUTES = Math.round(STEP_TIMEOUT_MS / 60_000);
