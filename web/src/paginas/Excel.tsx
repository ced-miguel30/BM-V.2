import { useState } from 'react';
import { Alert, Anchor, Badge, Button, Card, FileButton, Group, List, NumberInput, Stack, Table, Text, Tooltip } from '@mantine/core';
import { IconCheck, IconDownload, IconFileSpreadsheet } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { BadgeServicio, Cabecera, Vacio } from '../comun';
import { euros, fecha } from '../formato';

type Dia = {
  hoja: string; fecha: string | null; tipo: string; servicio: string; comensales: number | null; filas: number;
  n_lineas: number; coste_estimado?: number; reemplaza: number; notas: string | null;
  errores: { fila: number; mensaje: string; nombre: string }[];
  avisos: string[];
};
const HOJA: Record<string, string> = {
  Registro: 'Desayuno', RegistroBebidasDesayuno: 'Bebidas desayuno', RegistroComida: 'Comida', RegistroCena: 'Cena', ConsumoBuffet: 'Buffet',
};

export function Excel() {
  const [archivo, setArchivo] = useState<File | null>(null);
  const [plan, setPlan] = useState<Dia[] | null>(null);
  const [cargando, setCargando] = useState(false);
  const [comensales, setComensales] = useState<Record<string, number | string>>({});

  const enviar = async (f: File, confirmar: boolean) => {
    const form = new FormData();
    form.append('archivo', f);
    form.append('comensales', JSON.stringify(comensales));
    return api<{ plan: Dia[]; importados: number }>(`/excel?confirmar=${confirmar}`, { form });
  };
  const previsualizar = async (f: File | null) => {
    if (!f) return;
    setCargando(true); setArchivo(f); setPlan(null); setComensales({});
    try { setPlan((await enviar(f, false)).plan); } catch (e) { avisoError(e); setArchivo(null); } finally { setCargando(false); }
  };
  const importar = async () => {
    if (!archivo) return;
    setCargando(true);
    try {
      const r = await enviar(archivo, true);
      avisoOk(`${r.importados} registros guardados. Ya puede borrar esas filas del Excel si quiere.`, 'Excel importado');
      setPlan(null); setArchivo(null);
    } catch (e) { avisoError(e); } finally { setCargando(false); }
  };

  const validos = plan?.filter((d) => !d.errores.length && d.n_lineas) ?? [];
  const conError = plan?.filter((d) => d.errores.length) ?? [];
  const verCoste = plan?.some((d) => d.coste_estimado !== undefined);

  return (
    <>
      <Cabecera titulo="Importar Excel" subtitulo="La plantilla de siempre: desayuno, bebidas, comida, cena y buffet.">
        <Button component="a" href="/api/excel/plantilla" variant="default" leftSection={<IconDownload size={16} />}>Descargar plantilla</Button>
        <FileButton onChange={previsualizar} accept=".xlsx">
          {(props) => <Button {...props} loading={cargando && !plan} leftSection={<IconFileSpreadsheet size={16} />}>Subir Excel</Button>}
        </FileButton>
      </Cabecera>

      {!plan ? (
        <Card>
          <Vacio texto="Sube el Excel rellenado. Primero verás una vista previa; no se guarda nada hasta confirmar.">
            <List size="sm" c="dimmed" mt="sm" spacing={4}>
              <List.Item>Cada día de cada hoja es un registro. Volver a subir un día lo sustituye, nunca duplica.</List.Item>
              <List.Item>Los días con algún error no se importan; el resto sí.</List.Item>
              <List.Item>La plantilla descargada trae los desplegables con las recetas actuales.</List.Item>
            </List>
          </Vacio>
        </Card>
      ) : (
        <Stack>
          {plan.some((d) => d.hoja === 'Registro' && d.fecha && !(comensales[d.fecha] ?? d.comensales)) && (
            <Alert color="yellow" title="Faltan los comensales de algunos días">
              El Excel no los trae (columna Huéspedes a 0). Escríbelos en la tabla: sin ellos no hay coste por comensal ni previsión del buffet.
            </Alert>
          )}
          {conError.length > 0 && (
            <Alert color="red" title={`${conError.length} días con errores (no se importarán)`}>
              Corrige esas filas en el Excel y vuelve a subirlo. {validos.length > 0 && 'Los demás días se pueden importar ya.'}
            </Alert>
          )}
          <Card p={0}>
            <Table.ScrollContainer minWidth={720}>
              <Table>
                <Table.Thead><Table.Tr><Table.Th>Fecha</Table.Th><Table.Th>Hoja</Table.Th><Table.Th className="num">Filas</Table.Th>
                  <Table.Th className="num">Comensales</Table.Th><Table.Th className="num">Productos</Table.Th>
                  {verCoste && <Table.Th className="num">Coste estimado</Table.Th>}<Table.Th>Estado</Table.Th></Table.Tr></Table.Thead>
                <Table.Tbody>
                  {plan.map((d, i) => (
                    <Table.Tr key={i} bg={d.errores.length ? 'var(--mantine-color-red-light)' : undefined}>
                      <Table.Td>{d.fecha ? fecha(d.fecha) : '—'}</Table.Td>
                      <Table.Td><Group gap={6}><Text size="sm">{HOJA[d.hoja] ?? d.hoja}</Text>{d.tipo === 'merma' && <Badge size="xs" color="red">Merma</Badge>}</Group></Table.Td>
                      <Table.Td className="num">{d.filas}</Table.Td>
                      <Table.Td className="num">{d.hoja === 'Registro' && d.fecha ? (
                        <NumberInput size="xs" w={90} min={0} allowDecimal={false} placeholder="¿?" ml="auto" aria-label={`Comensales ${d.fecha}`}
                          value={comensales[d.fecha] ?? (d.comensales || '')} error={!(comensales[d.fecha] ?? d.comensales)}
                          onChange={(x) => setComensales({ ...comensales, [d.fecha!]: x })} />) : (d.comensales ?? '—')}</Table.Td>
                      <Table.Td className="num">{d.n_lineas}</Table.Td>
                      {verCoste && <Table.Td className="num">{euros(d.coste_estimado)}</Table.Td>}
                      <Table.Td>
                        {d.errores.length ? (
                          <Stack gap={2}>{d.errores.map((e, j) => <Text key={j} size="xs" c="red">Fila {e.fila}: {e.mensaje}</Text>)}</Stack>
                        ) : <Group gap={6}>
                          {d.reemplaza ? <Badge color="yellow" variant="light">Sustituye lo registrado</Badge> : <Badge color="teal" variant="light">Nuevo</Badge>}
                          {d.avisos?.length > 0 && <Tooltip multiline w={360} label={d.avisos.join(' · ')}><Badge color="blue" variant="light">{d.avisos.length} avisos</Badge></Tooltip>}
                        </Group>}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Card>
          <Group justify="space-between">
            <Anchor size="sm" onClick={() => { setPlan(null); setArchivo(null); }}>Cancelar</Anchor>
            <Button size="md" leftSection={<IconCheck size={18} />} onClick={importar} loading={cargando} disabled={!validos.length}>
              Importar {validos.length} {validos.length === 1 ? 'registro' : 'registros'}
            </Button>
          </Group>
          <Group gap={6}><BadgeServicio valor="desayuno" /><Text size="xs" c="dimmed">Las bebidas y el buffet del desayuno cuentan en el servicio de desayuno.</Text></Group>
        </Stack>
      )}
    </>
  );
}
