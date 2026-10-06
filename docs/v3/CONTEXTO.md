# Contexto para continuar BM v3 (06/10/2026)

**Proyecto:** BM = control de consumo, inventario, stock y coste F&B de Royal Marina Suites (restaurante + departamentos).
Repo `D:\RMS\BM-V.2`, GitHub `ced-miguel30/BM-V.2`, **rama `v3`** (la v2 Flet/Streamlit sigue en `main`, no se toca).
**No se instala en el hotel hasta que esté completa y probada.** Objetivo: que lo lleve todo sola; la persona solo hace
inventarios físicos y confirma propuestas.

## Arquitectura
- `bm/` FastAPI + SQLite (un solo proceso escritor; `python -m bm.servidor`). Módulos: `bc` (import BC), `costing` (FIFO
  anclado a inventarios), `inventario` (stock por ubicación física), `tpv`, `excel`, `comandas`, `buffet`, `prevision`
  (pedidos/reposición), `compras`, `analisis`, `avisos`, `cierre`; rutas `api_*.py` registradas sobre `bm.app`.
- `web/` React + Mantine 9 (`npm run build` → `bm/static`, que se versiona). Tabla común `web/src/Tabla.tsx`.
- Tests: `python -m unittest discover -s bm/tests -t .` (39 tests). Docs: `docs/v3/` (HOJA_DE_RUTA, MANUAL, INSTALACION).
- Base de desarrollo: `datos/bm.sqlite` (gitignored). Usuario dev en `datos/DEV_LOGIN.txt`. Recarga completa:
  `python -m bm.importar --productos Productos.xlsx --movs "Movs. productos.xlsx" --bm2 datos_hotel.json --tpv-pdf X.pdf`.

## Decisiones del usuario
- Compras y precios los registra administración en **Business Central**; BM importa ("Movimientos de producto", "Productos",
  "Líneas factura compra registradas") y nunca registra dos veces.
- Coste **FIFO** con precios reales de BC, anclado a cada inventario (BC mensual o recuento BM). Precios disparatados de BC
  se ignoran (se listan para corregir).
- Ubicaciones **físicas**: Economato y Restaurante y cocina. Almacenes BC (DESAYUNO, SNACK...) son contables (`almacenes_bc`).
- Traslados: BM propone reposición; se registran en BC y BM los importa.
- TPV: PDF "Ventas TPV por categoría" de BC (sin OCR), por día y artículo PV, asignación artículo → receta/producto.
- **Desayuno:** comandas en papel que toma el camarero; **administración las pasa después**. Cada línea = 1 huésped.
  Pantalla "Comandas de desayuno" con entrada rápida por teclado (`2 ingles +bacon -tomate`) + botones + historial.
  El Excel antiguo sigue valiendo (tolerante: fechas heredadas, erratas, comensales = nº de líneas).
- IGIC ventas 7 %, objetivo food cost 30 % (configurables).

## Estado
Fases 1-12 hechas + comandas (ver `docs/v3/HOJA_DE_RUTA.md`). Datos de prueba cargados: BC hasta 06/10, BM v2 hasta 27/09,
desayunos Excel 03-12/09, TPV 22/08-06/10.

## Pendiente / siguiente
- El usuario debe revisar la aplicación; ajustar según su uso real.
- 47 artículos TPV sin asignar (32 con sugerencia): Smoothie (497 €) y Ración croquetas (280 €) necesitan receta.
- 10 fichas de receta con errores (Recetas → A revisar); 58 precios dudosos en BC.
- Buffet no registrado desde agosto: usar "Buffet del día".
- Falta: export de BC "Líneas factura compra registradas" (enlace factura↔albarán) y datos de contacto de proveedores.
- Antes de instalar: cargar datos frescos, prueba con el personal, ejecutar `instalar\instalar.ps1` en el servidor.
- Entorno: Bash corta heredocs > ~7 KB (escribir ficheros en trozos); `gh` sin sesión (CI en GitHub sin verificar).
