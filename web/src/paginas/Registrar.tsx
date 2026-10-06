import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActionIcon, Button, Card, Grid, Group, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Textarea,
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconDeviceFloppy, IconPlus, IconTrash } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera, Vacio } from '../comun';
import { cantidad, hoy } from '../formato';
import { useCentros, useUbicaciones } from '../centros';

type Catalogo = {
  recetas: { id: string; nombre: string; servicio: string | null }[];
  productos: { codigo: string; nombre: string; unidad: string | null }[];
};
type Item = { clave: string; nombre: string; unidad: string; cantidad: number };

export function Registrar() {
  const [cat, setCat] = useState<Catalogo | null>(null);
  const [fecha, setFecha] = useState<string>(hoy());
  const [servicio, setServicio] = useState<string>('desayuno');
  const [tipo, setTipo] = useState<string>('consumo');
  const [comensales, setComensales] = useState<number | string>('');
  const [nota, setNota] = useState('');
  const [items, setItems] = useState<Item[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [cant, setCant] = useState<number | string>(1);
  const [guardando, setGuardando] = useState(false);
  const cantRef = useRef<HTMLInputElement>(null);
  const centros = useCentros();
  const ubicaciones = useUbicaciones();
  const [ubicacion, setUbicacion] = useState<string | null>(null);
  const centro = centros.find((c) => c.codigo === servicio);
  const ubicacionFinal = ubicacion ?? centro?.ubicacion ?? null;

  useEffect(() => { api<Catalogo>('/catalogo').then(setCat).catch(avisoError); }, []);

  const opciones = useMemo(() => {
    if (!cat) return [];
    const recetas = cat.recetas
      .filter((r) => !r.servicio || r.servicio === servicio || tipo === 'merma')
      .map((r) => ({ value: `r:${r.id}`, label: r.nombre }));
    const productos = cat.productos.map((p) => ({ value: `p:${p.codigo}`, label: `${p.nombre} (${p.unidad ?? 'ud'})` }));
    return [{ group: 'Recetas / platos', items: recetas }, { group: 'Productos sueltos', items: productos }];
  }, [cat, servicio, tipo]);

  const info = (clave: string) => {
    const [t, id] = [clave.slice(0, 1), clave.slice(2)];
    if (t === 'r') return { nombre: cat!.recetas.find((r) => r.id === id)!.nombre, unidad: 'raciones' };
    const p = cat!.productos.find((x) => x.codigo === id)!;
    return { nombre: p.nombre, unidad: p.unidad ?? 'ud' };
  };

  const anadir = () => {
    const q = Number(cant);
    if (!sel || !(q > 0)) return;
    setItems((xs) => {
      const i = xs.findIndex((x) => x.clave === sel);
      if (i >= 0) return xs.map((x, j) => (j === i ? { ...x, cantidad: x.cantidad + q } : x));
      return [...xs, { clave: sel, ...info(sel), cantidad: q }];
    });
    setSel(null);
    setCant(1);
  };

  const guardar = async () => {
    setGuardando(true);
    try {
      await api('/consumos', {
        body: {
          fecha, servicio, tipo, nota: nota || null,
          ubicacion: ubicacion && ubicacion !== centro?.ubicacion ? ubicacion : null,
          comensales: servicio === 'desayuno' && tipo === 'consumo' && comensales !== '' ? Number(comensales) : null,
          items: items.map((x) => (x.clave.startsWith('r:')
            ? { receta_id: x.clave.slice(2), cantidad: x.cantidad } : { producto: x.clave.slice(2), cantidad: x.cantidad })),
        },
      });
      avisoOk(`${items.length} líneas guardadas`, tipo === 'merma' ? 'Merma registrada' : 'Consumo registrado');
      setItems([]);
      setNota('');
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };

  return (
    <>
      <Cabecera titulo="Registrar" subtitulo="Anota lo que se ha servido o tirado. El coste y el stock se calculan solos." />
      <Grid>
        <Grid.Col span={{ base: 12, md: 5, lg: 4 }}>
          <Card>
            <Stack>
              <DateInput label="Fecha" value={fecha} onChange={(x) => x && setFecha(String(x).slice(0, 10))} valueFormat="DD/MM/YYYY" maxDate={new Date()} />
              <div>
                <Text size="sm" fw={500} mb={4}>Tipo</Text>
                <SegmentedControl fullWidth value={tipo} onChange={setTipo}
                  data={[{ value: 'consumo', label: 'Consumo' }, { value: 'merma', label: 'Merma' }]} />
              </div>
              <div>
                <Text size="sm" fw={500} mb={4}>Servicio</Text>
                <SimpleGrid cols={2} spacing={6}>
                  {centros.filter((c) => c.tipo === 'restauracion' && c.activo).map((c) => (
                    <Button key={c.codigo} variant={servicio === c.codigo ? 'filled' : 'default'} color={c.color} onClick={() => { setServicio(c.codigo); setUbicacion(null); }}>
                      {c.nombre}
                    </Button>
                  ))}
                </SimpleGrid>
                <Select mt={6} placeholder="…o un departamento" clearable value={centro?.tipo === 'departamento' ? servicio : null}
                  data={centros.filter((c) => c.tipo === 'departamento' && c.activo).map((c) => ({ value: c.codigo, label: c.nombre }))}
                  onChange={(x) => { setServicio(x ?? 'desayuno'); setUbicacion(null); }} aria-label="Departamento" />
              </div>
              {servicio === 'desayuno' && tipo === 'consumo' && (
                <NumberInput label="Comensales" value={comensales} onChange={setComensales} min={0} allowDecimal={false} placeholder="Nº de huéspedes" />
              )}
              <Select label="Sale del almacén" description="El stock se descuenta de aquí" searchable value={ubicacionFinal}
                data={ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }))} onChange={setUbicacion} />
              <Textarea label={tipo === 'merma' ? 'Motivo de la merma' : 'Nota'} value={nota} onChange={(e) => setNota(e.currentTarget.value)}
                autosize minRows={2} required={tipo === 'merma'} />
            </Stack>
          </Card>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7, lg: 8 }}>
          <Card>
            <Group align="flex-end" wrap="wrap" gap="sm">
              <Select label="Plato o producto" placeholder={cat ? 'Escribe para buscar…' : 'Cargando…'} data={opciones} value={sel}
                onChange={(x) => { setSel(x); setTimeout(() => cantRef.current?.select(), 0); }}
                searchable clearable nothingFoundMessage="Sin resultados" style={{ flex: 1, minWidth: 240 }} limit={60} />
              <NumberInput ref={cantRef} label={sel ? `Cantidad (${info(sel).unidad})` : 'Cantidad'} value={cant} onChange={setCant}
                min={0} decimalScale={3} w={160} onKeyDown={(e) => e.key === 'Enter' && anadir()} />
              <Button leftSection={<IconPlus size={16} />} onClick={anadir} disabled={!sel}>Añadir</Button>
            </Group>

            {items.length ? (
              <Table mt="md">
                <Table.Thead><Table.Tr><Table.Th>Línea</Table.Th><Table.Th className="num">Cantidad</Table.Th><Table.Th w={40} /></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {items.map((x) => (
                    <Table.Tr key={x.clave}>
                      <Table.Td><Text size="sm" fw={500}>{x.nombre}</Text><Text size="xs" c="dimmed">{x.clave.startsWith('r:') ? 'Receta' : 'Producto'}</Text></Table.Td>
                      <Table.Td className="num">{cantidad(x.cantidad)} {x.unidad}</Table.Td>
                      <Table.Td>
                        <ActionIcon variant="subtle" color="red" aria-label="Quitar" onClick={() => setItems((xs) => xs.filter((y) => y.clave !== x.clave))}>
                          <IconTrash size={16} />
                        </ActionIcon>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            ) : <Vacio texto="Añade los platos o productos servidos" />}

            <Group justify="flex-end" mt="md">
              <Button size="md" leftSection={<IconDeviceFloppy size={18} />} onClick={guardar} loading={guardando}
                disabled={!items.length || (tipo === 'merma' && !nota.trim())}>
                Guardar {tipo === 'merma' ? 'merma' : 'consumo'}
              </Button>
            </Group>
          </Card>
        </Grid.Col>
      </Grid>
    </>
  );
}
