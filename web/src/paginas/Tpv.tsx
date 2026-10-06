import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Badge, Button, Card, FileButton, Group, Loader, Modal, NumberInput, SegmentedControl, Select, Stack, Table, Text, TextInput,
} from '@mantine/core';
import { IconFileTypePdf, IconSearch } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { BadgeServicio, Cabecera, Vacio } from '../comun';
import { SERVICIOS, euros } from '../formato';

type Articulo = {
  codigo: string; nombre: string; categoria: string | null; servicio: string; receta_id: string | null; producto: string | null;
  factor: number; precio: number | null; ignorar: number; receta: string | null; producto_nombre: string | null;
  producto_unidad: string | null; importe: number; dias: number;
};
type Catalogo = { recetas: { id: string; nombre: string }[]; productos: { codigo: string; nombre: string; unidad: string | null }[] };

const estadoDe = (a: Articulo) => (a.ignorar ? 'ignorado' : a.receta_id || a.producto ? 'asignado' : 'pendiente');

export function Tpv() {
  const [arts, setArts] = useState<Articulo[] | null>(null);
  const [cat, setCat] = useState<Catalogo | null>(null);
  const [filtro, setFiltro] = useState('pendiente');
  const [q, setQ] = useState('');
  const [subiendo, setSubiendo] = useState(false);
  const [ed, setEd] = useState<Articulo | null>(null);
  const [modo, setModo] = useState('receta');
  const [guardando, setGuardando] = useState(false);

  const cargar = () => api<Articulo[]>('/tpv/articulos').then(setArts).catch(avisoError);
  useEffect(() => { cargar(); api<Catalogo>('/catalogo').then(setCat).catch(avisoError); }, []);

  const subir = async (f: File | null) => {
    if (!f) return;
    setSubiendo(true);
    const form = new FormData();
    form.append('archivo', f);
    try {
      const r = await api<{ dias: string[]; lineas: number; importe: number; pendientes: number }>('/tpv/pdf', { form });
      avisoOk(`${r.dias.length} días · ${r.lineas} líneas · ${euros(r.importe)}${r.pendientes ? ` · ${r.pendientes} artículos sin asignar` : ''}`, 'Ventas importadas');
      cargar();
    } catch (e) { avisoError(e); } finally { setSubiendo(false); }
  };

  const abrir = (a: Articulo) => { setEd({ ...a }); setModo(a.ignorar ? 'ignorar' : a.producto ? 'producto' : 'receta'); };

  const guardar = async () => {
    if (!ed) return;
    setGuardando(true);
    try {
      const r = await api<{ dias_recalculados: number }>(`/tpv/articulos/${ed.codigo}`, {
        method: 'PUT',
        body: {
          receta_id: modo === 'receta' ? ed.receta_id : null, producto: modo === 'producto' ? ed.producto : null,
          factor: ed.factor || 1, servicio: ed.servicio, precio: ed.precio, ignorar: modo === 'ignorar',
        },
      });
      avisoOk(`${r.dias_recalculados} días recalculados`, ed.nombre);
      setEd(null);
      cargar();
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };

  const cuenta = useMemo(() => (arts ?? []).reduce<Record<string, number>>((acc, a) => ({ ...acc, [estadoDe(a)]: (acc[estadoDe(a)] ?? 0) + 1 }), {}), [arts]);
  const visibles = (arts ?? []).filter((a) => (filtro === 'todos' || estadoDe(a) === filtro)
    && (!q || `${a.nombre} ${a.codigo} ${a.receta ?? ''} ${a.producto_nombre ?? ''}`.toLowerCase().includes(q.toLowerCase())));
  const pendienteImporte = (arts ?? []).filter((a) => estadoDe(a) === 'pendiente').reduce((s, a) => s + a.importe, 0);

  return (
    <>
      <Cabecera titulo="Ventas TPV" subtitulo="Cada artículo del TPV se asigna una vez a su receta o producto. Al cambiarlo se recalcula todo el histórico.">
        <FileButton onChange={subir} accept="application/pdf">
          {(props) => <Button {...props} leftSection={<IconFileTypePdf size={18} />} loading={subiendo}>Subir PDF de ventas</Button>}
        </FileButton>
      </Cabecera>
      {pendienteImporte > 0 && (
        <Alert color="orange" mb="md" title={`${cuenta.pendiente} artículos vendidos sin asignar (${euros(pendienteImporte)})`}>
          Mientras no se asignen no descuentan consumo ni cuentan en el food cost. Empieza por los de más importe.
        </Alert>
      )}
      <Card p={0}>
        <Group p="md" justify="space-between">
          <SegmentedControl value={filtro} onChange={setFiltro} data={[
            { value: 'pendiente', label: `Pendientes (${cuenta.pendiente ?? 0})` }, { value: 'asignado', label: `Asignados (${cuenta.asignado ?? 0})` },
            { value: 'ignorado', label: `Ignorados (${cuenta.ignorado ?? 0})` }, { value: 'todos', label: 'Todos' },
          ]} />
          <TextInput leftSection={<IconSearch size={16} />} placeholder="Buscar" value={q} onChange={(e) => setQ(e.currentTarget.value)} w={240} />
        </Group>
        {!arts ? <Group justify="center" p="xl"><Loader /></Group> : !visibles.length ? <Vacio texto="Nada en esta lista" /> : (
          <Table.ScrollContainer minWidth={760}>
            <Table className="tabla-click">
              <Table.Thead><Table.Tr><Table.Th>Artículo TPV</Table.Th><Table.Th>Servicio</Table.Th><Table.Th className="num">Vendido</Table.Th>
                <Table.Th className="num">PVP</Table.Th><Table.Th>Descuenta</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {visibles.map((a) => (
                  <Table.Tr key={a.codigo} onClick={() => abrir(a)}>
                    <Table.Td><Text size="sm" fw={500}>{a.nombre}</Text><Text size="xs" c="dimmed">{a.codigo} · {a.dias} días</Text></Table.Td>
                    <Table.Td><BadgeServicio valor={a.servicio} /></Table.Td>
                    <Table.Td className="num" fw={600}>{euros(a.importe)}</Table.Td>
                    <Table.Td className="num">{euros(a.precio)}</Table.Td>
                    <Table.Td>
                      {a.ignorar ? <Badge color="gray" variant="light">No descuenta</Badge>
                        : a.receta ? <Text size="sm">Receta: {a.receta}</Text>
                        : a.producto_nombre ? <Text size="sm">{a.factor !== 1 ? `${a.factor} × ` : ''}{a.producto_nombre}</Text>
                        : <Badge color="orange" variant="light">Sin asignar</Badge>}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>

      <Modal opened={!!ed} onClose={() => setEd(null)} title={ed?.nombre} size="lg" centered>
        {ed && (
          <Stack>
            <Text size="sm" c="dimmed">{ed.codigo} · vendido {euros(ed.importe)} en {ed.dias} días
              {ed.precio ? ` · ≈ ${Math.round(ed.importe / ed.precio)} unidades` : ''}</Text>
            <SegmentedControl value={modo} onChange={setModo} data={[
              { value: 'receta', label: 'Es una receta' }, { value: 'producto', label: 'Es un producto' }, { value: 'ignorar', label: 'No descuenta' },
            ]} />
            {modo === 'receta' && (
              <Select label="Receta" searchable data={(cat?.recetas ?? []).map((r) => ({ value: r.id, label: r.nombre }))}
                value={ed.receta_id} onChange={(x) => setEd({ ...ed, receta_id: x })} nothingFoundMessage="Crea la receta primero en Recetas" />
            )}
            {modo === 'producto' && (
              <Group grow align="flex-end">
                <Select label="Producto del almacén" searchable limit={80}
                  data={(cat?.productos ?? []).map((p) => ({ value: p.codigo, label: `${p.nombre} (${p.unidad ?? 'ud'})` }))}
                  value={ed.producto} onChange={(x) => setEd({ ...ed, producto: x })} />
                <NumberInput label="Cantidad por venta" description="p. ej. 1 lata, 0,33 L" value={ed.factor} min={0} decimalScale={4}
                  onChange={(x) => setEd({ ...ed, factor: Number(x) || 1 })} />
              </Group>
            )}
            {modo === 'ignorar' && <Text size="sm">Para servicios sin coste de almacén (p. ej. cubiertos, suplementos o cosas ya contadas en otra receta).</Text>}
            <Group grow>
              <Select label="Servicio" data={SERVICIOS.map((s) => ({ value: s.value, label: s.label }))} value={ed.servicio}
                onChange={(x) => x && setEd({ ...ed, servicio: x })} />
              <NumberInput label="PVP unitario" description="Para pasar de importe a unidades" value={ed.precio ?? ''} min={0} decimalScale={2} suffix=" €"
                onChange={(x) => setEd({ ...ed, precio: Number(x) || null })} />
            </Group>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setEd(null)}>Cancelar</Button>
              <Button onClick={guardar} loading={guardando}
                disabled={(modo === 'receta' && !ed.receta_id) || (modo === 'producto' && !ed.producto) || (modo !== 'ignorar' && !ed.precio)}>
                Guardar y recalcular
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}
