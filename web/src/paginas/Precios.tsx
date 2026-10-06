import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Badge, Tabs, Text } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { api, avisoError } from '../api';
import { Cabecera } from '../comun';
import { cantidad, euros, fecha } from '../formato';
import { Tabla } from '../Tabla';

type Var = { producto: string; nombre: string; proveedor: string; fecha: string; precio: number; referencia: number; variacion: number; consumo_30d: number; impacto_mes: number };
type Dud = { producto: string; nombre: string; unidad: string | null; documento: string; fecha: string; proveedor: string; cantidad: number; importe: number; precio: number; precio_habitual: number };

export function Precios() {
  const [d, setD] = useState<{ variaciones: Var[]; dudosos: Dud[] } | null>(null);
  const nav = useNavigate();
  useEffect(() => { api<typeof d>('/analisis/precios').then(setD).catch(avisoError); }, []);
  const ir = (p: { producto: string }) => nav(`/productos?codigo=${p.producto}`);

  return (
    <>
      <Cabecera titulo="Precios de compra" subtitulo="Cambios de precio de proveedor y precios sospechosos en Business Central" />
      <Tabs defaultValue="variaciones">
        <Tabs.List mb="md">
          <Tabs.Tab value="variaciones">Variaciones ({d?.variaciones.length ?? '…'})</Tabs.Tab>
          <Tabs.Tab value="dudosos" color="orange">Precios a revisar en BC ({d?.dudosos.length ?? '…'})</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="variaciones">
          <Tabla datos={d?.variaciones ?? null} clave={(v) => v.producto} buscar exportar="variacion_precios" alPulsar={ir} anchoMin={900}
            vacio="Sin cambios de precio en los últimos 90 días" columnas={[
              { clave: 'nombre', titulo: 'Producto', render: (v) => <><Text size="sm" fw={500}>{v.nombre}</Text><Text size="xs" c="dimmed">{v.proveedor}</Text></> },
              { clave: 'fecha', titulo: 'Última compra', render: (v) => fecha(v.fecha) },
              { clave: 'referencia', titulo: 'Antes', num: true, render: (v) => euros(v.referencia) },
              { clave: 'precio', titulo: 'Ahora', num: true, render: (v) => <Text size="sm" fw={600}>{euros(v.precio)}</Text> },
              { clave: 'variacion', titulo: 'Cambio', num: true, render: (v) => <Badge color={v.variacion > 0 ? 'red' : 'teal'} variant="light">{v.variacion > 0 ? '+' : ''}{v.variacion} %</Badge> },
              { clave: 'consumo_30d', titulo: 'Consumo 30 d', num: true, render: (v) => cantidad(v.consumo_30d) },
              { clave: 'impacto_mes', titulo: 'Impacto / mes', num: true, render: (v) => <Text size="sm" fw={600} c={v.impacto_mes > 0 ? 'red' : v.impacto_mes < 0 ? 'teal' : undefined}>{euros(v.impacto_mes)}</Text> },
            ]} />
        </Tabs.Panel>
        <Tabs.Panel value="dudosos">
          <Alert color="orange" icon={<IconAlertTriangle />} mb="md" title="Probables errores de unidad o importe en Business Central">
            BM no usa estos precios para calcular costes (usa el último precio fiable). Conviene corregirlos en BC y volver a importar los movimientos.
          </Alert>
          <Tabla datos={d?.dudosos ?? null} clave={(x) => `${x.documento}|${x.producto}|${x.fecha}`} buscar exportar="precios_dudosos_bc" alPulsar={ir} anchoMin={900}
            vacio="Ningún precio sospechoso" orden={{ clave: 'fecha', desc: true }} columnas={[
              { clave: 'fecha', titulo: 'Fecha', render: (x) => fecha(x.fecha) },
              { clave: 'documento', titulo: 'Documento', render: (x) => <><Text size="sm" fw={500}>{x.documento}</Text><Text size="xs" c="dimmed">{x.proveedor}</Text></> },
              { clave: 'nombre', titulo: 'Producto' },
              { clave: 'cantidad', titulo: 'Cantidad', num: true, render: (x) => `${cantidad(x.cantidad)} ${x.unidad ?? ''}` },
              { clave: 'importe', titulo: 'Importe', num: true, render: (x) => euros(x.importe) },
              { clave: 'precio', titulo: 'Precio ud.', num: true, render: (x) => <Text size="sm" fw={600} c="orange">{euros(x.precio)}</Text> },
              { clave: 'precio_habitual', titulo: 'Habitual', num: true, render: (x) => euros(x.precio_habitual) },
            ]} />
        </Tabs.Panel>
      </Tabs>
    </>
  );
}
