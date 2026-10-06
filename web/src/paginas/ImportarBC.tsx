import { useEffect, useState } from 'react';
import { Button, Card, FileButton, List, SimpleGrid, Stack, Text, ThemeIcon, Title } from '@mantine/core';
import { IconFileSpreadsheet } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera } from '../comun';
import { fecha } from '../formato';

function Subida({ tipo, titulo, pasos, alSubir }: { tipo: string; titulo: string; pasos: string[]; alSubir?: () => void }) {
  const [cargando, setCargando] = useState(false);
  const subir = async (f: File | null) => {
    if (!f) return;
    setCargando(true);
    const form = new FormData();
    form.append('archivo', f);
    try {
      const r = await api<{ filas: number }>(`/bc/${tipo}`, { form });
      avisoOk(`${r.filas.toLocaleString('es-ES')} filas. Costes recalculados.`, titulo);
      alSubir?.();
    } catch (e) { avisoError(e); } finally { setCargando(false); }
  };
  return (
    <Card>
      <Stack>
        <ThemeIcon size={44} radius="md" variant="light" color="teal"><IconFileSpreadsheet size={24} /></ThemeIcon>
        <Title order={4}>{titulo}</Title>
        <List type="ordered" size="sm" spacing={6}>{pasos.map((p) => <List.Item key={p}>{p}</List.Item>)}</List>
        <FileButton onChange={subir} accept=".xlsx">
          {(props) => <Button {...props} loading={cargando}>Subir Excel</Button>}
        </FileButton>
      </Stack>
    </Card>
  );
}

export function ImportarBC() {
  const [estado, setEstado] = useState<{ ultimo: string | null; exportar_desde: string | null } | null>(null);
  const cargar = () => api<typeof estado>('/bc/estado').then(setEstado).catch(avisoError);
  useEffect(() => { cargar(); }, []);
  return (
    <>
      <Cabecera titulo="Importar de Business Central" subtitulo="Reimportar es seguro: lo que ya existe se actualiza, nunca se duplica." />
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <Subida tipo="movimientos" titulo="Movimientos de producto" alSubir={cargar} pasos={[
          'En BC busca (Alt+Q) "Movimientos de producto".',
          estado?.exportar_desde
            ? `Filtra Fecha registro escribiendo ${estado.exportar_desde.slice(8, 10)}/${estado.exportar_desde.slice(5, 7)}/${estado.exportar_desde.slice(2, 4)}.. (último importado: ${fecha(estado.ultimo)}). Solo lo nuevo: tarda segundos; todo el histórico, casi un minuto.`
            : 'Primera vez: sin filtro de fecha (todo el histórico).',
          'Compartir → Abrir en Excel y guarda el fichero.',
          'Súbelo aquí. Recomendado: cada semana y tras el inventario de fin de mes.',
        ]} />
        <Subida tipo="productos" titulo="Maestro de productos" pasos={[
          'En BC busca "Productos".',
          'Compartir → Abrir en Excel.',
          'Súbelo aquí cuando se den de alta artículos nuevos.',
        ]} />
        <Subida tipo="facturas" titulo="Facturas de compra (enlace con albaranes)" pasos={[
          'En BC busca "Líneas factura compra registradas" (o "Hist. líneas factura compra").',
          'Comprueba que se ven las columnas Nº documento y Nº albarán (⚙ Personalizar si falta).',
          'Filtra por fecha, Compartir → Abrir en Excel y súbelo aquí.',
        ]} />
      </SimpleGrid>
      <Text size="sm" c="dimmed" mt="lg">
        Cada compra de BC es un lote con su precio real. Los consumos de BM gastan lotes por orden de entrada (FIFO) y el inventario
        de fin de mes de BC reajusta lo que queda. Los albaranes aún sin facturar se valoran provisionalmente con el último precio facturado.
      </Text>
    </>
  );
}
