import { useEffect, useState } from 'react';
import { ActionIcon, Affix, Badge, Button, Card, Chip, Drawer, Group, SegmentedControl, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { IconSend, IconToolsKitchen2, IconTrash } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { cantidad as fmt, hoy } from '../formato';
import { enviarOGuardar } from '../pendientes';
import { Boton, Personalizar, resumen, type Catalogo, type Dia, type Item } from './Comandas';

type Plato = { nombre: string; cantidad: number; extras: [string, number][]; omitir: string[] };
const BORRADOR = 'bm.comandero';  // la cesta sin enviar sobrevive a un bloqueo del móvil
const leer = (): { mesa: string; cesta: Plato[] } => { try { return JSON.parse(localStorage.getItem(BORRADOR) ?? ''); } catch { return { mesa: '', cesta: [] }; } };

// Comandero digital en el móvil de la empresa: mesa, platos con un toque, cesta y «Enviar». Se registra igual que las
// comandas en papel (consumo, coste y comensales: cada plato es un huésped). Sin cobertura se envía solo después.
export function Comandero() {
  const [d, setD] = useState<Dia | null>(null);
  const [cat, setCat] = useState<Catalogo | null>(null);
  const [{ mesa, cesta }, setEstado] = useState(leer);
  const [tab, setTab] = useState('platos');
  const [plato, setPlato] = useState<Item | null>(null);
  const [verCesta, setVerCesta] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const guardar = (e: { mesa: string; cesta: Plato[] }) => { setEstado(e); try { localStorage.setItem(BORRADOR, JSON.stringify(e)); } catch { /* sin almacenamiento */ } };
  const cargar = () => api<Dia>(`/comandas?fecha=${hoy()}`).then((x) => { setD(x); if (x.catalogo) setCat(x.catalogo); }).catch(avisoError);
  useEffect(() => { cargar(); }, []);

  const anadir = (nombre: string, cantidad = 1, extras: [string, number][] = [], omitir: string[] = []) => {
    setPlato(null);
    navigator.vibrate?.(30);
    guardar({ mesa, cesta: [...cesta, { nombre, cantidad, extras, omitir }] });
  };
  const enviar = async () => {
    setEnviando(true);
    try {
      const n = cesta.reduce((s, p) => s + p.cantidad, 0);
      const r = await enviarOGuardar('/comandas/mesa', { fecha: hoy(), mesa: mesa || null, lineas: cesta }, `Mesa ${mesa || '—'}: ${fmt(n)} platos`);
      avisoOk(r === 'enviado' ? `${fmt(n)} platos apuntados` : 'Sin cobertura: se enviará solo al volver la conexión', `Mesa ${mesa || '—'}`);
      guardar({ mesa: '', cesta: [] }); setVerCesta(false); cargar();
    } catch (e) { avisoError(e); } finally { setEnviando(false); }
  };
  const mesas = [...new Set((d?.lineas ?? []).map((l) => l.mesa).filter((m): m is string => !!m))].sort((a, b) => a.localeCompare(b, 'es', { numeric: true }));
  const yaEnviado = (d?.lineas ?? []).filter((l) => mesa && l.mesa === mesa);
  const lista = tab === 'platos' ? cat?.platos ?? [] : tab === 'bebidas' ? cat?.bebidas ?? [] : (cat?.extras ?? []).map((a) => ({ nombre: a.etiqueta, uso: a.uso, ingredientes: [] }));

  return (
    <Stack pb={90}>
      <Group justify="space-between" wrap="nowrap">
        <Text fz={22} fw={700}>Comandero</Text>
        <Badge size="lg" variant="light" leftSection={<IconToolsKitchen2 size={14} />}>{d?.comensales ?? '…'} comensales hoy</Badge>
      </Group>
      <TextInput size="lg" label="Mesa o habitación" placeholder="Ej.: 12 o 305" inputMode="numeric" value={mesa}
        onChange={(e) => guardar({ mesa: e.currentTarget.value, cesta })} />
      {mesas.length > 0 && (
        <Chip.Group value={mesa} onChange={(v) => guardar({ mesa: v as string, cesta })}>
          <Group gap={6}>{mesas.map((m) => <Chip key={m} value={m} size="sm">{m}</Chip>)}</Group>
        </Chip.Group>
      )}
      {yaEnviado.length > 0 && (
        <Text size="xs" c="dimmed">Ya enviado de la mesa {mesa}: {yaEnviado.map((l) => `${l.cantidad !== 1 ? `${fmt(l.cantidad)} × ` : ''}${l.nombre}`).join(', ')}</Text>
      )}
      <SegmentedControl fullWidth size="md" value={tab} onChange={setTab}
        data={[{ value: 'platos', label: 'Platos' }, { value: 'bebidas', label: 'Bebidas' }, { value: 'sueltos', label: 'Sueltos' }]} />
      {!cat ? <Text c="dimmed">Cargando…</Text> : (
        <SimpleGrid cols={2} spacing="sm">
          {lista.map((p) => tab === 'platos'
            ? <Boton key={p.nombre} nombre={p.nombre} onClick={() => setPlato(p)} onMas={() => anadir(p.nombre)} />
            : <Boton key={p.nombre} nombre={p.nombre} onClick={() => anadir(p.nombre)} />)}
        </SimpleGrid>
      )}
      <Affix position={{ bottom: 16, left: 16, right: 16 }}>
        <Button fullWidth size="lg" radius="xl" disabled={!cesta.length} onClick={() => setVerCesta(true)} style={{ boxShadow: 'var(--mantine-shadow-lg)' }}>
          {cesta.length ? `Cesta: ${cesta.length} · enviar mesa ${mesa || '…'}` : 'Toca los platos para apuntarlos'}
        </Button>
      </Affix>
      <Drawer opened={verCesta} onClose={() => setVerCesta(false)} position="bottom" size="auto" title={<Text fw={700}>Mesa {mesa || 'sin número'}</Text>}>
        <Stack gap="xs">
          {cesta.map((p, i) => {
            const detalle = resumen({ ...p, id: 0, hora: '', mesa: null });
            return (
              <Card key={i} p="xs" withBorder>
                <Group justify="space-between" wrap="nowrap">
                  <div style={{ minWidth: 0 }}>
                    <Text fw={600}>{p.cantidad !== 1 ? `${p.cantidad} × ` : ''}{p.nombre}</Text>
                    {detalle && <Text size="xs" c="dimmed">{detalle}</Text>}
                  </div>
                  <ActionIcon variant="subtle" color="red" aria-label={`Quitar ${p.nombre}`} onClick={() => guardar({ mesa, cesta: cesta.filter((_, j) => j !== i) })}><IconTrash size={18} /></ActionIcon>
                </Group>
              </Card>
            );
          })}
          {!mesa && <Text size="sm" c="orange">Sin número de mesa: se apuntará igual, pero mejor ponerlo.</Text>}
          <Button size="lg" leftSection={<IconSend size={20} />} onClick={enviar} loading={enviando} disabled={!cesta.length}>Enviar mesa {mesa || ''}</Button>
        </Stack>
      </Drawer>
      {plato && cat && <Personalizar plato={plato} cat={cat} cerrar={() => setPlato(null)} anadir={(n, e, o) => anadir(plato.nombre, n, e, o)} />}
    </Stack>
  );
}
