import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Badge, Card, Drawer, Loader, Group, SimpleGrid, Stack, Table, Tabs, Text, TextInput } from '@mantine/core';
import { LineChart } from '@mantine/charts';
import { useDebouncedValue } from '@mantine/hooks';
import { IconSearch } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { BadgeServicio, Cabecera, Vacio } from '../comun';
import { cantidad, euros, fecha, fechaCorta } from '../formato';
import { Tabla } from '../Tabla';

type Fila = { codigo: string; nombre: string; unidad: string | null; categoria: string | null; origen: string; stock_bc: number | null; ultima_compra: string | null; ultimo_precio: number | null };
type Mov = { n_mov: number; fecha: string; tipo: string; tipo_doc: string; documento: string; proveedor: string; almacen: string; cantidad: number; coste_unit: number | null };
type Ficha = Fila & { precio_actual: number | null; movimientos: Mov[]; consumo: { mes: string; servicio: string; cantidad: number; coste: number }[]; recetas: { id: string; nombre: string; cantidad: number }[] };

export function Productos() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState('');
  const [qd] = useDebouncedValue(q, 250);
  const [filas, setFilas] = useState<Fila[] | null>(null);
  const [ficha, setFicha] = useState<Ficha | null>(null);
  const codigo = params.get('codigo');

  useEffect(() => { setFilas(null); api<Fila[]>(`/productos?q=${encodeURIComponent(qd)}`).then(setFilas).catch(avisoError); }, [qd]);
  useEffect(() => { setFicha(null); if (codigo) api<Ficha>(`/productos/${codigo}`).then(setFicha).catch(avisoError); }, [codigo]);

  const compras = (ficha?.movimientos ?? []).filter((m) => m.tipo === 'Compra' && m.cantidad > 0 && m.coste_unit).slice().reverse()
    .map((m) => ({ fecha: fechaCorta(m.fecha), precio: Number(m.coste_unit!.toFixed(4)) }));

  return (
    <>
      <Cabecera titulo="Productos" subtitulo="Maestro de artículos de Business Central">
        <TextInput leftSection={<IconSearch size={16} />} placeholder="Nombre o código" value={q} onChange={(e) => setQ(e.currentTarget.value)} w={260} />
      </Cabecera>
      <Tabla datos={filas} clave={(p) => p.codigo} alPulsar={(p) => setParams({ codigo: p.codigo })} exportar="productos" vacio="Sin resultados"
        columnas={[
          { clave: 'nombre', titulo: 'Producto', render: (p) => <><Group gap={6}><Text size="sm" fw={500}>{p.nombre}</Text>
            {p.origen === 'bm2' && <Badge size="xs" color="orange" variant="light">Sin código BC</Badge>}</Group><Text size="xs" c="dimmed">{p.codigo}</Text></> },
          { clave: 'unidad', titulo: 'Unidad' },
          { clave: 'ultimo_precio', titulo: 'Último precio', num: true, render: (p) => <Text size="sm" fw={600}>{euros(p.ultimo_precio)}</Text> },
          { clave: 'ultima_compra', titulo: 'Última compra', render: (p) => fecha(p.ultima_compra) },
          { clave: 'stock_bc', titulo: 'Stock total', num: true, render: (p) => cantidad(p.stock_bc) },
        ]} />

      <Drawer opened={!!codigo} onClose={() => setParams({})} position="right" size="xl" title={ficha?.nombre ?? 'Producto'}>
        {!ficha ? <Loader /> : (
          <Stack>
            <SimpleGrid cols={3}>
              <div><Text size="xs" c="dimmed">Precio actual</Text><Text fw={700} fz="lg">{euros(ficha.precio_actual)} / {ficha.unidad}</Text></div>
              <div><Text size="xs" c="dimmed">Código BC</Text><Text fw={600}>{ficha.codigo}</Text></div>
              <div><Text size="xs" c="dimmed">Usado en</Text><Text fw={600}>{ficha.recetas.length} recetas</Text></div>
            </SimpleGrid>
            {compras.length > 1 && (
              <Card>
                <Text fw={600} size="sm" mb="sm">Evolución del precio de compra</Text>
                <LineChart h={180} data={compras} dataKey="fecha" series={[{ name: 'precio', label: 'Precio', color: 'marina.6' }]}
                  valueFormatter={(x) => euros(x)} curveType="stepAfter" withDots={false} gridAxis="y" />
              </Card>
            )}
            <Tabs defaultValue="movs">
              <Tabs.List>
                <Tabs.Tab value="movs">Compras e inventarios</Tabs.Tab>
                <Tabs.Tab value="consumo">Consumo en BM</Tabs.Tab>
                <Tabs.Tab value="recetas">Recetas</Tabs.Tab>
              </Tabs.List>
              <Tabs.Panel value="movs" pt="sm">
                <Table>
                  <Table.Thead><Table.Tr><Table.Th>Fecha</Table.Th><Table.Th>Documento</Table.Th><Table.Th className="num">Cantidad</Table.Th><Table.Th className="num">Coste ud.</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {ficha.movimientos.map((m) => (
                      <Table.Tr key={m.n_mov}>
                        <Table.Td>{fecha(m.fecha)}</Table.Td>
                        <Table.Td><Text size="sm">{m.documento}</Text><Text size="xs" c="dimmed">{m.tipo === 'Compra' ? m.proveedor : m.tipo} · {m.almacen}</Text></Table.Td>
                        <Table.Td className="num" c={m.cantidad < 0 ? 'red' : undefined}>{cantidad(m.cantidad)}</Table.Td>
                        <Table.Td className="num">{m.coste_unit ? euros(m.coste_unit) : <Badge size="xs" color="yellow" variant="light">sin facturar</Badge>}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Tabs.Panel>
              <Tabs.Panel value="consumo" pt="sm">
                {!ficha.consumo.length ? <Vacio texto="Sin consumos registrados" /> : (
                  <Table>
                    <Table.Thead><Table.Tr><Table.Th>Mes</Table.Th><Table.Th>Servicio</Table.Th><Table.Th className="num">Cantidad</Table.Th><Table.Th className="num">Coste</Table.Th></Table.Tr></Table.Thead>
                    <Table.Tbody>
                      {ficha.consumo.map((c, i) => (
                        <Table.Tr key={i}><Table.Td>{c.mes}</Table.Td><Table.Td><BadgeServicio valor={c.servicio} /></Table.Td>
                          <Table.Td className="num">{cantidad(c.cantidad)}</Table.Td><Table.Td className="num">{euros(c.coste)}</Table.Td></Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )}
              </Tabs.Panel>
              <Tabs.Panel value="recetas" pt="sm">
                {!ficha.recetas.length ? <Vacio texto="No se usa en ninguna receta" /> : (
                  <Stack gap={4}>{ficha.recetas.map((r) => <Text key={r.id} size="sm">{r.nombre} · {cantidad(r.cantidad)} {ficha.unidad}</Text>)}</Stack>
                )}
              </Tabs.Panel>
            </Tabs>
          </Stack>
        )}
      </Drawer>
    </>
  );
}
