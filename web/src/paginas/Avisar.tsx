import { useEffect, useState } from 'react';
import { ActionIcon, Button, Card, Group, NumberInput, SegmentedControl, Select, Stack, Tabs, Text, Textarea } from '@mantine/core';
import { IconSend, IconTrash } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera, Vacio } from '../comun';
import { BotonEscanear, type Producto } from '../EscanearProducto';
import { ListaSolicitudes, type Solicitud } from '../Solicitudes';

// Camareros y cocineros avisan al jefe de lo que queda poco o recomiendan pedir algo. El jefe decide.
export function Avisar() {
  const [tipo, setTipo] = useState<'queda_poco' | 'pedido'>('queda_poco');
  const [productos, setProductos] = useState<Producto[]>([]);
  const [lineas, setLineas] = useState<Record<string, number | string>>({});
  const [nota, setNota] = useState('');
  const [enviando, setEnviando] = useState(false);
  const [mios, setMios] = useState<Solicitud[] | null>(null);
  const cargar = () => api<Solicitud[]>('/solicitudes?de=mias').then(setMios).catch(avisoError);
  useEffect(() => { cargar(); api<{ productos: Producto[] }>('/catalogo').then((c) => setProductos(c.productos)).catch(avisoError); }, []);

  const p = (c: string) => productos.find((x) => x.codigo === c);
  const anadir = (c: string | null) => {
    if (!c) return;
    if (lineas[c] === undefined) setLineas({ ...lineas, [c]: '' });
    setTimeout(() => document.getElementById(`av-${c}`)?.focus(), 100);
  };
  const enviar = async () => {
    setEnviando(true);
    try {
      await api('/solicitudes', { body: { para: 'jefe', tipo, nota: nota || null,
        lineas: Object.entries(lineas).map(([producto, q]) => ({ producto, cantidad: q === '' ? null : Number(q) })) } });
      avisoOk('El jefe de restaurante lo verá en sus avisos', 'Aviso enviado');
      setLineas({}); setNota(''); cargar();
    } catch (e) { avisoError(e); } finally { setEnviando(false); }
  };
  const vacio = tipo === 'pedido' ? !Object.values(lineas).some((q) => Number(q) > 0) : !Object.keys(lineas).length;

  return (
    <>
      <Cabecera titulo="Avisar al jefe" subtitulo="Si algo se acaba o crees que hay que pedirlo, avísale desde aquí" />
      <Tabs defaultValue="avisar">
        <Tabs.List mb="md"><Tabs.Tab value="avisar">Avisar</Tabs.Tab><Tabs.Tab value="mios">Mis avisos</Tabs.Tab></Tabs.List>
        <Tabs.Panel value="avisar">
          <Stack>
            <SegmentedControl fullWidth value={tipo} onChange={(v) => setTipo(v as typeof tipo)}
              data={[{ value: 'queda_poco', label: 'Queda poco' }, { value: 'pedido', label: 'Recomiendo pedir' }]} />
            <Group wrap="wrap">
              <BotonEscanear productos={productos} texto="Escanear" elegido={anadir} />
              <Select placeholder="Busca el producto" searchable limit={50} value={null} onChange={anadir} style={{ flex: 1, minWidth: 200 }}
                data={productos.map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.unidad ?? 'ud'})` }))} />
            </Group>
            {!Object.keys(lineas).length && <Card><Vacio texto={tipo === 'queda_poco' ? 'Escanea o busca lo que se está acabando' : 'Escanea o busca lo que habría que pedir'} /></Card>}
            {Object.keys(lineas).map((c) => (
              <Card key={c} p="sm" withBorder>
                <Group justify="space-between" wrap="nowrap">
                  <Text fw={500} style={{ minWidth: 0 }}>{p(c)?.nombre ?? c}</Text>
                  <Group gap={6} wrap="nowrap">
                    <NumberInput id={`av-${c}`} value={lineas[c]} onChange={(x) => setLineas({ ...lineas, [c]: x })} min={0} decimalScale={3} w={130} hideControls
                      placeholder={tipo === 'queda_poco' ? '¿Cuánto queda?' : '¿Cuánto pedir?'} aria-label={`Cantidad de ${p(c)?.nombre ?? c}`}
                      rightSection={<Text size="xs" c="dimmed" pr={6}>{p(c)?.unidad}</Text>} rightSectionWidth={40} />
                    <ActionIcon variant="subtle" color="red" aria-label="Quitar" onClick={() => { const { [c]: _, ...resto } = lineas; setLineas(resto); }}><IconTrash size={16} /></ActionIcon>
                  </Group>
                </Group>
              </Card>
            ))}
            {tipo === 'queda_poco' && Object.keys(lineas).length > 0 && <Text size="xs" c="dimmed">Si no sabes cuánto queda, déjalo en blanco.</Text>}
            <Textarea label="Nota (opcional)" placeholder="Lo piden mucho, se ha roto una caja…" value={nota} onChange={(e) => setNota(e.currentTarget.value)} autosize minRows={2} />
            <Button size="md" leftSection={<IconSend size={18} />} onClick={enviar} loading={enviando} disabled={vacio}>Avisar al jefe</Button>
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="mios"><ListaSolicitudes lista={mios} /></Tabs.Panel>
      </Tabs>
    </>
  );
}
