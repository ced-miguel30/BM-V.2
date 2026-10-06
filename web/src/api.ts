import { notifications } from '@mantine/notifications';

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function api<T = any>(url: string, opts: { method?: string; body?: unknown; form?: FormData } = {}): Promise<T> {
  const r = await fetch(`/api${url}`, {
    method: opts.method ?? (opts.body || opts.form ? 'POST' : 'GET'),
    headers: opts.body ? { 'Content-Type': 'application/json' } : undefined,
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