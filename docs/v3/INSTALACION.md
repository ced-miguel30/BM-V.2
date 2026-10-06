# Instalación en el servidor del hotel

Requisitos: Windows con **Python 3.11 o superior** (python.org, marcar "Add to PATH") y la carpeta de
BM copiada en el servidor (por ejemplo `C:\BM`). Si hay git: `git clone -b v3 https://github.com/ced-miguel30/BM-V.2 C:\BM`.

1. **Instalar** (PowerShell como administrador, una sola vez):
   ```powershell
   powershell -ExecutionPolicy Bypass -File C:\BM\instalar\instalar.ps1
   ```
   Crea el entorno, registra la tarea "BM servidor" (arranca con Windows y se reinicia si falla)
   y abre el puerto 8000 solo para la red del hotel.
2. **Primer usuario de Dirección** (el instalador muestra el comando exacto):
   ```powershell
   $env:BM_DB='C:\BM\datos\bm.sqlite'; C:\BM\.venv\Scripts\python.exe -m bm.usuarios direccion "Nombre" direccion
   ```
   El resto de usuarios se crean desde Configuración → Usuarios.
3. **Carga inicial de datos** (una vez): exportar de BC "Productos" y "Movimientos de producto"
   (Compartir → Abrir en Excel) y, si se quiere migrar el histórico de BM v2, su `datos_hotel.json`:
   ```powershell
   $env:BM_DB='C:\BM\datos\bm.sqlite'
   C:\BM\.venv\Scripts\python.exe -m bm.importar --productos Productos.xlsx --movs "Movs. productos.xlsx" --bm2 datos_hotel.json
   ```
   Después, todo se importa desde la web (Importar de BC, Ventas TPV, Importar Excel).
4. **Entrar**: desde cualquier equipo de la red, `http://NOMBRE-DEL-SERVIDOR:8000`.

## Actualizar a una versión nueva

```powershell
powershell -ExecutionPolicy Bypass -File C:\BM\instalar\actualizar.ps1
```
Hace copia de seguridad, actualiza el código, pasa los tests y vuelve a arrancar. Los datos no se tocan.

## Copias de seguridad

Automáticas cada día en `datos\copias` (se guardan 30). Desde Configuración → Copias se puede hacer una
al momento y descargarla. Para restaurar: parar la tarea "BM servidor", copiar la copia elegida sobre
`datos\bm.sqlite` y arrancar la tarea.

## Acceso desde fuera del hotel (opcional, más adelante)

Con Cloudflare Tunnel (gratuito) sin abrir puertos del router. No es necesario para trabajar dentro del hotel.
