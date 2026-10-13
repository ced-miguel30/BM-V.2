import { useState } from 'react';
import { Badge, Button, Card, Group, Stack, Text, TextInput } from '@mantine/core';
import { api, avisoError, avisoOk } from './api';
import { Vacio } from './comun';
import { cantidad } from './formato';

export type Solicitud = { id: number; creado: string; usuario: string | null; estado: string; nota: string | null; respuesta: string | null;
  respondido: string | null; respondido_por: string | null; lineas: { producto: string; nombre: string; unidad: string | null; cantidad: number }[] };
const ESTADO: Record<string, { texto: string; color: string }> = {
  pendiente: { texto: 'Pendiente', color: 'orange' }, pedida: { texto: 'Pedido hecho', color: 'teal' }, rechazada: { texto: 'Rechazada', color: 'red' } };
const cuando = (s: string) => `${s.slice(8, 10)}/${s.slice(5, 7)} ${s.slice(11, 16)}`;

/** Solicitudes de pedido. Con `recargar`, administración puede responderlas; sin él, solo se consultan (el jefe). */
export function ListaSolicitudes({ lista, recargar }: { lista: Solicitud[] | null; recargar?: () => void }) {
  const [motivo, setMotivo] = useState<Record<number, string>>({});
  const responder = async (s: Solicitud, estado: 'pedida' | 'rechazada') => {
    try {
      await api(`/solicitudes/${s.id}/responder`, { body: { estado, respuesta: motivo[s.id] || null } });
      avisoOk(estado === 'pedida' ? 'El jefe verá que ya está pedido' : 'El jefe verá el motivo', 'Solicitud respondida');
      recargar?.();
    } catch (e) { avisoError(e); }
  };
  if (!lista) return <Text c="dimmed">Cargando…</Text>;
  if (!lista.length) return <Card><Vacio texto="No hay solicitudes de pedido" /></Card>;
  return (
    <Stack>
      {lista.map((s) => (
        <Card key={s.id} p="md" opacity={s.estado === 'pendiente' ? 1 : 0.75}>
          <Group justify="space-between" mb="xs" wrap="wrap">
            <Text fw={600}>{s.usuario ?? '—'} · {cuando(s.creado)}</Text>
            <Badge variant="light" color={ESTADO[s.estado]?.color}>{ESTADO[s.estado]?.texto ?? s.estado}</Badge>
          </Group>
          <Stack gap={2}>
            {s.lineas.map((l) => <Text key={l.producto} size="sm"><b>{cantidad(l.cantidad)} {l.unidad ?? ''}</b> {l.nombre}</Text>)}
          </Stack>
          {s.nota && <Text size="sm" c="dimmed" mt={4}>«{s.nota}»</Text>}
          {s.respuesta && <Text size="sm" mt={4}>Respuesta de {s.respondido_por}: {s.respuesta}</Text>}
          {recargar && s.estado === 'pendiente' && (
            <Group mt="sm" align="flex-end" wrap="wrap">
              <TextInput placeholder="Respuesta (obligatoria si se rechaza)" value={motivo[s.id] ?? ''} style={{ flex: 1, minWidth: 200 }}
                onChange={(e) => setMotivo({ ...motivo, [s.id]: e.currentTarget.value })} />
              <Button color="teal" variant="light" onClick={() => responder(s, 'pedida')}>Ya está pedido</Button>
              <Button color="red" variant="light" onClick={() => responder(s, 'rechazada')}>Rechazar</Button>
            </Group>
          )}
        </Card>
      ))}
    </Stack>
  );
}
