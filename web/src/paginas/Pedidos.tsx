import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Alert, Badge, Button, Card, Group, Modal, NumberInput, SimpleGrid, Stack, Table, Tabs, Text, TextInput, Tooltip } from '@mantine/core';
import { BarChart } from '@mantine/charts';
import { IconAlertTriangle, IconCheck, IconCopy, IconMail } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { BadgeServicio, Cabecera, Vacio } from '../comun';
import { cantidad, euros, fecha, fechaCorta } from '../formato';
import { Tabla } from '../Tabla';

type Linea = { producto: string; nombre: string; unidad: string | null; stock: number; ritmo: number; dias_quedan: number; pedir: number;
  lote: number | null; precio: number | null; llega: string; inventario: string | null; en_camino: number };
type Pedido = { proveedor: string; email: string | null; telefono: string | null; pedido_minimo: number | null; llega: string; importe: number; lineas: Linea[] };
type Urgente = Linea & { proveedor: string; falta: number };
type Fav = { top: { codigo: string; nombre: string; servicio: string; uds_28d: number; por_dia: number; tendencia: number | null }[];
  comensales: { fecha: string; comensales: number | null }[] };

function texto(p: Pedido, cant: Record<string, number>) {
  const lineas = p.lineas.filter((l) => (cant[l.producto] ?? l.pedir) > 0)
    .map((l) => `- ${cantidad(cant[l.producto] ?? l.pedir)} ${l.unidad ?? ''}  ${l.nombre} (${l.producto})`);
  return `Buenos días,\n\nOs pasamos el pedido de Royal Marina Suites para la entrega del ${fecha(p.llega)}:\n\n${lineas.join('\n')}\n\nGracias.\nUn saludo.`;
}

function TarjetaPedido({ p, alPedir }: { p: Pedido; alPedir: () => void }) {
  const [cant, setCant] = useState<Record<string, number>>({});
  const nav = useNavigate();
  const importe = p.lineas.reduce((s, l) => s + (cant[l.producto] ?? l.pedir) * (l.precio ?? 0), 0);
  const corto = p.pedido_minimo != null && importe < p.pedido_minimo;
  const copiar = async () => { await navigator.clipboard.writeText(texto(p, cant)); avisoOk('Pégalo en el correo o en WhatsApp', 'Pedido copiado'); };
  // Guardar el pedido como hecho: deja de proponerse y se comprueba contra el albarán cuando llegue de BC.
  const pedido = async (porCorreo: boolean) => {
    try {
      await api('/pedidos', { body: { proveedor: p.proveedor, entrega: p.llega,
        lineas: p.lineas.map((l) => ({ producto: l.producto, cantidad: cant[l.producto] ?? l.pedir })) } });
      if (porCorreo) window.location.href = correo;
      avisoOk('Se comprobará con el albarán cuando llegue de BC', 'Pedido guardado');
      alPedir();
    } catch (e) { avisoError(e); }
  };
  const correo = `mailto:${p.email ?? ''}?subject=${encodeURIComponent(`Pedido Royal Marina Suites · entrega ${fecha(p.llega)}`)}&body=${encodeURIComponent(texto(p, cant))}`;
  return (
    <Card>
      <Group justify="space-between" mb="sm" wrap="wrap">
        <div>
          <Text fw={700}>{p.proveedor}</Text>
          <Text size="sm" c="dimmed">Si se pide hoy llega el {fecha(p.llega)} · {p.email ?? p.telefono ?? 'sin contacto: complétalo en Compras → Proveedores'}</Text>
        </div>
        <Group gap="xs">
          <Text fw={700} c={corto ? 'orange' : undefined}>{euros(importe)}</Text>
          {corto && <Tooltip label={`Pedido mínimo ${euros(p.pedido_minimo)}`}><IconAlertTriangle size={16} color="orange" /></Tooltip>}
          <Button size="xs" variant="default" leftSection={<IconCopy size={14} />} onClick={copiar}>Copiar</Button>
          <Button size="xs" variant="default" leftSection={<IconCheck size={14} />} onClick={() => pedido(false)}>Ya pedido</Button>
          <Button size="xs" leftSection={<IconMail size={14} />} disabled={!p.email} onClick={() => pedido(true)}>Enviar correo</Button>
        </Group>
      </Group>
      <Table.ScrollContainer minWidth={640}>
        <Table>
          <Table.Thead><Table.Tr><Table.Th>Producto</Table.Th><Table.Th className="num">Hay</Table.Th><Table.Th className="num">Gasto/día</Table.Th>
            <Table.Th className="num">Días</Table.Th><Table.Th w={140}>Pedir</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>
            {p.lineas.map((l) => (
              <Table.Tr key={l.producto}>
                <Table.Td><Text size="sm" fw={500} style={{ cursor: 'pointer' }} onClick={() => nav(`/productos?codigo=${l.producto}`)}>{l.nombre}</Text>
                  <Text size="xs" c="dimmed">{l.lote ? `Se compra de ${cantidad(l.lote)} en ${cantidad(l.lote)}` : l.producto}{l.en_camino > 0 ? ` · ${cantidad(l.en_camino)} ya pedido` : ''}</Text></Table.Td>
                <Table.Td className="num">{cantidad(l.stock)} {l.unidad}</Table.Td>
                <Table.Td className="num">{cantidad(l.ritmo)}</Table.Td>
                <Table.Td className="num"><Text size="sm" c={l.dias_quedan < 2 ? 'red' : undefined}>{l.dias_quedan}</Text></Table.Td>
                <Table.Td><NumberInput size="xs" min={0} decimalScale={2} value={cant[l.producto] ?? l.pedir} onChange={(x) => setCant({ ...cant, [l.producto]: Number(x) || 0 })}
                  rightSection={<Text size="xs" c="dimmed" pr={4}>{l.unidad}</Text>} rightSectionWidth={34} aria-label={`Pedir ${l.nombre}`} /></Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Card>
  );
}


type Enviado = { id: number; proveedor: string; fecha: string; entrega: string | null; estado: string; albaranes: string | null; usuario: string | null;
  nota: string | null; retrasado: boolean; faltan: number; lineas: { producto: string; nombre: string; unidad: string | null; cantidad: number; recibido: number }[] };
const ESTADO: Record<string, { label: string; color: string }> = {
  enviado: { label: 'En camino', color: 'blue' }, recibido: { label: 'Recibido completo', color: 'teal' },
  incompleto: { label: 'Incompleto', color: 'red' }, cerrado: { label: 'Cerrado', color: 'gray' }, anulado: { label: 'Anulado', color: 'gray' },
};

function Enviados({ lista, recargar }: { lista: Enviado[] | null; recargar: () => void }) {
  const [ver, setVer] = useState<Enviado | null>(null);
  const [nota, setNota] = useState('');
  const cerrar = async (estado: 'cerrado' | 'anulado') => {
    if (!ver) return;
    try { await api(`/pedidos/${ver.id}/cerrar`, { body: { estado, nota } }); avisoOk(ver.proveedor, estado === 'cerrado' ? 'Pedido cerrado' : 'Pedido anulado'); setVer(null); setNota(''); recargar(); }
    catch (e) { avisoError(e); }
  };
  const texto = (e: Enviado) => e.retrasado ? { label: 'Sin albarán', color: 'orange' } : ESTADO[e.estado] ?? { label: e.estado, color: 'gray' };
  return (
    <>
      <Tabla datos={lista} clave={(e) => e.id} alPulsar={setVer} exportar="pedidos_enviados" orden={{ clave: 'fecha', desc: true }} anchoMin={720}
        vacio="Aún no hay pedidos hechos desde BM" atenuar={(e) => ['cerrado', 'anulado', 'recibido'].includes(e.estado)} columnas={[
          { clave: 'fecha', titulo: 'Pedido', render: (e) => fecha(e.fecha) },
          { clave: 'proveedor', titulo: 'Proveedor' },
          { clave: 'entrega', titulo: 'Entrega', render: (e) => fecha(e.entrega) },
          { clave: 'estado', titulo: 'Estado', valor: (e) => texto(e).label, render: (e) => <Badge variant="light" color={texto(e).color}>{texto(e).label}</Badge> },
          { clave: 'faltan', titulo: 'Faltan', num: true, render: (e) => e.faltan ? <Text size="sm" fw={700} c="red">{e.faltan}</Text> : '—' },
          { clave: 'albaranes', titulo: 'Albarán BC', render: (e) => e.albaranes ?? '—' },
        ]} />
      <Modal opened={!!ver} onClose={() => setVer(null)} size="lg" centered title={ver ? `${ver.proveedor} · pedido del ${fecha(ver.fecha)}` : ''}>
        {ver && (
          <Stack>
            <Group gap="xs"><Badge variant="light" color={texto(ver).color}>{texto(ver).label}</Badge>
              <Text size="sm" c="dimmed">{ver.albaranes ? `Albarán ${ver.albaranes}` : `Entrega prevista ${fecha(ver.entrega)}`}{ver.usuario ? ` · pedido por ${ver.usuario}` : ''}</Text></Group>
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Producto</Table.Th><Table.Th className="num">Pedido</Table.Th><Table.Th className="num">Recibido</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{ver.lineas.map((l) => (
                <Table.Tr key={l.producto}><Table.Td>{l.nombre}</Table.Td><Table.Td className="num">{cantidad(l.cantidad)} {l.unidad}</Table.Td>
                  <Table.Td className="num"><Text size="sm" fw={600} c={ver.albaranes && l.recibido < l.cantidad * 0.98 ? 'red' : undefined}>{ver.albaranes ? `${cantidad(l.recibido)} ${l.unidad ?? ''}` : '—'}</Text></Table.Td></Table.Tr>
              ))}</Table.Tbody>
            </Table>
            {ver.nota && <Text size="sm" c="dimmed">{ver.nota}</Text>}
            {['enviado', 'incompleto'].includes(ver.estado) && (
              <Group align="flex-end">
                <TextInput label="Nota" placeholder={ver.estado === 'incompleto' ? 'p. ej. reclamado, lo abonan' : 'p. ej. no se llegó a enviar'} value={nota}
                  onChange={(e) => setNota(e.currentTarget.value)} style={{ flex: 1 }} />
                {ver.estado === 'incompleto' && <Button variant="light" onClick={() => cerrar('cerrado')}>Dar por cerrado</Button>}
                {ver.estado === 'enviado' && <Button variant="light" color="red" onClick={() => cerrar('anulado')}>Anular</Button>}
              </Group>
            )}
          </Stack>
        )}
      </Modal>
    </>
  );
}

export function Pedidos() {
  const [d, setD] = useState<{ pedidos: Pedido[]; urgentes: Urgente[] } | null>(null);
  const [fav, setFav] = useState<Fav | null>(null);
  const [enviados, setEnviados] = useState<Enviado[] | null>(null);
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const cargar = () => {
    api<typeof d>('/prevision/pedidos').then(setD).catch(avisoError);
    api<Enviado[]>('/pedidos').then(setEnviados).catch(avisoError);
  };
  useEffect(() => {
    cargar();
    api<Fav>('/prevision/favoritos').then(setFav).catch(avisoError);
  }, []);
  const base = d?.urgentes[0]?.inventario ?? d?.pedidos[0]?.lineas[0]?.inventario;
  return (
    <>
      <Cabecera titulo="Pedidos" subtitulo={`Qué pedir a cada proveedor para llegar a su siguiente reparto, según el consumo real${base ? ` (último inventario: ${fecha(base)})` : ''}`} />
      <Tabs value={params.get('vista') ?? 'pedidos'} onChange={(v) => v && setParams({ vista: v })}>
        <Tabs.List mb="md">
          <Tabs.Tab value="pedidos">Pedidos por proveedor ({d?.pedidos.length ?? '…'})</Tabs.Tab>
          <Tabs.Tab value="enviados">Enviados ({enviados?.filter((e) => ['enviado', 'incompleto'].includes(e.estado)).length ?? '…'} abiertos)</Tabs.Tab>
          <Tabs.Tab value="urgentes" color="red">Comprar por fuera ({d?.urgentes.length ?? '…'})</Tabs.Tab>
          <Tabs.Tab value="prevision">Previsión</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="pedidos">
          {!d ? <Text c="dimmed">Calculando…</Text> : !d.pedidos.length ? <Card><Vacio texto="No hace falta pedir nada ahora" /></Card> : (
            <Stack>{d.pedidos.map((p) => <TarjetaPedido key={p.proveedor} p={p} alPedir={cargar} />)}</Stack>
          )}
        </Tabs.Panel>
        <Tabs.Panel value="enviados"><Enviados lista={enviados} recargar={cargar} /></Tabs.Panel>
        <Tabs.Panel value="urgentes">
          <Alert color="red" icon={<IconAlertTriangle />} mb="md" title="Se acaban antes de que llegue el próximo reparto">
            Si no se compran por fuera (supermercado, cash) faltarán. La cantidad cubre hasta la entrega del proveedor más el margen de seguridad.
            Solo salen productos con stock fiable (inventario de hace 10 días o menos, o consumo registrado en BM): cuanto más se cuente, más avisa.
          </Alert>
          <Tabla datos={d?.urgentes ?? null} clave={(u) => u.producto} buscar exportar="comprar_por_fuera" alPulsar={(u) => nav(`/productos?codigo=${u.producto}`)}
            orden={{ clave: 'dias_quedan' }} anchoMin={760} vacio="Nada urgente" columnas={[
              { clave: 'nombre', titulo: 'Producto', render: (u) => <><Text size="sm" fw={500}>{u.nombre}</Text><Text size="xs" c="dimmed">{u.proveedor}</Text></> },
              { clave: 'stock', titulo: 'Queda', num: true, render: (u) => `${cantidad(u.stock)} ${u.unidad ?? ''}` },
              { clave: 'ritmo', titulo: 'Gasto/día', num: true, render: (u) => cantidad(u.ritmo) },
              { clave: 'llega', titulo: 'Próximo reparto', render: (u) => fecha(u.llega) },
              { clave: 'falta', titulo: 'Comprar', num: true, render: (u) => <Text size="sm" fw={700} c="red">{cantidad(u.falta)} {u.unidad}</Text> },
            ]} />
        </Tabs.Panel>
        <Tabs.Panel value="prevision">
          {!fav ? <Text c="dimmed">Calculando…</Text> : (
            <Stack>
              <Card>
                <Text fw={600} mb="sm">Comensales de desayuno previstos (media del mismo día de la semana)</Text>
                <BarChart h={200} data={fav.comensales.map((c) => ({ dia: fechaCorta(c.fecha), comensales: c.comensales ?? 0 }))} dataKey="dia"
                  series={[{ name: 'comensales', label: 'Comensales', color: 'var(--serie-dorado)' }]} gridAxis="y" tickLine="none" withBarValueLabel />
              </Card>
              <Tabla datos={fav.top} clave={(x) => x.codigo} buscar exportar="mas_vendidos" porPagina={15} orden={{ clave: 'uds_28d', desc: true }}
                columnas={[
                  { clave: 'nombre', titulo: 'Lo más vendido (TPV, 28 días)' },
                  { clave: 'servicio', titulo: 'Servicio', render: (x) => <BadgeServicio valor={x.servicio} /> },
                  { clave: 'uds_28d', titulo: 'Unidades', num: true },
                  { clave: 'por_dia', titulo: 'Al día', num: true },
                  { clave: 'tendencia', titulo: 'vs 28 días antes', num: true, render: (x) => x.tendencia == null ? <Badge variant="light" color="gray">nuevo</Badge>
                    : <Badge variant="light" color={x.tendencia >= 0 ? 'teal' : 'red'}>{x.tendencia > 0 ? '+' : ''}{Math.max(-100, Math.min(x.tendencia, 999))} %</Badge> },
                ]} />
            </Stack>
          )}
        </Tabs.Panel>
      </Tabs>
    </>
  );
}
