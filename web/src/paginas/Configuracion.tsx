import { useEffect, useState } from 'react';
import {
  Alert, Badge, Button, Card, Group, Modal, NumberInput, PasswordInput, SegmentedControl, Select, SimpleGrid, Stack, Switch, Tabs, Text, TextInput,
} from '@mantine/core';
import { IconDatabaseExport, IconDownload, IconPlus } from '@tabler/icons-react';
import { api, avisoError, avisoOk } from '../api';
import { BadgeServicio, Cabecera } from '../comun';
import { olvidarCatalogos } from '../centros';
import { fecha } from '../formato';
import { Tabla } from '../Tabla';

type Cfg = {
  ajustes: Record<string, string>;
  centros: { codigo: string; nombre: string; tipo: string; ubicacion: string | null; color: string; orden: number; activo: number }[];
  ubicaciones: { codigo: string; nombre: string; activo: number }[];
  almacenes_bc: { codigo: string; ubicacion: string; centro: string | null; movimientos: number }[];
  atajos: { etiqueta: string; grupo: string; producto: string | null; receta_id: string | null; cantidad: number; sustituye: string | null; activo: number; producto_nombre: string | null; unidad: string | null; receta_nombre: string | null }[];
  recetas_dia: { etiqueta: string; dia_semana: number; receta_id: string; receta_nombre: string }[];
  usuarios: { id: string; nombre: string; login: string | null; rol: string; activo: number }[];
  copias: { nombre: string; tamano: number; fecha: string }[];
};
const ROLES = [{ value: 'direccion', label: 'Dirección' }, { value: 'administracion', label: 'Administración' }, { value: 'recepcion', label: 'Recepción' }, { value: 'restaurante', label: 'Restaurante' }];
const COLORES = ['orange', 'teal', 'indigo', 'grape', 'cyan', 'blue', 'lime', 'gray', 'yellow', 'pink', 'red', 'green', 'violet'];
const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const GRUPOS: Record<string, string> = { extra: 'Extras de plato', leche: 'Leches', bebida: 'Bebidas', buffet: 'Buffet', omitir: 'Quitar' };

function General({ cfg, recargar }: { cfg: Cfg; recargar: () => void }) {
  const [a, setA] = useState({ igic_ventas: Number(cfg.ajustes.igic_ventas ?? 7), objetivo_food_cost: Number(cfg.ajustes.objetivo_food_cost ?? 30), traslados_en: cfg.ajustes.traslados_en ?? 'bc' });
  const guardar = async () => { try { await api('/config/ajustes', { method: 'PUT', body: a }); avisoOk('Ajustes guardados'); recargar(); } catch (e) { avisoError(e); } };
  return (
    <Card maw={620}>
      <Stack>
        <NumberInput label="IGIC incluido en las ventas del TPV" description="Se descuenta para calcular el food cost sobre venta neta" suffix=" %" min={0} max={30} decimalScale={2}
          value={a.igic_ventas} onChange={(x) => setA({ ...a, igic_ventas: Number(x) })} />
        <NumberInput label="Objetivo de food cost" suffix=" %" min={1} max={99} value={a.objetivo_food_cost} onChange={(x) => setA({ ...a, objetivo_food_cost: Number(x) })} />
        <div>
          <Text size="sm" fw={500}>Los traslados entre almacenes se registran en</Text>
          <SegmentedControl mt={4} value={a.traslados_en} onChange={(x) => setA({ ...a, traslados_en: x })}
            data={[{ value: 'bc', label: 'Business Central (se importan)' }, { value: 'bm', label: 'BM' }]} />
          <Text size="xs" c="dimmed" mt={4}>Nunca en los dos: si se pasa a BM, los traslados importados de BC dejan de contar.</Text>
        </div>
        <Group justify="flex-end"><Button onClick={guardar}>Guardar</Button></Group>
      </Stack>
    </Card>
  );
}

function Usuarios({ cfg, recargar }: { cfg: Cfg; recargar: () => void }) {
  const vacio = { login: '', nombre: '', rol: 'restaurante', activo: true, password: '', nuevo: true };
  const [ed, setEd] = useState<typeof vacio | null>(null);
  const guardar = async () => {
    if (!ed) return;
    try {
      await api('/config/usuarios', { body: { login: ed.login, nombre: ed.nombre, rol: ed.rol, activo: ed.activo, password: ed.password || null } });
      avisoOk(ed.nuevo ? 'Usuario creado' : 'Usuario actualizado', ed.nombre); setEd(null); recargar();
    } catch (e) { avisoError(e); }
  };
  return (
    <>
      <Group justify="flex-end" mb="sm"><Button leftSection={<IconPlus size={16} />} onClick={() => setEd(vacio)}>Nuevo usuario</Button></Group>
      <Tabla datos={cfg.usuarios} clave={(u) => u.id} atenuar={(u) => !u.activo} alPulsar={(u) => u.login && setEd({ login: u.login, nombre: u.nombre, rol: u.rol, activo: !!u.activo, password: '', nuevo: false })}
        columnas={[
          { clave: 'nombre', titulo: 'Nombre' },
          { clave: 'login', titulo: 'Usuario', render: (u) => u.login ?? <Text size="sm" c="dimmed">sin acceso</Text> },
          { clave: 'rol', titulo: 'Rol', valor: (u) => ROLES.find((r) => r.value === u.rol)?.label ?? u.rol },
          { clave: 'activo', titulo: 'Estado', render: (u) => <Badge color={u.activo ? 'teal' : 'gray'} variant="light">{u.activo ? 'Activo' : 'Desactivado'}</Badge> },
        ]} />
      <Modal opened={!!ed} onClose={() => setEd(null)} title={ed?.nuevo ? 'Nuevo usuario' : ed?.nombre} centered>
        {ed && (
          <Stack>
            <TextInput label="Usuario (para entrar)" value={ed.login} disabled={!ed.nuevo} onChange={(e) => setEd({ ...ed, login: e.currentTarget.value })} />
            <TextInput label="Nombre" value={ed.nombre} onChange={(e) => setEd({ ...ed, nombre: e.currentTarget.value })} />
            <Select label="Rol" data={ROLES} value={ed.rol} onChange={(x) => x && setEd({ ...ed, rol: x })} allowDeselect={false}
              description="Restaurante y Recepción registran pero no ven costes" />
            <PasswordInput label={ed.nuevo ? 'Contraseña' : 'Nueva contraseña (dejar vacío para no cambiar)'} value={ed.password}
              onChange={(e) => setEd({ ...ed, password: e.currentTarget.value })} description="Mínimo 8 caracteres" autoComplete="new-password" />
            <Switch label="Activo" checked={ed.activo} onChange={(e) => setEd({ ...ed, activo: e.currentTarget.checked })} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setEd(null)}>Cancelar</Button><Button onClick={guardar} disabled={!ed.login || !ed.nombre}>Guardar</Button></Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}

function Centros({ cfg, recargar }: { cfg: Cfg; recargar: () => void }) {
  type C = Cfg['centros'][number] & { nuevo?: boolean };
  const [ed, setEd] = useState<C | null>(null);
  const guardar = async () => {
    if (!ed) return;
    try {
      await api(`/config/centros/${encodeURIComponent(ed.codigo)}`, { method: 'PUT', body: { ...ed, activo: !!ed.activo } });
      olvidarCatalogos(); avisoOk('Centro guardado', ed.nombre); setEd(null); recargar();
    } catch (e) { avisoError(e); }
  };
  const ubs = cfg.ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }));
  return (
    <>
      <Group justify="space-between" mb="sm">
        <Text size="sm" c="dimmed">Servicios de restauración y departamentos del hotel. Cada consumo pertenece a uno solo.</Text>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setEd({ codigo: '', nombre: '', tipo: 'departamento', ubicacion: null, color: 'gray', orden: 50, activo: 1, nuevo: true })}>Nuevo centro</Button>
      </Group>
      <Tabla datos={cfg.centros} clave={(c) => c.codigo} atenuar={(c) => !c.activo} alPulsar={(c) => setEd({ ...c })} orden={{ clave: 'orden', desc: false }}
        columnas={[
          { clave: 'nombre', titulo: 'Centro', render: (c) => <BadgeServicio valor={c.codigo} /> },
          { clave: 'tipo', titulo: 'Tipo', valor: (c) => (c.tipo === 'restauracion' ? 'Restauración' : 'Departamento') },
          { clave: 'ubicacion', titulo: 'Almacén por defecto', valor: (c) => cfg.ubicaciones.find((u) => u.codigo === c.ubicacion)?.nombre ?? '—' },
          { clave: 'orden', titulo: 'Orden', num: true },
        ]} />
      <Modal opened={!!ed} onClose={() => setEd(null)} title={ed?.nuevo ? 'Nuevo centro' : ed?.nombre} centered>
        {ed && (
          <Stack>
            {ed.nuevo && <TextInput label="Código" description="Sin espacios, p. ej. spa" value={ed.codigo} onChange={(e) => setEd({ ...ed, codigo: e.currentTarget.value })} />}
            <TextInput label="Nombre" value={ed.nombre} onChange={(e) => setEd({ ...ed, nombre: e.currentTarget.value })} />
            <SegmentedControl value={ed.tipo} onChange={(x) => setEd({ ...ed, tipo: x })} data={[{ value: 'restauracion', label: 'Restauración' }, { value: 'departamento', label: 'Departamento' }]} />
            <Select label="Almacén del que sale el stock" data={ubs} value={ed.ubicacion} onChange={(x) => setEd({ ...ed, ubicacion: x })} searchable clearable />
            <Group grow>
              <Select label="Color" data={COLORES} value={ed.color} onChange={(x) => x && setEd({ ...ed, color: x })} allowDeselect={false} />
              <NumberInput label="Orden" value={ed.orden} onChange={(x) => setEd({ ...ed, orden: Number(x) })} />
            </Group>
            <Switch label="Activo" checked={!!ed.activo} onChange={(e) => setEd({ ...ed, activo: e.currentTarget.checked ? 1 : 0 })} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setEd(null)}>Cancelar</Button><Button onClick={guardar}>Guardar</Button></Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}

function Ubicaciones({ cfg, recargar }: { cfg: Cfg; recargar: () => void }) {
  const [ed, setEd] = useState<{ codigo: string; nombre: string; activo: number; nuevo?: boolean } | null>(null);
  const guardar = async () => {
    if (!ed) return;
    try { await api(`/config/ubicaciones/${encodeURIComponent(ed.codigo)}`, { method: 'PUT', body: { nombre: ed.nombre, activo: !!ed.activo } });
      olvidarCatalogos(); avisoOk('Ubicación guardada', ed.nombre); setEd(null); recargar(); } catch (e) { avisoError(e); }
  };
  const guardarAlmacen = async (codigo: string, ubicacion: string, centro: string | null) => {
    try { await api(`/config/almacenes/${encodeURIComponent(codigo)}`, { method: 'PUT', body: { ubicacion, centro } }); avisoOk(codigo, 'Almacén asignado'); recargar(); }
    catch (e) { avisoError(e); }
  };
  return (
    <>
      <Group justify="space-between" mb="sm">
        <Text size="sm" c="dimmed">Sitios físicos donde se guarda la mercancía y donde se hacen los recuentos.</Text>
        <Button leftSection={<IconPlus size={16} />} onClick={() => setEd({ codigo: '', nombre: '', activo: 1, nuevo: true })}>Nueva ubicación</Button>
      </Group>
      <Tabla datos={cfg.ubicaciones} clave={(u) => u.codigo} atenuar={(u) => !u.activo} alPulsar={(u) => setEd({ ...u })}
        columnas={[{ clave: 'nombre', titulo: 'Ubicación física' }, { clave: 'codigo', titulo: 'Código' },
          { clave: 'activo', titulo: 'Estado', render: (u) => <Badge color={u.activo ? 'teal' : 'gray'} variant="light">{u.activo ? 'Activa' : 'Oculta'}</Badge> }]} />
      <Text fw={600} mt="xl" mb={4}>Almacenes de Business Central</Text>
      <Text size="sm" c="dimmed" mb="sm">En BC son destinos contables. Indica dónde está físicamente su mercancía y a qué centro de consumo corresponde.</Text>
      <Tabla datos={cfg.almacenes_bc} clave={(a) => a.codigo} buscar porPagina={50} columnas={[
        { clave: 'codigo', titulo: 'Almacén BC' },
        { clave: 'movimientos', titulo: 'Movimientos', num: true },
        { clave: 'ubicacion', titulo: 'Está físicamente en', ordenable: false, render: (a) => (
          <Select size="xs" w={210} value={a.ubicacion} allowDeselect={false} data={cfg.ubicaciones.map((u) => ({ value: u.codigo, label: u.nombre }))}
            onChange={(x) => x && guardarAlmacen(a.codigo, x, a.centro)} aria-label={`Ubicación de ${a.codigo}`} />) },
        { clave: 'centro', titulo: 'Centro de consumo', ordenable: false, render: (a) => (
          <Select size="xs" w={190} value={a.centro} clearable placeholder="—" data={cfg.centros.map((c) => ({ value: c.codigo, label: c.nombre }))}
            onChange={(x) => guardarAlmacen(a.codigo, a.ubicacion, x)} aria-label={`Centro de ${a.codigo}`} />) },
      ]} />
      <Modal opened={!!ed} onClose={() => setEd(null)} title={ed?.nuevo ? 'Nueva ubicación' : ed?.codigo} centered>
        {ed && (
          <Stack>
            {ed.nuevo && <TextInput label="Código" value={ed.codigo} onChange={(e) => setEd({ ...ed, codigo: e.currentTarget.value.toUpperCase() })} />}
            <TextInput label="Nombre" value={ed.nombre} onChange={(e) => setEd({ ...ed, nombre: e.currentTarget.value })} />
            <Switch label="Activa (aparece en listas)" checked={!!ed.activo} onChange={(e) => setEd({ ...ed, activo: e.currentTarget.checked ? 1 : 0 })} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setEd(null)}>Cancelar</Button><Button onClick={guardar} disabled={!ed.codigo || !ed.nombre}>Guardar</Button></Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}

function Atajos({ cfg, recargar }: { cfg: Cfg; recargar: () => void }) {
  type A = Cfg['atajos'][number] & { etiqueta_anterior?: string | null };
  const [grupo, setGrupo] = useState('extra');
  const [ed, setEd] = useState<A | null>(null);
  const [cat, setCat] = useState<{ recetas: { id: string; nombre: string }[]; productos: { codigo: string; nombre: string; unidad: string | null }[] } | null>(null);
  useEffect(() => { api<typeof cat>('/catalogo').then(setCat).catch(avisoError); }, []);
  const guardar = async () => {
    if (!ed) return;
    try { await api('/config/atajos', { method: 'PUT', body: { ...ed, activo: !!ed.activo } }); avisoOk('Atajo guardado', ed.etiqueta); setEd(null); recargar(); }
    catch (e) { avisoError(e); }
  };
  return (
    <>
      <Text size="sm" c="dimmed" mb="sm">Lo que significa cada palabra del Excel: «Bacon» = 0,015 KG de bacon. «Sustituye» hace que un huevo o pan reemplace al de la receta en vez de sumarse.</Text>
      <Tabla datos={cfg.atajos.filter((a) => a.grupo === grupo)} clave={(a) => `${a.grupo}|${a.etiqueta}`} buscar atenuar={(a) => !a.activo} alPulsar={(a) => setEd({ ...a, etiqueta_anterior: a.etiqueta })}
        filtros={<Group gap="xs"><SegmentedControl value={grupo} onChange={setGrupo} data={Object.entries(GRUPOS).map(([value, label]) => ({ value, label }))} />
          <Button size="xs" variant="light" leftSection={<IconPlus size={14} />} onClick={() => setEd({ etiqueta: '', grupo, producto: null, receta_id: null, cantidad: 1, sustituye: null, activo: 1, producto_nombre: null, unidad: null, receta_nombre: null })}>Nuevo</Button></Group>}
        columnas={[
          { clave: 'etiqueta', titulo: 'En el Excel' },
          { clave: 'producto_nombre', titulo: 'Descuenta', valor: (a) => a.receta_nombre ? `Receta: ${a.receta_nombre}` : a.producto_nombre ?? '(solo quita)' },
          { clave: 'cantidad', titulo: 'Cantidad', num: true, render: (a) => a.producto ? `${a.cantidad} ${a.unidad ?? ''}` : a.receta_id ? `${a.cantidad} rac.` : '—' },
          { clave: 'sustituye', titulo: 'Sustituye', render: (a) => (a.sustituye ? <Badge variant="light">{a.sustituye}</Badge> : null) },
        ]} />
      <Modal opened={!!ed} onClose={() => setEd(null)} title={ed?.etiqueta || 'Nuevo atajo'} centered>
        {ed && cat && (
          <Stack>
            <TextInput label="Palabra en el Excel" value={ed.etiqueta} onChange={(e) => setEd({ ...ed, etiqueta: e.currentTarget.value })} />
            <Select label="Producto" searchable clearable limit={60} value={ed.producto} onChange={(x) => setEd({ ...ed, producto: x, receta_id: x ? null : ed.receta_id })}
              data={cat.productos.map((p) => ({ value: p.codigo, label: `${p.nombre} (${p.unidad ?? 'ud'})` }))} />
            <Select label="…o receta" searchable clearable value={ed.receta_id} onChange={(x) => setEd({ ...ed, receta_id: x, producto: x ? null : ed.producto })}
              data={cat.recetas.map((r) => ({ value: r.id, label: r.nombre }))} />
            <Group grow>
              <NumberInput label="Cantidad por unidad" value={ed.cantidad} min={0} decimalScale={4} onChange={(x) => setEd({ ...ed, cantidad: Number(x) })} />
              <Select label="Sustituye a" clearable data={[{ value: 'huevo', label: 'Huevo de la receta' }, { value: 'pan', label: 'Pan de la receta' }]}
                value={ed.sustituye} onChange={(x) => setEd({ ...ed, sustituye: x })} />
            </Group>
            <Switch label="Activo" checked={!!ed.activo} onChange={(e) => setEd({ ...ed, activo: e.currentTarget.checked ? 1 : 0 })} />
            <Group justify="flex-end"><Button variant="default" onClick={() => setEd(null)}>Cancelar</Button><Button onClick={guardar} disabled={!ed.etiqueta.trim()}>Guardar</Button></Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}

function RecetasDia({ cfg, recargar }: { cfg: Cfg; recargar: () => void }) {
  const [recetas, setRecetas] = useState<{ value: string; label: string }[]>([]);
  useEffect(() => { api<{ recetas: { id: string; nombre: string }[] }>('/catalogo').then((c) => setRecetas(c.recetas.map((r) => ({ value: r.id, label: r.nombre })))).catch(avisoError); }, []);
  const etiquetas = [...new Set(cfg.recetas_dia.map((r) => r.etiqueta))];
  const cambiar = async (etiqueta: string, dia: number, receta_id: string | null) => {
    if (!receta_id) return;
    try { await api('/config/recetas_dia', { method: 'PUT', body: { etiqueta, dia_semana: dia, receta_id } }); avisoOk(`${etiqueta} · ${DIAS[dia]}`, 'Guardado (TPV recalculado)'); recargar(); }
    catch (e) { avisoError(e); }
  };
  return (
    <SimpleGrid cols={{ base: 1, md: 2 }}>
      {etiquetas.map((et) => (
        <Card key={et}>
          <Text fw={600} mb="sm">{et}</Text>
          <Stack gap="xs">
            {DIAS.map((d, i) => (
              <Group key={d} justify="space-between" wrap="nowrap">
                <Text size="sm" w={90}>{d}</Text>
                <Select searchable data={recetas} style={{ flex: 1 }} value={cfg.recetas_dia.find((r) => r.etiqueta === et && r.dia_semana === i)?.receta_id ?? null}
                  onChange={(x) => cambiar(et, i, x)} aria-label={`${et} ${d}`} />
              </Group>
            ))}
          </Stack>
        </Card>
      ))}
    </SimpleGrid>
  );
}

function Copias({ cfg, recargar }: { cfg: Cfg; recargar: () => void }) {
  const ahora = async () => { try { const r = await api<{ nombre: string }>('/config/copias', { method: 'POST' }); avisoOk(r.nombre, 'Copia hecha'); recargar(); } catch (e) { avisoError(e); } };
  return (
    <>
      <Alert color="blue" mb="md">BM hace una copia completa cada día automáticamente y guarda las 30 últimas en el servidor. Conviene descargar una de vez en cuando a otro sitio.</Alert>
      <Group justify="flex-end" mb="sm"><Button leftSection={<IconDatabaseExport size={16} />} onClick={ahora}>Hacer copia ahora</Button></Group>
      <Tabla datos={cfg.copias} clave={(c) => c.nombre} vacio="Aún no hay copias" columnas={[
        { clave: 'fecha', titulo: 'Fecha', render: (c) => c.fecha.replace('T', ' ') },
        { clave: 'nombre', titulo: 'Fichero' },
        { clave: 'tamano', titulo: 'Tamaño', num: true, render: (c) => `${(c.tamano / 1048576).toFixed(1)} MB` },
        { clave: 'd', titulo: '', ordenable: false, exportar: false, render: (c) => (
          <Button component="a" href={`/api/config/copias/${encodeURIComponent(c.nombre)}`} size="compact-sm" variant="subtle" leftSection={<IconDownload size={14} />}>Descargar</Button>) },
      ]} />
    </>
  );
}

function Actividad() {
  const [filas, setFilas] = useState<{ id: number; cuando: string; usuario: string | null; metodo: string; ruta: string; estado: number }[] | null>(null);
  useEffect(() => { api<typeof filas>('/config/actividad').then(setFilas).catch(avisoError); }, []);
  return (
    <Tabla datos={filas} clave={(f) => f.id} buscar exportar="actividad" porPagina={50} columnas={[
      { clave: 'cuando', titulo: 'Cuándo', render: (f) => `${fecha(f.cuando.slice(0, 10))} ${f.cuando.slice(11, 16)}` },
      { clave: 'usuario', titulo: 'Quién' },
      { clave: 'ruta', titulo: 'Acción', valor: (f) => `${f.metodo} ${f.ruta}` },
      { clave: 'estado', titulo: 'Resultado', render: (f) => <Badge color={f.estado < 300 ? 'teal' : 'red'} variant="light">{f.estado < 300 ? 'Hecho' : `Rechazado (${f.estado})`}</Badge> },
    ]} />
  );
}

export function Configuracion() {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [rol, setRol] = useState('');
  const recargar = () => api<Cfg>('/config').then(setCfg).catch(avisoError);
  useEffect(() => { recargar(); api<{ rol: string }>('/me').then((u) => setRol(u.rol)).catch(() => null); }, []);
  const dir = rol === 'direccion';
  return (
    <>
      <Cabecera titulo="Configuración" subtitulo="Ajustes del hotel, usuarios, catálogos de trabajo y seguridad" />
      {!cfg ? <Text c="dimmed">Cargando…</Text> : (
        <Tabs defaultValue="general" keepMounted={false}>
          <Tabs.List mb="md">
            <Tabs.Tab value="general">General</Tabs.Tab>
            {dir && <Tabs.Tab value="usuarios">Usuarios</Tabs.Tab>}
            <Tabs.Tab value="centros">Centros de consumo</Tabs.Tab>
            <Tabs.Tab value="ubicaciones">Ubicaciones</Tabs.Tab>
            <Tabs.Tab value="atajos">Atajos del Excel</Tabs.Tab>
            <Tabs.Tab value="dia">Recetas del día</Tabs.Tab>
            <Tabs.Tab value="copias">Copias de seguridad</Tabs.Tab>
            {dir && <Tabs.Tab value="actividad">Actividad</Tabs.Tab>}
          </Tabs.List>
          <Tabs.Panel value="general">{dir ? <General cfg={cfg} recargar={recargar} /> : <Text c="dimmed">Solo Dirección puede cambiar los ajustes generales.</Text>}</Tabs.Panel>
          <Tabs.Panel value="usuarios"><Usuarios cfg={cfg} recargar={recargar} /></Tabs.Panel>
          <Tabs.Panel value="centros"><Centros cfg={cfg} recargar={recargar} /></Tabs.Panel>
          <Tabs.Panel value="ubicaciones"><Ubicaciones cfg={cfg} recargar={recargar} /></Tabs.Panel>
          <Tabs.Panel value="atajos"><Atajos cfg={cfg} recargar={recargar} /></Tabs.Panel>
          <Tabs.Panel value="dia"><RecetasDia cfg={cfg} recargar={recargar} /></Tabs.Panel>
          <Tabs.Panel value="copias"><Copias cfg={cfg} recargar={recargar} /></Tabs.Panel>
          <Tabs.Panel value="actividad"><Actividad /></Tabs.Panel>
        </Tabs>
      )}
    </>
  );
}
