import { useEffect, useState } from 'react';
import { ActionIcon, Badge, Button, Card, Checkbox, Grid, Group, NumberInput, SegmentedControl, Select, Stack, Text, TextInput, Tooltip } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconCheck, IconPlus, IconPrinter, IconTrash } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera } from '../comun';
import { nombreUbicacion, useUbicaciones } from '../centros';
import { cantidad, fecha, hoy } from '../formato';
import { imprimirEtiqueta, type DatosEtiqueta } from '../etiqueta';
import { Tabla } from '../Tabla';
import { BotonEscanear } from '../EscanearProducto';

type Cad = { id: number; producto: string; nombre: string; unidad: string | null; ubicacion: string | null; cantidad: number;
  caduca: string; dias: number; nota: string | null; usuario: string | null; estado: string; cerrado: string | null; creado: string };

const masDias = (n: number) => { const d = new Date(`${hoy()}T12:00:00`); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

function Plazo({ dias }: { dias: number }) {
  if (dias < 0) return <Badge color="red">Caducado hace {-dias} d</Badge>;
  if (dias === 0) return <Badge color="red" variant="light">Caduca hoy</Badge>;
  if (dias <= 2) return <Badge color="orange" variant="light">En {dias} d</Badge>;
  return <Badge color="gray" variant="light">En {dias} d</Badge>;
}

export function Caducidades() {
  const ubicaciones = useUbicaciones();
  const [estado, setEstado] = useState('activa');
  const [lista, setLista] = useState<Cad[] | null>(null);
  const [productos, setProductos] = useState<{ codigo: string; nombre: string; unidad: string | null }[]>([]);
  const [etiqueta, setEtiqueta] = useState(true);
  const [form, setForm] = useState({ producto: null as string | null, ubicacion: null as string | null, cantidad: 1 as number | string, caduca: null as string | null, nota: '' });

  const cargar = () => { setLista(null); api<Cad[]>(`/caducidades?estado=${estado}`).then(setLista).catch(avisoError); };
  useEffect(cargar, [estado]);
  useEffect(() => { api<{ productos: typeof productos }>('/catalogo').then((c) => setProductos(c.productos)).catch(avisoError); }, []);

  const crear = async () => {
    try {
      const r = await api<DatosEtiqueta>('/caducidades', { body: { ...form, cantidad: Number(form.cantidad), nota: form.nota || null } });
      avisoOk('Te avisaremos antes de que caduque', 'Caducidad registrada');
      if (etiqueta) imprimirEtiqueta(r, r.ubicacion ? nombreUbicacion(ubicaciones, r.ubicacion) : "");
      setForm({ ...form, producto: null, cantidad: 1, nota: '' });
      if (estado === 'activa') cargar();
    } catch (e) { avisoError(e); }
  };
  const cerrar = async (c: Cad, nuevo: 'usada' | 'merma') => {
    try {
      await api(`/caducidades/${c.id}/cerrar`, { body: { estado: nuevo } });
      avisoOk(nuevo === 'merma' ? 'Registrada como merma (coste y stock actualizados)' : 'Marcado como usado', c.nombre);
      cargar();
    } catch (e) { avisoError(e); }
  };
  const unidad = productos.find((p) => p.codigo === form.producto)?.unidad ?? '';

  return (
    <>
      <Cabecera titulo="Caducidades" subtitulo="Apunta lo que caduca pronto. Si se tira, pasa a merma automáticamente." />
      <Grid>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card>
            <Stack>
              <Text fw={600}>Nueva caducidad</Text>
              <Select label="Producto" searchable limit={60} value={form.producto} onChange={(x) => setForm({ ...form, producto: x })}
                data={productos.map((p) => ({ value: p.codigo, label: `${p.nombre} (${p.unidad ?? 'ud'})` }))} />
              <BotonEscanear productos={productos} texto="Escanear el envase" elegido={(p) => setForm((f) => ({ ...f, producto: p }))} />
              <Select label="Ubicación" searchable value={form.ubicacion} onChange={(x) => setForm({ ...form, ubicacion: x })}
                data={ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }))} />
              <Group grow>
                <NumberInput label="Cantidad" value={form.cantidad} onChange={(x) => setForm({ ...form, cantidad: x })} min={0} decimalScale={3}
                  rightSection={<Text size="xs" c="dimmed" pr={6}>{unidad}</Text>} rightSectionWidth={40} />
                <DateInput label="Caduca el" value={form.caduca} onChange={(x) => setForm({ ...form, caduca: x ? String(x).slice(0, 10) : null })} valueFormat="DD/MM/YYYY" />
              </Group>
              <Group gap={6}>
                <Text size="xs" c="dimmed">Abierto o elaborado hoy, caduca en</Text>
                {[1, 2, 3, 5].map((n) => (
                  <Button key={n} size="compact-xs" variant={form.caduca === masDias(n) ? 'filled' : 'default'} onClick={() => setForm({ ...form, caduca: masDias(n) })}>+{n} d</Button>
                ))}
              </Group>
              <TextInput label="Nota" placeholder="Lote, envase abierto…" value={form.nota} onChange={(e) => setForm({ ...form, nota: e.currentTarget.value })} />
              <Checkbox label="Imprimir etiqueta para el envase" checked={etiqueta} onChange={(e) => setEtiqueta(e.currentTarget.checked)} />
              <Button leftSection={<IconPlus size={16} />} onClick={crear} disabled={!form.producto || !form.caduca || !(Number(form.cantidad) > 0)}>Registrar</Button>
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Tabla datos={lista} clave={(c) => c.id} buscar exportar="caducidades" orden={{ clave: 'caduca' }} anchoMin={680}
            vacio={estado === 'activa' ? 'Nada pendiente de caducar' : 'Sin registros'}
            filtros={<SegmentedControl value={estado} onChange={setEstado} data={[
              { value: 'activa', label: 'Pendientes' }, { value: 'usada', label: 'Usadas' }, { value: 'merma', label: 'Tiradas' }]} />}
            columnas={[
              { clave: 'nombre', titulo: 'Producto', render: (c) => <><Text size="sm" fw={500}>{c.nombre}</Text><Text size="xs" c="dimmed">{c.nota ?? c.producto}</Text></> },
              { clave: 'ubicacion', titulo: 'Ubicación', valor: (c) => nombreUbicacion(ubicaciones, c.ubicacion) },
              { clave: 'cantidad', titulo: 'Cantidad', num: true, render: (c) => `${cantidad(c.cantidad)} ${c.unidad ?? ''}` },
              { clave: 'caduca', titulo: 'Caduca', render: (c) => <Group gap={6} wrap="nowrap"><Text size="sm">{fecha(c.caduca)}</Text>{c.estado === 'activa' && <Plazo dias={c.dias} />}</Group> },
              { clave: 'acciones', titulo: '', ordenable: false, exportar: false, render: (c) => c.estado === 'activa' ? (
                <Group gap={6} wrap="nowrap" justify="flex-end">
                  <Tooltip label="Imprimir etiqueta"><ActionIcon variant="subtle" color="gray" aria-label="Imprimir etiqueta"
                    onClick={() => imprimirEtiqueta(c, c.ubicacion ? nombreUbicacion(ubicaciones, c.ubicacion) : "")}><IconPrinter size={16} /></ActionIcon></Tooltip>
                  <Button size="compact-sm" variant="light" color="teal" leftSection={<IconCheck size={14} />} onClick={() => cerrar(c, 'usada')}>Usado</Button>
                  <Button size="compact-sm" variant="light" color="red" leftSection={<IconTrash size={14} />} onClick={() => cerrar(c, 'merma')}>Tirar</Button>
                </Group>) : <Text size="xs" c="dimmed">{c.cerrado?.slice(0, 10)}</Text> },
            ]} />
        </Grid.Col>
      </Grid>
    </>
  );
}
