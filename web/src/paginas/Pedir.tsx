import { useEffect, useState } from 'react';
import { ActionIcon, Alert, Button, Card, Group, NumberInput, Select, Stack, Tabs, Text, Textarea } from '@mantine/core';
import { IconSend, IconTrash } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera, Vacio } from '../comun';
import { BotonEscanear, type Producto } from '../EscanearProducto';
import { ListaSolicitudes, type Solicitud } from '../Solicitudes';
import { TarjetaPedido, type Pedido } from './Pedidos';

// El jefe de restaurante: pide a administración lo que necesita y, de los proveedores que administración le haya
// autorizado (Configuración → Permisos), hace él mismo el pedido con la propuesta de BM.
export function Pedir() {
  const [productos, setProductos] = useState<Producto[]>([]);
  const [lineas, setLineas] = useState<Record<string, number | string>>({});
  const [nota, setNota] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [mias, setMias] = useState<Solicitud[] | null>(null);
  const [directos, setDirectos] = useState<{ proveedores: string[] | null; pedidos: Pedido[] } | null>(null);

  const cargar = () => {
    api<Solicitud[]>('/solicitudes').then(setMias).catch(avisoError);
    api<typeof directos>('/pedidos/directos').then(setDirectos).catch(avisoError);
  };
  useEffect(() => { cargar(); api<{ productos: Producto[] }>('/catalogo').then((c) => setProductos(c.productos)).catch(avisoError); }, []);

  const nombre = (p: string) => productos.find((x) => x.codigo === p);
  const anadir = (p: string | null) => {
    if (!p) return;
    if (lineas[p] === undefined) setLineas({ ...lineas, [p]: '' });
    setTimeout(() => document.getElementById(`sol-${p}`)?.focus(), 100);
  };
  const enviar = async () => {
    setEnviando(true);
    try {
      await api('/solicitudes', { body: { nota: nota || null,
        lineas: Object.entries(lineas).filter(([, q]) => Number(q) > 0).map(([producto, q]) => ({ producto, cantidad: Number(q) })) } });
      avisoOk('Administración lo verá en sus avisos', 'Solicitud enviada');
      setLineas({}); setNota(''); cargar();
    } catch (e) { avisoError(e); } finally { setEnviando(false); }
  };
  const listas = Object.values(lineas).filter((q) => Number(q) > 0).length;
  const pendientes = mias?.filter((s) => s.estado === 'pendiente').length ?? 0;
  const autorizados = directos?.proveedores ?? [];

  return (
    <>
      <Cabecera titulo="Pedir" subtitulo="Pide a administración lo que necesitas, o haz tú el pedido a los proveedores que te han autorizado" />
      <Tabs defaultValue="solicitar">
        <Tabs.List mb="md">
          <Tabs.Tab value="solicitar">Pedir a administración</Tabs.Tab>
          <Tabs.Tab value="mias">Mis solicitudes{pendientes ? ` (${pendientes} pendientes)` : ''}</Tabs.Tab>
          {autorizados.length > 0 && <Tabs.Tab value="directo">Pedido directo ({autorizados.length})</Tabs.Tab>}
        </Tabs.List>
        <Tabs.Panel value="solicitar">
          <Stack>
            <Group wrap="wrap">
              <BotonEscanear productos={productos} texto="Escanear" elegido={anadir} />
              <Select placeholder="Busca el producto que hace falta" searchable limit={50} value={null} onChange={anadir} style={{ flex: 1, minWidth: 220 }}
                data={productos.map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.unidad ?? 'ud'})` }))} />
            </Group>
            {!Object.keys(lineas).length && <Card><Vacio texto="Añade lo que hay que pedir" /></Card>}
            {Object.keys(lineas).map((p) => (
              <Card key={p} p="sm" withBorder>
                <Group justify="space-between" wrap="nowrap">
                  <Text fw={500} style={{ minWidth: 0 }}>{nombre(p)?.nombre ?? p}</Text>
                  <Group gap={6} wrap="nowrap">
                    <NumberInput id={`sol-${p}`} value={lineas[p]} onChange={(x) => setLineas({ ...lineas, [p]: x })} min={0} decimalScale={3} w={120} hideControls
                      placeholder="Cantidad" rightSection={<Text size="xs" c="dimmed" pr={6}>{nombre(p)?.unidad}</Text>} rightSectionWidth={40} aria-label={`Cantidad de ${nombre(p)?.nombre ?? p}`} />
                    <ActionIcon variant="subtle" color="red" aria-label="Quitar" onClick={() => { const { [p]: _, ...resto } = lineas; setLineas(resto); }}><IconTrash size={16} /></ActionIcon>
                  </Group>
                </Group>
              </Card>
            ))}
            <Textarea label="Nota para administración (opcional)" placeholder="Para el fin de semana, evento del sábado…" value={nota} onChange={(e) => setNota(e.currentTarget.value)} autosize minRows={2} />
            <Group justify="flex-end"><Button leftSection={<IconSend size={16} />} onClick={enviar} loading={enviando} disabled={!listas}>Enviar a administración</Button></Group>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="mias"><ListaSolicitudes lista={mias} /></Tabs.Panel>
        <Tabs.Panel value="directo">
          <Alert color="blue" variant="light" mb="md">Administración te ha autorizado a pedir a: <b>{autorizados.join(', ')}</b>. Esta es la propuesta de BM según lo que se gasta.</Alert>
          {!directos ? <Text c="dimmed">Calculando…</Text> : !directos.pedidos.length ? <Card><Vacio texto="No hace falta pedirles nada ahora" /></Card>
            : <Stack>{directos.pedidos.map((p) => <TarjetaPedido key={p.proveedor} p={p} alPedir={cargar} />)}</Stack>}
        </Tabs.Panel>
      </Tabs>
    </>
  );
}
