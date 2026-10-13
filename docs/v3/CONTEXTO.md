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

Bloque "funciones nuevas" (11/10/2026): pedidos enviados + control del albarán (`bm/pedidos.py`, Pedidos → Enviados);
carpeta de entrada que importa sola TPV y Excel de BC (`bm/entrada.py`, `datos\entrada`); PVP objetivo por plato y aviso
de subidas de ingredientes de carta; etiquetas de caducidad 60×40 mm (`web/src/etiqueta.ts`); escáner de códigos en el
recuento (USB/Bluetooth siempre; cámara solo con https). Paleta de gráficos elegante (variables `--serie-*` en app.css).

12-13/10/2026: maestro de Proveedores de BC importado (94; pocos con correo/teléfono). **Ingredientes intercambiables**
(`bm/intercambiables.py`, Recetas → Intercambiables): se consume el que caduca antes o el más barato comprado en 30 días.
`bm/semillas_carta.json` siembra grupos y 5 recetas estimadas (smoothie, croquetas, espagueti, paella, surtido ibérico).
**En el hotel a BC lo llaman "Noray".** Conexión API con BC en curso: app "BM Royal Marina" registrada en Entra ID
(tenant 980048cf-…, cliente 1140153d-…), permiso API.ReadWrite.All añadido, **falta el consentimiento de administrador**,
el secreto, el alta en BC (Aplicaciones de Microsoft Entra, D365 READ) y publicar páginas 38/31/líneas factura como OData.
**Servidor: en la nube**, accesible desde los PCs → necesita https (también hace falta para la cámara del móvil).
Copia secundaria: "otra carpeta".

13/10/2026 — **recuento en el móvil como app**: BM es instalable (PWA: `web/public/manifest.json`, iconos, `sw.js`); abre sin
cobertura con los últimos datos vistos. Lector de códigos propio (zxing en wasm, servido por BM) cuando el navegador no
trae BarcodeDetector → funciona en iPhone. **Modo escáner** (`web/src/ModoEscaner.tsx`): cámara abierta, escanear →
cantidad → Siguiente, zona elegida (se aprende sola), lista de lo que falta, sumar/sustituir, productos sin código.
Recuentos sin cobertura quedan en cola en el móvil (`web/src/pendientes.ts`) y se envían solos al volver; `recuentos.ref`
evita duplicados. Todo exige https en producción. Pendiente de decisión: escribir el recuento en Noray (ver abajo, punto 10). Prueba con personal cuando todo esté perfecto; después, datos frescos.

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
7. **Cámara del escáner:** requiere abrir BM por https en la red del hotel (certificado o Cloudflare Tunnel). Sin eso,
   lector USB/Bluetooth. Envío de pedidos: abre el correo del PC (mailto); envío directo necesitaría datos SMTP.
8. **Idea no hecha (necesita a administración de BC):** leer BC directamente por su API (OData/API web) en vez de
   exportar Excel. Sería lo que más trabajo quita; requiere usuario/permiso de servicio en BC.
9. Sigue faltando: export "Líneas factura compra registradas", contactos de proveedores, datos frescos, prueba con
   el personal, `instalar\instalar.ps1` en el servidor.
10. **Recuento → Noray (BC), decidido el 13/10:** ya no se hace inventario completo. BM calcula el stock a diario, se cuenta
   solo lo **fresco** (comprado ≥4 días en 60) y lo **caro** (productos que suman el 50 % del valor), y solo si se ha movido
   en 60 días (`cierre.recomendados`). A fin de mes, Cierre → **Para Noray** (`bm/noray.py`) da la cantidad física por
   almacén de Noray: lo del restaurante se reparte entre DESAYUNO, SNACK… según lo que Noray tiene en cada uno menos lo que
   BM vio gastar a su centro (opción "a" del usuario). Administración la pega en el diario de inventario físico y registra.
   El usuario acepta la estimación de BM para lo no contado. Cierre → **Revisar** (`analisis.anomalias`): actividad de 14 días
   fuera de lo habitual (×2 o −60 %) y recuentos que no cuadran con lo gastado por recetas → contar y revisar receta.
   Siguiente paso cuando la API de BC esté activa: escribir esas líneas en el diario **sin registrar** (necesita permiso de escritura).
11. **Perfil Cocina** (13/10): solo Recuento, a ciegas de verdad (la API no le devuelve stock esperado ni valores) y solo
    avisos de qué contar. Usuario de pruebas `cocina` en `datos/DEV_LOGIN.txt`. Servidor: Dormakaba gestiona el Windows
    del hotel (sistema de cerraduras): no instalar ahí sin su permiso; aplazado por el usuario.
- Entorno: Bash corta heredocs > ~7 KB (escribir ficheros en trozos); `gh` sin sesión (CI en GitHub sin verificar).
