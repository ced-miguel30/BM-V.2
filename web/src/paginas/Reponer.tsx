import { useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Group, Stack, Text } from '@mantine/core';
import { IconInfoCircle, IconPrinter } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { BotonEscanear, type Producto } from '../EscanearProducto';
import { Cabecera, Vacio } from '../comun';
import { cantidad, hoy } from '../formato';

// Lo marcado como subido se guarda en el móvil hasta el día siguiente (si se recarga la página no se pierde).
const clave = () => `bm.reponer.${hoy()}`;
const leer = (): Record<string, boolean> => { try { return JSON.parse(localStorage.getItem(clave()) ?? '{}'); } catch { return {}; } };

type Linea = { producto: string; nombre: string; unidad: string | null; restaurante: number; minimo: number; economato: number; ritmo: number; subir: number; fiable: boolean };

export function Reponer() {
  const [lista, setLista] = useState<Linea[] | null>(null);
  const [hecho, setHechoEstado] = useState<Record<string, boolean>>(leer);
  const [productos, setProductos] = useState<Producto[]>([]);
  const setHecho = (h: Record<string, boolean>) => { setHechoEstado(h); try { localStorage.setItem(clave(), JSON.stringify(h)); } catch { /* sin almacenamiento */ } };
  useEffect(() => {
    api<Linea[]>('/prevision/reposicion').then(setLista).catch(avisoError);
    api<{ productos: Producto[] }>('/catalogo').then((c) => setProductos(c.productos)).catch(() => null);
  }, []);
  // Escanear lo que se va cogiendo del economato lo tacha de la lista.
  const escaneado = (p: string) => {
    const l = lista?.find((x) => x.producto === p);
    if (!l) { avisoError(new Error(`${productos.find((x) => x.codigo === p)?.nombre ?? p} no está en la lista de hoy`)); return; }
    setHecho({ ...leer(), [p]: true });
    avisoOk(`${cantidad(l.subir)} ${l.unidad ?? ''}`, `✓ ${l.nombre}`);
  };
  const pendientes = (lista ?? []).filter((l) => !hecho[l.producto]).length;
  return (
    <>
      <Cabecera titulo="Reponer restaurante" subtitulo="Lo que conviene subir hoy del economato a Restaurante y cocina, según lo que se gasta">
        <Button variant="default" leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>Imprimir lista</Button>
      </Cabecera>
      <Alert icon={<IconInfoCircle />} color="blue" mb="md" className="no-imprimir">
        Al subirlo, registra el traslado en Noray (Economato → almacén del servicio). BM lo importará con los movimientos.
      </Alert>
      {!lista ? <Text c="dimmed">Calculando…</Text> : !lista.length ? <Card><Vacio texto="Nada que reponer: el restaurante tiene de todo para los próximos días" /></Card> : (
        <Stack gap={6}>
          <Group justify="space-between" className="no-imprimir">
            <Text size="sm" c="dimmed">{pendientes} de {lista.length} pendientes</Text>
            <BotonEscanear productos={productos} texto="Escanear lo que subo" elegido={escaneado} />
          </Group>
          {lista.map((l) => (
            <Card key={l.producto} p="sm" withBorder opacity={hecho[l.producto] ? 0.5 : 1}>
              <Group justify="space-between" wrap="nowrap">
                <Checkbox size="md" checked={!!hecho[l.producto]} onChange={(e) => setHecho({ ...hecho, [l.producto]: e.currentTarget.checked })}
                  label={<><Text fw={500} td={hecho[l.producto] ? 'line-through' : undefined}>{l.nombre}</Text>
                    <Text size="xs" c="dimmed">{l.fiable ? `Queda ${cantidad(l.restaurante)}` : 'Puede que quede poco (estimado: míralo antes de subir)'} · se gastan {cantidad(l.ritmo)}/día · en economato {cantidad(l.economato)}</Text></>} />
                <Text fw={700} fz="lg" style={{ whiteSpace: 'nowrap' }}>{cantidad(l.subir)} {l.unidad}</Text>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </>
  );
}
