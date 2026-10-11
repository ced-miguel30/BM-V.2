// Etiqueta de caducidad (60 × 40 mm) impresa desde el navegador con un marco oculto: sin ventanas emergentes.
export type DatosEtiqueta = { id: number; nombre: string; cantidad: number; unidad: string | null; caduca: string;
  ubicacion: string | null; usuario: string | null; creado: string };

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!));
const dia = (iso: string) => new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString('es-ES', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' });

export function imprimirEtiqueta(e: DatosEtiqueta, ubicacion?: string) {
  const creado = new Date(e.creado.includes('T') || e.creado.endsWith('Z') ? e.creado : `${e.creado.replace(' ', 'T')}Z`);  // BD en UTC
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Etiqueta</title><style>
    @page { size: 60mm 40mm; margin: 0 }
    body { margin: 0; font-family: Arial, sans-serif; }
    .e { width: 60mm; height: 40mm; box-sizing: border-box; padding: 2.5mm 3mm; display: flex; flex-direction: column; justify-content: space-between; }
    .p { font-weight: 700; font-size: 11pt; line-height: 1.1; max-height: 2.3em; overflow: hidden; }
    .c { font-size: 7.5pt; color: #333; }
    .k { border: 1.5pt solid #000; padding: 1mm 2mm; }
    .k small { display: block; font-size: 7pt; letter-spacing: .5pt; }
    .k b { font-size: 14pt; }
    .f { display: flex; justify-content: space-between; font-size: 7pt; color: #333; }
  </style></head><body><div class="e">
    <div class="p">${esc(e.nombre)}</div>
    <div class="c">${esc(String(e.cantidad).replace('.', ','))} ${esc(e.unidad ?? '')} · abierto/elaborado ${creado.toLocaleString('es-ES', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</div>
    <div class="k"><small>CONSUMIR ANTES DE</small><b>${esc(dia(e.caduca))}</b></div>
    <div class="f"><span>${esc(ubicacion ?? e.ubicacion ?? '')}</span><span>${esc(e.usuario ?? '')} · #${e.id}</span></div>
  </div></body></html>`;
  const marco = document.createElement('iframe');
  marco.style.cssText = 'position:fixed;width:0;height:0;border:0;right:0;bottom:0';
  document.body.appendChild(marco);
  const doc = marco.contentDocument!;
  doc.open(); doc.write(html); doc.close();
  setTimeout(() => { marco.contentWindow!.focus(); marco.contentWindow!.print(); setTimeout(() => marco.remove(), 1000); }, 100);
}
