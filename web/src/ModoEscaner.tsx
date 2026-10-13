import { useRef, useState } from 'react';
import { ActionIcon, Badge, Button, Card, Group, Modal, NumberInput, Select, Stack, Text } from '@mantine/core';
import { IconCheck, IconPlus, IconX } from '@tabler/icons-react';
import { api, avisoError } from './api';
import { Camara } from './Escaner';
import { cantidad } from './formato';

export type Linea = { producto: string; nombre: string; unidad: string | null; teorico?: number; zona?: string | null };
type Producto = { codigo: string; nombre: string; unidad: string | null };
type Valor = number | string;

// Recuento a pie de estantería: la cámara queda abierta; se escanea, se escribe la cantidad, «Siguiente» y vuelta a escanear.
// Debajo, lo que falta por contar en la zona elegida.
export function ModoEscaner({ abierto, cerrar, ubicacion, lineas, catalogo, contado, cambiar, anadirLinea, zona, setZona, zonas, ponerZona, codigos, setCodigos, recomendados }: {
  abierto: boolean; cerrar: () => void; ubicacion: string; lineas: Linea[]; catalogo: Producto[];
  contado: Record<string, Valor>; cambiar: (v: Record<string, Valor>) => void; anadirLinea: (p: string) => void;
  zona: string; setZona: (z: string) => void; zonas: string[]; ponerZona: (l: Linea, z: string, silencioso?: boolean) => void;
  codigos: Record<string, string>; setCodigos: (c: Record<string, string>) => void; recomendados: Set<string>;
}) {
  const [actual, setActual] = useState<{ codigo?: string; producto: string | null } | null>(null);
  const [q, setQ] = useState<Valor>('');
  const [buscar, setBuscar] = useState(false);
  const [recientes, setRecientes] = useState<string[]>([]);
  const ultimo = useRef({ codigo: '', t: 0 });

  const hecho = (p: string) => contado[p] !== undefined && contado[p] !== '';
  const enZona = (l: Linea) => zona === 'todas' || (zona === '' ? !l.zona : l.zona === zona);
  // Lo recomendado (fresco y caro sin contar este mes) va primero.
  const faltan = lineas.filter((l) => enZona(l) && !hecho(l.producto))
    .sort((a, b) => Number(recomendados.has(b.producto)) - Number(recomendados.has(a.producto)));
  const vacia = !lineas.some(enZona);
  const n = Object.values(contado).filter((v) => v !== '' && v != null).length;
  const nombre = (p: string) => lineas.find((l) => l.producto === p && l.nombre !== p)?.nombre ?? catalogo.find((c) => c.codigo === p)?.nombre ?? p;
  const unidad = (p: string) => lineas.find((l) => l.producto === p)?.unidad ?? catalogo.find((c) => c.codigo === p)?.unidad ?? '';

  const leido = (codigo: string) => {
    // El mismo envase sigue delante de la cámara justo después de contarlo: no se cuenta dos veces.
    if (codigo === ultimo.current.codigo && Date.now() - ultimo.current.t < 3000) return;
    setQ(''); setActual({ codigo, producto: codigos[codigo] ?? null });
  };
  const elegir = (producto: string) => { setQ(''); setBuscar(false); setActual({ producto }); };

  const asociar = async (producto: string | null) => {
    if (!actual?.codigo || !producto) return;
    try {
      await api('/codigos', { method: 'PUT', body: { codigo: actual.codigo, producto } });
      setCodigos({ ...codigos, [actual.codigo]: producto });
      setActual({ ...actual, producto });
    } catch (e) { avisoError(e); }
  };

  const confirmar = (sumar: boolean) => {
    const p = actual?.producto;
    if (!p || q === '' || Number(q) < 0) return;
    const total = sumar && hecho(p) ? Number(contado[p]) + Number(q) : Number(q);
    cambiar({ ...contado, [p]: Math.round(total * 1000) / 1000 });
    anadirLinea(p);
    const l = lineas.find((x) => x.producto === p);
    if (zona !== 'todas' && zona !== '' && !l?.zona) ponerZona(l ?? { producto: p, nombre: nombre(p), unidad: null }, zona, true);  // la zona se aprende sola
    setRecientes([p, ...recientes.filter((x) => x !== p)].slice(0, 5));
    ultimo.current = { codigo: actual?.codigo ?? '', t: Date.now() };
    setActual(null);
  };
  const ya = actual?.producto && hecho(actual.producto) ? Number(contado[actual.producto]) : null;

  return (
    <Modal opened={abierto} onClose={cerrar} fullScreen withCloseButton={false} padding="sm" transitionProps={{ duration: 0 }}>
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap">
          <Select size="sm" value={zona === '' ? 'sin' : zona} onChange={(z) => z !== null && setZona(z === 'sin' ? '' : z)} allowDeselect={false} style={{ flex: 1, minWidth: 0 }} aria-label="Zona"
            data={[{ value: 'todas', label: 'Todas las zonas' }, ...zonas.map((z) => ({ value: z, label: z })), { value: 'sin', label: 'Sin zona' }]} />
          <Button size="sm" onClick={cerrar}>Terminar</Button>
        </Group>
        {abierto && <Camara activa={!actual && !buscar} leido={leido} />}
        {actual ? (
          <Card p="sm" withBorder style={{ borderColor: 'var(--mantine-color-marina-5)' }}>
            {!actual.producto ? (
              <Stack gap="xs">
                <Text size="sm">Código <b>{actual.codigo}</b> nuevo. ¿Qué producto es? BM lo recordará la próxima vez.</Text>
                <Select searchable limit={50} autoFocus placeholder="Busca el producto" onChange={asociar}
                  data={catalogo.map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.unidad ?? 'ud'})` }))} comboboxProps={{ withinPortal: false }} />
                <Button variant="default" onClick={() => setActual(null)}>Cancelar</Button>
              </Stack>
            ) : (
              <Stack gap="xs">
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <div style={{ minWidth: 0 }}>
                    <Text fw={600} lh={1.25}>{nombre(actual.producto)}</Text>
                    <Text size="xs" c="dimmed">{actual.producto}{ya !== null ? ` · ya contado: ${cantidad(ya)} ${unidad(actual.producto)}` : ''}</Text>
                  </div>
                  <ActionIcon variant="subtle" color="gray" onClick={() => setActual(null)} aria-label="Cancelar"><IconX size={18} /></ActionIcon>
                </Group>
                <NumberInput value={q} onChange={setQ} min={0} decimalScale={3} size="xl" autoFocus inputMode="decimal" hideControls placeholder="Cantidad"
                  rightSection={<Text c="dimmed" pr="sm">{unidad(actual.producto)}</Text>} rightSectionWidth={60} aria-label="Cantidad"
                  onKeyDown={(e) => e.key === 'Enter' && confirmar(true)} />
                {ya !== null ? (
                  <Group grow>
                    <Button size="md" onClick={() => confirmar(true)} disabled={q === ''}>Sumar ({cantidad(ya + Number(q || 0))})</Button>
                    <Button size="md" variant="light" onClick={() => confirmar(false)} disabled={q === ''}>Sustituir</Button>
                  </Group>
                ) : <Button size="md" leftSection={<IconCheck size={18} />} onClick={() => confirmar(false)} disabled={q === ''}>Siguiente</Button>}
              </Stack>
            )}
          </Card>
        ) : buscar ? (
          <Group wrap="nowrap">
            <Select searchable limit={50} autoFocus placeholder="Producto sin código (fruta, granel…)" onChange={(p) => p && elegir(p)} style={{ flex: 1 }}
              data={catalogo.map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.unidad ?? 'ud'})` }))} comboboxProps={{ withinPortal: false }} />
            <Button variant="default" onClick={() => setBuscar(false)}>Volver</Button>
          </Group>
        ) : (
          <Group justify="space-between">
            <Text size="sm" c="dimmed">Apunta al código de barras</Text>
            <Button size="compact-sm" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setBuscar(true)}>Sin código</Button>
          </Group>
        )}
        {recientes.length > 0 && !actual && (
          <Group gap={6}>
            {recientes.map((p) => <Badge key={p} variant="outline" style={{ cursor: 'pointer', textTransform: 'none' }} onClick={() => elegir(p)}>{nombre(p)}: {cantidad(Number(contado[p] ?? 0))}</Badge>)}
          </Group>
        )}
        <Group justify="space-between" gap="xs">
          <Text size="sm" fw={600}>{vacia ? `${zona}: aún sin productos. Lo que cuentes aquí quedará en esta zona.`
            : faltan.length ? `Falta por contar${zona === 'todas' ? '' : ` en ${zona || 'sin zona'}`}: ${faltan.length}` : 'Todo contado en esta zona'}</Text>
          <Badge variant="light" color="teal">{n === 1 ? '1 contado' : `${n} contados`}</Badge>
        </Group>
        <div style={{ maxHeight: '40vh', overflowY: 'auto' }}>
          <Stack gap={4}>
            {faltan.map((l) => (
              <Button key={l.producto} variant="default" justify="space-between" fullWidth onClick={() => elegir(l.producto)}
                leftSection={recomendados.has(l.producto) ? '★' : undefined}
                rightSection={<Text size="xs" c="dimmed">{l.unidad}</Text>} styles={{ inner: { minWidth: 0 }, label: { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }}>
                {l.nombre}
              </Button>
            ))}
          </Stack>
        </div>
        <Text size="xs" c="dimmed">Lo contado se guarda en este móvil. Al terminar, pulsa «Guardar recuento» (sin cobertura, se envía solo después). Ubicación: {ubicacion}</Text>
      </Stack>
    </Modal>
  );
}
