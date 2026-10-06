import { Badge, Group, Stack, Text, ThemeIcon, Title, Tooltip } from '@mantine/core';
import { IconInbox } from '@tabler/icons-react';
import type { ReactNode } from 'react';
import { ESTADOS, ESTADO_POR_NIVEL, servicio } from './formato';

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
  const s = servicio(valor);
  return s ? <Badge variant="light" color={s.color}>{s.label}</Badge> : <Text c="dimmed" size="sm">—</Text>;
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