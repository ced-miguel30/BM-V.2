import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Affix, Alert, Badge, Button, Card, Chip, Group, Menu, Modal, NumberInput, Select, Stack, Switch, Tabs, Text, TextInput, Textarea,
} from '@mantine/core';
import { IconCheck, IconMapPin, IconPlus, IconSearch } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera, Vacio } from '../comun';
import { nombreUbicacion, useUbicaciones } from '../centros';
import { cantidad, euros, fecha, hoy } from '../formato';
import { Tabla } from '../Tabla';

type Linea = { producto: string; nombre: string; unidad: string | null; teorico?: number; zona?: string | null };

// Zonas habituales; las que se creen a mano se suman a la lista.
const ZONAS_BASE = ['Nevera', 'Congelador', 'Cámara', 'Estantería', 'Bar'];
type Historial = { id: number; fecha: string; ubicacion: string; usuario: string | null; n_productos: number; anulado: number; nota: string | null };
type Detalle = Historial & { lineas: { producto: string; nombre: string; unidad: string; contado: number; teorico: number; diferencia: number; diferencia_valor: number | null }[] };

// Borrador en el dispositivo: si el móvil se bloquea o se recarga a mitad de recuento, no se pierde lo contado.
const claveBorrador = (ub: string) => `bm.recuento.${ub}`;
const leerBorrador = (ub: string): Record<string, number | string> => {
  try { return JSON.parse(localStorage.getItem(claveBorrador(ub)) ?? '{}'); } catch { return {}; }
};
const guardarBorrador = (ub: string, v: Record<string, number | string>) => {
  try { if (Object.keys(v).length) localStorage.setItem(claveBorrador(ub), JSON.stringify(v)); else localStorage.removeItem(claveBorrador(ub)); } catch { /* sin almacenamiento */ }
};

const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function Contar({ gestion }: { gestion: boolean }) {
  const ubicaciones = useUbicaciones();
  const [params, setParams] = useSearchParams();
  const ub = params.get('ubicacion');
  const [lineas, setLineas] = useState<Linea[] | null>(null);
  const [contado, setContado] = useState<Record<string, number | string>>({});
  const [q, setQ] = useState('');
  const [verTeorico, setVerTeorico] = useState(false);
  const [zona, setZona] = useState('todas');
  const [extra, setExtra] = useState<string | null>(null);
  const [catalogo, setCatalogo] = useState<{ codigo: string; nombre: string; unidad: string | null }[]>([]);
  const [confirmar, setConfirmar] = useState(false);
  const [nota, setNota] = useState('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => { api<{ productos: typeof catalogo }>('/catalogo').then((c) => setCatalogo(c.productos)).catch(avisoError); }, []);
  useEffect(() => {
    setLineas(null); setZona('todas'); setContado(ub ? leerBorrador(ub) : {});
    if (ub) api<any[]>(`/stock?ubicacion=${encodeURIComponent(ub)}`).then((xs) => {
      const ls: Linea[] = xs.filter((x) => x.stock > 1e-6 || x.salidas_desde_recuento > 0)
        .map((x) => ({ producto: x.producto, nombre: x.nombre, unidad: x.unidad, teorico: x.stock, zona: x.zona }))
        .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
      // Lo añadido a mano en un borrador anterior vuelve arriba de la lista.
      const extras = Object.keys(leerBorrador(ub)).filter((p) => !ls.some((l) => l.producto === p))
        .map((p) => ({ producto: p, nombre: p, unidad: null }));
      setLineas([...extras, ...ls]);
    }).catch(avisoError);
  }, [ub]);

  const cambiar = (v: Record<string, number | string>) => { setContado(v); if (ub) guardarBorrador(ub, v); };

  const contados = Object.entries(contado).filter(([, v]) => v !== '' && v != null);
  const visibles = useMemo(() => (lineas ?? []).filter((l) => (!q || norm(`${l.nombre} ${l.producto}`).includes(norm(q)))
    && (zona === 'todas' || (zona === '' ? !l.zona : l.zona === zona))), [lineas, q, zona]);
  const zonas = useMemo(() => [...new Set([...ZONAS_BASE, ...(lineas ?? []).map((l) => l.zona).filter((z): z is string => !!z)])], [lineas]);
  const resumenZona = (z: string) => {
    const ls = (lineas ?? []).filter((l) => (z === '' ? !l.zona : l.zona === z));
    return { total: ls.length, hechos: ls.filter((l) => contado[l.producto] !== undefined && contado[l.producto] !== '').length };
  };
  const ponerZona = async (l: Linea, z: string | null) => {
    if (z === null) return;
    try {
      await api('/zonas', { method: 'PUT', body: { producto: l.producto, ubicacion: ub, zona: z } });
      const limpia = z.trim() ? z.trim()[0].toUpperCase() + z.trim().slice(1) : null;
      setLineas((ls) => (ls ?? []).map((x) => (x.producto === l.producto ? { ...x, zona: limpia } : x)));
    } catch (e) { avisoError(e); }
  };
  const anadir = () => {
    const p = catalogo.find((c) => c.codigo === extra);
    if (p && !lineas?.some((l) => l.producto === p.codigo)) setLineas([{ producto: p.codigo, nombre: p.nombre, unidad: p.unidad }, ...(lineas ?? [])]);
    setExtra(null);
  };
  const guardar = async () => {
    setGuardando(true);
    try {
      await api('/recuentos', { body: { fecha: hoy(), ubicacion: ub, nota: nota || null,
        lineas: contados.map(([producto, v]) => ({ producto, contado: Number(v) })) } });
      avisoOk(`${contados.length} productos contados en ${nombreUbicacion(ubicaciones, ub)}`, 'Recuento guardado');
      cambiar({}); setConfirmar(false); setNota('');
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };

  return (
    <Stack>
      <Group align="flex-end" wrap="wrap">
        <Select label="Ubicación que vas a contar" data={ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }))} value={ub}
          onChange={(x) => x && setParams({ ubicacion: x })} searchable w={260} placeholder="Elige ubicación" size="md" />
        {ub && <TextInput leftSection={<IconSearch size={16} />} placeholder="Buscar producto" value={q} onChange={(e) => setQ(e.currentTarget.value)} size="md" style={{ flex: 1, minWidth: 200 }} />}
        {ub && gestion && <Switch label="Mostrar teórico" checked={verTeorico} onChange={(e) => setVerTeorico(e.currentTarget.checked)} />}
      </Group>
      {!ub ? <Card><Vacio texto="Elige la ubicación que vas a contar" /></Card> : !lineas ? <Card><Text c="dimmed">Cargando…</Text></Card> : (
        <>
          {contados.length > 0 && (
            <Alert color="blue" variant="light" p="xs">
              <Group justify="space-between" gap="xs">
                <Text size="sm">{contados.length === 1 ? "1 producto contado guardado" : `${contados.length} productos contados guardados`} en este dispositivo hasta que pulses Guardar.</Text>
                <Button size="compact-sm" variant="subtle" color="red" onClick={() => cambiar({})}>Empezar de cero</Button>
              </Group>
            </Alert>
          )}
          <Group align="flex-end">
            <Select placeholder="¿Hay algo que no está en la lista? Búscalo" searchable limit={50} value={extra} onChange={setExtra}
              data={catalogo.map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.unidad ?? 'ud'})` }))} style={{ flex: 1 }} />
            <Button variant="light" leftSection={<IconPlus size={16} />} onClick={anadir} disabled={!extra}>Añadir</Button>
          </Group>
          <Chip.Group value={zona} onChange={(v) => setZona(v as string)}>
            <Group gap={6}>
              <Chip value="todas" size="sm">Todas</Chip>
              {[...zonas, ''].map((z) => {
                const r = resumenZona(z);
                return r.total ? <Chip key={z || 'sin'} value={z} size="sm">{z || 'Sin zona'} {r.hechos}/{r.total}</Chip> : null;
              })}
            </Group>
          </Chip.Group>
          <Stack gap={6} pb={90}>
            {visibles.map((l) => (
              <Card key={l.producto} p="sm" withBorder style={{ borderColor: contado[l.producto] !== undefined && contado[l.producto] !== '' ? 'var(--mantine-color-teal-5)' : undefined }}>
                <Group justify="space-between" wrap="nowrap">
                  <div style={{ minWidth: 0 }}>
                    <Text fw={500} lineClamp={2} lh={1.25}>{l.nombre === l.producto ? catalogo.find((c) => c.codigo === l.producto)?.nombre ?? l.nombre : l.nombre}</Text>
                    <Group gap={6} rowGap={0}>
                      <Text size="xs" c="dimmed">{l.producto}{verTeorico && l.teorico !== undefined ? ` · teórico ${cantidad(l.teorico)}` : ''}</Text>
                      <Menu position="bottom-start" withinPortal>
                        <Menu.Target>
                          <Button size="compact-xs" variant="subtle" color={l.zona ? 'gray' : 'blue'} leftSection={<IconMapPin size={12} />} aria-label={`Zona de ${l.nombre}`}>
                            {l.zona ?? 'Zona'}
                          </Button>
                        </Menu.Target>
                        <Menu.Dropdown>
                          {zonas.map((z) => <Menu.Item key={z} onClick={() => ponerZona(l, z)}>{z}</Menu.Item>)}
                          <Menu.Divider />
                          <Menu.Item onClick={() => ponerZona(l, window.prompt('Nombre de la zona (p. ej. Estantería 2)'))}>Otra zona…</Menu.Item>
                          {l.zona && <Menu.Item color="red" onClick={() => ponerZona(l, '')}>Quitar zona</Menu.Item>}
                        </Menu.Dropdown>
                      </Menu>
                    </Group>
                  </div>
                  <NumberInput value={contado[l.producto] ?? ''} onChange={(x) => cambiar({ ...contado, [l.producto]: x })} min={0} decimalScale={3}
                    w={130} style={{ flex: "0 0 130px" }} size="md" placeholder="—" rightSection={<Text size="xs" c="dimmed" pr={6}>{l.unidad}</Text>} rightSectionWidth={44}
                    aria-label={`Cantidad contada de ${l.nombre}`} hideControls />
                </Group>
              </Card>
            ))}
            {!visibles.length && <Vacio texto="Ningún producto con esa búsqueda" />}
          </Stack>
          <Affix position={{ bottom: 16, right: 16 }}>
            <Button size="lg" leftSection={<IconCheck size={20} />} disabled={!contados.length} onClick={() => setConfirmar(true)} radius="xl" style={{ boxShadow: 'var(--mantine-shadow-lg)' }}>
              Guardar recuento ({contados.length})
            </Button>
          </Affix>
        </>
      )}
      <Modal opened={confirmar} onClose={() => setConfirmar(false)} title="Guardar recuento" centered>
        <Stack>
          <Text size="sm">{contados.length} productos contados en <b>{nombreUbicacion(ubicaciones, ub)}</b>. Lo contado pasa a ser el stock real; la diferencia con lo esperado queda registrada.</Text>
          <Text size="sm" c="dimmed">Los productos que no has contado no cambian.</Text>
          <Textarea label="Nota (opcional)" value={nota} onChange={(e) => setNota(e.currentTarget.value)} autosize minRows={2} />
          <Group justify="flex-end"><Button variant="default" onClick={() => setConfirmar(false)}>Seguir contando</Button><Button onClick={guardar} loading={guardando}>Guardar</Button></Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function Historico() {
  const ubicaciones = useUbicaciones();
  const [lista, setLista] = useState<Historial[] | null>(null);
  const [det, setDet] = useState<Detalle | null>(null);
  const [motivo, setMotivo] = useState('');
  const cargar = () => api<Historial[]>('/recuentos').then(setLista).catch(avisoError);
  useEffect(() => { cargar(); }, []);
  const anular = async () => {
    if (!det) return;
    try { await api(`/recuentos/${det.id}/anular`, { body: { motivo } }); avisoOk('El stock vuelve a calcularse sin este recuento', 'Recuento anulado'); setDet(null); setMotivo(''); cargar(); }
    catch (e) { avisoError(e); }
  };
  const total = det?.lineas.reduce((s, l) => s + (l.diferencia_valor ?? 0), 0) ?? 0;
  return (
    <>
      <Tabla datos={lista} clave={(r) => r.id} exportar="recuentos" orden={{ clave: 'fecha', desc: true }} atenuar={(r) => !!r.anulado}
        alPulsar={(r) => api<Detalle>(`/recuentos/${r.id}`).then(setDet).catch(avisoError)} vacio="Aún no hay recuentos hechos en BM"
        columnas={[
          { clave: 'fecha', titulo: 'Fecha', render: (r) => fecha(r.fecha) },
          { clave: 'ubicacion', titulo: 'Ubicación', valor: (r) => nombreUbicacion(ubicaciones, r.ubicacion) },
          { clave: 'n_productos', titulo: 'Productos', num: true },
          { clave: 'usuario', titulo: 'Contado por' },
          { clave: 'anulado', titulo: 'Estado', valor: (r) => (r.anulado ? 'Anulado' : 'Válido'),
            render: (r) => r.anulado ? <Badge color="gray">Anulado</Badge> : <Badge color="teal" variant="light">Válido</Badge> },
        ]} />
      <Modal opened={!!det} onClose={() => setDet(null)} size="xl" centered title={det ? `Recuento ${nombreUbicacion(ubicaciones, det.ubicacion)} · ${fecha(det.fecha)}` : ''}>
        {det && (
          <Stack>
            <Group><Text>Diferencia total:</Text><Text fw={700} c={total < 0 ? 'red' : 'teal'}>{euros(total)}</Text></Group>
            <Tabla datos={det.lineas} clave={(l) => l.producto} exportar={`recuento_${det.id}`} orden={{ clave: 'diferencia_valor' }} porPagina={15}
              columnas={[
                { clave: 'nombre', titulo: 'Producto' },
                { clave: 'teorico', titulo: 'Esperado', num: true, render: (l) => `${cantidad(l.teorico)} ${l.unidad}` },
                { clave: 'contado', titulo: 'Contado', num: true, render: (l) => `${cantidad(l.contado)} ${l.unidad}` },
                { clave: 'diferencia', titulo: 'Diferencia', num: true, render: (l) => <Text size="sm" c={l.diferencia < 0 ? 'red' : 'teal'}>{l.diferencia > 0 ? '+' : ''}{cantidad(l.diferencia)}</Text> },
                { clave: 'diferencia_valor', titulo: '€', num: true, render: (l) => <Text size="sm" fw={600} c={(l.diferencia_valor ?? 0) < 0 ? 'red' : undefined}>{euros(l.diferencia_valor)}</Text> },
              ]} />
            {!det.anulado && (
              <Group align="flex-end">
                <TextInput label="Motivo para anular" value={motivo} onChange={(e) => setMotivo(e.currentTarget.value)} style={{ flex: 1 }} />
                <Button color="red" variant="light" onClick={anular} disabled={!motivo.trim()}>Anular recuento</Button>
              </Group>
            )}
          </Stack>
        )}
      </Modal>
    </>
  );
}

export function Recuento() {
  const [gestion, setGestion] = useState(false);
  useEffect(() => { api<{ rol: string }>('/me').then((u) => setGestion(['direccion', 'administracion'].includes(u.rol))).catch(() => null); }, []);
  return (
    <>
      <Cabecera titulo="Recuento" subtitulo="Cuenta lo que hay. Lo contado pasa a ser el stock real y la diferencia queda registrada." />
      {gestion ? (
        <Tabs defaultValue="contar">
          <Tabs.List mb="md"><Tabs.Tab value="contar">Contar</Tabs.Tab><Tabs.Tab value="historial">Recuentos hechos</Tabs.Tab></Tabs.List>
          <Tabs.Panel value="contar"><Contar gestion /></Tabs.Panel>
          <Tabs.Panel value="historial"><Historico /></Tabs.Panel>
        </Tabs>
      ) : <Contar gestion={false} />}
    </>
  );
}
