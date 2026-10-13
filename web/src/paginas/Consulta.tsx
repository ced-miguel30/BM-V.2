import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Badge, Button, Card, Group, Select, Stack, Text } from '@mantine/core';
import { api, avisoError, avisoOk } from '../api';
import { Cabecera, Vacio } from '../comun';
import { nombreUbicacion, useUbicaciones } from '../centros';
import { cantidad, euros, fecha } from '../formato';
import { BotonEscanear, type Producto } from '../EscanearProducto';

type Ficha = Producto & {
  sitios: { ubicacion: string; zona: string | null; stock: number | null; ultimo_recuento: string | null; valor: number | null }[];
  caducidades: { id: number; ubicacion: string | null; cantidad: number; caduca: string; dias: number }[];
  precio: number | null; ultima_compra: { fecha: string; proveedor: string } | null; codigos: string[];
};

// Escanear cualquier producto y ver dónde está, en qué zona, cuándo se contó y si caduca pronto.
export function Consulta() {
  const ubicaciones = useUbicaciones();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const producto = params.get('producto');
  const [productos, setProductos] = useState<Producto[]>([]);
  const [f, setF] = useState<Ficha | null>(null);
  const [rol, setRol] = useState('');
  useEffect(() => {
    api<{ productos: Producto[] }>('/catalogo').then((c) => setProductos(c.productos)).catch(avisoError);
    api<{ rol: string }>('/me').then((u) => setRol(u.rol)).catch(() => null);
  }, []);
  const quedaPoco = async () => {  // atajo: tras escanear, avisar al jefe sin rellenar nada
    try {
      await api('/solicitudes', { body: { para: 'jefe', tipo: 'queda_poco', lineas: [{ producto }] } });
      avisoOk('El jefe de restaurante lo verá en sus avisos', `Aviso enviado: queda poco ${f?.nombre ?? ''}`);
    } catch (e) { avisoError(e); }
  };
  useEffect(() => { setF(null); if (producto) api<Ficha>(`/consulta/${encodeURIComponent(producto)}`).then(setF).catch(avisoError); }, [producto]);
  const elegir = (p: string | null) => p && setParams({ producto: p });

  return (
    <>
      <Cabecera titulo="Consultar producto" subtitulo="Escanea o busca un producto: dónde está, cuándo se contó y si caduca pronto" />
      <Group align="flex-end" mb="md" wrap="wrap">
        <BotonEscanear productos={productos} texto="Escanear un producto" elegido={elegir} />
        <Select placeholder="…o búscalo por nombre" searchable limit={50} value={producto} onChange={elegir} style={{ flex: 1, minWidth: 220 }}
          data={productos.map((p) => ({ value: p.codigo, label: `${p.nombre} (${p.unidad ?? 'ud'})` }))} />
      </Group>
      {!producto ? <Card><Vacio texto="Escanea el código de barras de un envase" /></Card> : !f ? <Text c="dimmed">Buscando…</Text> : (
        <Stack>
          <Card>
            <Text fw={700} fz="lg">{f.nombre}</Text>
            <Text size="sm" c="dimmed">{f.codigo} · {f.unidad ?? 'ud'}{f.codigos.length ? ` · códigos de barras: ${f.codigos.join(', ')}` : ''}</Text>
            {rol === 'cocina' && <Button mt="sm" variant="light" color="orange" onClick={quedaPoco}>Avisar al jefe: queda poco</Button>}
            {f.precio !== null && (
              <Text size="sm" mt={4}>Precio: <b>{euros(f.precio)}</b> / {f.unidad ?? 'ud'}
                {f.ultima_compra && <> · última compra {fecha(f.ultima_compra.fecha)} a {f.ultima_compra.proveedor}</>}</Text>
            )}
          </Card>
          <Card>
            <Text fw={600} mb="xs">Dónde está</Text>
            {!f.sitios.length ? <Text size="sm" c="dimmed">BM no tiene existencias de este producto.</Text> : (
              <Stack gap="xs">
                {f.sitios.map((s) => (
                  <Group key={s.ubicacion} justify="space-between" wrap="nowrap">
                    <div>
                      <Text fw={500}>{nombreUbicacion(ubicaciones, s.ubicacion)}{s.zona ? ` · ${s.zona}` : ''}</Text>
                      <Text size="xs" c="dimmed">Contado por última vez: {s.ultimo_recuento ? fecha(s.ultimo_recuento) : 'nunca'}</Text>
                    </div>
                    <Group gap="xs" wrap="nowrap">
                      {s.stock !== null && <Text fw={600}>{cantidad(s.stock)} {f.unidad}{s.valor !== null ? ` · ${euros(s.valor)}` : ''}</Text>}
                      <Button size="compact-sm" variant="light" onClick={() => nav(`/recuento?ubicacion=${s.ubicacion}`)}>Contar</Button>
                    </Group>
                  </Group>
                ))}
              </Stack>
            )}
          </Card>
          <Card>
            <Group justify="space-between" mb="xs">
              <Text fw={600}>Caducidades</Text>
              <Button size="compact-sm" variant="light" onClick={() => nav('/caducidades')}>Apuntar una</Button>
            </Group>
            {!f.caducidades.length ? <Text size="sm" c="dimmed">Ninguna pendiente.</Text> : f.caducidades.map((c) => (
              <Group key={c.id} justify="space-between">
                <Text size="sm">{cantidad(c.cantidad)} {f.unidad} · {nombreUbicacion(ubicaciones, c.ubicacion)}</Text>
                <Badge color={c.dias <= 0 ? 'red' : c.dias <= 2 ? 'orange' : 'gray'} variant="light">
                  {c.dias < 0 ? `Caducado hace ${-c.dias} d` : c.dias === 0 ? 'Caduca hoy' : `${fecha(c.caduca)} (en ${c.dias} d)`}
                </Badge>
              </Group>
            ))}
          </Card>
        </Stack>
      )}
    </>
  );
}
