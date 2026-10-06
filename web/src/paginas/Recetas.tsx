import { useEffect, useState } from 'react';
import {
  ActionIcon, Badge, Button, Drawer, Group, List, NumberInput, SegmentedControl, Select, Stack, Switch, Table, Text, TextInput, Tooltip,
} from '@mantine/core';
import { IconAlertTriangle, IconPlus, IconSearch, IconTrash } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { BadgeServicio, Cabecera } from '../comun';
import { cantidad, euros } from '../formato';
import { useCentros } from '../centros';
import { Tabla } from '../Tabla';

type Resumen = { id: string; nombre: string; servicio: string | null; porciones: number; activo: number; coste_racion: number; completo: boolean; n_ingredientes: number };
type Linea = { producto: string; nombre?: string; unidad?: string | null; cantidad: number; precio?: number | null; coste?: number | null };
type Receta = Omit<Resumen, 'n_ingredientes'> & { lineas: Linea[]; coste_total: number };
type Producto = { codigo: string; nombre: string; unidad: string | null };

const NUEVA: Receta = { id: '', nombre: '', servicio: 'comida', porciones: 1, activo: 1, coste_racion: 0, coste_total: 0, completo: true, lineas: [] };

export function Recetas() {
  const [lista, setLista] = useState<Resumen[] | null>(null);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [q, setQ] = useState('');
  const [ed, setEd] = useState<Receta | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [vista, setVista] = useState('todas');
  const [fichas, setFichas] = useState<{ id: string; nombre: string; servicio: string | null; coste_racion: number; pvp: number | null; problemas: string[]; avisos: string[] }[] | null>(null);
  const servicios = useCentros().filter((c) => c.tipo === 'restauracion').map((c) => ({ value: c.codigo, label: c.nombre }));

  const cargar = () => { api<Resumen[]>('/recetas').then(setLista).catch(avisoError); api<NonNullable<typeof fichas>>('/analisis/fichas').then(setFichas).catch(avisoError); };
  useEffect(() => { cargar(); api<{ productos: Producto[] }>('/catalogo').then((c) => setProductos(c.productos)).catch(avisoError); }, []);

  const abrir = (id: string) => api<Receta>(`/recetas/${id}`).then(setEd).catch(avisoError);
  const linea = (i: number, cambio: Partial<Linea>) => setEd((r) => r && { ...r, lineas: r.lineas.map((l, j) => (j === i ? { ...l, ...cambio, coste: undefined } : l)) });

  const guardar = async () => {
    if (!ed) return;
    setGuardando(true);
    try {
      const body = { nombre: ed.nombre, servicio: ed.servicio, porciones: ed.porciones, activo: !!ed.activo,
        lineas: ed.lineas.filter((l) => l.producto && l.cantidad > 0).map((l) => ({ producto: l.producto, cantidad: l.cantidad })) };
      const r = await api<{ id: string }>(ed.id ? `/recetas/${ed.id}` : '/recetas', { method: ed.id ? 'PUT' : 'POST', body });
      avisoOk('Costes y consumos TPV recalculados', 'Receta guardada');
      abrir(r.id);
      cargar();
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };

  const visibles = (lista ?? []).filter((r) => !q || r.nombre.toLowerCase().includes(q.toLowerCase()));

  return (
    <>
      <Cabecera titulo="Recetas" subtitulo="Coste teórico con el precio de la última compra en BC">
        <SegmentedControl value={vista} onChange={setVista} data={[{ value: 'todas', label: 'Todas' },
          { value: 'revisar', label: `A revisar (${fichas?.filter((f) => f.problemas.length).length ?? '…'})` }, { value: 'avisos', label: `Avisos (${fichas?.filter((f) => !f.problemas.length && f.avisos.length).length ?? '…'})` }]} />
        <TextInput leftSection={<IconSearch size={16} />} placeholder="Buscar receta" value={q} onChange={(e) => setQ(e.currentTarget.value)} w={220} />
        <Button leftSection={<IconPlus size={16} />} onClick={() => setEd({ ...NUEVA, lineas: [] })}>Nueva receta</Button>
      </Cabecera>
      {vista !== 'todas' ? (
        <Tabla datos={fichas ? fichas.filter((f) => (vista === 'revisar' ? f.problemas.length : !f.problemas.length && f.avisos.length) && (!q || f.nombre.toLowerCase().includes(q.toLowerCase()))) : null}
          clave={(f) => f.id} alPulsar={(f) => abrir(f.id)} exportar="fichas_a_revisar" vacio="Ninguna ficha con problemas" anchoMin={760}
          columnas={[
            { clave: 'nombre', titulo: 'Receta', render: (f) => <Text size="sm" fw={500}>{f.nombre}</Text> },
            { clave: 'servicio', titulo: 'Servicio', render: (f) => <BadgeServicio valor={f.servicio} /> },
            { clave: 'problemas', titulo: 'Qué revisar', valor: (f) => [...f.problemas, ...f.avisos].join('; '), render: (f) => (
              <List size="sm" spacing={2}>{[...f.problemas, ...f.avisos].map((x) => <List.Item key={x}><Text size="sm" c={f.problemas.includes(x) ? 'red' : 'dimmed'}>{x}</Text></List.Item>)}</List>) },
            { clave: 'coste_racion', titulo: 'Coste / ración', num: true, render: (f) => euros(f.coste_racion) },
            { clave: 'pvp', titulo: 'PVP', num: true, render: (f) => euros(f.pvp) },
          ]} />
      ) : (
      <Tabla datos={lista ? visibles : null} clave={(r) => r.id} alPulsar={(r) => abrir(r.id)} atenuar={(r) => !r.activo} exportar="recetas"
        orden={{ clave: 'nombre' }} vacio="Sin recetas"
        columnas={[
          { clave: 'nombre', titulo: 'Receta', render: (r) => <Group gap={6}><Text size="sm" fw={500}>{r.nombre}</Text>{!r.activo && <Badge size="xs" color="gray">Inactiva</Badge>}</Group> },
          { clave: 'servicio', titulo: 'Servicio', render: (r) => <BadgeServicio valor={r.servicio} /> },
          { clave: 'porciones', titulo: 'Raciones', num: true },
          { clave: 'n_ingredientes', titulo: 'Ingredientes', num: true },
          { clave: 'coste_racion', titulo: 'Coste / ración', num: true, render: (r) => (
            <Group gap={4} justify="flex-end" wrap="nowrap">
              {!r.completo && <Tooltip label="Algún ingrediente sin precio en BC"><IconAlertTriangle size={14} color="orange" /></Tooltip>}
              <Text size="sm" fw={600}>{euros(r.coste_racion)}</Text>
            </Group>) },
        ]} />
      )}

      <Drawer opened={!!ed} onClose={() => setEd(null)} position="right" size="xl" title={ed?.id ? ed.nombre : 'Nueva receta'}>
        {ed && (
          <Stack>
            <TextInput label="Nombre" value={ed.nombre} onChange={(e) => setEd({ ...ed, nombre: e.currentTarget.value })} required />
            <Group grow>
              <Select label="Servicio" data={servicios} value={ed.servicio} onChange={(x) => setEd({ ...ed, servicio: x })} />
              <NumberInput label="Raciones que salen" value={ed.porciones} min={0.01} decimalScale={2} onChange={(x) => setEd({ ...ed, porciones: Number(x) || 1 })} />
            </Group>
            <Switch label="Activa (aparece al registrar)" checked={!!ed.activo} onChange={(e) => setEd({ ...ed, activo: e.currentTarget.checked ? 1 : 0 })} />
            <Text fw={600} mt="sm">Ingredientes (para todas las raciones)</Text>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Producto</Table.Th><Table.Th w={130}>Cantidad</Table.Th><Table.Th className="num">Precio</Table.Th><Table.Th className="num">Coste</Table.Th><Table.Th w={36} /></Table.Tr></Table.Thead>
              <Table.Tbody>
                {ed.lineas.map((l, i) => (
                  <Table.Tr key={i}>
                    <Table.Td miw={220}>
                      <Select searchable limit={60} value={l.producto || null} placeholder="Producto"
                        data={productos.map((p) => ({ value: p.codigo, label: `${p.nombre} (${p.unidad ?? 'ud'})` }))}
                        onChange={(x) => linea(i, { producto: x ?? '', unidad: productos.find((p) => p.codigo === x)?.unidad, precio: undefined })} />
                    </Table.Td>
                    <Table.Td><NumberInput value={l.cantidad} min={0} decimalScale={4} onChange={(x) => linea(i, { cantidad: Number(x) || 0 })} rightSection={<Text size="xs" c="dimmed">{l.unidad}</Text>} /></Table.Td>
                    <Table.Td className="num">{l.precio === undefined ? '…' : euros(l.precio)}</Table.Td>
                    <Table.Td className="num">{l.coste === undefined ? '…' : euros(l.coste)}</Table.Td>
                    <Table.Td><ActionIcon variant="subtle" color="red" onClick={() => setEd({ ...ed, lineas: ed.lineas.filter((_, j) => j !== i) })} aria-label="Quitar"><IconTrash size={16} /></ActionIcon></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Button variant="light" leftSection={<IconPlus size={16} />} onClick={() => setEd({ ...ed, lineas: [...ed.lineas, { producto: '', cantidad: 0 }] })}>Añadir ingrediente</Button>
            {ed.id && (
              <Group justify="space-between" p="sm" bg="var(--mantine-color-default-hover)" style={{ borderRadius: 8 }}>
                <Text size="sm">Total {euros(ed.coste_total)} · {cantidad(ed.porciones)} raciones</Text>
                <Text fw={700}>{euros(ed.coste_racion)} / ración</Text>
              </Group>
            )}
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setEd(null)}>Cerrar</Button>
              <Button onClick={guardar} loading={guardando} disabled={!ed.nombre.trim()}>Guardar</Button>
            </Group>
          </Stack>
        )}
      </Drawer>
    </>
  );
}
