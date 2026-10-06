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
Fases 1-12 hechas + comandas + mejoras del 06/10 noche (ver abajo). Datos de prueba cargados: BC hasta 06/10,
BM v2 hasta 27/09, desayunos Excel 03-12/09, TPV 22/08-06/10. 

Mejoras 06/10 (noche): sugerencias TPV sin parecidos falsos; recuento con borrador en el dispositivo y **zonas**
(nevera, congelador...) para contar por partes; `index.html` sin caché (tras actualizar, todos ven la versión nueva);
segunda carpeta de copias con aviso si falla; revisión de fichas avisa de ingredientes que ya no se compran ni quedan;
"comprar por fuera" y "reponer" solo alarman con stock fiable (inventario ≤ 10 días o consumo registrado en BM);
Importar de BC indica desde qué fecha exportar; nombres legibles de almacenes de departamento.
Segunda tanda: comensales automáticos del desayuno = nº de platos (antes contaba líneas: "2 ingles" era 1);
food cost TPV solo sobre venta asignada (octubre 15,6 % → 19,7 %, el panel dice cuánto queda fuera); cierre de mes
con días que faltan y solo artículos TPV vendidos ese mes; login bloqueado 15 min tras 10 fallos (queda en Actividad);
informe/productos/compras adaptados al móvil. Tests: 47.

## Pendiente de revisar por el usuario
1. **TPV (47 sin asignar):** las sugerencias ya son fiables, pero revisar: *Pescado del día* (sugiere caldo de
   pescado: no aceptar), *Ración croquetas* → producto Croquetas de pollo (¿cuántas por ración?), *Smoothie* →
   producto Smoothies B2 (¿es el que se usa?). Sin sugerencia: Espagueti boloñesa, Paella, Surtido ibérico, etc.
2. **Fichas:** 10 con problemas (food cost bajísimo: ¿faltan ingredientes?) y ~20 con ingredientes que ya no se
   compran (Lechuga romana, Queso emmental lonchas, Vino tinto brik desde 2023, Leche de coco, Jack Daniel's...):
   decir qué producto se usa ahora. Recetas → Avisos.
3. **Datos de BC para administración:** *Langostinos Nº 2 salvaje* a 3,65 €/KG siempre (¿unidad mal en BC?);
   productos con nombre vacío o raro (C0000027 ",", PV00000253 "1", LIM, VINO, V000001, TPV00000001); precios dudosos.
4. **Zonas del recuento:** se asignan solas al contar la primera vez (botón "Zona" de cada producto).
5. **Copias:** decidir la segunda carpeta en el servidor (NAS, otro disco u OneDrive) → Configuración → Copias.
6. **Pedidos:** con el último inventario del 31/08 las propuestas son extrapolación; mejoran con recuentos frecuentes.
7. **Idea no hecha (necesita a administración de BC):** leer BC directamente por su API (OData/API web) en vez de
   exportar Excel. Sería lo que más trabajo quita; requiere usuario/permiso de servicio en BC.
8. Sigue faltando: export "Líneas factura compra registradas", contactos de proveedores, datos frescos, prueba con
   el personal, `instalar\instalar.ps1` en el servidor.
- Entorno: Bash corta heredocs > ~7 KB (escribir ficheros en trozos); `gh` sin sesión (CI en GitHub sin verificar).
