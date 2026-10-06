import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Anchor, Badge, Button, Chip, Drawer, FileButton, Group, Loader, NumberInput, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput, Textarea, Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { IconCamera, IconPaperclip } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera } from '../comun';
import { cantidad, euros, fecha } from '../formato';
import { Tabla } from '../Tabla';

type Doc = { documento: string; fecha: string; tipo_doc: string; proveedor: string; lineas: number; importe: number; estado: string;
  adjuntos: number; facturas: string | null; albaranes: string | null };
type Detalle = { documento: string; fecha: string; tipo_doc: string; proveedor: string; importe: number; facturas: string[]; albaranes: string[];
  lineas: { n_mov: number; producto: string; nombre: string | null; unidad: string | null; almacen: string; cantidad: number; coste_total: number; precio: number | null }[];
  adjuntos: { id: number; nombre: string; tipo: string | null; subido: string; usuario: string | null }[] };
type Prov = { nombre: string; email: string | null; telefono: string | null; contacto: string | null; dias_reparto: string | null; plazo_dias: number | null;
  pedido_minimo: number | null; notas: string | null; activo: number; documentos_90d: number; gasto_90d: number; ultimo: string | null;
  productos_90d: number; dias: number[]; dias_deducidos: number[] };

export const DIAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const ESTADO: Record<string, { label: string; color: string; ayuda: string }> = {
  facturado: { label: 'Facturado', color: 'teal', ayuda: 'Albarán con su factura registrada en BC' },
  pendiente: { label: 'Pendiente de factura', color: 'yellow', ayuda: 'Albarán aún sin facturar: BM usa el último precio conocido' },
  parcial: { label: 'Facturado en parte', color: 'orange', ayuda: 'Algunas líneas sin facturar' },
  factura: { label: 'Factura', color: 'blue', ayuda: 'Factura de compra' },
  devolucion: { label: 'Devolución', color: 'red', ayuda: 'Devolución a proveedor' },
};
const hace = (d: number) => new Date(Date.now() - d * 864e5).toISOString().slice(0, 10);

function DetalleDoc({ doc, cerrar, abrir }: { doc: string; cerrar: () => void; abrir: (d: string) => void }) {
  const [d, setD] = useState<Detalle | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const cargar = () => api<Detalle>(`/compras/${encodeURIComponent(doc)}`).then(setD).catch(avisoError);
  useEffect(() => { setD(null); cargar(); }, [doc]);
  const subir = async (f: File | null) => {
    if (!f) return;
    setSubiendo(true);
    const form = new FormData();
    form.append('archivo', f);
    try { await api(`/compras/${encodeURIComponent(doc)}/adjuntos`, { form }); avisoOk(f.name, 'Adjunto guardado'); cargar(); }
    catch (e) { avisoError(e); } finally { setSubiendo(false); }
  };
  if (!d) return <Loader />;
  const enlazados = [...d.facturas, ...d.albaranes];
  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, sm: 3 }}>
        <div><Text size="xs" c="dimmed">Proveedor</Text><Text fw={600}>{d.proveedor}</Text></div>
        <div><Text size="xs" c="dimmed">Fecha</Text><Text fw={600}>{fecha(d.fecha)}</Text></div>
        <div><Text size="xs" c="dimmed">Importe</Text><Text fw={700} fz="lg">{euros(d.importe)}</Text></div>
      </SimpleGrid>
      {enlazados.length > 0 && (
        <Group gap={6}><Text size="sm">{d.facturas.length ? 'Facturado en:' : 'Recoge los albaranes:'}</Text>
          {enlazados.map((x) => <Anchor key={x} size="sm" onClick={() => abrir(x)}>{x}</Anchor>)}</Group>
      )}
      <Table>
        <Table.Thead><Table.Tr><Table.Th>Producto</Table.Th><Table.Th>Almacén</Table.Th><Table.Th className="num">Cantidad</Table.Th><Table.Th className="num">Precio</Table.Th><Table.Th className="num">Importe</Table.Th></Table.Tr></Table.Thead>
        <Table.Tbody>
          {d.lineas.map((l) => (
            <Table.Tr key={l.n_mov}>
              <Table.Td><Text size="sm" fw={500}>{l.nombre ?? l.producto}</Text><Text size="xs" c="dimmed">{l.producto}</Text></Table.Td>
              <Table.Td><Text size="xs">{l.almacen}</Text></Table.Td>
              <Table.Td className="num">{cantidad(l.cantidad)} {l.unidad}</Table.Td>
              <Table.Td className="num">{l.precio ? euros(l.precio) : <Badge size="xs" color="yellow" variant="light">sin facturar</Badge>}</Table.Td>
              <Table.Td className="num" fw={600}>{euros(l.coste_total)}</Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
      <Group justify="space-between">
        <Text fw={600}>Papel escaneado / foto</Text>
        <FileButton onChange={subir} accept="application/pdf,image/*" capture="environment">
          {(p) => <Button {...p} size="xs" leftSection={<IconCamera size={14} />} loading={subiendo}>Adjuntar foto o PDF</Button>}
        </FileButton>
      </Group>
      {d.adjuntos.length ? d.adjuntos.map((a) => (
        <Group key={a.id} gap={8}><IconPaperclip size={14} /><Anchor href={`/api/adjuntos/${a.id}`} target="_blank" size="sm">{a.nombre}</Anchor>
          <Text size="xs" c="dimmed">{a.subido.slice(0, 16)} · {a.usuario}</Text></Group>
      )) : <Text size="sm" c="dimmed">Sin adjuntos</Text>}
      <Group justify="flex-end"><Button variant="default" onClick={cerrar}>Cerrar</Button></Group>
    </Stack>
  );
}

function FichaProveedor({ p, guardado }: { p: Prov; guardado: () => void }) {
  const [f, setF] = useState({ email: p.email ?? '', telefono: p.telefono ?? '', contacto: p.contacto ?? '', dias: (p.dias_reparto ? p.dias : []).map(String),
    plazo_dias: p.plazo_dias ?? '', pedido_minimo: p.pedido_minimo ?? '', notas: p.notas ?? '' });
  const [prods, setProds] = useState<{ producto: string; nombre: string; unidad: string | null; entregas: number; ultima: string }[] | null>(null);
  useEffect(() => { api<typeof prods>(`/proveedores/${encodeURIComponent(p.nombre)}/productos`).then(setProds).catch(avisoError); }, [p.nombre]);
  const guardar = async () => {
    try {
      await api(`/proveedores/${encodeURIComponent(p.nombre)}`, { method: 'PUT', body: {
        email: f.email || null, telefono: f.telefono || null, contacto: f.contacto || null, dias_reparto: f.dias.map(Number),
        plazo_dias: f.plazo_dias === '' ? null : Number(f.plazo_dias), pedido_minimo: f.pedido_minimo === '' ? null : Number(f.pedido_minimo),
        notas: f.notas || null, activo: true } });
      avisoOk(p.nombre, 'Proveedor guardado'); guardado();
    } catch (e) { avisoError(e); }
  };
  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, sm: 3 }}>
        <div><Text size="xs" c="dimmed">Compras 90 días</Text><Text fw={700}>{euros(p.gasto_90d)}</Text></div>
        <div><Text size="xs" c="dimmed">Entregas 90 días</Text><Text fw={700}>{p.documentos_90d}</Text></div>
        <div><Text size="xs" c="dimmed">Última</Text><Text fw={700}>{fecha(p.ultimo)}</Text></div>
      </SimpleGrid>
      <Group grow>
        <TextInput label="Correo para pedidos" value={f.email} onChange={(e) => setF({ ...f, email: e.currentTarget.value })} type="email" />
        <TextInput label="Teléfono" value={f.telefono} onChange={(e) => setF({ ...f, telefono: e.currentTarget.value })} />
      </Group>
      <TextInput label="Persona de contacto" value={f.contacto} onChange={(e) => setF({ ...f, contacto: e.currentTarget.value })} />
      <div>
        <Text size="sm" fw={500}>Días de reparto</Text>
        <Text size="xs" c="dimmed" mb={6}>Si no marcas ninguno, BM usa los deducidos de las entregas: {p.dias_deducidos.map((i) => DIAS[i]).join(', ') || 'sin datos suficientes'}</Text>
        <Chip.Group multiple value={f.dias} onChange={(x) => setF({ ...f, dias: x })}>
          <Group gap={6}>{DIAS.map((d, i) => <Chip key={d} value={String(i)} variant={p.dias_deducidos.includes(i) ? 'filled' : 'outline'}>{d}</Chip>)}</Group>
        </Chip.Group>
      </div>
      <Group grow>
        <NumberInput label="Plazo (días desde el pedido)" min={0} value={f.plazo_dias} onChange={(x) => setF({ ...f, plazo_dias: x as any })} />
        <NumberInput label="Pedido mínimo" min={0} suffix=" €" value={f.pedido_minimo} onChange={(x) => setF({ ...f, pedido_minimo: x as any })} />
      </Group>
      <Textarea label="Notas" value={f.notas} onChange={(e) => setF({ ...f, notas: e.currentTarget.value })} autosize minRows={2} />
      <Group justify="flex-end"><Button onClick={guardar}>Guardar ficha</Button></Group>
      <Text fw={600} mt="sm">Qué nos sirve (último año)</Text>
      <Tabla datos={prods} clave={(x) => x.producto} porPagina={10} columnas={[
        { clave: 'nombre', titulo: 'Producto' },
        { clave: 'entregas', titulo: 'Entregas', num: true },
        { clave: 'ultima', titulo: 'Última', render: (x) => fecha(x.ultima) },
      ]} />
    </Stack>
  );
}

export function Compras() {
  const [params, setParams] = useSearchParams();
  const doc = params.get('doc');
  const [rango, setRango] = useState<[string | null, string | null]>([hace(60), hace(0)]);
  const [prov, setProv] = useState<string | null>(null);
  const [estado, setEstado] = useState<string | null>(null);
  const [docs, setDocs] = useState<Doc[] | null>(null);
  const [provs, setProvs] = useState<Prov[] | null>(null);
  const [ficha, setFicha] = useState<Prov | null>(null);
  const cargarProvs = () => api<Prov[]>('/proveedores').then(setProvs).catch(avisoError);
  useEffect(() => {
    const [a, b] = rango;
    if (!a || !b) return;
    setDocs(null);
    api<Doc[]>(`/compras?desde=${a}&hasta=${b}${prov ? `&proveedor=${encodeURIComponent(prov)}` : ''}`).then(setDocs).catch(avisoError);
  }, [rango, prov]);
  useEffect(() => { cargarProvs(); }, []);
  const abrir = (d: string) => setParams({ doc: d });
  const visibles = (docs ?? []).filter((d) => !estado || d.estado === estado);

  return (
    <>
      <Cabecera titulo="Compras" subtitulo="Albaranes y facturas registrados en Business Central, con su papel adjunto, y fichas de proveedor" />
      <Tabs defaultValue="documentos">
        <Tabs.List mb="md"><Tabs.Tab value="documentos">Albaranes y facturas</Tabs.Tab><Tabs.Tab value="proveedores">Proveedores</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="documentos">
          <Tabla datos={docs ? visibles : null} clave={(d) => d.documento} buscar="Documento o proveedor" exportar="compras" alPulsar={(d) => abrir(d.documento)}
            anchoMin={860} vacio="Sin compras en estas fechas" filtros={<>
              <DatePickerInput type="range" value={rango} onChange={(x) => setRango([x[0] && String(x[0]).slice(0, 10), x[1] && String(x[1]).slice(0, 10)])} valueFormat="DD/MM/YY" w={200} aria-label="Fechas" />
              <Select placeholder="Proveedor" searchable clearable w={220} value={prov} onChange={setProv} data={(provs ?? []).map((p) => p.nombre)} />
              <Select placeholder="Estado" clearable w={190} value={estado} onChange={setEstado} data={Object.entries(ESTADO).map(([value, e]) => ({ value, label: e.label }))} />
            </>}
            columnas={[
              { clave: 'fecha', titulo: 'Fecha', render: (d) => fecha(d.fecha) },
              { clave: 'documento', titulo: 'Documento', render: (d) => <Group gap={6}><Text size="sm" fw={500}>{d.documento}</Text>{d.adjuntos > 0 && <IconPaperclip size={14} />}</Group> },
              { clave: 'proveedor', titulo: 'Proveedor' },
              { clave: 'lineas', titulo: 'Líneas', num: true },
              { clave: 'importe', titulo: 'Importe', num: true, render: (d) => <Text size="sm" fw={600}>{euros(d.importe)}</Text> },
              { clave: 'estado', titulo: 'Estado', valor: (d) => ESTADO[d.estado]?.label, render: (d) => (
                <Tooltip label={ESTADO[d.estado]?.ayuda}><Badge color={ESTADO[d.estado]?.color} variant="light">{ESTADO[d.estado]?.label}</Badge></Tooltip>) },
            ]} />
        </Tabs.Panel>
        <Tabs.Panel value="proveedores">
          <Tabla datos={provs} clave={(p) => p.nombre} buscar exportar="proveedores" alPulsar={setFicha} orden={{ clave: 'gasto_90d', desc: true }} anchoMin={820}
            columnas={[
              { clave: 'nombre', titulo: 'Proveedor', render: (p) => <><Text size="sm" fw={500}>{p.nombre}</Text><Text size="xs" c="dimmed">{p.email ?? p.telefono ?? 'Sin contacto'}</Text></> },
              { clave: 'dias', titulo: 'Reparto', valor: (p) => p.dias.map((i) => DIAS[i]).join(' '), render: (p) => (
                <Group gap={3}>{p.dias.length ? p.dias.map((i) => <Badge key={i} size="sm" variant={p.dias_reparto ? 'filled' : 'light'}>{DIAS[i]}</Badge>) : <Text size="xs" c="dimmed">—</Text>}</Group>) },
              { clave: 'gasto_90d', titulo: 'Compras 90 d', num: true, render: (p) => euros(p.gasto_90d) },
              { clave: 'documentos_90d', titulo: 'Entregas', num: true },
              { clave: 'ultimo', titulo: 'Última', render: (p) => fecha(p.ultimo) },
            ]} />
        </Tabs.Panel>
      </Tabs>
      <Drawer opened={!!doc} onClose={() => setParams({})} position="right" size="xl" title={doc}>
        {doc && <DetalleDoc doc={doc} cerrar={() => setParams({})} abrir={abrir} />}
      </Drawer>
      <Drawer opened={!!ficha} onClose={() => setFicha(null)} position="right" size="lg" title={ficha?.nombre}>
        {ficha && <FichaProveedor p={ficha} guardado={() => { cargarProvs(); setFicha(null); }} />}
      </Drawer>
    </>
  );
}
