import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Button, Card, Group, Select, SimpleGrid, Text, Tooltip } from '@mantine/core';
import { IconClipboardCheck } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera } from '../comun';
import { useUbicaciones } from '../centros';
import { cantidad, euros, fecha } from '../formato';
import { Tabla } from '../Tabla';

type Fila = {
  producto: string; ubicacion: string; nombre: string; unidad: string | null; stock: number; ultimo_recuento: string | null;
  fuente_recuento: string | null; desviacion: number | null; salidas_desde_recuento: number; precio?: number | null;
  valor?: number | null; desviacion_valor?: number | null;
};

function Dato({ titulo, valor, ayuda, color }: { titulo: string; valor: string; ayuda?: string; color?: string }) {
  return (
    <Card>
      <Text size="xs" c="dimmed" fw={600} tt="uppercase" lts={0.5}>{titulo}</Text>
      <Text fw={700} fz={22} mt={4} c={color} style={{ fontVariantNumeric: 'tabular-nums' }}>{valor}</Text>
      {ayuda && <Text size="xs" c="dimmed" mt={2}>{ayuda}</Text>}
    </Card>
  );
}

export function Stock() {
  const ubicaciones = useUbicaciones();
  const [params, setParams] = useSearchParams();
  const ub = params.get('ubicacion') ?? 'ECONOMATO';
  const [filas, setFilas] = useState<Fila[] | null>(null);
  const [soloStock, setSoloStock] = useState<string | null>('con');
  const nav = useNavigate();

  useEffect(() => { setFilas(null); api<Fila[]>(`/stock?ubicacion=${encodeURIComponent(ub)}`).then(setFilas).catch(avisoError); }, [ub]);

  const visibles = useMemo(() => (filas ?? []).filter((f) =>
    soloStock === 'con' ? f.stock > 1e-6 : soloStock === 'negativo' ? f.stock < -1e-6 : soloStock === 'desviacion' ? (f.desviacion ?? 0) < 0 : true), [filas, soloStock]);
  const valor = (filas ?? []).reduce((s, f) => s + (f.valor ?? 0), 0);
  const negativos = (filas ?? []).filter((f) => f.stock < -1e-6).length;
  const ultimo = (filas ?? []).reduce<string | null>((m, f) => (f.ultimo_recuento && (!m || f.ultimo_recuento > m) ? f.ultimo_recuento : m), null);
  // Solo el recuento más reciente: lo que faltó (o sobró) respecto a lo registrado en BM.
  const desv = (filas ?? []).filter((f) => f.ultimo_recuento === ultimo).reduce((s, f) => s + (f.desviacion_valor ?? 0), 0);

  return (
    <>
      <Cabecera titulo="Stock" subtitulo="Teórico por ubicación: último recuento + entradas − consumos registrados">
        <Select data={ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }))} value={ub} searchable w={220}
          onChange={(x) => x && setParams({ ubicacion: x })} aria-label="Ubicación" />
        <Button leftSection={<IconClipboardCheck size={16} />} onClick={() => nav(`/recuento?ubicacion=${encodeURIComponent(ub)}`)}>Contar esta ubicación</Button>
      </Cabecera>
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="lg">
        <Dato titulo="Valor en stock" valor={euros(valor)} ayuda="A precio de la última compra" />
        <Dato titulo="Productos con stock" valor={(filas ?? []).filter((f) => f.stock > 1e-6).length.toLocaleString('es-ES')} />
        <Dato titulo="No registrado en BM" valor={euros(desv)} color={desv < 0 ? 'red' : undefined}
          ayuda={ultimo ? `Diferencia del recuento del ${fecha(ultimo)}` : 'Sin recuentos'} />
        <Dato titulo="Stock negativo" valor={String(negativos)} color={negativos ? 'orange' : undefined} ayuda="Consumos sin entrada registrada" />
      </SimpleGrid>
      <Tabla datos={filas ? visibles : null} clave={(f) => f.producto} buscar="Buscar producto" exportar={`stock_${ub}`}
        alPulsar={(f) => nav(`/productos?codigo=${f.producto}`)} orden={{ clave: 'nombre' }}
        filtros={<Select value={soloStock} onChange={setSoloStock} w={210} allowDeselect={false} data={[
          { value: 'con', label: 'Con stock' }, { value: 'desviacion', label: 'Con pérdida en recuento' },
          { value: 'negativo', label: 'Stock negativo' }, { value: 'todos', label: 'Todos' }]} />}
        columnas={[
          { clave: 'nombre', titulo: 'Producto', render: (f) => <><Text size="sm" fw={500}>{f.nombre}</Text><Text size="xs" c="dimmed">{f.producto}</Text></> },
          { clave: 'stock', titulo: 'Stock', num: true, render: (f) => <Text size="sm" fw={600} c={f.stock < 0 ? 'orange' : undefined}>{cantidad(f.stock)} {f.unidad}</Text> },
          { clave: 'ultimo_recuento', titulo: 'Último recuento', render: (f) => f.ultimo_recuento ? (
            <Group gap={6} wrap="nowrap"><Text size="sm">{fecha(f.ultimo_recuento)}</Text>
              <Badge size="xs" variant="light" color={f.fuente_recuento === 'recuento' ? 'teal' : 'gray'}>{f.fuente_recuento === 'recuento' ? 'BM' : 'BC'}</Badge></Group>) : <Text size="sm" c="dimmed">Nunca</Text> },
          { clave: 'desviacion', titulo: 'Diferencia al contar', num: true, render: (f) => f.desviacion == null ? '—' : (
            <Tooltip label={f.desviacion_valor != null ? euros(f.desviacion_valor) : 'Sin precio'}>
              <Text size="sm" c={f.desviacion < 0 ? 'red' : f.desviacion > 0 ? 'teal' : undefined}>{f.desviacion > 0 ? '+' : ''}{cantidad(f.desviacion)}</Text>
            </Tooltip>) },
          { clave: 'desviacion_valor', titulo: 'Diferencia €', num: true, render: (f) => <Text size="sm" c={(f.desviacion_valor ?? 0) < 0 ? 'red' : undefined}>{euros(f.desviacion_valor)}</Text> },
          { clave: 'salidas_desde_recuento', titulo: 'Salidas registradas', num: true, render: (f) => cantidad(f.salidas_desde_recuento) },
          { clave: 'valor', titulo: 'Valor', num: true, render: (f) => <Text size="sm" fw={600}>{euros(f.valor)}</Text> },
        ]} />
    </>
  );
}
