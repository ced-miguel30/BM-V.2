import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Alert, Anchor, Badge, Button, Card, Group, Stack, Tabs, Text, ThemeIcon } from '@mantine/core';
import { MonthPickerInput } from '@mantine/dates';
import { IconAlertTriangle, IconCheck, IconFileText, IconX } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera } from '../comun';
import { Tabla } from '../Tabla';
import { cantidad, euros, fecha } from '../formato';
import { nombreUbicacion, useUbicaciones } from '../centros';

type Paso = { clave: string; titulo: string; ok: boolean; detalle: string; ruta: string; obligatorio: boolean };
const mesAnterior = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return d.toISOString().slice(0, 7); };

type LineaNoray = { almacen: string; producto: string; nombre: string; unidad: string | null; calculada: number; fisica: number; diferencia: number; valor_diferencia: number | null; origen: string };
type Recomendado = { producto: string; nombre: string; unidad: string | null; stock: number; valor: number | null; motivos: string[]; ultimo_recuento: string | null };
type Raro = { tipo: string; producto: string; nombre: string; impacto: number; detalle: string };

// Lo que administración pega en el diario de inventario físico de Noray: «Cantidad física» por almacén y producto.
function ParaNoray({ mes }: { mes: string }) {
  const [d, setD] = useState<{ fecha: string; lineas: LineaNoray[] } | null>(null);
  useEffect(() => { setD(null); api<{ fecha: string; lineas: LineaNoray[] }>(`/cierre/noray?mes=${mes}`).then(setD).catch(avisoError); }, [mes]);
  const total = d?.lineas.reduce((s, l) => s + (l.valor_diferencia ?? 0), 0) ?? 0;
  return (
    <Stack>
      <Alert color="blue" variant="light">
        Cantidad de cada producto en cada almacén de Noray a <b>{d ? fecha(d.fecha) : '…'}</b>. Lo del restaurante se reparte entre DESAYUNO, SNACK…
        según lo que Noray tiene en cada uno menos lo que BM ha visto gastar a cada centro. En Noray: diario de inventario físico →
        «Calcular inventario» → copiar la columna <b>Cantidad física</b> (exporta esta tabla a Excel) → revisar → registrar.
        Diferencia total: <b>{euros(total)}</b>.
      </Alert>
      <Tabla datos={d?.lineas ?? null} clave={(l) => `${l.almacen}|${l.producto}`} exportar={`noray_inventario_${mes}`} porPagina={25}
        vacio="Nada que pasar a Noray" columnas={[
          { clave: 'almacen', titulo: 'Almacén' },
          { clave: 'producto', titulo: 'Nº producto' },
          { clave: 'nombre', titulo: 'Descripción' },
          { clave: 'calculada', titulo: 'Cantidad (calculada)', num: true, render: (l) => `${cantidad(l.calculada)} ${l.unidad ?? ''}` },
          { clave: 'fisica', titulo: 'Cantidad física', num: true, render: (l) => <Text size="sm" fw={600}>{cantidad(l.fisica)}</Text> },
          { clave: 'diferencia', titulo: 'Diferencia', num: true, render: (l) => <Text size="sm" c={l.diferencia < 0 ? 'red' : l.diferencia > 0 ? 'teal' : 'dimmed'}>{l.diferencia > 0 ? '+' : ''}{cantidad(l.diferencia)}</Text> },
          { clave: 'valor_diferencia', titulo: '€', num: true, render: (l) => euros(l.valor_diferencia) },
          { clave: 'origen', titulo: 'De dónde sale', render: (l) => <Text size="xs" c={l.origen.startsWith('Contado') ? 'teal' : 'dimmed'}>{l.origen}</Text> },
        ]} />
    </Stack>
  );
}

// Fresco y caro sin contar este mes: lo que conviene contar en recuentos pequeños; lo demás va calculado.
function Contar({ mes }: { mes: string }) {
  const ubicaciones = useUbicaciones();
  const nav = useNavigate();
  const [d, setD] = useState<[string, Recomendado[]][] | null>(null);
  useEffect(() => {
    setD(null);
    Promise.all(['ECONOMATO', 'RESTAURANTE'].map((u) => api<Recomendado[]>(`/cierre/recomendados?ubicacion=${u}&desde=${mes}-01`).then((x) => [u, x] as [string, Recomendado[]])))
      .then(setD).catch(avisoError);
  }, [mes]);
  if (!d) return <Text c="dimmed">Calculando…</Text>;
  return (
    <Stack>
      <Text size="sm" c="dimmed">Lo fresco (se compra casi cada semana) y lo caro (los pocos productos que suman la mitad del valor) se cuentan a mano;
        el resto lo calcula BM. Mejor poco a poco durante el mes, en recuentos de una nevera o una estantería.</Text>
      {d.map(([u, xs]) => (
        <Card key={u}>
          <Group justify="space-between" mb="sm">
            <Text fw={600}>{nombreUbicacion(ubicaciones, u)}: {xs.length ? `faltan ${xs.length}` : 'todo contado'}</Text>
            {xs.length > 0 && <Button size="xs" onClick={() => nav(`/recuento?ubicacion=${u}&recomendados=1`)}>Ir a contar</Button>}
          </Group>
          <Tabla datos={xs} clave={(x) => x.producto} exportar={`contar_${u}_${mes}`} porPagina={10} orden={{ clave: 'valor', desc: true }} columnas={[
            { clave: 'nombre', titulo: 'Producto' },
            { clave: 'motivos', titulo: 'Por qué', valor: (x) => x.motivos.join(', '),
              render: (x) => <Group gap={4}>{x.motivos.map((m) => <Badge key={m} size="xs" variant="light" color={m === 'caro' ? 'grape' : 'green'}>{m}</Badge>)}</Group> },
            { clave: 'stock', titulo: 'BM calcula', num: true, render: (x) => `${cantidad(x.stock)} ${x.unidad ?? ''}` },
            { clave: 'valor', titulo: 'Valor', num: true, render: (x) => euros(x.valor) },
            { clave: 'ultimo_recuento', titulo: 'Último recuento', render: (x) => (x.ultimo_recuento ? fecha(x.ultimo_recuento) : 'nunca') },
          ]} />
        </Card>
      ))}
    </Stack>
  );
}

function Revisar() {
  const [d, setD] = useState<Raro[] | null>(null);
  useEffect(() => { api<Raro[]>('/anomalias').then(setD).catch(avisoError); }, []);
  return (
    <Stack>
      <Text size="sm" c="dimmed">Productos cuyo consumo registrado se sale de lo normal, o que al contarlos no cuadraron con lo que gastaron las recetas.
        Cuéntalos de nuevo y, si se repite, ajusta la receta.</Text>
      <Tabla datos={d} clave={(x) => `${x.tipo}|${x.producto}`} exportar="revisar" orden={{ clave: 'impacto', desc: true }} vacio="Nada raro" columnas={[
        { clave: 'nombre', titulo: 'Producto' },
        { clave: 'tipo', titulo: 'Qué pasa', valor: (x) => (x.tipo === 'actividad' ? 'Actividad rara' : 'No cuadra al contar'),
          render: (x) => <Badge variant="light" color={x.tipo === 'actividad' ? 'orange' : 'red'}>{x.tipo === 'actividad' ? 'Actividad rara' : 'No cuadra al contar'}</Badge> },
        { clave: 'detalle', titulo: 'Detalle', render: (x) => <Text size="sm">{x.detalle}</Text> },
        { clave: 'impacto', titulo: 'Impacto', num: true, render: (x) => euros(x.impacto) },
      ]} />
    </Stack>
  );
}

export function Cierre() {
  const [mes, setMes] = useState(mesAnterior());
  const [d, setD] = useState<{ pasos: Paso[]; listo: boolean } | null>(null);
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const vista = params.get('vista') ?? 'pasos';
  useEffect(() => { setD(null); api<typeof d>(`/cierre?mes=${mes}`).then(setD).catch(avisoError); }, [mes]);
  const hechos = d?.pasos.filter((p) => p.ok).length ?? 0;
  return (
    <>
      <Cabecera titulo="Cierre de mes" subtitulo="Lo que hace falta para que los números del mes sean definitivos. BM lo comprueba solo.">
        <MonthPickerInput value={`${mes}-01`} onChange={(x) => x && setMes(String(x).slice(0, 7))} valueFormat="MMMM YYYY" w={180} aria-label="Mes" />
        <Button leftSection={<IconFileText size={16} />} onClick={() => nav(`/informe?mes=${mes}`)}>Informe del mes</Button>
      </Cabecera>
      <Tabs value={vista} onChange={(v) => v && setParams({ vista: v })} mb="md">
        <Tabs.List>
          <Tabs.Tab value="pasos">Pasos</Tabs.Tab>
          <Tabs.Tab value="contar">Contar antes del cierre</Tabs.Tab>
          <Tabs.Tab value="revisar">Revisar</Tabs.Tab>
          <Tabs.Tab value="noray">Para Noray</Tabs.Tab>
        </Tabs.List>
      </Tabs>
      {vista === 'noray' ? <ParaNoray mes={mes} /> : vista === 'contar' ? <Contar mes={mes} /> : vista === 'revisar' ? <Revisar />
        : !d ? <Text c="dimmed">Comprobando…</Text> : (
        <Stack>
          {d.listo ? <Alert color="teal" icon={<IconCheck />} title="Mes listo para cerrar">Los datos del mes están completos. El informe ya es definitivo.</Alert>
            : <Alert color="orange" icon={<IconAlertTriangle />} title={`${hechos} de ${d.pasos.length} pasos completos`}>Hasta completar los obligatorios, las cifras del mes pueden cambiar.</Alert>}
          {d.pasos.map((p, i) => (
            <Card key={p.clave} p="md">
              <Group justify="space-between" wrap="nowrap">
                <Group wrap="nowrap" gap="md">
                  <ThemeIcon radius="xl" size={34} color={p.ok ? 'teal' : p.obligatorio ? 'red' : 'yellow'} variant={p.ok ? 'filled' : 'light'}>
                    {p.ok ? <IconCheck size={18} /> : p.obligatorio ? <IconX size={18} /> : <IconAlertTriangle size={18} />}
                  </ThemeIcon>
                  <div>
                    <Group gap={6}><Text fw={600}>{i + 1}. {p.titulo}</Text>{!p.obligatorio && <Badge size="xs" variant="light" color="gray">recomendado</Badge>}</Group>
                    <Text size="sm" c="dimmed">{p.detalle}</Text>
                  </div>
                </Group>
                {!p.ok && <Anchor size="sm" onClick={() => nav(p.ruta)} style={{ whiteSpace: 'nowrap' }}>Ir a resolverlo →</Anchor>}
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </>
  );
}
