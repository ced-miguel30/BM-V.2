import { useEffect, useState } from 'react';
import { ActionIcon, Alert, Badge, Button, Card, Grid, Group, NumberInput, Select, Stack, Table, Text, TextInput } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconArrowRight, IconInfoCircle, IconPlus, IconTrash } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera } from '../comun';
import { nombreUbicacion, useUbicaciones } from '../centros';
import { fecha, hoy } from '../formato';
import { Tabla } from '../Tabla';

type T = { id: number; fecha: string; origen: string; destino: string; nota: string | null; usuario: string | null; anulado: number; n_productos: number };
type Prod = { codigo: string; nombre: string; unidad: string | null };

export function Traslados() {
  const ubicaciones = useUbicaciones();
  const [datos, setDatos] = useState<{ traslados_en: string; lista: T[] } | null>(null);
  const [productos, setProductos] = useState<Prod[]>([]);
  const [f, setF] = useState({ fecha: hoy(), origen: 'ECONOMATO' as string | null, destino: null as string | null, nota: '' });
  const [items, setItems] = useState<{ producto: string | null; cantidad: number | string }[]>([{ producto: null, cantidad: '' }]);
  const [guardando, setGuardando] = useState(false);

  const cargar = () => api<typeof datos>('/traslados').then(setDatos).catch(avisoError);
  useEffect(() => { cargar(); api<{ productos: Prod[] }>('/catalogo').then((c) => setProductos(c.productos)).catch(avisoError); }, []);

  const guardar = async () => {
    setGuardando(true);
    try {
      await api('/traslados', { body: { ...f, nota: f.nota || null, items: items.filter((i) => i.producto && Number(i.cantidad) > 0).map((i) => ({ producto: i.producto, cantidad: Number(i.cantidad) })) } });
      avisoOk(`${nombreUbicacion(ubicaciones, f.origen)} → ${nombreUbicacion(ubicaciones, f.destino)}`, 'Traslado registrado');
      setItems([{ producto: null, cantidad: '' }]); setF({ ...f, nota: '' }); cargar();
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };
  const ubOpts = ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }));
  const enBc = datos?.traslados_en === 'bc';
  const validos = items.filter((i) => i.producto && Number(i.cantidad) > 0).length;

  return (
    <>
      <Cabecera titulo="Traslados" subtitulo="Mover producto entre ubicaciones. No es consumo: el stock total del hotel no cambia." />
      {enBc && (
        <Alert icon={<IconInfoCircle />} color="blue" mb="lg" title="Ahora mismo los traslados se hacen en Business Central">
          BM los importa con los movimientos de BC para no registrarlos dos veces. Cuando el hotel decida hacerlos en BM, se activa en Configuración.
        </Alert>
      )}
      <Grid>
        {!enBc && (
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <Card>
              <Stack>
                <DateInput label="Fecha" value={f.fecha} onChange={(x) => x && setF({ ...f, fecha: String(x).slice(0, 10) })} valueFormat="DD/MM/YYYY" maxDate={new Date()} />
                <Group grow align="flex-end" wrap="nowrap">
                  <Select label="Desde" data={ubOpts} value={f.origen} onChange={(x) => setF({ ...f, origen: x })} searchable />
                  <IconArrowRight style={{ flex: '0 0 20px', marginBottom: 8 }} />
                  <Select label="Hacia" data={ubOpts.filter((u) => u.value !== f.origen)} value={f.destino} onChange={(x) => setF({ ...f, destino: x })} searchable />
                </Group>
                <Table>
                  <Table.Tbody>
                    {items.map((it, i) => (
                      <Table.Tr key={i}>
                        <Table.Td pl={0}><Select searchable limit={50} placeholder="Producto" value={it.producto}
                          data={productos.map((p) => ({ value: p.codigo, label: `${p.nombre} (${p.unidad ?? 'ud'})` }))}
                          onChange={(x) => setItems(items.map((y, j) => (j === i ? { ...y, producto: x } : y)))} /></Table.Td>
                        <Table.Td w={110}><NumberInput placeholder="Cant." value={it.cantidad} min={0} decimalScale={3} hideControls
                          onChange={(x) => setItems(items.map((y, j) => (j === i ? { ...y, cantidad: x } : y)))} /></Table.Td>
                        <Table.Td w={36} pr={0}><ActionIcon variant="subtle" color="red" aria-label="Quitar" onClick={() => setItems(items.filter((_, j) => j !== i))}><IconTrash size={16} /></ActionIcon></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
                <Button variant="light" leftSection={<IconPlus size={16} />} onClick={() => setItems([...items, { producto: null, cantidad: '' }])}>Otra línea</Button>
                <TextInput label="Nota" value={f.nota} onChange={(e) => setF({ ...f, nota: e.currentTarget.value })} />
                <Button onClick={guardar} loading={guardando} disabled={!f.origen || !f.destino || !validos}>Registrar traslado ({validos})</Button>
              </Stack>
            </Card>
          </Grid.Col>
        )}
        <Grid.Col span={{ base: 12, lg: enBc ? 12 : 7 }}>
          <Tabla datos={datos?.lista ?? null} clave={(t) => t.id} exportar="traslados" orden={{ clave: 'fecha', desc: true }} atenuar={(t) => !!t.anulado}
            vacio="No hay traslados registrados en BM"
            columnas={[
              { clave: 'fecha', titulo: 'Fecha', render: (t) => fecha(t.fecha) },
              { clave: 'origen', titulo: 'Desde', valor: (t) => nombreUbicacion(ubicaciones, t.origen) },
              { clave: 'destino', titulo: 'Hacia', valor: (t) => nombreUbicacion(ubicaciones, t.destino) },
              { clave: 'n_productos', titulo: 'Productos', num: true },
              { clave: 'usuario', titulo: 'Por' },
              { clave: 'anulado', titulo: '', valor: (t) => (t.anulado ? 'Anulado' : ''), render: (t) => (t.anulado ? <Badge color="gray">Anulado</Badge> : null) },
            ]} />
        </Grid.Col>
      </Grid>
    </>
  );
}
