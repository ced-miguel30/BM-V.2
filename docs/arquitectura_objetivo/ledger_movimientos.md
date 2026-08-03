# Ledger de movimientos — Fase 7B (ledger, ubicación, traslados, recuentos)

Documento vivo. **Fase 7B entregada**.

## Estado

| Aspecto | Estado |
|---------|--------|
| Dual-write 7A | **Hecho** |
| Reconciliación + frontera activación | **Hecho (7B.1)** |
| Saldo sombra | **Hecho (7B.2)** |
| Stock por ubicación | **Hecho (7B.3)** |
| Traslados | **Hecho (7B.4)** |
| Ledger como fuente de verdad (configurable) | **Hecho (7B.5)** |
| Recuentos por ubicación | **Hecho (7B.6)** |

**Versión:** `BM-V.2 · Ledger y stock por ubicación`.

## Modos de saldo (`ledger_balance_mode`)

| Modo | Lectura operativa | Notas |
|------|-------------------|--------|
| `legacy` | `cantidad_restante` | Sin comparación ledger |
| `shadow` (**default**) | `cantidad_restante` | Ledger en paralelo; diagnostica diferencias |
| `ledger` | Saldo ledger si cobertura completa / inconsistencia post-activación | Histórico parcial → legacy híbrido |

`cantidad_restante` **no se elimina**. En modo ledger es espejo de compatibilidad; la autoridad es el movimiento.

## Frontera de activación

Persistida en `ConfiguracionHotel.ledger_activation_iso` (+ `ledger_schema_version`).  
Se fija una vez (explícita o derivada del primer `creado_en` de movimientos). **No** se re-infiere desde `datetime.now()` en cada ejecución.

## Cobertura por lote

`historico_sin_ledger` · `cobertura_parcial` · `cobertura_completa` · `inconsistencia_posterior_activacion` · `sin_movimientos`

Histórico pre-frontera no es error automático. No hay backfill ni corrección automática de saldos.

## Ubicaciones

Campos aditivos en movimiento: `ubicacion_origen_id`, `ubicacion_destino_id`.  
Estado `sin_ubicacion_historica` = ausencia controlada (no es ID de catálogo).  
`Producto.ubicacion_ids` = permitidas, no cantidades. Saldo por ubicación se deriva del ledger.

## Traslados

Tipo `traslado`: origen ≠ destino, cantidad > 0, stock hotel y coste invariantes, FIFO global intacto. Anulación = traslado reverso (append-only).

## Recuentos

Sesión borrador → confirmación atómica → `ajuste_entrada` / `ajuste_salida` + espejo ledger. Anulación vía ajustes inversos. Sin escáner ni multiusuario avanzado.

## Rollback

- Volver a `shadow`/`legacy` por configuración sin borrar movimientos.
- Cada subfase 7B es un commit independiente.
- Backup 7A: `data/backups/datos_hotel_7a_freeze_*.json`.

## Limitaciones

- Modo default sigue siendo `shadow` (activar `ledger` solo sin diferencias post-activación).
- Sin proveedores, documentos, facturas, API, Flet.
- Sin préstamos / activos individuales.
