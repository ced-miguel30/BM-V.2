import { useEffect, useState } from 'react';
import {
  Badge, Button, Card, Drawer, Group, Loader, Modal, Select, Stack, Table, Text, Textarea, Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { IconBan } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { BadgeEstado, BadgeServicio, Cabecera, ORIGEN, Vacio } from '../comun';
import { SERVICIOS, cantidad, euros, fecha } from '../formato';

type Fila = {
  id: number; fecha: string; servicio: string | null; tipo: string; origen: string; comensales: number | null;
  nota: string | null; usuario: string | null; anulado: number; n_lineas: number; coste: number | null; peor: number | null;
};
type Traza = { cantidad: number; coste_unit: number | null; documento: string | null; fecha: string | null; proveedor: string | null; tipo_doc: string | null };
type Detalle = Fila & { lineas: { id: number; nombre: string; producto: string; unidad: string; cantidad: number; coste: number | null; coste_estado: string; receta: string | null; traza: Traza[] }[] };

const inicioMes = () => new Date().toISOString().slice(0, 8) + '01';

export function Consumos() {
  const [rango, setRango] = useState<[string | null, string | null]>([inicioMes(), new Date().toISOString().slice(0, 10)]);
  const [serv, setServ] = useState<string | null>(null);
  const [tipo, setTipo] = useState<string | null>(null);
  const [filas, setFilas] = useState<Fila[] | null>(null);
  const [abierto, setAbierto] = useState<number | null>(null);
  const [det, setDet] = useState<Detalle | null>(null);
  const [anular, setAnular] = useState(false);
  const [motivo, setMotivo] = useState('');

  const cargar = () => {
    const [d, h] = rango;
    if (!d || !h) return;
    setFilas(null);
    const q = new URLSearchParams({ desde: d, hasta: h, ...(serv ? { servicio: serv } : {}), ...(tipo ? { tipo } : {}) });
    api<Fila[]>(`/consumos?${q}`).then(setFilas).catch(avisoError);
  };
  useEffect(cargar, [rango, serv, tipo]);
  useEffect(() => {
    setDet(null);
    if (abierto != null) api<Detalle>(`/consumos/${abierto}`).then(setDet).catch(avisoError);
  }, [abierto]);

  const confirmarAnular = async () => {
    try {
      await api(`/consumos/${abierto}/anular`, { body: { motivo } });
      avisoOk('El registro ya no cuenta en costes ni stock', 'Anulado');
      setAnular(false); setMotivo(''); setAbierto(null); cargar();
    } catch (e) { avisoError(e); }
  };

  const total = filas?.filter((f) => !f.anulado).reduce((a, f) => a + (f.coste ?? 0), 0) ?? 0;

  return (
    <>
      <Cabecera titulo="Consumos" subtitulo={filas ? `${filas.length} registros · ${euros(total)}` : 'Cargando…'}>
        <DatePickerInput type="range" value={rango} onChange={(x) => setRango([x[0] && String(x[0]).slice(0, 10), x[1] && String(x[1]).slice(0, 10)])}
          valueFormat="DD/MM/YY" w={220} aria-label="Fechas" />
        <Select placeholder="Servicio" data={SERVICIOS.map((s) => ({ value: s.value, label: s.label }))} value={serv} onChange={setServ} clearable w={150} />
        <Select placeholder="Tipo" data={[{ value: 'consumo', label: 'Consumo' }, { value: 'merma', label: 'Merma' }]} value={tipo} onChange={setTipo} clearable w={130} />
      </Cabecera>
      <Card p={0}>
        {!filas ? <Group justify="center" p="xl"><Loader /></Group> : !filas.length ? <Vacio texto="No hay registros en estas fechas" /> : (
          <Table.ScrollContainer minWidth={760}>
            <Table className="tabla-click" stickyHeader>
              <Table.Thead>
                <Table.Tr><Table.Th>Fecha</Table.Th><Table.Th>Servicio</Table.Th><Table.Th>Origen</Table.Th><Table.Th>Detalle</Table.Th>
                  <Table.Th className="num">Líneas</Table.Th><Table.Th className="num">Coste</Table.Th><Table.Th>Fiabilidad</Table.Th></Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filas.map((f) => (
                  <Table.Tr key={f.id} onClick={() => setAbierto(f.id)} opacity={f.anulado ? 0.45 : 1}>
                    <Table.Td>{fecha(f.fecha)}</Table.Td>
                    <Table.Td><Group gap={6}><BadgeServicio valor={f.servicio} />{f.tipo === 'merma' && <Badge color="red" variant="light">Merma</Badge>}</Group></Table.Td>
                    <Table.Td><Text size="sm">{ORIGEN[f.origen] ?? f.origen}</Text></Table.Td>
                    <Table.Td maw={320}>
                      <Text size="sm" truncate>{f.anulado ? 'ANULADO · ' : ''}{f.comensales ? `${f.comensales} comensales · ` : ''}{f.nota ?? ''}</Text>
                    </Table.Td>
                    <Table.Td className="num">{f.n_lineas}</Table.Td>
                    <Table.Td className="num" fw={600}>{euros(f.coste)}</Table.Td>
                    <Table.Td><BadgeEstado nivel={f.peor} /></Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Card>

      <Drawer opened={abierto != null} onClose={() => setAbierto(null)} position="right" size="xl"
        title={det ? <Group gap="sm"><Text fw={700}>{fecha(det.fecha)}</Text><BadgeServicio valor={det.servicio} /></Group> : 'Detalle'}>
        {!det ? <Loader /> : (
          <Stack>
            <Group gap="lg">
              <div><Text size="xs" c="dimmed">Coste total</Text><Text fw={700} fz="xl">{euros(det.lineas.reduce((a, l) => a + (l.coste ?? 0), 0))}</Text></div>
              {det.comensales ? <div><Text size="xs" c="dimmed">Comensales</Text><Text fw={700} fz="xl">{det.comensales}</Text></div> : null}
              <div><Text size="xs" c="dimmed">Origen</Text><Text fw={600}>{ORIGEN[det.origen] ?? det.origen}{det.usuario ? ` · ${det.usuario}` : ''}</Text></div>
            </Group>
            {det.nota && <Text size="sm" c="dimmed">{det.nota}</Text>}
            <Table>
              <Table.Thead><Table.Tr><Table.Th>Producto</Table.Th><Table.Th className="num">Cantidad</Table.Th><Table.Th className="num">Coste</Table.Th><Table.Th>De dónde sale</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>
                {det.lineas.map((l) => (
                  <Table.Tr key={l.id}>
                    <Table.Td><Text size="sm" fw={500}>{l.nombre}</Text><Text size="xs" c="dimmed">{l.receta ? `Receta: ${l.receta}` : l.producto}</Text></Table.Td>
                    <Table.Td className="num">{cantidad(l.cantidad)} {l.unidad}</Table.Td>
                    <Table.Td className="num" fw={600}>{euros(l.coste)}</Table.Td>
                    <Table.Td>
                      <Stack gap={2}>
                        <BadgeEstado estado={l.coste_estado} />
                        {l.traza.map((t, i) => (
                          <Tooltip key={i} label={t.proveedor || 'Último precio conocido'}>
                            <Text size="xs" c="dimmed">{cantidad(t.cantidad)} × {euros(t.coste_unit)} · {t.documento ? `${t.documento} (${fecha(t.fecha)})` : 'sin lote'}</Text>
                          </Tooltip>
                        ))}
                      </Stack>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            {!det.anulado && det.origen !== 'tpv' && (
              <Group justify="flex-end"><Button color="red" variant="light" leftSection={<IconBan size={16} />} onClick={() => setAnular(true)}>Anular registro</Button></Group>
            )}
            {det.origen === 'tpv' && <Text size="sm" c="dimmed">Los consumos TPV se corrigen cambiando la asignación del artículo en Ventas TPV.</Text>}
          </Stack>
        )}
      </Drawer>

      <Modal opened={anular} onClose={() => setAnular(false)} title="Anular registro" centered>
        <Stack>
          <Text size="sm">El registro queda visible pero deja de contar en costes y stock. Los lotes se recalculan.</Text>
          <Textarea label="Motivo" value={motivo} onChange={(e) => setMotivo(e.currentTarget.value)} required autosize minRows={2} />
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAnular(false)}>Cancelar</Button>
            <Button color="red" onClick={confirmarAnular} disabled={!motivo.trim()}>Anular</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
