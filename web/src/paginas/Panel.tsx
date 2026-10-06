import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Anchor, Badge, Card, Grid, Group, SimpleGrid, Skeleton, Stack, Table, Text, ThemeIcon } from '@mantine/core';
import { MonthPickerInput } from '@mantine/dates';
import { BarChart, DonutChart } from '@mantine/charts';
import {
  IconAlertTriangle, IconArrowDownRight, IconArrowUpRight, IconCalendarOff, IconCoffee, IconPercentage,
  IconReceipt2, IconScale, IconTrash,
} from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera, Vacio } from '../comun';
import { cantidad, euros, fecha, fechaCorta } from '../formato';
import { useCentros } from '../centros';

type Resumen = Record<string, number | null>;
type Datos = {
  mes: string; actual: Resumen; anterior: Resumen;
  serie: { fecha: string; servicio: string; coste: number }[];
  top: { codigo: string; nombre: string; unidad: string; cantidad: number; coste: number }[];
  alertas: {
    dias_sin_desayuno: string[]; tpv_pendientes: number; tpv_pendiente_importe: number;
    lineas_por_estado: Record<string, number>; ultimo_movimiento_bc: string | null; ultimo_inventario_bc: string | null;
  };
};

function Kpi({ titulo, valor, anterior, formato, icono: Icono, color, ayuda, menosEsMejor = true }: {
  titulo: string; valor: number | null | undefined; anterior?: number | null; formato: (x: number | null | undefined) => string;
  icono: typeof IconScale; color: string; ayuda?: string; menosEsMejor?: boolean;
}) {
  const delta = valor != null && anterior ? ((valor - anterior) / anterior) * 100 : null;
  const bueno = delta == null ? null : menosEsMejor ? delta <= 0 : delta >= 0;
  return (
    <Card>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <div>
          <Text size="xs" c="dimmed" fw={600} tt="uppercase" lts={0.5}>{titulo}</Text>
          <Text fw={700} fz={26} mt={4} style={{ fontVariantNumeric: 'tabular-nums' }}>{formato(valor)}</Text>
        </div>
        <ThemeIcon variant="light" color={color} size={42} radius="md"><Icono size={22} stroke={1.6} /></ThemeIcon>
      </Group>
      <Group gap={4} mt="xs" wrap="nowrap">
        {delta != null && Number.isFinite(delta) ? (
          <>
            <Text size="sm" fw={600} c={bueno ? 'teal' : 'red'} style={{ display: 'flex', alignItems: 'center' }}>
              {delta >= 0 ? <IconArrowUpRight size={16} /> : <IconArrowDownRight size={16} />}
              {Math.abs(delta).toFixed(1)}%
            </Text>
            <Text size="sm" c="dimmed">vs mes anterior (mismos días)</Text>
          </>
        ) : <Text size="sm" c="dimmed">{ayuda ?? 'Sin comparación'}</Text>}
      </Group>
    </Card>
  );
}

const pct = (x: number | null | undefined) => (x == null ? '—' : `${x.toLocaleString('es-ES')} %`);

export function Panel() {
  const [mes, setMes] = useState<string>(new Date().toISOString().slice(0, 7));
  const [d, setD] = useState<Datos | null>(null);
  const nav = useNavigate();
  const centros = useCentros();

  useEffect(() => {
    setD(null);
    api<Datos>(`/panel?mes=${mes}`).then(setD).catch(avisoError);
  }, [mes]);

  const porDia = d ? Object.values(d.serie.reduce<Record<string, any>>((acc, x) => {
    acc[x.fecha] ??= { fecha: fechaCorta(x.fecha) };
    acc[x.fecha][x.servicio] = x.coste;
    return acc;
  }, {})) : [];
  const reparto = d ? centros.map((c) => ({ name: c.nombre, value: (d.actual[c.codigo] as number) ?? 0, color: `${c.color}.6` })).filter((x) => x.value > 0) : [];
  const conSerie = centros.filter((c) => d?.serie.some((x) => x.servicio === c.codigo));
  const estados = d?.alertas.lineas_por_estado ?? {};
  const totalLineas = Object.values(estados).reduce((a, b) => a + b, 0);
  const dudosas = (estados.sin_stock ?? 0) + (estados.sin_precio ?? 0);

  return (
    <>
      <Cabecera titulo="Panel" subtitulo="Coste de consumo valorado con precios reales de compra (Business Central)">
        <MonthPickerInput value={`${mes}-01`} onChange={(x) => x && setMes(String(x).slice(0, 7))}
          valueFormat="MMMM YYYY" w={190} maxDate={new Date()} aria-label="Mes" />
      </Cabecera>

      {!d ? (
        <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }}>{[1, 2, 3, 4].map((i) => <Skeleton key={i} h={130} radius="lg" />)}</SimpleGrid>
      ) : (
        <Stack gap="lg">
          <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }}>
            <Kpi titulo="Coste de consumo" valor={d.actual.consumo} anterior={d.anterior.consumo} formato={euros} icono={IconScale} color="marina" />
            <Kpi titulo="Ventas TPV" valor={d.actual.ventas_tpv} anterior={d.anterior.ventas_tpv} formato={euros} icono={IconReceipt2} color="teal" menosEsMejor={false} />
            <Kpi titulo="Food cost TPV" valor={d.actual.food_cost_pct} anterior={d.anterior.food_cost_pct} formato={pct} icono={IconPercentage} color="grape"
              ayuda="Coste de lo vendido / ventas" />
            <Kpi titulo="Desayuno por comensal" valor={d.actual.coste_por_comensal} anterior={d.anterior.coste_por_comensal} formato={euros} icono={IconCoffee} color="orange"
              ayuda={`${d.actual.comensales_desayuno ?? 0} comensales`} />
          </SimpleGrid>

          <Grid>
            <Grid.Col span={{ base: 12, lg: 8 }}>
              <Card h="100%">
                <Text fw={600} mb="md">Coste diario por servicio</Text>
                {porDia.length ? (
                  <BarChart h={300} data={porDia} dataKey="fecha" type="stacked" valueFormatter={(x) => euros(x)}
                    series={conSerie.map((c) => ({ name: c.codigo, label: c.nombre, color: `${c.color}.6` }))}
                    withLegend legendProps={{ verticalAlign: 'bottom' }} gridAxis="y" tickLine="none" />
                ) : <Vacio texto="Sin consumos registrados en este mes" />}
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, lg: 4 }}>
              <Card h="100%">
                <Text fw={600} mb="md">Reparto del mes</Text>
                {reparto.length ? (
                  <Stack align="center">
                    <DonutChart data={reparto} size={180} thickness={26} valueFormatter={(x) => euros(x)} withTooltip
                      chartLabel={euros(d.actual.consumo)} />
                    <Stack gap={6} w="100%">
                      {reparto.map((r) => (
                        <Group key={r.name} justify="space-between">
                          <Group gap={8}><Badge color={r.color} variant="filled" size="xs" circle> </Badge><Text size="sm">{r.name}</Text></Group>
                          <Text size="sm" fw={600} className="num">{euros(r.value)}</Text>
                        </Group>
                      ))}
                      <Group justify="space-between">
                        <Group gap={8}><IconTrash size={14} /><Text size="sm">Mermas (aparte)</Text></Group>
                        <Text size="sm" fw={600} className="num">{euros(d.actual.mermas)}</Text>
                      </Group>
                    </Stack>
                  </Stack>
                ) : <Vacio texto="Sin datos" />}
              </Card>
            </Grid.Col>
          </Grid>

          <Grid>
            <Grid.Col span={{ base: 12, lg: 7 }}>
              <Card h="100%">
                <Text fw={600} mb="sm">Productos que más cuestan</Text>
                {d.top.length ? (
                  <Table.ScrollContainer minWidth={420}>
                    <Table className="tabla-click">
                      <Table.Thead><Table.Tr><Table.Th>Producto</Table.Th><Table.Th className="num">Cantidad</Table.Th><Table.Th className="num">Coste</Table.Th></Table.Tr></Table.Thead>
                      <Table.Tbody>
                        {d.top.map((p) => (
                          <Table.Tr key={p.codigo} onClick={() => nav(`/productos?codigo=${p.codigo}`)}>
                            <Table.Td><Text size="sm" fw={500}>{p.nombre}</Text><Text size="xs" c="dimmed">{p.codigo}</Text></Table.Td>
                            <Table.Td className="num">{cantidad(p.cantidad)} {p.unidad}</Table.Td>
                            <Table.Td className="num" fw={600}>{euros(p.coste)}</Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Table.ScrollContainer>
                ) : <Vacio texto="Sin consumos" />}
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, lg: 5 }}>
              <Card h="100%">
                <Text fw={600} mb="sm">Pendiente de revisar</Text>
                <Stack gap="sm">
                  {d.alertas.tpv_pendientes > 0 && (
                    <Alert color="orange" icon={<IconReceipt2 />} title={`${d.alertas.tpv_pendientes} artículos TPV sin asignar`}>
                      {euros(d.alertas.tpv_pendiente_importe)} vendidos que aún no descuentan consumo.{' '}
                      <Anchor size="sm" onClick={() => nav('/tpv')}>Asignar ahora</Anchor>
                    </Alert>
                  )}
                  {d.alertas.dias_sin_desayuno.length > 0 && (
                    <Alert color="yellow" icon={<IconCalendarOff />} title={`${d.alertas.dias_sin_desayuno.length} días sin desayuno registrado`}>
                      {d.alertas.dias_sin_desayuno.slice(0, 8).map(fechaCorta).join(', ')}{d.alertas.dias_sin_desayuno.length > 8 ? '…' : ''}
                    </Alert>
                  )}
                  {dudosas > 0 && (
                    <Alert color="gray" icon={<IconAlertTriangle />} title={`${dudosas} de ${totalLineas} líneas sin lote en BC`}>
                      Valoradas con el último precio conocido. Se corrigen solas al importar movimientos nuevos de BC.
                    </Alert>
                  )}
                  <Text size="sm" c="dimmed">
                    Último movimiento importado de BC: <b>{fecha(d.alertas.ultimo_movimiento_bc)}</b> · último inventario: <b>{fecha(d.alertas.ultimo_inventario_bc)}</b>
                  </Text>
                </Stack>
              </Card>
            </Grid.Col>
          </Grid>
        </Stack>
      )}
    </>
  );
}
