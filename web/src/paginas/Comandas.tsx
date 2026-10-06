import { useEffect, useState } from 'react';
import {
  ActionIcon, Badge, Button, Card, Grid, Group, Modal, ScrollArea, SegmentedControl, SimpleGrid, Stack, Text, UnstyledButton,
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconMinus, IconPlus, IconTrash, IconUsers } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { cantidad as fmt, hoy } from '../formato';

type Item = { nombre: string; uso: number; ingredientes: string[] };
type Atajo = { etiqueta: string; grupo: string; sustituye: string | null; uso: number };
type Catalogo = { platos: Item[]; bebidas: Item[]; extras: Atajo[]; sustituir: Atajo[]; quitar: Atajo[] };
type Linea = { id: number; hora: string; nombre: string; cantidad: number; extras: [string, number][]; omitir: string[] };
type Dia = { fecha: string; comensales: number; lineas: Linea[]; platos: number; catalogo?: Catalogo };

function Boton({ nombre, onClick, onMas }: { nombre: string; onClick: () => void; onMas?: () => void }) {
  return (
    <Card p={0} withBorder style={{ position: 'relative' }}>
      <UnstyledButton onClick={onClick} p="md" w="100%" h={84} style={{ display: 'flex', alignItems: 'center' }}>
        <Text fw={600} size="md" lh={1.2} pr={onMas ? 36 : 0}>{nombre}</Text>
      </UnstyledButton>
      {onMas && (
        <ActionIcon variant="light" size="lg" radius="xl" onClick={onMas} aria-label={`Añadir ${nombre} sin cambios`}
          style={{ position: 'absolute', top: 8, right: 8 }}><IconPlus size={18} /></ActionIcon>
      )}
    </Card>
  );
}

function resumen(l: Linea) {
  return [...l.extras.map(([e, n]) => `+${n > 1 ? `${n} ` : ''}${e}`), ...l.omitir.map((o) => (o.toLowerCase().startsWith('sin') ? o : `sin ${o}`))].join(' · ');
}

function Personalizar({ plato, cat, cerrar, anadir }: { plato: Item; cat: Catalogo; cerrar: () => void;
  anadir: (cantidad: number, extras: [string, number][], omitir: string[]) => void }) {
  const [n, setN] = useState(1);
  const [extras, setExtras] = useState<Record<string, number>>({});
  const [cambio, setCambio] = useState<Record<string, string>>({});
  const [quitar, setQuitar] = useState<string[]>([]);
  const grupos = [...new Set(cat.sustituir.map((a) => a.sustituye!))];
  const toggle = (x: string) => setQuitar(quitar.includes(x) ? quitar.filter((y) => y !== x) : [...quitar, x]);
  const ok = () => anadir(n, [...Object.values(cambio).map((e) => [e, 1] as [string, number]), ...Object.entries(extras).filter(([, v]) => v > 0)], quitar);
  return (
    <Modal opened onClose={cerrar} title={<Text fw={700} fz="lg">{plato.nombre}</Text>} size="xl" centered>
      <Stack>
        <Group justify="center" gap="lg">
          <ActionIcon size={48} radius="xl" variant="light" onClick={() => setN(Math.max(1, n - 1))} aria-label="Uno menos"><IconMinus /></ActionIcon>
          <Text fz={36} fw={700} w={60} ta="center">{n}</Text>
          <ActionIcon size={48} radius="xl" variant="light" onClick={() => setN(n + 1)} aria-label="Uno más"><IconPlus /></ActionIcon>
        </Group>
        {grupos.map((g) => (
          <div key={g}>
            <Text size="sm" fw={600} mb={4}>{g === 'huevo' ? 'Huevo' : 'Pan'} (cambia el de la ficha)</Text>
            <Group gap={6}>{cat.sustituir.filter((a) => a.sustituye === g).map((a) => (
              <Button key={a.etiqueta} size="sm" radius="xl" variant={cambio[g] === a.etiqueta ? 'filled' : 'default'}
                onClick={() => setCambio({ ...cambio, [g]: cambio[g] === a.etiqueta ? '' : a.etiqueta })}>{a.etiqueta}</Button>
            ))}</Group>
          </div>
        ))}
        <div>
          <Text size="sm" fw={600} mb={4}>Añadir (toca varias veces para más)</Text>
          <ScrollArea.Autosize mah={150}><Group gap={6}>{cat.extras.slice(0, 30).map((a) => (
            <Button key={a.etiqueta} size="sm" radius="xl" variant={extras[a.etiqueta] ? 'filled' : 'default'} color="teal"
              onClick={() => setExtras({ ...extras, [a.etiqueta]: (extras[a.etiqueta] ?? 0) + 1 })}
              rightSection={extras[a.etiqueta] ? <Badge size="sm" circle color="dark" onClick={(e) => { e.stopPropagation(); setExtras({ ...extras, [a.etiqueta]: 0 }); }}>{extras[a.etiqueta]}</Badge> : null}>
              {a.etiqueta}</Button>
          ))}</Group></ScrollArea.Autosize>
        </div>
        <div>
          <Text size="sm" fw={600} mb={4}>Quitar</Text>
          <Group gap={6}>{[...cat.quitar.map((a) => a.etiqueta), ...plato.ingredientes].map((x) => (
            <Button key={x} size="sm" radius="xl" color="red" variant={quitar.includes(x) ? 'filled' : 'default'} onClick={() => toggle(x)}>
              {x.toLowerCase().startsWith('sin') ? x : `Sin ${x.toLowerCase()}`}</Button>
          ))}</Group>
        </div>
        <Button size="xl" onClick={ok}>Añadir {n > 1 ? `${n} × ` : ''}{plato.nombre}</Button>
      </Stack>
    </Modal>
  );
}

export function Comandas() {
  const [fecha, setFecha] = useState(hoy());
  const [d, setD] = useState<Dia | null>(null);
  const [cat, setCat] = useState<Catalogo | null>(null);
  const [tab, setTab] = useState('platos');
  const [plato, setPlato] = useState<Item | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    setD(null);
    api<Dia>(`/comandas?fecha=${fecha}`).then((x) => { setD(x); setCat(x.catalogo ?? null); }).catch(avisoError);
  }, [fecha]);

  const enviar = async (fn: () => Promise<Dia>) => {
    setOcupado(true);
    try { setD(await fn()); } catch (e) { avisoError(e); } finally { setOcupado(false); }
  };
  const anadir = (nombre: string, cantidad = 1, extras: [string, number][] = [], omitir: string[] = []) => {
    setPlato(null);
    enviar(() => api<Dia>('/comandas', { body: { fecha, nombre, cantidad, extras, omitir } }));
  };
  const comensales = (n: number) => enviar(() => api<Dia>('/comandas/comensales', { method: 'PUT', body: { fecha, comensales: Math.max(0, n) } }));
  const borrar = (id: number) => enviar(() => api<Dia>(`/comandas/${id}`, { method: 'DELETE' }));

  const lista = tab === 'platos' ? cat?.platos ?? [] : tab === 'bebidas' ? cat?.bebidas ?? [] : (cat?.extras ?? []).map((a) => ({ nombre: a.etiqueta, uso: a.uso, ingredientes: [] }));
  return (
    <>
      <Group justify="space-between" mb="md" wrap="wrap">
        <div>
          <Text fz={26} fw={700}>Comandas de desayuno</Text>
          <Text size="sm" c="dimmed">Toca cada plato que sale de cocina. Todo se guarda al momento.</Text>
        </div>
        <DateInput value={fecha} onChange={(x) => x && setFecha(String(x).slice(0, 10))} valueFormat="DD/MM/YYYY" w={150} maxDate={new Date()} aria-label="Fecha" />
      </Group>
      <Grid>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Card mb="md">
            <Group justify="space-between" wrap="wrap">
              <Group gap="sm"><IconUsers size={28} /><div><Text size="xs" c="dimmed" fw={700} tt="uppercase">Comensales</Text><Text fz={34} fw={800} lh={1}>{d?.comensales ?? '…'}</Text></div></Group>
              <Group gap={6}>
                <Button size="lg" variant="default" onClick={() => comensales((d?.comensales ?? 0) - 1)} disabled={!d || ocupado}>−1</Button>
                {[1, 2, 4].map((k) => <Button key={k} size="lg" onClick={() => comensales((d?.comensales ?? 0) + k)} disabled={!d || ocupado}>+{k}</Button>)}
              </Group>
            </Group>
          </Card>
          <SegmentedControl fullWidth size="md" mb="md" value={tab} onChange={setTab}
            data={[{ value: 'platos', label: 'Platos' }, { value: 'bebidas', label: 'Bebidas' }, { value: 'sueltos', label: 'Sueltos' }]} />
          <SimpleGrid cols={{ base: 2, sm: 3, lg: 4 }} spacing="sm">
            {lista.map((p) => tab === 'platos'
              ? <Boton key={p.nombre} nombre={p.nombre} onClick={() => setPlato(p)} onMas={() => anadir(p.nombre)} />
              : <Boton key={p.nombre} nombre={p.nombre} onClick={() => anadir(p.nombre)} />)}
          </SimpleGrid>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Card style={{ position: 'sticky', top: 76 }}>
            <Group justify="space-between" mb="sm"><Text fw={700}>Hoy</Text><Badge size="lg" variant="light">{d?.platos ?? 0} platos</Badge></Group>
            <ScrollArea.Autosize mah="calc(100vh - 220px)">
              <Stack gap={6}>
                {!d?.lineas.length && <Text c="dimmed" size="sm">Aún no hay nada apuntado.</Text>}
                {d?.lineas.map((l) => (
                  <Group key={l.id} justify="space-between" wrap="nowrap" p={6} style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
                    <div style={{ minWidth: 0 }}>
                      <Text size="sm" fw={600}>{l.cantidad !== 1 ? `${fmt(l.cantidad)} × ` : ''}{l.nombre}</Text>
                      <Text size="xs" c="dimmed">{l.hora.slice(0, 5)}{resumen(l) ? ` · ${resumen(l)}` : ''}</Text>
                    </div>
                    <ActionIcon variant="subtle" color="red" onClick={() => borrar(l.id)} aria-label={`Quitar ${l.nombre}`} disabled={ocupado}><IconTrash size={16} /></ActionIcon>
                  </Group>
                ))}
              </Stack>
            </ScrollArea.Autosize>
          </Card>
        </Grid.Col>
      </Grid>
      {plato && cat && <Personalizar plato={plato} cat={cat} cerrar={() => setPlato(null)} anadir={(n, e, o) => anadir(plato.nombre, n, e, o)} />}
    </>
  );
}
