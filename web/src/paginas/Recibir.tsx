import { useEffect, useState } from 'react';
import { Alert, Button, Card, Group, NumberInput, Select, Stack, Text, Textarea } from '@mantine/core';
import { IconArrowLeft, IconCheck, IconChecks, IconTruckDelivery } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera, Vacio } from '../comun';
import { cantidad, fecha, hoy } from '../formato';
import { BotonEscanear, type Producto } from '../EscanearProducto';
import { enviarOGuardar } from '../pendientes';

type LineaP = { producto: string; nombre: string; unidad: string | null; pedido: number; recibido: number };
type PedidoR = { id: number; proveedor: string; fecha: string; entrega: string | null; lineas: LineaP[] };
type Valor = number | string;
type Falta = { nombre: string; unidad: string | null; falta: number };

// Borrador en el móvil: si se bloquea a mitad de la descarga, no se pierde lo apuntado.
const clave = (id: number | 'sin') => `bm.recibir.${id}`;
const leer = (id: number | 'sin'): Record<string, Valor> => { try { return JSON.parse(localStorage.getItem(clave(id)) ?? '{}'); } catch { return {}; } };
const guardarBorrador = (id: number | 'sin', v: Record<string, Valor>) => {
  try { if (Object.keys(v).length) localStorage.setItem(clave(id), JSON.stringify(v)); else localStorage.removeItem(clave(id)); } catch { /* sin almacenamiento */ }
};

// Llega el proveedor: se escanea lo que descarga y BM dice en el momento qué falta respecto al pedido.
// No mueve stock (la compra la registra Noray con el albarán); BM luego comprueba que el albarán no cobre lo que no llegó.
export function Recibir() {
  const [datos, setDatos] = useState<{ pedidos: PedidoR[]; proveedores: string[] } | null>(null);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [sel, setSel] = useState<PedidoR | 'sin' | null>(null);
  const [proveedor, setProveedor] = useState<string | null>(null);
  const [llegado, setLlegadoEstado] = useState<Record<string, Valor>>({});
  const [nota, setNota] = useState('');
  const [faltas, setFaltas] = useState<Falta[] | null>(null);
  const [guardando, setGuardando] = useState(false);

  const cargar = () => api<typeof datos>('/recepcion/pedidos').then(setDatos).catch(avisoError);
  useEffect(() => { cargar(); api<{ productos: Producto[] }>('/catalogo').then((c) => setProductos(c.productos)).catch(() => null); }, []);

  const id = sel === 'sin' ? 'sin' : sel?.id ?? 'sin';
  const setLlegado = (v: Record<string, Valor>) => { setLlegadoEstado(v); guardarBorrador(id, v); };
  const abrir = (p: PedidoR | 'sin') => { setSel(p); setFaltas(null); setNota(''); setProveedor(null); setLlegadoEstado(leer(p === 'sin' ? 'sin' : p.id)); };
  const lineas: LineaP[] = sel === null ? [] : [
    ...(sel === 'sin' ? [] : sel.lineas),
    ...Object.keys(llegado).filter((p) => sel === 'sin' || !sel.lineas.some((l) => l.producto === p)).map((p) => {
      const x = productos.find((c) => c.codigo === p);
      return { producto: p, nombre: x?.nombre ?? p, unidad: x?.unidad ?? null, pedido: 0, recibido: 0 };
    }),
  ];
  const pendiente = (l: LineaP) => Math.max(l.pedido - l.recibido, 0);
  const anadir = (p: string) => {
    if (llegado[p] === undefined) setLlegado({ ...llegado, [p]: '' });
    setTimeout(() => document.getElementById(`rec-${p}`)?.focus(), 150);
  };
  const todo = () => setLlegado(Object.fromEntries(lineas.map((l) => [l.producto, llegado[l.producto] !== undefined && llegado[l.producto] !== '' ? llegado[l.producto] : pendiente(l)])));

  const guardar = async () => {
    const prov = sel === 'sin' ? proveedor : sel?.proveedor;
    if (!sel || !prov) return;
    setGuardando(true);
    try {
      const r = await enviarOGuardar('/recepciones', {
        pedido_id: sel === 'sin' ? null : sel.id, proveedor: prov, fecha: hoy(), nota: nota || null,
        lineas: Object.entries(llegado).filter(([, v]) => v !== '').map(([producto, v]) => ({ producto, cantidad: Number(v) })),
      }, `Recepción de ${prov}`);
      // Lo que falta se calcula aquí mismo: así se sabe en la puerta aunque no haya cobertura.
      setFaltas(lineas.map((l) => ({ nombre: l.nombre, unidad: l.unidad, falta: Math.round((pendiente(l) - Number(llegado[l.producto] || 0)) * 1000) / 1000 }))
        .filter((f) => f.falta > 1e-6));
      if (r === 'en cola') avisoOk('Sin cobertura: se enviará solo al volver la conexión', 'Recepción guardada en el móvil');
      setLlegado({});
      cargar();
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };

  if (faltas) return (
    <>
      <Cabecera titulo="Recepción guardada" subtitulo={sel === 'sin' ? proveedor ?? '' : sel?.proveedor ?? ''} />
      {faltas.length ? (
        <Alert color="orange" title={faltas.length === 1 ? "Falta 1 producto del pedido" : `Faltan ${faltas.length} productos del pedido`} mb="md">
          <Stack gap={2}>{faltas.map((f) => <Text key={f.nombre} size="sm">{f.nombre}: faltan <b>{cantidad(f.falta)} {f.unidad ?? ''}</b></Text>)}</Stack>
          <Text size="sm" mt="xs">Díselo al repartidor y que lo anote en el albarán. BM avisará si Noray registra más de lo que ha llegado.</Text>
        </Alert>
      ) : <Alert color="teal" icon={<IconCheck />} title="Ha llegado todo lo pedido" mb="md">Nada que reclamar.</Alert>}
      <Button onClick={() => { setSel(null); setFaltas(null); }}>Terminar</Button>
    </>
  );

  if (!sel) return (
    <>
      <Cabecera titulo="Recibir mercancía" subtitulo="Escanea lo que descarga el proveedor: BM te dice en el momento si falta algo del pedido" />
      {!datos ? <Text c="dimmed">Cargando…</Text> : (
        <Stack>
          {!datos.pedidos.length && <Card><Vacio texto="No hay pedidos pendientes de llegar" /></Card>}
          {datos.pedidos.map((p) => (
            <Card key={p.id} p="md">
              <Group justify="space-between" wrap="nowrap">
                <div>
                  <Text fw={600}>{p.proveedor}</Text>
                  <Text size="sm" c="dimmed">Pedido el {fecha(p.fecha)}{p.entrega ? ` · llega ${fecha(p.entrega)}` : ''} · {p.lineas.length} productos</Text>
                </div>
                <Button leftSection={<IconTruckDelivery size={18} />} onClick={() => abrir(p)}>Recibir</Button>
              </Group>
            </Card>
          ))}
          <Button variant="default" onClick={() => abrir('sin')}>Llega algo sin pedido</Button>
        </Stack>
      )}
    </>
  );

  return (
    <>
      <Cabecera titulo={sel === 'sin' ? 'Recibir sin pedido' : sel.proveedor} subtitulo="Escribe lo que ha llegado de cada producto">
        <Button variant="default" leftSection={<IconArrowLeft size={16} />} onClick={() => setSel(null)}>Volver</Button>
      </Cabecera>
      <Stack pb={80}>
        {sel === 'sin' && <Select label="Proveedor" searchable value={proveedor} onChange={setProveedor} data={datos?.proveedores ?? []} />}
        <Group wrap="wrap">
          <BotonEscanear productos={productos} texto="Escanear lo que llega" elegido={anadir} />
          {sel !== 'sin' && <Button variant="light" color="teal" leftSection={<IconChecks size={18} />} onClick={todo}>Ha llegado todo</Button>}
          <Select placeholder="Añadir otro producto" searchable limit={50} value={null} onChange={(p) => p && anadir(p)} style={{ flex: 1, minWidth: 200 }}
            data={productos.map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.unidad ?? 'ud'})` }))} />
        </Group>
        {!lineas.length && <Card><Vacio texto="Escanea o añade lo que ha llegado" /></Card>}
        {lineas.map((l) => {
          const v = llegado[l.producto];
          const ok = v !== undefined && v !== '' && Number(v) >= pendiente(l) * 0.98;
          return (
            <Card key={l.producto} p="sm" withBorder style={{ borderColor: v === undefined || v === '' ? undefined : ok ? 'var(--mantine-color-teal-5)' : 'var(--mantine-color-orange-5)' }}>
              <Group justify="space-between" wrap="nowrap">
                <div style={{ minWidth: 0 }}>
                  <Text fw={500} lh={1.25}>{l.nombre}</Text>
                  <Text size="xs" c="dimmed">{l.pedido ? `Pedido ${cantidad(l.pedido)} ${l.unidad ?? ''}${l.recibido ? ` · ya llegó ${cantidad(l.recibido)}` : ''}` : 'Sin pedir'}</Text>
                </div>
                <NumberInput id={`rec-${l.producto}`} value={v ?? ''} onChange={(x) => setLlegado({ ...llegado, [l.producto]: x })} min={0} decimalScale={3}
                  w={130} style={{ flex: '0 0 130px' }} size="md" placeholder="—" hideControls aria-label={`Ha llegado de ${l.nombre}`}
                  rightSection={<Text size="xs" c="dimmed" pr={6}>{l.unidad}</Text>} rightSectionWidth={44} />
              </Group>
            </Card>
          );
        })}
        <Textarea label="Nota (opcional)" placeholder="Producto en mal estado, cambio de marca…" value={nota} onChange={(e) => setNota(e.currentTarget.value)} autosize minRows={2} />
        <Button size="lg" leftSection={<IconCheck size={20} />} onClick={guardar} loading={guardando}
          disabled={!Object.values(llegado).some((x) => x !== '') || (sel === 'sin' && !proveedor)}>Guardar recepción</Button>
      </Stack>
    </>
  );
}
