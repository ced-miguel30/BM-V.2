import { useEffect, useState } from 'react';
import { api } from './api';

export type Centro = { codigo: string; nombre: string; tipo: 'restauracion' | 'departamento'; ubicacion: string | null; color: string; orden: number; activo: number };
export type Ubicacion = { codigo: string; nombre: string; activo: number; movimientos: number };

let centros: Centro[] | null = null;
let ubicaciones: Ubicacion[] | null = null;
let pc: Promise<Centro[]> | null = null;
let pu: Promise<Ubicacion[]> | null = null;

/** Centros de consumo (servicios y departamentos), cargados una vez por sesión. */
export function useCentros(): Centro[] {
  const [c, setC] = useState<Centro[]>(centros ?? []);
  useEffect(() => {
    if (centros) return;
    (pc ??= api<Centro[]>('/centros')).then((x) => { centros = x; setC(x); }).catch(() => { pc = null; });
  }, []);
  return c;
}

export function useUbicaciones(): Ubicacion[] {
  const [u, setU] = useState<Ubicacion[]>(ubicaciones ?? []);
  useEffect(() => {
    if (ubicaciones) return;
    (pu ??= api<Ubicacion[]>('/ubicaciones')).then((x) => { ubicaciones = x; setU(x); }).catch(() => { pu = null; });
  }, []);
  return u;
}

export const nombreUbicacion = (us: Ubicacion[], codigo: string | null | undefined) =>
  us.find((u) => u.codigo === codigo)?.nombre ?? codigo ?? '—';

/** Para que la configuración refresque tras editar. */
export function olvidarCatalogos() { centros = ubicaciones = null; pc = pu = null; }
