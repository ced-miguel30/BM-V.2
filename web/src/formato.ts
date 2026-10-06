const eur = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR' });
const num = new Intl.NumberFormat('es-ES', { maximumFractionDigits: 3 });

export const euros = (v: number | null | undefined) => (v == null ? '—' : eur.format(v));
export const cantidad = (v: number | null | undefined) => (v == null ? '—' : num.format(v));
export const fecha = (iso: string | null | undefined) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
export const fechaCorta = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
export const hoy = () => new Date().toISOString().slice(0, 10);

export const SERVICIOS = [
  { value: 'desayuno', label: 'Desayuno', color: 'orange' },
  { value: 'comida', label: 'Comida', color: 'teal' },
  { value: 'cena', label: 'Cena', color: 'indigo' },
  { value: 'bebidas', label: 'Bebidas', color: 'grape' },
] as const;
export const servicio = (v: string | null | undefined) => SERVICIOS.find((s) => s.value === v);

export const ESTADOS: Record<string, { label: string; color: string; ayuda: string }> = {
  fifo: { label: 'Real', color: 'teal', ayuda: 'Coste sacado de albaranes facturados (FIFO)' },
  provisional: { label: 'Provisional', color: 'yellow', ayuda: 'Algún albarán aún sin facturar: último precio facturado' },
  sin_stock: { label: 'Sin lote', color: 'orange', ayuda: 'No quedaban lotes en BC: último precio conocido' },
  sin_precio: { label: 'Sin precio', color: 'red', ayuda: 'Producto sin compras ni coste en BC' },
};
export const ESTADO_POR_NIVEL = ['fifo', 'provisional', 'sin_stock', 'sin_precio'];