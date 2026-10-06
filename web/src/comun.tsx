import { Badge, Group, Stack, Text, ThemeIcon, Title, Tooltip } from '@mantine/core';
import { IconInbox } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { ESTADOS, ESTADO_POR_NIVEL } from './formato';
import { useCentros } from './centros';

export function Cabecera({ titulo, subtitulo, children }: { titulo: string; subtitulo?: ReactNode; children?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" mb="lg" gap="sm">
      <div>
        <Title order={2}>{titulo}</Title>
        {subtitulo && <Text c="dimmed" size="sm" mt={2}>{subtitulo}</Text>}
      </div>
      {children && <Group gap="sm">{children}</Group>}
    </Group>
  );
}

export function Vacio({ texto, children }: { texto: string; children?: ReactNode }) {
  return (
    <Stack align="center" gap="xs" py={48}>
      <ThemeIcon size={48} radius="xl" variant="light" color="gray"><IconInbox size={26} /></ThemeIcon>
      <Text c="dimmed">{texto}</Text>
      {children}
    </Stack>
  );
}

export function BadgeServicio({ valor }: { valor: string | null }) {
  const c = useCentros().find((x) => x.codigo === valor);
  if (!valor) return <Text c="dimmed" size="sm">—</Text>;
  return <Badge variant="light" color={c?.color ?? 'gray'}>{c?.nombre ?? valor}</Badge>;
}

/** Monograma Royal Marina: RM sobre una ola. */
export function Logo({ size = 34, claro = false }: { size?: number; claro?: boolean }) {
  const fondo = claro ? '#ffffff' : 'var(--mantine-color-marina-9)';
  const tinta = claro ? 'var(--mantine-color-marina-9)' : '#ffffff';
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" role="img" aria-label="Royal Marina">
      <rect width="40" height="40" rx="10" fill={fondo} />
      <text x="20" y="22" textAnchor="middle" fontFamily="Inter Variable, Inter, sans-serif" fontWeight="800" fontSize="15" fill={tinta} letterSpacing="-0.5">RM</text>
      <path d="M8 29c3-2.6 5.3-2.6 8 0s5 2.6 8 0 5.3-2.6 8 0" fill="none" stroke="var(--mantine-color-cyan-4)" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

export function BadgeEstado({ estado, nivel }: { estado?: string | null; nivel?: number | null }) {
  const e = ESTADOS[estado ?? ESTADO_POR_NIVEL[nivel ?? 0]];
  if (!e) return null;
  return (
    <Tooltip label={e.ayuda} withArrow>
      <Badge variant="dot" color={e.color}>{e.label}</Badge>
    </Tooltip>
  );
}

export const ORIGEN: Record<string, string> = { manual: 'Manual', excel: 'Excel', tpv: 'TPV', bm2: 'BM v2' };