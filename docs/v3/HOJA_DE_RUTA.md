# BM v3 — Hoja de ruta a versión profesional

Objetivo: BM es el programa de **consumo, inventario, stock y coste** del restaurante y de los
departamentos del hotel. Business Central (BC) sigue siendo contabilidad y compras: BM importa de BC,
nunca se registra lo mismo dos veces. No se instala en el hotel hasta completar todas las fases.

## Decisiones de modelo

| Tema | Decisión |
|------|----------|
| Compras / precios | Vienen de BC ("Movimientos de producto"). Cada compra = lote con coste real. |
| Coste | FIFO por producto, anclado a cada inventario (de BC o recuento de BM). |
| Centros de consumo | Configurables: desayuno, comida, cena, bebidas + departamentos (pisos, limpieza, mantenimiento…). Cada uno con almacén por defecto. Exclusivos: un consumo pertenece a un solo centro. |
| Stock por ubicación | Libro de movimientos: compras y traslados BC + consumos/mermas/traslados BM. El último recuento (BC o BM) de esa ubicación manda; desde ahí se suma/resta. |
| Traslados | Ajuste `traslados_en`: `bc` (por defecto, se importan) o `bm` (se registran en BM y se ignoran los de BC). Nunca ambos. |
| Recuentos | Por ubicación, desde tablet/móvil. Fijan el stock real y la diferencia queda como desviación (control). |
| Caducidades | Registro de producto + ubicación + cantidad + fecha; avisos y salida a merma. |
| Histórico | Nunca se borra: anular deja rastro. Todo cambio guarda quién y cuándo. |

## Fases

1. **Modelo de inventario** — centros de consumo, ubicaciones, libro de stock anclado a recuentos, ajuste de traslados. Tests.
2. **Inventario** — stock por ubicación, recuentos rápidos (móvil), traslados, caducidades, mermas desde inventario.
3. **Sistema de diseño** — tabla profesional común (ordenar, filtrar, paginar, exportar Excel), identidad, estados de carga/vacío/error, móvil y tablet verificados.
4. **Análisis de dirección** — panel ejecutivo (12 meses, objetivos), rentabilidad por plato (PVP − coste), control real vs teórico por producto/ubicación, evolución de precios de proveedor, informes Excel/PDF.
5. **Configuración y seguridad** — usuarios y roles, atajos y buffet, centros y objetivos, registro de auditoría, copias de seguridad automáticas, sesiones persistentes.
6. **Calidad y puesta en marcha** — tests de API y de pantallas, comprobación automática en GitHub, instalación como servicio en el servidor, manual de uso.

## Estado

- [x] Base: BC → SQLite, FIFO con traza, TPV sin OCR, Excel de desayuno, web inicial (rama `v3`).
- [x] Fase 1: modelo de inventario (centros, ubicaciones, libro de stock anclado, recuentos, traslados, caducidades)
- [x] Fase 2: inventario (stock por ubicación, recuento a ciegas en móvil, traslados, caducidades)
- [x] Fase 3: sistema de diseño (tabla común con orden/búsqueda/paginación/exportar, logo, Inter, menú por secciones)
- [x] Fase 4: análisis (rentabilidad por plato, control real vs teórico, precios de compra y dudosos de BC, tendencia 12 meses, food cost neto de IGIC vs objetivo)
- [x] Fase 5: configuración y seguridad (ajustes, usuarios, centros, ubicaciones, atajos, recetas del día, sesiones persistentes, registro de actividad, copias diarias, cambio de contraseña)
- [ ] Fase 6
