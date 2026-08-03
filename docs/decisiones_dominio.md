# Decisiones de dominio (Fase 2)

Documento vivo de decisiones **cerradas** en diseño y **pendientes** explícitas.  
Sin implementación de código en esta fase.

## Decisiones cerradas

| ID | Decisión | Implicación |
|----|----------|-------------|
| D01 | Una sola app / una sola fuente de datos; tres espacios de trabajo | No clonar sistemas |
| D02 | Producto maestro ≠ proveedor | Proveedores solo en Fase 8 |
| D03 | Fase 6 sin proveedores | Evita rehacer catálogo en F8 |
| D04 | Dimensiones separadas (depto, categoría, ubicación, servicio, tipo) | No fusionar enums |
| D05 | `LoteStock` no se convierte en factura | Documentos aparte |
| D06 | Albarán confirmado incrementa stock; factura conciliación no | Ledger + flujo documental |
| D07 | Ledger: cantidad siempre > 0 + `direccion`; `cantidad_firmada` derivada | Ver ledger_movimientos.md |
| D08 | Traslado = par salida/entrada con `grupo_id`; total hotel invariante | Stock por ubicación |
| D09 | Reversos append-only; sin borrar movimientos confirmados | Igual filosofía soft-delete actual |
| D10 | Sin trazabilidad suficiente → bloqueo anulación | Ya en código; se mantiene |
| D11 | Sin backfill silencioso de snapshots / consumos_lote | Histórico incompleto visible |
| D12 | Decimal en módulo documental/impuestos futuros; no ampliar float ahí | Núcleo actual sigue float hasta migración controlada |
| D13 | ID técnico ≠ proveedor+fecha | Generador de IDs central (F3) |
| D14 | Auth final ≠ `st.session_state` | F16 |
| D15 | Almacenamiento operativo multiusuario = PostgreSQL | SQLite solo posible como puente local |
| D16 | No software fiscal de emisión a cliente sin decisión posterior | Factura = documento recibido interno |
| D17 | F1A/F1B ∥ F2 (docs); F2 no toca código productivo | Cumplido |
| D18 | Nav 3 modos: integración F5 tras frontera F3; prototipo aislado opcional | F5 hecha |
| D19 | Ledger conceptual en F2; código en F7 antes de depender de documentos | |
| D20 | Conservar stacks desayuno + registros_servicio por ahora | Unificación no es F2/F3 |
| D21 | **Fase 6A completada** — `Departamento`, `Categoria`, `Subcategoria` | Soft-delete; sin backfill de `categoria_inventario` |
| D22 | `departamento_ids` = ámbitos de uso; **no** ubicación ni stock | Distinto de `ubicacion_ids` |
| D23 | `categoria_inventario` convive con `categoria_id` | Sin conversión automática de strings a filas |
| D24 | **Fase 6B completada** — `Ubicacion` + `producto.ubicacion_ids` | Catálogo + vínculo; **sin** stock por ubicación |
| D25 | P02 (stock por ubicación materializado vs ledger) **aplazada a F7** | 6B no materializa cantidades |
| D26 | **Fase 6C completada** — enum `TipoArticulo` (consumible / reutilizable) | Taxonomía fija; sin CRUD; sin backfill |
| D27 | `es_bebida` ≠ `tipo_articulo` | Independientes; no migrar uno desde el otro |
| D28 | Históricos sin tipo → `None` («Sin clasificar») | Excepción temporal: edición de otros campos sin forzar tipo |
| D29 | Cambiar tipo no altera stock/FIFO/lotes/consumos | Reglas operativas de reutilizable → F7+ |
| D30 | **Fase 7A.1** — `MovimientoInventario` + `AppData.movimientos` | Ledger espejo; sin dual-write operativo |
| D31 | Fuente de verdad del stock = `LoteStock.cantidad_restante` | Ledger no calcula stock operativo en 7A |
| D32 | Cantidad de movimiento siempre > 0; dirección fija por tipo | Sin cantidades negativas |
| D33 | Idempotencia por clave origen+línea+lote+tipo | Duplicados controlados; no solo ID secuencial |
| D34 | Movimientos confirmados inmutables | Sin edición/borrado; correcciones = reversión |
| D35 | Sin backfill ni reconstrucción histórica de movimientos | Ausencia histórica ≠ error en 7A.1 |
| D36 | Reconciliación ledger vs lote solo informativa en 7A | No corrige, no bloquea, no sustituye |
| D37 | **Fase 7A.2** — dual-write `registrar_lote` + `aplicar_ajuste` | Espejo; fallo del ledger aborta la operación |
| D38 | **Fase 7A.3** — dual-write merma + anulación merma | Un movimiento por línea; históricos sin backfill |
| D39 | Línea de merma sin `id`: `origen_linea_id = lnNN` | Índice estable en lista append-only |
| D40 | Anulación histórica sin espejo → `anulacion_merma_historica` | `movimiento_revertido_id=None`; no inventar salida |
| D41 | **Fase 7A.4 / 7A completa** — dual-write consumos + anulaciones registro/compra | Un movimiento por fragmento `consumos_lote` |
| D42 | `origen_linea_id` consumo = `detNN:fragNN` | Índices estables append-only |
| D43 | Anulación compra → `reversion_entrada` por restante anulado | Puede diferir de cantidad de entrada si hubo consumo (compra intacta exige restante=compra) |
| D44 | Fase 7A cerrada en modo espejo | Stock seguía en lotes |
| D45 | **Fase 7B** — frontera `ledger_activation_iso` persistida | No re-inferir en cada ejecución |
| D46 | Modos `legacy` / `shadow` / `ledger`; default `shadow` | `cantidad_restante` no se elimina |
| D47 | Stock por ubicación derivado del ledger | `ubicacion_origen_id` / `ubicacion_destino_id` aditivos |
| D48 | `sin_ubicacion_historica` ≠ ubicación de catálogo | Sin backfill de ubicaciones |
| D49 | Traslado neto 0 en lote; anulación = traslado reverso | FIFO global intacto |
| D50 | Recuento → ajuste_entrada/salida + espejo | No sobrescribir saldo directo |
| D51 | En modo `ledger`, autoridad = movimientos | Restante = espejo de compatibilidad |
| D52 | **Fase 8** — `Proveedor`, `Impuesto` (Decimal), `RelacionProductoProveedor` | Sin facturas/albaranes |
| D53 | Snapshots en vínculo producto–proveedor | Editar maestro no reescribe snapshot ni `marca_proveedor` |

## Decisiones pendientes (no bloquean F3)

| ID | Pregunta | Notas |
|----|----------|-------|
| P01 | ¿Cuándo unificar `RegistroDesayuno` en `RegistroServicio`? | Tras desacople; alto riesgo |
| P02 | ~~¿Stock por ubicación materializado vs ledger?~~ | **Cerrado en D47** — derivado del ledger |
| P03 | Política exacta de préstamo/textil/activo | **Esbozo:** herramienta/préstamo; textil circulante; activo individual — **no implementados** |
| P04 | ¿Movimiento `conciliacion` neutro en factura o solo metadatos? | F11 |
| P05 | Migración de costes `float` → `Decimal` en consumo | Impuesto ya usa Decimal (F8); consumo pendiente |
| P06 | Multi-almacén vs multi-ubicación simple; jerarquía/tipos de ubicación | Lista plana en 7B |
| P07 | Retención y borrado legal de archivos documentales | F9/F17 |
| P08 | ~~¿Cuándo el ledger pasa a fuente de verdad?~~ | **Cerrado en D46/D51** — modo configurable; default shadow |

## Compatibilidad histórica — reglas permanentes

1. Campos nuevos aditivos.  
2. Ausencia → UI “No configurado” / “Sin desglose histórico” / bloqueo si la operación lo requiere.  
3. No reinterpretar `servicios_disponibles=[]` como “todos”.  
4. IDs legacy preservados en migración.  
5. `marca_proveedor` y costes ya guardados no se reescriben al crear Proveedor maestro.  
6. Referencias de catálogo huérfanas se conservan y se etiquetan «Referencia no encontrada»; no se anulan en silencio.  
7. `tipo_articulo` desconocido se conserva y se diagnostica; no se convierte en consumible.
8. `movimientos` / `recuentos` / `proveedores` / `impuestos` / relaciones ausentes → `[]`; tipos desconocidos se conservan.
9. No asignar ubicaciones ficticias a históricos.

## Próximo paso de implementación

**Fase 9+** — documentos (albarán / factura / conciliación), tras revisión de F8.
