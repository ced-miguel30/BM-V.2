import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Grid, Group, SimpleGrid, Stack, Text } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { DonutChart } from '@mantine/charts';
import { api, avisoError } from '../api';
import { BadgeServicio, Cabecera, Vacio } from '../comun';
import { cantidad, euros } from '../formato';
import { Tabla } from '../Tabla';

type Datos = {
  personal: number; mermas_total: number; diferencias_inventario: number; motivos: Record<string, string>;
  mermas: { motivo: string; coste: number; registros: number }[];
  top_mermas: { producto: string; nombre: string; unidad: string | null; motivo: string | null; cantidad: number; coste: number }[];
  platos_que_no_salen: { codigo: string; nombre: string; servicio: string; unidades: number; ventas_netas: number; margen_total: number | null }[];
};
const COLORES = ['red.6', 'orange.6', 'yellow.6', 'grape.6', 'blue.6', 'gray.6', 'teal.6'];
const hace = (d: number) => new Date(Date.now() - d * 864e5).toISOString().slice(0, 10);

function Dato({ titulo, valor, ayuda, color }: { titulo: string; valor: string; ayuda: string; color?: string }) {
  return (
    <Card>
      <Text size="xs" c="dimmed" fw={600} tt="uppercase">{titulo}</Text>
      <Text fw={700} fz={24} c={color}>{valor}</Text>
      <Text size="xs" c="dimmed">{ayuda}</Text>
    </Card>
  );
}

export function Perdidas() {
  const [rango, setRango] = useState<[string | null, string | null]>([hace(60), hace(0)]);
  const [d, setD] = useState<Datos | null>(null);
  const nav = useNavigate();
  useEffect(() => {
    const [a, b] = rango;
    if (!a || !b) return;
    setD(null);
    api<Datos>(`/analisis/perdidas?desde=${a}&hasta=${b}`).then(setD).catch(avisoError);
  }, [rango]);
  const etiqueta = (m: string | null) => (m && d?.motivos[m]) || 'Sin motivo';

  return (
    <>
      <Cabecera titulo="Pérdidas" subtitulo="Lo que cuesta y no se vende: comida de personal, mermas, diferencias de inventario y platos que no salen">
        <DatePickerInput type="range" value={rango} onChange={(x) => setRango([x[0] && String(x[0]).slice(0, 10), x[1] && String(x[1]).slice(0, 10)])} valueFormat="DD/MM/YY" w={220} aria-label="Periodo" />
      </Cabecera>
      {!d ? <Text c="dimmed">Calculando…</Text> : (
        <Stack gap="lg">
          <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
            <Dato titulo="Comida de personal" valor={euros(d.personal)} ayuda="Consumo registrado en el centro Personal" />
            <Dato titulo="Mermas registradas" valor={euros(d.mermas_total)} color={d.mermas_total ? 'orange' : undefined} ayuda="Error de cocina, caducado, roturas…" />
            <Dato titulo="Salió sin registrar" valor={euros(d.diferencias_inventario)} color={d.diferencias_inventario < 0 ? 'red' : undefined} ayuda="Diferencias en los inventarios" />
            <Dato titulo="Platos que no salen" valor={String(d.platos_que_no_salen.length)} ayuda="Poco vendidos y poco margen" />
          </SimpleGrid>
          <Grid>
            <Grid.Col span={{ base: 12, md: 5 }}>
              <Card h="100%">
                <Text fw={600} mb="sm">Mermas por motivo</Text>
                {d.mermas.length ? (
                  <Stack align="center">
                    <DonutChart data={d.mermas.map((m, i) => ({ name: etiqueta(m.motivo), value: m.coste, color: COLORES[i % COLORES.length] }))}
                      valueFormatter={(x) => euros(x)} withTooltip size={170} thickness={24} />
                    <Stack gap={4} w="100%">{d.mermas.map((m) => <Group key={m.motivo} justify="space-between"><Text size="sm">{etiqueta(m.motivo)} ({m.registros})</Text><Text size="sm" fw={600}>{euros(m.coste)}</Text></Group>)}</Stack>
                  </Stack>
                ) : <Vacio texto="Sin mermas registradas en el periodo" />}
              </Card>
            </Grid.Col>
            <Grid.Col span={{ base: 12, md: 7 }}>
              <Tabla datos={d.top_mermas} clave={(m) => `${m.producto}|${m.motivo}`} exportar="mermas" porPagina={10} vacio="Sin mermas" alPulsar={(m) => nav(`/productos?codigo=${m.producto}`)}
                columnas={[
                  { clave: 'nombre', titulo: 'Lo que más se tira' },
                  { clave: 'motivo', titulo: 'Motivo', valor: (m) => etiqueta(m.motivo) },
                  { clave: 'cantidad', titulo: 'Cantidad', num: true, render: (m) => `${cantidad(m.cantidad)} ${m.unidad ?? ''}` },
                  { clave: 'coste', titulo: 'Coste', num: true, render: (m) => <Text size="sm" fw={600}>{euros(m.coste)}</Text> },
                ]} />
            </Grid.Col>
          </Grid>
          <Tabla datos={d.platos_que_no_salen} clave={(p) => p.codigo} exportar="platos_que_no_salen" vacio="Todos los platos funcionan"
            columnas={[
              { clave: 'nombre', titulo: 'Platos que no salen (poca venta y poco margen)' },
              { clave: 'servicio', titulo: 'Servicio', render: (p) => <BadgeServicio valor={p.servicio} /> },
              { clave: 'unidades', titulo: 'Vendidos', num: true },
              { clave: 'ventas_netas', titulo: 'Ventas netas', num: true, render: (p) => euros(p.ventas_netas) },
              { clave: 'margen_total', titulo: 'Margen', num: true, render: (p) => euros(p.margen_total) },
            ]} />
        </Stack>
      )}
    </>
  );
}
