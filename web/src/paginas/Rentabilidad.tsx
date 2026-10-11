import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Anchor, Badge, Card, Grid, Group, SegmentedControl, SimpleGrid, Stack, Text, Tooltip } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { ScatterChart } from '@mantine/charts';
import { IconAlertTriangle } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera, Punto } from '../comun';
import { euros } from '../formato';
import { Tabla } from '../Tabla';

type Plato = { codigo: string; nombre: string; servicio: string; unidades: number; pvp: number; pvp_neto: number; ventas_netas: number;
  coste_unidad: number | null; margen_unidad: number | null; food_cost: number | null; margen_total: number | null; asignado: boolean;
  clase?: string; mix?: number; pvp_recomendado: number | null };

const CLASES: Record<string, { label: string; color: string; accion: string }> = {
  estrella: { label: 'Estrella', color: 'var(--serie-petroleo)', accion: 'Se vende mucho y deja buen margen. Mantener y destacar.' },
  caballo: { label: 'Caballo de batalla', color: 'var(--serie-marino)', accion: 'Se vende mucho, margen bajo. Revisar precio o abaratar la ficha.' },
  enigma: { label: 'Enigma', color: 'var(--serie-dorado)', accion: 'Buen margen pero se vende poco. Promocionar o recolocar en carta.' },
  perro: { label: 'Perro', color: 'var(--serie-terracota)', accion: 'Se vende poco y deja poco. Plantear retirarlo o rediseñarlo.' },
};
const hace = (d: number) => new Date(Date.now() - d * 864e5).toISOString().slice(0, 10);

export function Rentabilidad() {
  const [rango, setRango] = useState<[string | null, string | null]>([hace(90), hace(0)]);
  const [servicio, setServicio] = useState('comida');
  const [d, setD] = useState<{ igic: number; objetivo_food_cost: number; platos: Plato[] } | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    const [a, b] = rango;
    if (!a || !b) return;
    setD(null);
    api<typeof d>(`/analisis/rentabilidad?desde=${a}&hasta=${b}`).then(setD).catch(avisoError);
  }, [rango]);

  const platos = useMemo(() => (d?.platos ?? []).filter((p) => p.servicio === servicio), [d, servicio]);
  const conCoste = platos.filter((p) => p.margen_unidad != null);
  const ventas = conCoste.reduce((s, p) => s + p.ventas_netas, 0);
  const coste = conCoste.reduce((s, p) => s + (p.coste_unidad ?? 0) * p.unidades, 0);
  const margen = conCoste.reduce((s, p) => s + (p.margen_total ?? 0), 0);
  const fc = ventas ? (100 * coste) / ventas : null;
  const objetivo = d?.objetivo_food_cost ?? 30;
  const sinCoste = platos.filter((p) => !p.asignado);
  const puntos = Object.entries(CLASES).map(([k, c]) => ({
    name: c.label, color: c.color,
    data: conCoste.filter((p) => p.clase === k).map((p) => ({ mix: p.mix ?? 0, margen: Number((p.margen_unidad ?? 0).toFixed(2)) })),
  }));

  return (
    <>
      <Cabecera titulo="Rentabilidad por plato" subtitulo={`Ingeniería de menú: precio de venta sin IGIC (${d?.igic ?? 7} %) frente al coste de la ficha a precio de última compra`}>
        <SegmentedControl value={servicio} onChange={setServicio} data={[{ value: 'comida', label: 'Comida' }, { value: 'bebidas', label: 'Bebidas' }, { value: 'cena', label: 'Cena' }]} />
        <DatePickerInput type="range" value={rango} onChange={(x) => setRango([x[0] && String(x[0]).slice(0, 10), x[1] && String(x[1]).slice(0, 10)])}
          valueFormat="DD/MM/YY" w={220} aria-label="Periodo" />
      </Cabecera>
      <Stack gap="lg">
        <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
          <Card><Text size="xs" c="dimmed" fw={600} tt="uppercase">Ventas netas</Text><Text fw={700} fz={24}>{euros(ventas)}</Text></Card>
          <Card><Text size="xs" c="dimmed" fw={600} tt="uppercase">Coste teórico</Text><Text fw={700} fz={24}>{euros(coste)}</Text></Card>
          <Card><Text size="xs" c="dimmed" fw={600} tt="uppercase">Food cost</Text>
            <Text fw={700} fz={24} c={fc != null && fc > objetivo ? 'red' : undefined}>{fc == null ? '—' : `${fc.toFixed(1)} %`}</Text>
            <Text size="xs" c="dimmed">Objetivo {objetivo} %</Text></Card>
          <Card><Text size="xs" c="dimmed" fw={600} tt="uppercase">Margen bruto</Text><Text fw={700} fz={24}>{euros(margen)}</Text></Card>
        </SimpleGrid>
        {sinCoste.length > 0 && (
          <Alert color="orange" icon={<IconAlertTriangle />} title={`${sinCoste.length} artículos vendidos sin receta asignada`}>
            No entran en el análisis: {sinCoste.slice(0, 6).map((p) => p.nombre).join(', ')}{sinCoste.length > 6 ? '…' : ''}.{' '}
            <Anchor size="sm" onClick={() => nav('/tpv')}>Asignarlos en Ventas TPV</Anchor>
          </Alert>
        )}
        <Grid>
          <Grid.Col span={{ base: 12, lg: 7 }}>
            <Card h="100%">
              <Text fw={600}>Mapa de la carta</Text>
              <Text size="xs" c="dimmed" mb="sm">Horizontal: % de las ventas del servicio. Vertical: margen por unidad (€).</Text>
              {conCoste.length ? (
                <ScatterChart h={320} data={puntos} dataKey={{ x: 'mix', y: 'margen' }} xAxisLabel="Popularidad (%)" yAxisLabel="Margen (€)"
                  valueFormatter={{ x: (x) => `${x} %`, y: (x) => euros(x) }} withLegend legendProps={{ verticalAlign: 'bottom' }} />
              ) : <Text c="dimmed">Sin platos con coste en el periodo</Text>}
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, lg: 5 }}>
            <Stack gap="sm" h="100%">
              {Object.entries(CLASES).map(([k, c]) => {
                const xs = conCoste.filter((p) => p.clase === k);
                return (
                  <Card key={k} p="md">
                    <Group justify="space-between"><Badge variant="default" size="lg" tt="none" leftSection={<Punto color={c.color} />}>{c.label}</Badge><Text fw={700}>{xs.length}</Text></Group>
                    <Text size="sm" c="dimmed" mt={6}>{c.accion}</Text>
                  </Card>
                );
              })}
            </Stack>
          </Grid.Col>
        </Grid>
        <Tabla datos={d ? platos : null} clave={(p) => p.codigo} buscar exportar={`rentabilidad_${servicio}`} orden={{ clave: 'margen_total', desc: true }} anchoMin={1000}
          vacio="Sin ventas en el periodo" columnas={[
            { clave: 'nombre', titulo: 'Plato', render: (p) => <Text size="sm" fw={500}>{p.nombre}</Text> },
            { clave: 'clase', titulo: 'Tipo', valor: (p) => (p.clase ? CLASES[p.clase].label : 'Sin coste'),
              render: (p) => p.clase ? <Badge variant="default" tt="none" leftSection={<Punto color={CLASES[p.clase].color} />}>{CLASES[p.clase].label}</Badge> : <Badge color="gray" variant="light">Sin coste</Badge> },
            { clave: 'unidades', titulo: 'Vendidos', num: true },
            { clave: 'pvp', titulo: 'PVP', num: true, render: (p) => euros(p.pvp) },
            { clave: 'coste_unidad', titulo: 'Coste', num: true, render: (p) => euros(p.coste_unidad) },
            { clave: 'food_cost', titulo: 'Food cost', num: true, render: (p) => p.food_cost == null ? '—' : (
              <Group gap={4} justify="flex-end" wrap="nowrap">
                {p.food_cost < 8 && <Tooltip label="Coste muy bajo: ¿la ficha está completa?"><IconAlertTriangle size={14} color="orange" /></Tooltip>}
                <Text size="sm" c={p.food_cost > objetivo ? 'red' : undefined}>{p.food_cost} %</Text>
              </Group>) },
            { clave: 'pvp_recomendado', titulo: 'PVP objetivo', num: true, render: (p) => p.pvp_recomendado == null ? '—' : (
              <Tooltip label={`Precio con IGIC que deja el food cost en el ${objetivo} %`}>
                <Text size="sm" fw={p.pvp < p.pvp_recomendado - 0.05 ? 700 : 400} c={p.pvp < p.pvp_recomendado - 0.05 ? 'red' : 'dimmed'}>{euros(p.pvp_recomendado)}</Text>
              </Tooltip>) },
            { clave: 'margen_unidad', titulo: 'Margen ud.', num: true, render: (p) => euros(p.margen_unidad) },
            { clave: 'margen_total', titulo: 'Margen total', num: true, render: (p) => <Text size="sm" fw={600}>{euros(p.margen_total)}</Text> },
          ]} />
      </Stack>
    </>
  );
}
