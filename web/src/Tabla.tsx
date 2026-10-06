import { useMemo, useState, type ReactNode } from 'react';
import { Button, Card, Group, Pagination, Skeleton, Stack, Table, Text, TextInput, UnstyledButton } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconChevronDown, IconChevronUp, IconDownload, IconSelector, IconSearch } from '@tabler/icons-react';
import { Vacio } from './comun';

export type Columna<T> = {
  clave: string;
  titulo: string;
  valor?: (fila: T) => string | number | null | undefined; // para ordenar, buscar y exportar
  render?: (fila: T) => ReactNode;
  num?: boolean;
  ancho?: number | string;
  ordenable?: boolean; // por defecto sí
  exportar?: boolean; // por defecto sí
};

type Props<T> = {
  datos: T[] | null;
  columnas: Columna<T>[];
  clave: (fila: T) => string | number;
  alPulsar?: (fila: T) => void;
  buscar?: boolean | string; // placeholder
  exportar?: string; // nombre de fichero
  porPagina?: number;
  vacio?: string;
  filtros?: ReactNode; // controles extra en la barra
  orden?: { clave: string; desc?: boolean };
  atenuar?: (fila: T) => boolean;
  pie?: ReactNode;
  anchoMin?: number;
};

const texto = (v: unknown) => (v == null ? '' : String(v));
const norm = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

function csv<T>(nombre: string, filas: T[], cols: Columna<T>[]) {
  const c = cols.filter((x) => x.exportar !== false);
  const celda = (v: unknown) => {
    const s = typeof v === 'number' ? v.toLocaleString('es-ES', { useGrouping: false, maximumFractionDigits: 4 }) : texto(v);
    return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lineas = [c.map((x) => celda(x.titulo)).join(';'), ...filas.map((f) => c.map((x) => celda(x.valor ? x.valor(f) : (f as any)[x.clave])).join(';'))];
  const blob = new Blob(['﻿' + lineas.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${nombre}_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Tabla estándar de BM: ordenar por columna, buscar, paginar y exportar a Excel (CSV). */
export function Tabla<T>({ datos, columnas, clave, alPulsar, buscar, exportar, porPagina = 25, vacio = 'Sin datos',
  filtros, orden: ordenInicial, atenuar, pie, anchoMin = 640 }: Props<T>) {
  const [q, setQ] = useState('');
  const [qd] = useDebouncedValue(q, 150);
  const [orden, setOrden] = useState(ordenInicial);
  const [pagina, setPagina] = useState(1);

  const val = (c: Columna<T>, f: T) => (c.valor ? c.valor(f) : (f as any)[c.clave]);
  const filtradas = useMemo(() => {
    let xs = datos ?? [];
    if (qd) {
      const n = norm(qd);
      xs = xs.filter((f) => columnas.some((c) => norm(texto(val(c, f))).includes(n)));
    }
    if (orden) {
      const c = columnas.find((x) => x.clave === orden.clave);
      if (c) {
        xs = [...xs].sort((a, b) => {
          const va = val(c, a), vb = val(c, b);
          const r = va == null ? 1 : vb == null ? -1 : typeof va === 'number' && typeof vb === 'number' ? va - vb : texto(va).localeCompare(texto(vb), 'es');
          return orden.desc ? -r : r;
        });
      }
    }
    return xs;
  }, [datos, qd, orden, columnas]);
  const paginas = Math.max(1, Math.ceil(filtradas.length / porPagina));
  const visibles = filtradas.slice((Math.min(pagina, paginas) - 1) * porPagina, Math.min(pagina, paginas) * porPagina);

  const cabecera = (c: Columna<T>) => {
    if (c.ordenable === false) return c.titulo;
    const activa = orden?.clave === c.clave;
    const Icono = activa ? (orden?.desc ? IconChevronDown : IconChevronUp) : IconSelector;
    return (
      <UnstyledButton onClick={() => { setOrden({ clave: c.clave, desc: activa ? !orden?.desc : !!c.num }); setPagina(1); }}
        style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontWeight: 600, fontSize: 'inherit' }}>
        {c.titulo}<Icono size={14} opacity={activa ? 1 : 0.35} />
      </UnstyledButton>
    );
  };

  return (
    <Card p={0}>
      {(buscar || exportar || filtros) && (
        <Group p="sm" gap="sm" justify="space-between" style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
          <Group gap="sm">
            {buscar && <TextInput leftSection={<IconSearch size={16} />} placeholder={typeof buscar === 'string' ? buscar : 'Buscar'}
              value={q} onChange={(e) => { setQ(e.currentTarget.value); setPagina(1); }} w={240} aria-label="Buscar" />}
            {filtros}
          </Group>
          <Group gap="sm">
            {datos && <Text size="sm" c="dimmed">{filtradas.length.toLocaleString('es-ES')} {filtradas.length === 1 ? 'fila' : 'filas'}</Text>}
            {exportar && <Button variant="default" size="xs" leftSection={<IconDownload size={14} />} disabled={!filtradas.length}
              onClick={() => csv(exportar, filtradas, columnas)}>Exportar</Button>}
          </Group>
        </Group>
      )}
      {!datos ? (
        <Stack p="md" gap="xs">{[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} h={28} />)}</Stack>
      ) : !filtradas.length ? <Vacio texto={qd ? 'Ningún resultado con esa búsqueda' : vacio} /> : (
        <Table.ScrollContainer minWidth={anchoMin}>
          <Table className={alPulsar ? 'tabla-click' : undefined} stickyHeader>
            <Table.Thead>
              <Table.Tr>{columnas.map((c) => <Table.Th key={c.clave} w={c.ancho} className={c.num ? 'num' : undefined}>{cabecera(c)}</Table.Th>)}</Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {visibles.map((f) => (
                <Table.Tr key={clave(f)} onClick={alPulsar ? () => alPulsar(f) : undefined} opacity={atenuar?.(f) ? 0.45 : 1}>
                  {columnas.map((c) => <Table.Td key={c.clave} className={c.num ? 'num' : undefined}>{c.render ? c.render(f) : texto(val(c, f))}</Table.Td>)}
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {(paginas > 1 || pie) && (
        <Group p="sm" justify="space-between" style={{ borderTop: '1px solid var(--mantine-color-default-border)' }}>
          <div>{pie}</div>
          {paginas > 1 && <Pagination size="sm" total={paginas} value={Math.min(pagina, paginas)} onChange={setPagina} />}
        </Group>
      )}
    </Card>
  );
}
