import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Card, Grid, Group, Select, Stack, Text } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { BarChart } from '@mantine/charts';
import { IconInfoCircle } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera } from '../comun';
import { nombreUbicacion, useUbicaciones } from '../centros';
import { cantidad, euros } from '../formato';
import { Tabla } from '../Tabla';

type Datos = {
  productos: { producto: string; ubicacion: string; nombre: string; unidad: string | null; diferencia: number; valor: number; recuentos: number }[];
  por_ubicacion: { ubicacion: string; valor: number }[]; por_mes: { mes: string; valor: number }[]; total: number;
};
const hace = (d: number) => new Date(Date.now() - d * 864e5).toISOString().slice(0, 10);

export function Control() {
  const ubicaciones = useUbicaciones();
  const [rango, setRango] = useState<[string | null, string | null]>([hace(120), hace(0)]);
  const [ub, setUb] = useState<string | null>(null);
  const [d, setD] = useState<Datos | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    const [a, b] = rango;
    if (!a || !b) return;
    setD(null);
    api<Datos>(`/analisis/control?desde=${a}&hasta=${b}${ub ? `&ubicacion=${encodeURIComponent(ub)}` : ''}`).then(setD).catch(avisoError);
  }, [rango, ub]);

  return (
    <>
      <Cabecera titulo="Control de stock" subtitulo="Lo que se contó en cada inventario frente a lo que BM esperaba según compras, traslados y consumos registrados">
        <Select placeholder="Todas las ubicaciones" clearable searchable w={210} value={ub} onChange={setUb}
          data={ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }))} />
        <DatePickerInput type="range" value={rango} onChange={(x) => setRango([x[0] && String(x[0]).slice(0, 10), x[1] && String(x[1]).slice(0, 10)])}
          valueFormat="DD/MM/YY" w={220} aria-label="Periodo" />
      </Cabecera>
      <Stack gap="lg">
        <Alert icon={<IconInfoCircle />} color="blue">
          Una diferencia negativa es producto que salió sin registrarse en BM: consumo no anotado, merma, invitaciones o pérdidas.
          Mientras no se registre todo el consumo en BM, aquí aparece también ese consumo. La meta es que solo queden mermas reales.
        </Alert>
        <Grid>
          <Grid.Col span={{ base: 12, md: 4 }}>
            <Card h="100%">
              <Text size="xs" c="dimmed" fw={600} tt="uppercase">Diferencia total del periodo</Text>
              <Text fw={700} fz={30} c={(d?.total ?? 0) < 0 ? 'red' : 'teal'}>{d ? euros(d.total) : '…'}</Text>
              <Stack gap={4} mt="md">
                {d?.por_mes.map((m) => <Group key={m.mes} justify="space-between"><Text size="sm">{m.mes}</Text><Text size="sm" fw={600}>{euros(m.valor)}</Text></Group>)}
              </Stack>
            </Card>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 8 }}>
            <Card h="100%">
              <Text fw={600} mb="sm">Por ubicación</Text>
              {d && d.por_ubicacion.length ? (
                <BarChart h={Math.max(160, d.por_ubicacion.slice(0, 8).length * 36)} orientation="vertical" dataKey="nombre" gridAxis="x"
                  data={d.por_ubicacion.slice(0, 8).map((x) => ({ nombre: nombreUbicacion(ubicaciones, x.ubicacion), valor: x.valor }))}
                  series={[{ name: 'valor', label: 'Diferencia', color: 'red.6' }]} valueFormatter={(x) => euros(x)} yAxisProps={{ width: 110 }} />
              ) : <Text c="dimmed">{d ? 'Sin inventarios en el periodo' : 'Cargando…'}</Text>}
            </Card>
          </Grid.Col>
        </Grid>
        <Tabla datos={d?.productos ?? null} clave={(p) => `${p.producto}|${p.ubicacion}`} buscar="Buscar producto" exportar="control_stock"
          orden={{ clave: 'valor' }} alPulsar={(p) => nav(`/productos?codigo=${p.producto}`)} vacio="Sin diferencias en el periodo"
          columnas={[
            { clave: 'nombre', titulo: 'Producto', render: (p) => <><Text size="sm" fw={500}>{p.nombre}</Text><Text size="xs" c="dimmed">{p.producto}</Text></> },
            { clave: 'ubicacion', titulo: 'Ubicación', valor: (p) => nombreUbicacion(ubicaciones, p.ubicacion) },
            { clave: 'recuentos', titulo: 'Inventarios', num: true },
            { clave: 'diferencia', titulo: 'Diferencia', num: true, render: (p) => <Text size="sm" c={p.diferencia < 0 ? 'red' : 'teal'}>{p.diferencia > 0 ? '+' : ''}{cantidad(p.diferencia)} {p.unidad}</Text> },
            { clave: 'valor', titulo: 'Valor', num: true, render: (p) => <Text size="sm" fw={600} c={p.valor < 0 ? 'red' : 'teal'}>{euros(p.valor)}</Text> },
          ]} />
      </Stack>
    </>
  );
}
