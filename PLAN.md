# Plan de fases — Breakfast Management

Trabajar por fases. Parar al final de cada fase para revisión del usuario.

## Fase 4 — Stock: productos y lotes ✅
- Crear producto y registrar lote con persistencia JSON
- **Vista inventario:** una fila por producto (stock total agregado)
- **Historial de compras:** lotes en detalle, no en inventario principal
- Modelo de datos sin cambios (lotes siguen en JSON)

## Fase 5 — Alertas stock operativas ✅
- Sincronización automática: stock bajo, stock cero, expiración próxima, expirado
- Crear y resolver alertas manuales
- Dashboard y Stock muestran alertas actualizadas

## Fase 6 — Registro desayuno (cesta) ✅
- Cesta funcional con búsqueda y añadir productos
- Registro diario con coste FIFO automático
- Descuento de stock por lotes (más antiguo primero)

## Fase 7 — Registro merma / expiración ✅
- Selector de lote concreto con fecha de compra visible
- Cesta de merma y registro con descuento del lote elegido
- Inventario sigue mostrando solo total por producto

## Fases 8–13
- KPIs, análisis, settings, exportación cliente

## Fase 14 — SQLite (NO antes)
- Eliminar mock_data.py y carpeta demo

## Fase 15 — Login (NO antes)
