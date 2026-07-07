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

## Fase 8 — KPIs y gráficos ✅
- Filtro por periodo (desde / hasta) en Análisis → KPIs
- Coste por huésped, evolución diaria con gráfico Altair
- Exportar Excel de KPIs
- Gráfico mensual en Dashboard

## Fase 9 — Gestor de consumo ✅
- Predicción de necesidades según huéspedes esperados
- Coste estimado y recomendaciones operativas

## Fase 10 — Gestor de costes ✅
- Comparación de periodos A / B por categoría
- Gráfico comparativo y exportación Excel

## Fase 11 — Business Intelligence ✅
- Preguntas sugeridas con respuestas por reglas
- Consulta libre con palabras clave
- Resumen automático del mes

## Fase 12 — Settings funcional ✅
- CRUD de usuarios (crear, editar, eliminar)
- Guardar configuración (nombre hotel, moneda)
- Subida y persistencia de logo
- Nombre del hotel dinámico en la barra lateral

## Fase 13 — Exportación cliente ✅
- Exportar actividad del día (Excel) → `exports/`
- Informe cliente con KPIs, desayunos, mermas, inventario y alertas
- Accesos rápidos: últimos 7 días y mes en curso

## Fase 14 — SQLite (NO antes)
- Eliminar mock_data.py y carpeta demo

## Fase 15 — Login (NO antes)
