import { useEffect, useMemo, useState } from 'react';
import { Alert, Badge, Button, Card, Group, NumberInput, SimpleGrid, Stack, Table, Text } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { IconCheck, IconWand } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera } from '../comun';
import { cantidad, hoy } from '../formato';

type Item = { etiqueta: string; seccion: string; unidad: string | null; producto: string | null; por_comensal: number | null;
  propuesta: number | null; sacado: number | null; sobro: number | null };
type Datos = { fecha: string; comensales_registrados: number | null; comensales_previstos: number | null; confirmado: boolean; items: Item[] };
type Valores = Record<string, { sacado: number | string; sobro: number | string }>;

export function Buffet() {
  const [fecha, setFecha] = useState(hoy());
  const [d, setD] = useState<Datos | null>(null);
  const [v, setV] = useState<Valores>({});
  const [comensales, setComensales] = useState<number | string>('');
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    setD(null);
    api<Datos>(`/buffet?fecha=${fecha}`).then((x) => {
      setD(x);
      setComensales(x.comensales_registrados ?? x.comensales_previstos ?? '');
      setV(Object.fromEntries(x.items.map((i) => [i.etiqueta, { sacado: i.sacado ?? '', sobro: i.sobro ?? '' }])));
    }).catch(avisoError);
  }, [fecha]);

  const secciones = useMemo(() => {
    const m = new Map<string, Item[]>();
    (d?.items ?? []).forEach((i) => m.set(i.seccion, [...(m.get(i.seccion) ?? []), i]));
    return [...m.entries()];
  }, [d]);
  const escala = d && d.comensales_registrados == null && d.comensales_previstos && Number(comensales) ? Number(comensales) / d.comensales_previstos : 1;
  const enteras = (u: string | null) => ['UD', 'PQ', 'BT', 'RAC'].includes((u ?? '').toUpperCase());
  const prop = (i: Item) => {
    if (i.propuesta == null) return null;
    const q = i.por_comensal != null && Number(comensales) ? i.por_comensal * Number(comensales) : i.propuesta * escala;
    return enteras(i.unidad) ? Math.max(1, Math.ceil(q - 1e-9)) : Math.ceil(q * 100) / 100;
  };
  const usarPropuesta = () => setV(Object.fromEntries((d?.items ?? []).map((i) => [i.etiqueta, { sacado: prop(i) ?? v[i.etiqueta]?.sacado ?? '', sobro: v[i.etiqueta]?.sobro ?? '' }])));
  const rellenos = Object.values(v).filter((x) => Number(x.sacado) > 0).length;

  const confirmar = async () => {
    setGuardando(true);
    try {
      await api('/buffet', { body: { fecha, comensales: Number(comensales) || null,
        items: Object.entries(v).filter(([, x]) => Number(x.sacado) > 0).map(([etiqueta, x]) => ({ etiqueta, sacado: Number(x.sacado), sobro: Number(x.sobro) || 0 })) } });
      avisoOk(`${rellenos} conceptos. El consumo y el stock quedan actualizados.`, 'Buffet registrado');
      setD(d && { ...d, confirmado: true });
    } catch (e) { avisoError(e); } finally { setGuardando(false); }
  };

  return (
    <>
      <Cabecera titulo="Buffet del día" subtitulo="Lo que conviene sacar según los comensales y lo que se gasta por comensal. Anota lo que sobró y confírmalo.">
        <DateInput value={fecha} onChange={(x) => x && setFecha(String(x).slice(0, 10))} valueFormat="DD/MM/YYYY" w={150} aria-label="Fecha" />
      </Cabecera>
      {!d ? <Text c="dimmed">Calculando…</Text> : (
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Card>
              <NumberInput label="Comensales" size="md" min={0} allowDecimal={false} value={comensales} onChange={setComensales}
                description={d.comensales_registrados != null ? 'Registrados en el desayuno de este día' : `Previstos: ${d.comensales_previstos ?? '—'} (media de este día de la semana)`} />
            </Card>
            <Card>
              <Stack gap="xs" justify="center" h="100%">
                <Button fullWidth variant="light" leftSection={<IconWand size={18} />} onClick={usarPropuesta}>Rellenar con la propuesta</Button>
                <Button fullWidth leftSection={<IconCheck size={18} />} onClick={confirmar} loading={guardando} disabled={!rellenos}>
                  {d.confirmado ? 'Corregir buffet' : 'Confirmar buffet'}{rellenos ? ` (${rellenos})` : ''}
                </Button>
                {d.confirmado && <Badge color="teal" variant="light" mx="auto">Ya confirmado este día</Badge>}
              </Stack>
            </Card>
          </SimpleGrid>
          {d.items.every((i) => i.propuesta == null) && (
            <Alert color="blue">Aún no hay histórico con comensales para proponer cantidades. Rellena lo sacado unos días y BM aprenderá solo.</Alert>
          )}
          <SimpleGrid cols={{ base: 1, lg: 2 }}>
            {secciones.map(([sec, items]) => (
              <Card key={sec} p="sm">
                <Text fw={700} mb={6}>{sec}</Text>
                <Table>
                  <Table.Thead><Table.Tr><Table.Th>Concepto</Table.Th><Table.Th className="num">Propuesta</Table.Th><Table.Th w={110}>Sacado</Table.Th><Table.Th w={100}>Sobró</Table.Th></Table.Tr></Table.Thead>
                  <Table.Tbody>
                    {items.map((i) => (
                      <Table.Tr key={i.etiqueta}>
                        <Table.Td><Text size="sm" fw={500}>{i.etiqueta}</Text>{i.por_comensal != null && <Text size="xs" c="dimmed">{cantidad(i.por_comensal)} {i.unidad} por comensal</Text>}</Table.Td>
                        <Table.Td className="num"><Text size="sm" c="dimmed">{prop(i) == null ? '—' : `${cantidad(prop(i))} ${i.unidad ?? ''}`}</Text></Table.Td>
                        <Table.Td><NumberInput size="xs" min={0} decimalScale={3} hideControls value={v[i.etiqueta]?.sacado ?? ''} aria-label={`Sacado ${i.etiqueta}`}
                          onChange={(x) => setV({ ...v, [i.etiqueta]: { ...v[i.etiqueta], sacado: x } })} rightSection={<Text size="xs" c="dimmed" pr={4}>{i.unidad}</Text>} rightSectionWidth={30} /></Table.Td>
                        <Table.Td><NumberInput size="xs" min={0} decimalScale={3} hideControls value={v[i.etiqueta]?.sobro ?? ''} aria-label={`Sobró ${i.etiqueta}`}
                          onChange={(x) => setV({ ...v, [i.etiqueta]: { ...v[i.etiqueta], sobro: x } })} /></Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Card>
            ))}
          </SimpleGrid>
        </Stack>
      )}
    </>
  );
}
