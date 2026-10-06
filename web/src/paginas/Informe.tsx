import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Alert, Badge, Button, Card, Grid, Group, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core';
import { IconPrinter } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Logo } from '../comun';
import { euros } from '../formato';

export function Informe() {
  const [params] = useSearchParams();
  const mes = params.get('mes') ?? new Date().toISOString().slice(0, 7);
  const [d, setD] = useState<any>(null);
  useEffect(() => { api(`/cierre/informe?mes=${mes}`).then(setD).catch(avisoError); }, [mes]);
  if (!d) return <Text c="dimmed">Preparando informe…</Text>;
  const r = d.resumen;
  const largo = new Date(`${mes}-01T00:00:00`).toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });
  const nombreMes = largo.charAt(0).toUpperCase() + largo.slice(1);
  const fila = (k: string, v: string) => <Table.Tr key={k}><Table.Td>{k}</Table.Td><Table.Td className="num" fw={600}>{v}</Table.Td></Table.Tr>;
  return (
    <Stack maw={980} mx="auto">
      <Group justify="space-between">
        <Group><Logo size={44} /><div><Text size="xs" c="dimmed" fw={700} tt="uppercase">Royal Marina Suites · Informe F&amp;B</Text><Title order={2}>{nombreMes}</Title></div></Group>
        <Button className="no-imprimir" leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>Imprimir / PDF</Button>
      </Group>
      {!d.estado.listo && <Alert color="orange">Mes sin cerrar del todo: {d.estado.pasos.filter((p: any) => !p.ok && p.obligatorio).map((p: any) => p.titulo.toLowerCase()).join(', ')}. Las cifras pueden cambiar.</Alert>}
      <SimpleGrid cols={4}>
        <Card><Text size="xs" c="dimmed">Coste de consumo</Text><Text fw={700} fz={22}>{euros(r.consumo)}</Text></Card>
        <Card><Text size="xs" c="dimmed">Ventas TPV (sin IGIC)</Text><Text fw={700} fz={22}>{euros(r.ventas_netas)}</Text></Card>
        <Card><Text size="xs" c="dimmed">Food cost TPV</Text><Text fw={700} fz={22} c={(r.food_cost_pct ?? 0) > d.objetivo_food_cost ? 'red' : 'teal'}>{r.food_cost_pct ?? '—'} %</Text><Text size="xs" c="dimmed">Objetivo {d.objetivo_food_cost} %</Text></Card>
        <Card><Text size="xs" c="dimmed">Desayuno / comensal</Text><Text fw={700} fz={22}>{euros(r.coste_por_comensal)}</Text><Text size="xs" c="dimmed">{r.comensales_desayuno} comensales</Text></Card>
      </SimpleGrid>
      <Grid>
        <Grid.Col span={6}><Card h="100%"><Text fw={700} mb="xs">Coste por centro</Text><Table><Table.Tbody>
          {d.centros.filter((c: any) => r[c.codigo]).map((c: any) => fila(c.nombre, euros(r[c.codigo])))}{fila('Mermas', euros(r.mermas))}
        </Table.Tbody></Table></Card></Grid.Col>
        <Grid.Col span={6}><Card h="100%"><Text fw={700} mb="xs">Pérdidas</Text><Table><Table.Tbody>
          {fila('Comida de personal', euros(d.perdidas.personal))}{fila('Mermas registradas', euros(d.perdidas.mermas_total))}
          {fila('Salió sin registrar (inventarios)', euros(d.perdidas.diferencias_inventario))}
        </Table.Tbody></Table></Card></Grid.Col>
        <Grid.Col span={6}><Card h="100%"><Text fw={700} mb="xs">Carta: lo que más deja</Text><Table><Table.Tbody>
          {d.estrellas.map((p: any) => fila(p.nombre, euros(p.margen_total)))}</Table.Tbody></Table>
          <Group gap={6} mt="xs">{Object.entries(d.clases).map(([k, v]) => <Badge key={k} variant="light">{k}: {String(v)}</Badge>)}</Group></Card></Grid.Col>
        <Grid.Col span={6}><Card h="100%"><Text fw={700} mb="xs">Platos que no salen</Text><Table><Table.Tbody>
          {d.perros.length ? d.perros.map((p: any) => fila(p.nombre, `${p.unidades} uds`)) : fila('Ninguno', '')}</Table.Tbody></Table></Card></Grid.Col>
        <Grid.Col span={6}><Card h="100%"><Text fw={700} mb="xs">Mayores diferencias de inventario</Text><Table><Table.Tbody>
          {d.desviaciones.map((x: any) => fila(x.nombre, euros(x.valor)))}</Table.Tbody></Table></Card></Grid.Col>
        <Grid.Col span={6}><Card h="100%"><Text fw={700} mb="xs">Compras por proveedor</Text><Table><Table.Tbody>
          {d.compras.map((x: any) => fila(`${x.proveedor} (${x.documentos})`, euros(x.importe)))}</Table.Tbody></Table></Card></Grid.Col>
      </Grid>
      <Text size="xs" c="dimmed" ta="center">Generado por BM el {new Date().toLocaleString('es-ES')} · costes FIFO con precios reales de compra de Business Central</Text>
    </Stack>
  );
}
