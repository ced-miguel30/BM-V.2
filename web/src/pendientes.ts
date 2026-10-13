import { api, ApiError, avisoOk } from './api';

// Envíos hechos sin cobertura (cámaras, almacén): quedan en este dispositivo y se mandan solos al volver la conexión.
// Cada envío lleva un `ref` propio: si llega dos veces, el servidor lo guarda una sola.
export type Pendiente = { ref: string; ruta: string; body: Record<string, unknown>; texto: string; error?: string };
const CLAVE = 'bm.pendientes';

export const pendientes = (): Pendiente[] => {
  try { return JSON.parse(localStorage.getItem(CLAVE) ?? '[]'); } catch { return []; }
};
const guardar = (xs: Pendiente[]) => {
  try { localStorage.setItem(CLAVE, JSON.stringify(xs)); } catch { /* sin almacenamiento */ }
  window.dispatchEvent(new Event('bm:pendientes'));
};
const nuevoRef = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);

/** Envía ya; sin conexión lo deja en cola. Un error de datos (no de red) se lanza como siempre. */
export async function enviarOGuardar(ruta: string, body: Record<string, unknown>, texto: string): Promise<'enviado' | 'en cola'> {
  const x: Pendiente = { ref: nuevoRef(), ruta, body, texto };
  x.body = { ...body, ref: x.ref };
  try { await api(ruta, { body: x.body }); return 'enviado'; } catch (e) {
    if (e instanceof ApiError) throw e;
    guardar([...pendientes(), x]);
    return 'en cola';
  }
}

export const descartar = (ref: string) => guardar(pendientes().filter((p) => p.ref !== ref));

let enviando = false;
export async function sincronizar() {
  if (enviando) return;
  enviando = true;
  try {
    for (const x of pendientes()) {
      if (x.error) continue;  // rechazado por el servidor: lo decide la persona (ver o descartar)
      try {
        await api(x.ruta, { body: x.body });
        descartar(x.ref);
        avisoOk(x.texto, 'Enviado al volver la conexión');
      } catch (e) {
        if (!(e instanceof ApiError) || e.status === 401) return;  // sigue sin red o sin sesión: otra vez luego
        guardar(pendientes().map((p) => (p.ref === x.ref ? { ...p, error: e.message } : p)));
      }
    }
  } finally { enviando = false; }
}
