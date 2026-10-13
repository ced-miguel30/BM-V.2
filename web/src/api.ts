import { notifications } from '@mantine/notifications';

export const verComo = (): string | null => { try { return localStorage.getItem('bm.verComo'); } catch { return null; } };

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(url: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const headers: Record<string, string> = opts.body ? { 'Content-Type': 'application/json' } : {};
  const como = verComo();
  if (como) headers['X-Ver-Como'] = como;  // el dueño viendo BM como otro perfil (el servidor solo lo acepta del dueño)
  const r = await fetch(`/api${url}`, {
    method: opts.method ?? (opts.body || opts.form ? 'POST' : 'GET'),
    headers,
    body: opts.form ?? (opts.body ? JSON.stringify(opts.body) : undefined),
    credentials: 'same-origin',
  });
  if (!r.ok) {
    let msg = r.statusText;
    try { const j = await r.json(); msg = typeof j.detail === 'string' ? j.detail : 'Datos no válidos'; } catch { /* sin cuerpo */ }
    if (r.status === 401 && url !== '/login' && url !== '/me') window.dispatchEvent(new Event('bm:401'));
    throw new ApiError(r.status, msg);
  }
  return r.json();
}

export function avisoError(e: unknown) {
  notifications.show({ color: 'red', title: 'No se pudo completar', message: e instanceof Error ? e.message : String(e) });
}

export function avisoOk(message: string, title = 'Hecho') {
  notifications.show({ color: 'teal', title, message });
}