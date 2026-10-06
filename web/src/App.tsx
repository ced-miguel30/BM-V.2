import { useEffect, useState } from 'react';
import { Navigate, NavLink as RouterLink, Route, Routes, useLocation } from 'react-router-dom';
import {
  ActionIcon, AppShell, Avatar, Box, Burger, Button, Center, Group, Loader, Menu, NavLink, Paper,
  PasswordInput, Stack, Text, TextInput, Title, Tooltip, useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconBook2, IconBuildingWarehouse, IconChartBar, IconCloudUpload, IconListDetails, IconLogout,
  IconMoon, IconPencilPlus, IconReceipt2, IconSun,
} from '@tabler/icons-react';
import { api, avisoError } from './api';
import { Panel } from './paginas/Panel';
import { Registrar } from './paginas/Registrar';
import { Consumos } from './paginas/Consumos';
import { Tpv } from './paginas/Tpv';
import { Recetas } from './paginas/Recetas';
import { Productos } from './paginas/Productos';
import { ImportarBC } from './paginas/ImportarBC';

export type Usuario = { id: string; nombre: string; rol: string; login: string };
const GESTION = ['direccion', 'administracion'];

const MENU = [
  { to: '/', label: 'Panel', icon: IconChartBar, roles: GESTION },
  { to: '/registrar', label: 'Registrar', icon: IconPencilPlus, roles: [...GESTION, 'recepcion', 'restaurante'] },
  { to: '/consumos', label: 'Consumos', icon: IconListDetails, roles: GESTION },
  { to: '/tpv', label: 'Ventas TPV', icon: IconReceipt2, roles: GESTION },
  { to: '/recetas', label: 'Recetas', icon: IconBook2, roles: GESTION },
  { to: '/productos', label: 'Productos', icon: IconBuildingWarehouse, roles: GESTION },
  { to: '/bc', label: 'Importar de BC', icon: IconCloudUpload, roles: GESTION },
];

const ROL: Record<string, string> = {
  direccion: 'Dirección', administracion: 'Administración', recepcion: 'Recepción', restaurante: 'Restaurante',
};

function Login({ onLogin }: { onLogin: (u: Usuario) => void }) {
  const [login, setLogin] = useState('');
  const [password, setPassword] = useState('');
  const [cargando, setCargando] = useState(false);
  const entrar = async (e: React.FormEvent) => {
    e.preventDefault();
    setCargando(true);
    try { onLogin(await api<Usuario>('/login', { body: { login, password } })); }
    catch (err) { avisoError(err); }
    finally { setCargando(false); }
  };
  return (
    <Center mih="100vh" p="md" bg="var(--mantine-color-marina-9)">
      <Paper w={380} maw="100%" p="xl" shadow="xl">
        <form onSubmit={entrar}>
          <Stack>
            <div>
              <Text c="dimmed" size="sm" fw={600} tt="uppercase" lts={1}>Royal Marina Suites</Text>
              <Title order={2}>Control F&amp;B</Title>
            </div>
            <TextInput label="Usuario" value={login} onChange={(e) => setLogin(e.currentTarget.value)} autoFocus required autoComplete="username" />
            <PasswordInput label="Contraseña" value={password} onChange={(e) => setPassword(e.currentTarget.value)} required autoComplete="current-password" />
            <Button type="submit" loading={cargando} size="md">Entrar</Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}

export function App() {
  const [usuario, setUsuario] = useState<Usuario | null | undefined>(undefined);
  const [abierto, { toggle, close }] = useDisclosure();
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const loc = useLocation();

  useEffect(() => {
    api<Usuario>('/me').then(setUsuario).catch(() => setUsuario(null));
    const caducada = () => setUsuario(null);
    window.addEventListener('bm:401', caducada);
    return () => window.removeEventListener('bm:401', caducada);
  }, []);
  useEffect(close, [loc.pathname]);

  if (usuario === undefined) return <Center mih="100vh"><Loader /></Center>;
  if (!usuario) return <Login onLogin={setUsuario} />;

  const menu = MENU.filter((m) => m.roles.includes(usuario.rol));
  const gestion = GESTION.includes(usuario.rol);
  const salir = async () => { await api('/logout', { method: 'POST' }).catch(() => null); setUsuario(null); };

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 240, breakpoint: 'sm', collapsed: { mobile: !abierto } }} padding="lg">
      <AppShell.Header bg="var(--mantine-color-marina-9)" c="white" withBorder={false}>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={abierto} onClick={toggle} hiddenFrom="sm" size="sm" color="white" />
            <Box>
              <Text fw={700} lh={1.1}>Royal Marina</Text>
              <Text size="xs" c="marina.2" lh={1.1}>Control F&amp;B</Text>
            </Box>
          </Group>
          <Group gap="xs" wrap="nowrap">
            <Tooltip label={colorScheme === 'dark' ? 'Modo claro' : 'Modo oscuro'}>
              <ActionIcon variant="subtle" color="gray.0" onClick={toggleColorScheme} aria-label="Cambiar tema">
                {colorScheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
            </Tooltip>
            <Menu position="bottom-end" shadow="md">
              <Menu.Target>
                <Group gap={8} style={{ cursor: 'pointer' }} wrap="nowrap">
                  <Avatar size={32} radius="xl" color="marina.2" variant="filled">{usuario.nombre.slice(0, 1)}</Avatar>
                  <Box visibleFrom="xs">
                    <Text size="sm" fw={600} lh={1.1}>{usuario.nombre}</Text>
                    <Text size="xs" c="marina.2" lh={1.1}>{ROL[usuario.rol] ?? usuario.rol}</Text>
                  </Box>
                </Group>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconLogout size={16} />} onClick={salir}>Cerrar sesión</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        <Stack gap={4}>
          {menu.map((m) => (
            <NavLink key={m.to} component={RouterLink} to={m.to} end={m.to === '/'} label={m.label}
              leftSection={<m.icon size={20} stroke={1.6} />} active={m.to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(m.to)}
              style={{ borderRadius: 'var(--mantine-radius-md)' }} fw={500} />
          ))}
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main>
        <Box maw={1400} mx="auto">
          <Routes>
            {gestion && <Route path="/" element={<Panel />} />}
            <Route path="/registrar" element={<Registrar />} />
            {gestion && <>
              <Route path="/consumos" element={<Consumos />} />
              <Route path="/tpv" element={<Tpv />} />
              <Route path="/recetas" element={<Recetas />} />
              <Route path="/productos" element={<Productos />} />
              <Route path="/bc" element={<ImportarBC />} />
            </>}
            <Route path="*" element={<Navigate to={gestion ? '/' : '/registrar'} replace />} />
          </Routes>
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}