import { useEffect, useRef, useState } from 'react';
import { Button, Group, Modal, Select, Stack, Text } from '@mantine/core';
import { IconScan } from '@tabler/icons-react';
import { api, avisoError } from './api';
import { Camara, hayCamara } from './Escaner';

export type Producto = { codigo: string; nombre: string; unidad: string | null };

// Códigos de barras aprendidos (código del envase -> producto). Se cargan una vez y se comparten entre pantallas.
let codigos: Promise<Record<string, string>> | null = null;
const cargarCodigos = () => (codigos ??= api<Record<string, string>>('/codigos').catch(() => { codigos = null; return {} as Record<string, string>; }));

/** Botón «Escanear» (cámara del móvil) + lector USB/Bluetooth en toda la pantalla mientras esté montado.
 *  Devuelve el código de producto de BM; un código de barras nuevo se asocia una vez y queda aprendido. */
export function BotonEscanear({ productos, elegido, texto = 'Escanear' }: { productos: Producto[]; elegido: (producto: string) => void; texto?: string }) {
  const [abierto, setAbierto] = useState(false);
  const [nuevo, setNuevo] = useState<string | null>(null);
  const actual = useRef(elegido);
  actual.current = elegido;
  const ocupado = useRef(false);  // la cámara sigue leyendo mientras se resuelve el código: una sola vez

  const leer = async (codigo: string) => {
    if (ocupado.current) return;
    ocupado.current = true;
    const p = (await cargarCodigos())[codigo];
    if (p) { setAbierto(false); actual.current(p); } else { setAbierto(true); setNuevo(codigo); }
    setTimeout(() => { ocupado.current = false; }, 1500);
  };
  const asociar = async (producto: string | null) => {
    if (!nuevo || !producto) return;
    try {
      await api('/codigos', { method: 'PUT', body: { codigo: nuevo, producto } });
      (await cargarCodigos())[nuevo] = producto;
      setNuevo(null); setAbierto(false); actual.current(producto);
    } catch (e) { avisoError(e); }
  };

  // Lector USB/Bluetooth: teclea los dígitos muy rápido y termina en Intro (una persona no teclea así).
  useEffect(() => {
    cargarCodigos();
    let buf = '', t = 0;
    const tecla = (e: KeyboardEvent) => {
      const ahora = performance.now();
      if (ahora - t > 60) buf = '';
      t = ahora;
      if (e.key === 'Enter' && buf.length >= 8) { e.preventDefault(); const c = buf; buf = ''; leer(c); }
      else if (/^\d$/.test(e.key)) buf += e.key;
    };
    window.addEventListener('keydown', tecla, true);
    return () => window.removeEventListener('keydown', tecla, true);
  }, []);

  const cerrar = () => { setAbierto(false); setNuevo(null); };
  return (
    <>
      {hayCamara() && <Button variant="light" leftSection={<IconScan size={18} />} onClick={() => setAbierto(true)}>{texto}</Button>}
      <Modal opened={abierto} onClose={cerrar} title={nuevo ? 'Código nuevo' : 'Escanear producto'} centered>
        {nuevo ? (
          <Stack>
            <Text size="sm">El código <b>{nuevo}</b> aún no está asociado. ¿Qué producto es? BM lo recordará la próxima vez.</Text>
            <Select searchable limit={50} autoFocus placeholder="Busca el producto" onChange={asociar} comboboxProps={{ withinPortal: false }}
              data={productos.map((c) => ({ value: c.codigo, label: `${c.nombre} (${c.unidad ?? 'ud'})` }))} />
            <Group justify="flex-end"><Button variant="default" onClick={cerrar}>Cancelar</Button></Group>
          </Stack>
        ) : abierto && <Camara activa leido={leer} />}
      </Modal>
    </>
  );
}
