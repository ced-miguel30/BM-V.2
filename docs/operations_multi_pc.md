# Instalación multiordenador — BM‑V.2 (carpeta compartida)

## Objetivo

Tres PCs con la aplicación **instalada localmente**, apuntando a **una carpeta
compartida** en el servidor (datos, adjuntos, backups). El ejecutable **no** se
abre desde el servidor.

```text
PC 1 ─┐
PC 2 ─┼─→ \\SERVIDOR\BM-V2\   (ejemplo UNC — sustituir por la ruta real)
PC 3 ─┘
```

Terminal Restaurante permanece funcional; el piloto inicial se centra en
**Administración** e **Inventario** en los tres puestos.

## Requisitos del servidor

- Carpeta SMB/NAS accesible por los tres PCs (lectura + escritura).
- Permisos NTFS/share: usuarios de caja con RW sobre la carpeta.
- Espacio para JSON + `data/documentos/` + `backups/` + `exports/`.
- Un único escritor concurrente a nivel de *transacción* (la app usa lock
  `.bm_shared.lock` + `meta.revision`). No abrir Streamlit y Flet a la vez
  sobre el mismo JSON.

## Estructura recomendada en el share

```text
\\SERVIDOR\BM-V2\
  data\
    datos_hotel.json
    documentos\
  backups\
  exports\
  logs\          (opcional compartido)
```

## Precedencia de configuración

1. `BM_INSTANCE_ROOT` (proceso / soporte)
2. `BM_SHARED_ROOT` (alias de instancia compartida)
3. Config local del cliente (`%LOCALAPPDATA%\BM-V2-client\config.json` → `shared_root`)
4. Valores por defecto de desarrollo

`BM_DEMO_FILE` puede forzar el JSON exacto en tests; **nunca** usar el demo
canónico del repo como productivo.

Detalle técnico: `docs/shared_storage.md`.

## Instalación local (cada PC)

### Opción A — Python administrado (estrategia C)

1. Instalar Python ≥ 3.10.
2. Copiar release / clonar repo a carpeta local (p. ej. `C:\Apps\BM-V2\`).
3. Crear `.venv` e instalar `requirements.txt`.
4. `deploy\windows\prepare_env.cmd` según P1/P2.
5. Arrancar: `deploy\windows\start_launcher.cmd` **o**
   `python -m app.presentation.flet.main_launcher`.

### Opción B — Ejecutable PyInstaller

```powershell
deploy\windows\build_exe.cmd
# Artefacto: dist\BM-Launcher\BM-Launcher.exe
```

Copiar la carpeta `dist\BM-Launcher\` a cada PC. No almacenar datos dentro.

## Configuración de la ruta compartida

1. Abrir **Administración Flet** → sección **Servidor** (o Configuración/servidor).
2. Introducir la UNC, p. ej. `\\SERVIDOR\BM-V2`.
3. **Validar** (prueba R/W con temporal seguro).
4. **Guardar** (solo guarda la referencia en el cliente local).
5. Reiniciar la app si se pide.

Si el servidor no está disponible: mensaje claro; **no** se crea copia local
alternativa de los datos.

## Prueba concurrente (mínima)

1. PC1 crea un producto.
2. PC2 pulsa Actualizar / cambia de sección y lo ve.
3. PC2 registra una compra → lote/stock.
4. PC3 consulta Inventario / stock.
5. Mientras PC1 edita, PC2 no debe sobrescribir en silencio (conflicto de revisión
   o espera de lock con mensaje).

## Carga inicial de datos

Seguir el orden de `docs/operations_go_live.md` (unidades/categorías vía Catálogos,
productos, proveedores, compras/inventario inicial, recetas, usuarios, backup).

## Si se pierde el servidor

1. No trabajar “en local” con otra carpeta improvisada.
2. Reintentar conexión.
3. Si el outage es largo: cerrar la app; no forzar writes.
4. Al volver: abrir, Actualizar dashboard, verificar revisión.

## Si aparece un lock

Mensaje típico: otro usuario/PC sostiene `.bm_shared.lock`.

1. Esperar (operación corta).
2. Comprobar que no hay otro Flet/Streamlit abierto.
3. Solo soporte técnico puede inspeccionar el lock; no borrar a ciegas locks
   remotos con lease vigente.

## Restauración

1. Dirección: Backup → inspeccionar → confirmar frase de restauración.
2. Lock exclusivo durante restore.
3. Todos los clientes deben **recargar** tras el restore (Actualizar / reiniciar).

## Actualizar la aplicación

1. Cerrar Flet/Streamlit en todos los PCs.
2. Backup del share.
3. Reemplazar carpeta de aplicación local (código/exe).
4. **No** tocar `\\SERVIDOR\BM-V2\data`.
5. Abrir y validar.

## Logs

- Cliente: consola del exe / logs de instancia si están configurados.
- No incluir secretos en tickets.

## Conectar Restaurante después

El Terminal Restaurante ya usa el mismo `FileBackedAppDataStore` coordinado.
Cuando se añada un 4º PC de cocina: misma instalación local + misma UNC; no hace
falta reescribir Flet.

## Multiordenador

Ver `docs/operations_multi_pc.md` (UNC, locks, tres PCs).
Ver `docs/shared_storage.md` (revisión + `.bm_shared.lock`).

