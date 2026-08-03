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
| D22 | `departamento_ids` = ámbitos de uso; **no** ubicación ni stock | Ubicaciones = F6B |
| D23 | `categoria_inventario` convive con `categoria_id` | Sin conversión automática de strings a filas |

## Decisiones pendientes (no bloquean F3)

| ID | Pregunta | Notas |
|----|----------|-------|
| P01 | ¿Cuándo unificar `RegistroDesayuno` en `RegistroServicio`? | Tras desacople; alto riesgo |
| P02 | ¿Stock por ubicación como tabla materializada o solo ledger? | Decidir en F6B/F7 |
| P03 | Política exacta de préstamo/textil/activo | Solo esbozo en F6C |
| P04 | ¿Movimiento `conciliacion` neutro en factura o solo metadatos? | F11 |
| P05 | Migración de costes `float` → `Decimal` en consumo | Fuera de docs; spike posterior |
| P06 | Multi-almacén vs multi-ubicación simple | Asumir ubicaciones simples hasta P02 |
| P07 | Retención y borrado legal de archivos documentales | F9/F17 |

## Compatibilidad histórica — reglas permanentes

1. Campos nuevos aditivos.  
2. Ausencia → UI “No configurado” / “Sin desglose histórico” / bloqueo si la operación lo requiere.  
3. No reinterpretar `servicios_disponibles=[]` como “todos”.  
4. IDs legacy preservados en migración.  
5. `marca_proveedor` y costes ya guardados no se reescriben al crear Proveedor maestro.  
6. Referencias de catálogo huérfanas se conservan y se etiquetan «Referencia no encontrada»; no se anulan en silencio.

## Próximo paso de implementación

**Fase 6B** — ubicaciones + relación producto-ubicación (tras aprobación explícita de 6A).
