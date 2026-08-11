# Puesta en marcha operativa — BM‑V.2 (cargar productos y recetas reales)

## Objetivo

Dejar el sistema listo para **cargar datos reales** (productos, recetas, proveedores,
inventario, usuarios) sin seguir construyendo infraestructura básica.

## Arranque desde código (desarrollo / piloto Python)

```powershell
cd "C:\Users\User\Desktop\HOTEL\BM V.2"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Instancia aislada (nunca el demo canónico ni BM-V2-pilot sin decisión)
$env:BM_DEPLOY_PROFILE = "dev"
$env:BM_DEMO_FILE = "C:\ruta\temporal\datos_hotel.json"   # copia del demo o vacío inicial
$env:BM_FLET_VIEW = "desktop"

python -m app.presentation.flet.main_launcher
```

Verticales sueltas:

| Terminal | Comando |
|----------|---------|
| Launcher | `python -m app.presentation.flet.main_launcher` |
| Restaurante | `python -m app.presentation.flet.main` |
| Inventario | `python -m app.presentation.flet.main_inventario` |
| Administración | `python -m app.presentation.flet.main_administracion` |

Instalación gestionada (estrategia C): ver `docs/deploy_local_p1.md` / `p2.md` y `deploy/windows\*.cmd`.

## Generar ejecutable Windows (PyInstaller)

```powershell
deploy\windows\build_exe.cmd
# → dist\BM-Launcher\BM-Launcher.exe
```

- Artefacto **onedir**; no commitear `dist/` / `build/`.
- Primera ejecución crea `%LOCALAPPDATA%\BM-V2-local\` (distinto de `BM-V2-pilot`).
- Copia demo embebido solo si aún no existe `datos_hotel.json` en la instancia.

## Orden de carga de datos reales (Administración Flet)

1. Instalar / configurar almacenamiento (`BM_INSTANCE_ROOT` o `BM_DEMO_FILE`).
2. Abrir **Administración** e iniciar sesión (usuario Dirección/Administración).
3. **Configuración**: nombre del hotel.
4. **Usuarios**: crear operadores; asignar roles; contraseñas seguras.
5. **Productos**: alta con código, unidad, tipo (consumible/reutilizable), stock mínimo.
6. **Proveedores**: alta de proveedores habituales.
7. **Compras** o **Inventario inicial**: entrar stock/lotes (compra confirmada o lote manual).
8. **Recetas**: ingredientes activos, porciones estándar, categoría/servicio.
9. **Responsables de merma**: para Terminal Inventario.
10. **Backup**: generar ZIP y guardar fuera del PC de caja.
11. Probar un registro controlado en **Restaurante** y consultar stock en **Inventario**.
12. Iniciar piloto.

## Credenciales

- **Producción:** las que cree el administrador; nunca las de tests.
- **Solo tests / fixture UI:** `tests/browser/fixtures_minimos.py` (`dir_ui` / `UiTestPass1`) — no usar en hotel.

## Primera acción del administrador

1. Entrar en Administración Flet.  
2. Crear backup preventivo.  
3. Crear/ajustar usuario Dirección si hace falta.  
4. Empezar por **Productos** y **Recetas** según el orden anterior.

## Qué no mezclar

| Almacén | Uso |
|---------|-----|
| `data/demo/datos_hotel.json` | Solo referencia / SHA canónico |
| `%LOCALAPPDATA%\BM-V2-pilot` | Piloto físico documentado (no tocar en desarrollo) |
| `%LOCALAPPDATA%\BM-V2-local` | Instancia del ejecutable empaquetado |
| Temp + `BM_DEMO_FILE` | Pruebas P3 / desarrollo |

## Documentación relacionada

- `docs/operations_multi_pc.md` — tres ordenadores + carpeta compartida
- `docs/shared_storage.md` — locks y revisión
- `docs/flet_administracion_operativa.md`
- `docs/flet_terminal_restaurante.md`
- `docs/flet_terminal_inventario.md`
- `docs/flet_launcher.md`
- `docs/deploy_local_p2.md`
- `docs/flet_packaging_plan.md`
