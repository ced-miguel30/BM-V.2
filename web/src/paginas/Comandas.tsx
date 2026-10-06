import { useEffect, useRef, useState } from 'react';
import {
  ActionIcon, Badge, Button, Card, Grid, Group, Kbd, Modal, ScrollArea, SegmentedControl, SimpleGrid, Stack, Text, TextInput, UnstyledButton,
} from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconChevronLeft, IconChevronRight, IconKeyboard, IconMinus, IconPlus, IconTrash, IconUsers } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { cantidad as fmt, euros, fecha as ffecha, hoy } from '../formato';
import { Tabla } from '../Tabla';

type Item = { nombre: string; uso: number; ingredientes: string[] };
type Atajo = { etiqueta: string; grupo: string; sustituye: string | null; uso: number };
type Catalogo = { platos: Item[]; bebidas: Item[]; extras: Atajo[]; sustituir: Atajo[]; quitar: Atajo[] };
type Linea = { id: number; hora: string; nombre: string; cantidad: number; extras: [string, number][]; omitir: string[] };
type Dia = { fecha: string; comensales: number; comensales_auto: boolean; lineas: Linea[]; platos: number; catalogo?: Catalogo };

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

const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();

/** Busca el nombre más probable: exacto, empieza por, contiene, o contiene todas las palabras. */
function buscar(texto: string, nombres: string[]): string | null {
  const t = norm(texto);
  if (!t) return null;
  const corto = (xs: string[]) => (xs.length ? xs.reduce((a, b) => (a.length <= b.length ? a : b)) : null);
  return nombres.find((n) => norm(n) === t)
    ?? corto(nombres.filter((n) => norm(n).startsWith(t)))
    ?? corto(nombres.filter((n) => norm(n).includes(t)))
    ?? corto(nombres.filter((n) => t.split(/\s+/).every((w) => norm(n).includes(w))));
}

type Interpretada = { nombre: string | null; cantidad: number; extras: [string, number][]; omitir: string[]; fallos: string[] };

/** "2 ingles +bacon +2 salchicha -tomate"  ->  2 × Desayuno ingles, +Bacon, +2 Salchicha, sin Tomate */
function interpretar(texto: string, cat: Catalogo): Interpretada {
  const trozos = texto.trim().split(/\s+(?=[+-])/);
  let base = (trozos.shift() ?? '').trim();
  let cantidad = 1;
  const m = base.match(/^(\d+)\s*x?\s+(.*)$/i) ?? base.match(/^(.*?)\s+x\s*(\d+)$/i);
  if (m) { const [a, b] = /^\d/.test(m[1]) ? [m[1], m[2]] : [m[2], m[1]]; cantidad = Number(a); base = b; }
  const todos = [...cat.platos, ...cat.bebidas].map((p) => p.nombre).concat(cat.extras.map((a) => a.etiqueta));
  const nombre = buscar(base, todos);
  const plato = cat.platos.find((p) => p.nombre === nombre);
  const fallos = base && !nombre ? [`No encuentro «${base}»`] : [];
  const extras: [string, number][] = [];
  const omitir: string[] = [];
  for (const t of trozos) {
    const quitar = t.startsWith('-');
    let resto = t.slice(1).trim();
    let n = 1;
    const k = resto.match(/^(\d+)\s+(.*)$/) ?? resto.match(/^(.*?)\s*x\s*(\d+)$/i);
    if (k) { [n, resto] = /^\d/.test(k[1]) ? [Number(k[1]), k[2]] : [Number(k[2]), k[1]]; }
    if (quitar) {
      const q = buscar(resto, cat.quitar.map((a) => a.etiqueta)) ?? buscar(`sin ${resto}`, cat.quitar.map((a) => a.etiqueta)) ?? buscar(resto, plato?.ingredientes ?? []);
      if (q) omitir.push(q); else fallos.push(`No sé quitar «${resto}»`);
    } else {
      const e = buscar(resto, [...cat.sustituir, ...cat.extras].map((a) => a.etiqueta));
      if (e) extras.push([e, n]); else fallos.push(`No encuentro el extra «${resto}»`);
    }
  }
  return { nombre, cantidad, extras, omitir, fallos };
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
  const [vista, setVista] = useState('apuntar');
  const [texto, setTexto] = useState('');
  const entrada = useRef<HTMLInputElement>(null);
  const mover = (dias: number) => { const f = new Date(`${fecha}T12:00:00`); f.setDate(f.getDate() + dias); setFecha(f.toISOString().slice(0, 10)); };

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

  const leida = cat && texto.trim() ? interpretar(texto, cat) : null;
  const enviarTexto = () => {
    if (!leida?.nombre || leida.fallos.length) return;
    anadir(leida.nombre, leida.cantidad, leida.extras, leida.omitir);
    setTexto('');
    entrada.current?.focus();
  };
  if (vista === 'historial') return <Historial volver={(f) => { setFecha(f); setVista('apuntar'); }} cambiar={setVista} />;
  const lista = tab === 'platos' ? cat?.platos ?? [] : tab === 'bebidas' ? cat?.bebidas ?? [] : (cat?.extras ?? []).map((a) => ({ nombre: a.etiqueta, uso: a.uso, ingredientes: [] }));
  return (
    <>
      <Group justify="space-between" mb="md" wrap="wrap">
        <div>
          <Text fz={26} fw={700}>Comandas de desayuno</Text>
          <Text size="sm" c="dimmed">Toca cada plato que sale de cocina. Todo se guarda al momento.</Text>
        </div>
        <Group gap={6}>
          <SegmentedControl value={vista} onChange={setVista} data={[{ value: 'apuntar', label: 'Apuntar' }, { value: 'historial', label: 'Historial' }]} />
          <ActionIcon size="lg" variant="default" onClick={() => mover(-1)} aria-label="Día anterior"><IconChevronLeft size={18} /></ActionIcon>
          <DateInput value={fecha} onChange={(x) => x && setFecha(String(x).slice(0, 10))} valueFormat="ddd DD/MM/YYYY" w={170} maxDate={new Date()} aria-label="Fecha" />
          <ActionIcon size="lg" variant="default" onClick={() => mover(1)} disabled={fecha >= hoy()} aria-label="Día siguiente"><IconChevronRight size={18} /></ActionIcon>
        </Group>
      </Group>
      <Grid>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Card mb="md">
            <TextInput ref={entrada} size="lg" autoFocus leftSection={<IconKeyboard size={20} />} value={texto} onChange={(e) => setTexto(e.currentTarget.value)}
              onKeyDown={(e) => e.key === 'Enter' && enviarTexto()} placeholder="Escribe la comanda y pulsa Intro:  ingles +bacon -tomate   ·   2 tostada francesa"
              aria-label="Escribir comanda" disabled={!cat} />
            <Group mt={6} gap={6} mih={22}>
              {leida ? (leida.fallos.length ? <Text size="sm" c="red">{leida.fallos.join(' · ')}</Text> : (
                <Text size="sm" c="teal">→ {leida.cantidad > 1 ? `${leida.cantidad} × ` : ''}<b>{leida.nombre}</b>{leida.extras.map(([e, n]) => ` · +${n > 1 ? `${n} ` : ''}${e}`).join('')}{leida.omitir.map((o) => ` · sin ${o.replace(/^sin /i, '')}`).join('')}  <Kbd>Intro</Kbd></Text>
              )) : <Text size="xs" c="dimmed">Nombre del plato · <b>+</b> añadir extra (+2 bacon) · <b>-</b> quitar (-huevo) · número delante para cantidad. También puedes tocar los botones.</Text>}
            </Group>
          </Card>
          <Card mb="md">
            <Group justify="space-between" wrap="wrap">
              <Group gap="sm"><IconUsers size={28} /><div><Text size="xs" c="dimmed" fw={700} tt="uppercase">Comensales{d?.comensales_auto ? ' · 1 por plato' : ' · a mano'}</Text><Text fz={34} fw={800} lh={1}>{d?.comensales ?? '…'}</Text></div></Group>
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

type DiaHist = { fecha: string; comensales: number | null; origen: string; coste?: number; coste_comensal?: number | null; comandas: number; buffet: number };

function Historial({ volver, cambiar }: { volver: (f: string) => void; cambiar: (v: string) => void }) {
  const [filas, setFilas] = useState<DiaHist[] | null>(null);
  useEffect(() => {
    const desde = new Date(Date.now() - 90 * 864e5).toISOString().slice(0, 10);
    api<DiaHist[]>(`/desayunos?desde=${desde}&hasta=${hoy()}`).then(setFilas).catch(avisoError);
  }, []);
  const conCoste = filas?.some((f) => f.coste !== undefined);
  return (
    <>
      <Group justify="space-between" mb="md" wrap="wrap">
        <div><Text fz={26} fw={700}>Registro de desayunos</Text><Text size="sm" c="dimmed">Cada día registrado, de comandas, Excel o histórico. Pulsa un día para verlo o completarlo.</Text></div>
        <SegmentedControl value="historial" onChange={cambiar} data={[{ value: 'apuntar', label: 'Apuntar' }, { value: 'historial', label: 'Historial' }]} />
      </Group>
      <Tabla datos={filas} clave={(f) => f.fecha} alPulsar={(f) => volver(f.fecha)} exportar="desayunos" orden={{ clave: 'fecha', desc: true }} vacio="Aún no hay desayunos registrados"
        columnas={[
          { clave: 'fecha', titulo: 'Día', render: (f) => ffecha(f.fecha) },
          { clave: 'comensales', titulo: 'Comensales', num: true },
          { clave: 'comandas', titulo: 'Comandas', num: true },
          { clave: 'buffet', titulo: 'Buffet', render: (f) => (f.buffet ? <Badge color="teal" variant="light">Sí</Badge> : <Badge color="gray" variant="light">No</Badge>), valor: (f) => (f.buffet ? 'Sí' : 'No') },
          ...(conCoste ? [
            { clave: 'coste', titulo: 'Coste', num: true, render: (f: DiaHist) => euros(f.coste) },
            { clave: 'coste_comensal', titulo: '€ / comensal', num: true, render: (f: DiaHist) => <Text size="sm" fw={600}>{euros(f.coste_comensal)}</Text> },
          ] : []),
          { clave: 'origen', titulo: 'Origen', valor: (f) => f.origen.replace('bm2', 'BM v2').replace('excel', 'Excel').replace('comandas', 'Comandas').replace('manual', 'Manual') },
        ]} />
    </>
  );
}
