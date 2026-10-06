import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Anchor, Badge, Button, Card, Group, Stack, Text, ThemeIcon } from '@mantine/core';
import { MonthPickerInput } from '@mantine/dates';
import { IconAlertTriangle, IconCheck, IconFileText, IconX } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera } from '../comun';

type Paso = { clave: string; titulo: string; ok: boolean; detalle: string; ruta: string; obligatorio: boolean };
const mesAnterior = () => { const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - 1); return d.toISOString().slice(0, 7); };

export function Cierre() {
  const [mes, setMes] = useState(mesAnterior());
  const [d, setD] = useState<{ pasos: Paso[]; listo: boolean } | null>(null);
  const nav = useNavigate();
  useEffect(() => { setD(null); api<typeof d>(`/cierre?mes=${mes}`).then(setD).catch(avisoError); }, [mes]);
  const hechos = d?.pasos.filter((p) => p.ok).length ?? 0;
  return (
    <>
      <Cabecera titulo="Cierre de mes" subtitulo="Lo que hace falta para que los números del mes sean definitivos. BM lo comprueba solo.">
        <MonthPickerInput value={`${mes}-01`} onChange={(x) => x && setMes(String(x).slice(0, 7))} valueFormat="MMMM YYYY" w={180} aria-label="Mes" />
        <Button leftSection={<IconFileText size={16} />} onClick={() => nav(`/informe?mes=${mes}`)}>Informe del mes</Button>
      </Cabecera>
      {!d ? <Text c="dimmed">Comprobando…</Text> : (
        <Stack>
          {d.listo ? <Alert color="teal" icon={<IconCheck />} title="Mes listo para cerrar">Los datos del mes están completos. El informe ya es definitivo.</Alert>
            : <Alert color="orange" icon={<IconAlertTriangle />} title={`${hechos} de ${d.pasos.length} pasos completos`}>Hasta completar los obligatorios, las cifras del mes pueden cambiar.</Alert>}
          {d.pasos.map((p, i) => (
            <Card key={p.clave} p="md">
              <Group justify="space-between" wrap="nowrap">
                <Group wrap="nowrap" gap="md">
                  <ThemeIcon radius="xl" size={34} color={p.ok ? 'teal' : p.obligatorio ? 'red' : 'yellow'} variant={p.ok ? 'filled' : 'light'}>
                    {p.ok ? <IconCheck size={18} /> : p.obligatorio ? <IconX size={18} /> : <IconAlertTriangle size={18} />}
                  </ThemeIcon>
                  <div>
                    <Group gap={6}><Text fw={600}>{i + 1}. {p.titulo}</Text>{!p.obligatorio && <Badge size="xs" variant="light" color="gray">recomendado</Badge>}</Group>
                    <Text size="sm" c="dimmed">{p.detalle}</Text>
                  </div>
                </Group>
                {!p.ok && <Anchor size="sm" onClick={() => nav(p.ruta)} style={{ whiteSpace: 'nowrap' }}>Ir a resolverlo →</Anchor>}
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </>
  );
}
