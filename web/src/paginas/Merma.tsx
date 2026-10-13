import { useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, Chip, Group, NumberInput, Select, Stack, Text } from '@mantine/core';
import { IconCheck, IconTrashX } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { cantidad as fmt, hoy } from '../formato';
import { useUbicaciones } from '../centros';
import { BotonEscanear, type Producto } from '../EscanearProducto';
import { enviarOGuardar } from '../pendientes';

type Catalogo = { recetas: { id: string; nombre: string }[]; productos: Producto[]; motivos: Record<string, string> };
type Hecha = { nombre: string; cantidad: number; unidad: string; motivo: string; enCola: boolean };

// Merma rápida en el móvil: escanear (o buscar el plato), cantidad, motivo y guardar. Una merma por toque.
export function Merma() {
  const ubicaciones = useUbicaciones();
  const [cat, setCat] = useState<Catalogo | null>(null);
  const [ubicacion, setUbicacion] = useState<string | null>('RESTAURANTE');
  const [motivo, setMotivo] = useState('error_cocina');
  const [sel, setSel] = useState<string | null>(null);  // p:CODIGO o r:ID
  const [cant, setCant] = useState<number | string>('');
  const [guardando, setGuardando] = useState(false);
  const [hechas, setHechas] = useState<Hecha[]>([]);
  const cantRef = useRef<HTMLInputElement>(null);
  useEffect(() => { api<Catalogo>('/catalogo').then(setCat).catch(avisoError); }, []);

  const info = (clave: string | null) => {
    if (!clave || !cat) return null;
    if (clave.startsWith('r:')) { const r = cat.recetas.find((x) => x.id === clave.slice(2)); return r && { nombre: r.nombre, unidad: 'raciones' }; }
    const p = cat.productos.find((x) => x.codigo === clave.slice(2));
    return p && { nombre: p.nombre, unidad: p.unidad ?? 'ud' };
  };
  const elegir = (clave: string | null) => { setSel(clave); setCant(''); setTimeout(() => cantRef.current?.focus(), 120); };
  const actual = info(sel);

  const guardar = async () => {
    if (!sel || !actual || !(Number(cant) > 0)) return;
    setGuardando(true);
    try {
      const item = sel.startsWith('r:') ? { receta_id: sel.slice(2), cantidad: Number(cant) } : { producto: sel.slice(2), cantidad: Number(cant) };
      const r = await enviarOGuardar('/consumos', { fecha: hoy(), tipo: 'merma', motivo, ubicacion, items: [item] },
        `Merma: ${fmt(Number(cant))} ${actual.unidad} de ${actual.nombre}`);
      setHechas([{ nombre: actual.nombre, cantidad: Number(cant), unidad: actual.unidad, motivo, enCola: r === 'en cola' }, ...hechas]);
      avisoOk(r === 'enviado' ? `${fmt(Number(cant))} ${actual.unidad} · ${cat?.motivos[motivo]}` : 'Sin cobertura: se enviará sola al volver', `Merma: ${actual.nombre}`);
      setSel(null); setCant('');
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };

  return (
    <Stack>
      <Group justify="space-between" wrap="nowrap">
        <Text fz={22} fw={700}>Merma</Text>
        <Select size="xs" w={170} value={ubicacion} onChange={setUbicacion} aria-label="Sale de" allowDeselect={false}
          data={ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }))} />
      </Group>
      <Text size="sm" c="dimmed">Lo que se tira, se rompe o vuelve de sala. Escanéalo o busca el plato.</Text>
      <Group wrap="nowrap">
        <BotonEscanear productos={cat?.productos ?? []} texto="Escanear" elegido={(p) => elegir(`p:${p}`)} />
        <Select placeholder="…o busca producto o plato" searchable limit={60} value={null} onChange={elegir} style={{ flex: 1 }}
          data={cat ? [{ group: 'Platos', items: cat.recetas.map((r) => ({ value: `r:${r.id}`, label: r.nombre })) },
            { group: 'Productos', items: cat.productos.map((p) => ({ value: `p:${p.codigo}`, label: `${p.nombre} (${p.unidad ?? 'ud'})` })) }] : []} />
      </Group>
      {actual && (
        <Card withBorder style={{ borderColor: 'var(--mantine-color-red-5)' }}>
          <Stack gap="sm">
            <Text fw={700} lh={1.25}>{actual.nombre}</Text>
            <NumberInput ref={cantRef} size="xl" value={cant} onChange={setCant} min={0} decimalScale={3} inputMode="decimal" hideControls placeholder="Cantidad"
              rightSection={<Text c="dimmed" pr="sm">{actual.unidad}</Text>} rightSectionWidth={90} aria-label="Cantidad tirada"
              onKeyDown={(e) => e.key === 'Enter' && guardar()} />
            <Chip.Group value={motivo} onChange={(v) => setMotivo(v as string)}>
              <Group gap={6}>{Object.entries(cat?.motivos ?? {}).map(([k, v]) => <Chip key={k} value={k} color="red">{v}</Chip>)}</Group>
            </Chip.Group>
            <Group grow>
              <Button variant="default" onClick={() => setSel(null)}>Cancelar</Button>
              <Button color="red" leftSection={<IconCheck size={18} />} onClick={guardar} loading={guardando} disabled={!(Number(cant) > 0)}>Guardar</Button>
            </Group>
          </Stack>
        </Card>
      )}
      {hechas.length > 0 && (
        <Card>
          <Group gap={6} mb="xs"><IconTrashX size={18} /><Text fw={600}>Apuntado ahora</Text></Group>
          <Stack gap={4}>
            {hechas.map((h, i) => (
              <Group key={i} justify="space-between" wrap="nowrap">
                <Text size="sm">{fmt(h.cantidad)} {h.unidad} · {h.nombre}</Text>
                <Badge size="sm" variant="light" color={h.enCola ? 'orange' : 'gray'}>{h.enCola ? 'en espera' : cat?.motivos[h.motivo]}</Badge>
              </Group>
            ))}
          </Stack>
        </Card>
      )}
    </Stack>
  );
}
