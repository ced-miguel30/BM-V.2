import { useEffect, useState } from 'react';
import { Navigate, NavLink as RouterLink, Route, Routes, useLocation } from 'react-router-dom';
import {
  ActionIcon, AppShell, Avatar, Box, Burger, Button, Center, Group, Loader, Menu, Modal, NavLink, Paper,
  PasswordInput, ScrollArea, Stack, Text, TextInput, Title, Tooltip, useMantineColorScheme,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconArrowsExchange, IconBook2, IconBuildingWarehouse, IconCalendarExclamation, IconChartBar, IconClipboardCheck,
  IconCloudUpload, IconFileSpreadsheet, IconListDetails, IconLogout, IconMoon, IconPackages, IconPencilPlus,
  IconReceipt2, IconSun, IconChartDots, IconScale, IconTrendingUp, IconSettings, IconKey, IconTruckDelivery, IconShoppingCart, IconStackPush, IconBread,
} from '@tabler/icons-react';
import { api, avisoError, avisoOk } from './api';
import { Logo } from './comun';
import { Panel } from './paginas/Panel';
import { Registrar } from './paginas/Registrar';
import { Consumos } from './paginas/Consumos';
import { Tpv } from './paginas/Tpv';
import { Recetas } from './paginas/Recetas';
import { Productos } from './paginas/Productos';
import { ImportarBC } from './paginas/ImportarBC';
import { Excel } from './paginas/Excel';
import { Stock } from './paginas/Stock';
import { Recuento } from './paginas/Recuento';
import { Traslados } from './paginas/Traslados';
import { Caducidades } from './paginas/Caducidades';
import { Rentabilidad } from './paginas/Rentabilidad';
import { Control } from './paginas/Control';
import { Precios } from './paginas/Precios';
import { Configuracion } from './paginas/Configuracion';
import { Compras } from './paginas/Compras';
import { Reponer } from './paginas/Reponer';
import { Pedidos } from './paginas/Pedidos';
import { Buffet } from './paginas/Buffet';

export type Usuario = { id: string; nombre: string; rol: string; login: string };
const GESTION = ['direccion', 'administracion'];
const TODOS = [...GESTION, 'recepcion', 'restaurante'];

const MENU = [
  { seccion: 'Operación', items: [
    { to: '/registrar', label: 'Registrar consumo', icon: IconPencilPlus, roles: TODOS, el: <Registrar /> },
    { to: '/buffet', label: 'Buffet del día', icon: IconBread, roles: TODOS, el: <Buffet /> },
    { to: '/excel', label: 'Importar Excel', icon: IconFileSpreadsheet, roles: TODOS, el: <Excel /> },
    { to: '/recuento', label: 'Recuento', icon: IconClipboardCheck, roles: TODOS, el: <Recuento /> },
    { to: '/caducidades', label: 'Caducidades', icon: IconCalendarExclamation, roles: TODOS, el: <Caducidades /> },
    { to: '/reponer', label: 'Reponer restaurante', icon: IconStackPush, roles: TODOS, el: <Reponer /> },
    { to: '/traslados', label: 'Traslados', icon: IconArrowsExchange, roles: TODOS, el: <Traslados /> },
  ] },
  { seccion: 'Control', items: [
    { to: '/', label: 'Panel', icon: IconChartBar, roles: GESTION, el: <Panel /> },
    { to: '/consumos', label: 'Consumos', icon: IconListDetails, roles: GESTION, el: <Consumos /> },
    { to: '/stock', label: 'Stock', icon: IconPackages, roles: GESTION, el: <Stock /> },
    { to: '/tpv', label: 'Ventas TPV', icon: IconReceipt2, roles: GESTION, el: <Tpv /> },
    { to: '/pedidos', label: 'Pedidos', icon: IconShoppingCart, roles: GESTION, el: <Pedidos /> },
    { to: '/compras', label: 'Compras y proveedores', icon: IconTruckDelivery, roles: GESTION, el: <Compras /> },
  ] },
  { seccion: 'Análisis', items: [
    { to: '/rentabilidad', label: 'Rentabilidad por plato', icon: IconChartDots, roles: GESTION, el: <Rentabilidad /> },
    { to: '/control', label: 'Control de stock', icon: IconScale, roles: GESTION, el: <Control /> },
    { to: '/precios', label: 'Precios de compra', icon: IconTrendingUp, roles: GESTION, el: <Precios /> },
  ] },
  { seccion: 'Catálogo', items: [
    { to: '/recetas', label: 'Recetas', icon: IconBook2, roles: GESTION, el: <Recetas /> },
    { to: '/productos', label: 'Productos', icon: IconBuildingWarehouse, roles: GESTION, el: <Productos /> },
  ] },
  { seccion: 'Sistema', items: [
    { to: '/bc', label: 'Importar de BC', icon: IconCloudUpload, roles: GESTION, el: <ImportarBC /> },
    { to: '/configuracion', label: 'Configuración', icon: IconSettings, roles: GESTION, el: <Configuracion /> },
  ] },
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
    <Center mih="100vh" p="md" style={{ background: 'linear-gradient(160deg, var(--mantine-color-marina-9) 0%, #0b1730 100%)' }}>
      <Paper w={400} maw="100%" p={36} shadow="xl" radius="lg">
        <form onSubmit={entrar}>
          <Stack gap="lg">
            <Group gap="sm">
              <Logo size={46} />
              <div>
                <Text c="dimmed" size="xs" fw={700} tt="uppercase" lts={1.2}>Royal Marina Suites</Text>
                <Title order={3}>Control F&amp;B e inventario</Title>
              </div>
            </Group>
            <TextInput label="Usuario" value={login} onChange={(e) => setLogin(e.currentTarget.value)} autoFocus required autoComplete="username" size="md" />
            <PasswordInput label="Contraseña" value={password} onChange={(e) => setPassword(e.currentTarget.value)} required autoComplete="current-password" size="md" />
            <Button type="submit" loading={cargando} size="md" fullWidth>Entrar</Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}

function CambiarClave({ abierto, cerrar }: { abierto: boolean; cerrar: () => void }) {
  const [actual, setActual] = useState('');
  const [nueva, setNueva] = useState('');
  const [repite, setRepite] = useState('');
  const guardar = async () => {
    try { await api('/me/password', { body: { actual, nueva } }); avisoOk('Contraseña cambiada'); setActual(''); setNueva(''); setRepite(''); cerrar(); }
    catch (e) { avisoError(e); }
  };
  return (
    <Modal opened={abierto} onClose={cerrar} title="Cambiar contraseña" centered>
      <Stack>
        <PasswordInput label="Contraseña actual" value={actual} onChange={(e) => setActual(e.currentTarget.value)} autoComplete="current-password" />
        <PasswordInput label="Nueva contraseña" description="Mínimo 8 caracteres" value={nueva} onChange={(e) => setNueva(e.currentTarget.value)} autoComplete="new-password" />
        <PasswordInput label="Repite la nueva" value={repite} onChange={(e) => setRepite(e.currentTarget.value)} autoComplete="new-password"
          error={repite && repite !== nueva ? 'No coincide' : undefined} />
        <Group justify="flex-end"><Button variant="default" onClick={cerrar}>Cancelar</Button>
          <Button onClick={guardar} disabled={!actual || nueva.length < 8 || nueva !== repite}>Guardar</Button></Group>
      </Stack>
    </Modal>
  );
}

export function App() {
  const [usuario, setUsuario] = useState<Usuario | null | undefined>(undefined);
  const [abierto, { toggle, close }] = useDisclosure();
  const [clave, setClave] = useState(false);
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

  const menu = MENU.map((s) => ({ ...s, items: s.items.filter((i) => i.roles.includes(usuario.rol)) })).filter((s) => s.items.length);
  const rutas = menu.flatMap((s) => s.items);
  const inicio = rutas.some((r) => r.to === '/') ? '/' : '/registrar';
  const salir = async () => { await api('/logout', { method: 'POST' }).catch(() => null); setUsuario(null); };
  const activo = (to: string) => (to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(to));

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 250, breakpoint: 'sm', collapsed: { mobile: !abierto } }} padding="lg">
      <AppShell.Header bg="var(--mantine-color-marina-9)" c="white" withBorder={false}>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={abierto} onClick={toggle} hiddenFrom="sm" size="sm" color="white" aria-label="Menú" />
            <Logo size={34} claro />
            <Box visibleFrom="xs">
              <Text fw={700} lh={1.15}>Royal Marina</Text>
              <Text size="xs" c="marina.2" lh={1.15}>Control F&amp;B e inventario</Text>
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
                  <Avatar size={32} radius="xl" color="cyan" variant="filled">{usuario.nombre.slice(0, 1)}</Avatar>
                  <Box visibleFrom="xs">
                    <Text size="sm" fw={600} lh={1.1}>{usuario.nombre}</Text>
                    <Text size="xs" c="marina.2" lh={1.1}>{ROL[usuario.rol] ?? usuario.rol}</Text>
                  </Box>
                </Group>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item leftSection={<IconKey size={16} />} onClick={() => setClave(true)}>Cambiar contraseña</Menu.Item>
                <Menu.Item leftSection={<IconLogout size={16} />} onClick={salir}>Cerrar sesión</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar>
        <ScrollArea p="sm">
          <Stack gap="md">
            {menu.map((s) => (
              <div key={s.seccion}>
                <Text size="xs" fw={700} c="dimmed" tt="uppercase" lts={0.8} px="sm" mb={4}>{s.seccion}</Text>
                <Stack gap={2}>
                  {s.items.map((m) => (
                    <NavLink key={m.to} component={RouterLink} to={m.to} end={m.to === '/'} label={m.label}
                      leftSection={<m.icon size={19} stroke={1.6} />} active={activo(m.to)} fw={500}
                      style={{ borderRadius: 'var(--mantine-radius-md)' }} />
                  ))}
                </Stack>
              </div>
            ))}
          </Stack>
        </ScrollArea>
      </AppShell.Navbar>

      <CambiarClave abierto={clave} cerrar={() => setClave(false)} />
      <AppShell.Main>
        <Box maw={1440} mx="auto">
          <Routes>
            {rutas.map((r) => <Route key={r.to} path={r.to} element={r.el} />)}
            <Route path="*" element={<Navigate to={inicio} replace />} />
          </Routes>
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
