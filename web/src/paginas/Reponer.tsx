import { useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Group, Stack, Text } from '@mantine/core';
import { IconInfoCircle, IconPrinter } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera, Vacio } from '../comun';
import { cantidad } from '../formato';

type Linea = { producto: string; nombre: string; unidad: string | null; restaurante: number; minimo: number; economato: number; ritmo: number; subir: number };

export function Reponer() {
  const [lista, setLista] = useState<Linea[] | null>(null);
  const [hecho, setHecho] = useState<Record<string, boolean>>({});
  useEffect(() => { api<Linea[]>('/prevision/reposicion').then(setLista).catch(avisoError); }, []);
  const pendientes = (lista ?? []).filter((l) => !hecho[l.producto]).length;
  return (
    <>
      <Cabecera titulo="Reponer restaurante" subtitulo="Lo que conviene subir hoy del economato a Restaurante y cocina, según lo que se gasta">
        <Button variant="default" leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>Imprimir lista</Button>
      </Cabecera>
      <Alert icon={<IconInfoCircle />} color="blue" mb="md" className="no-imprimir">
        Al subirlo, registra el traslado en Business Central (Economato → almacén del servicio). BM lo importará con los movimientos.
      </Alert>
      {!lista ? <Text c="dimmed">Calculando…</Text> : !lista.length ? <Card><Vacio texto="Nada que reponer: el restaurante tiene de todo para los próximos días" /></Card> : (
        <Stack gap={6}>
          <Text size="sm" c="dimmed">{pendientes} de {lista.length} pendientes</Text>
          {lista.map((l) => (
            <Card key={l.producto} p="sm" withBorder opacity={hecho[l.producto] ? 0.5 : 1}>
              <Group justify="space-between" wrap="nowrap">
                <Checkbox size="md" checked={!!hecho[l.producto]} onChange={(e) => setHecho({ ...hecho, [l.producto]: e.currentTarget.checked })}
                  label={<><Text fw={500} td={hecho[l.producto] ? 'line-through' : undefined}>{l.nombre}</Text>
                    <Text size="xs" c="dimmed">Queda {cantidad(l.restaurante)} · se gastan {cantidad(l.ritmo)}/día · en economato {cantidad(l.economato)}</Text></>} />
                <Text fw={700} fz="lg" style={{ whiteSpace: 'nowrap' }}>{cantidad(l.subir)} {l.unidad}</Text>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </>
  );
}
