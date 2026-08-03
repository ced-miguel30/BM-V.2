# Ledger de movimientos — modo espejo (Fase 7A)

Documento vivo. Implementación de código: **Fase 7A** (subfases).  
Documentos (albarán/factura) **no** se implementan sin dual-write estable.

## Estado actual (7A.3)

| Aspecto | Estado |
|---------|--------|
| Modelo + persistencia | **7A.1** |
| Dual-write lote + ajustes | **7A.2** |
| Dual-write merma + anulación merma | **7A.3 hecha** |
| Dual-write consumo / anulación registro | **Pendiente 7A.4** |
| Ledger como fuente de verdad | **No** |

**Fuente de verdad:** `LoteStock.cantidad_restante`.  
**Versión UI:** `BM-V.2 · Ledger espejo 7A.3`.

### Identidad de línea de merma (sin campo `id` en `LineaMerma`)

`origen_linea_id = ln{índice:02d}` (índice 0-based en `RegistroMerma.lineas`).  
Las líneas no se reordenan tras persistir. No se añadió ID nuevo al modelo.

| Operación | origen_tipo | origen_id | tipo |
|-----------|-------------|-----------|------|
| Registrar merma | `merma` | id registro | `merma` (salida) |
| Anular (con espejo) | `anulacion_merma` | id registro | `reversion_merma` |
| Anular histórica sin espejo | `anulacion_merma_historica` | id registro | `reversion_merma` (`movimiento_revertido_id=None`) |

Sin backfill. Históricos sin movimiento: cobertura parcial; anulación repone stock y escribe reverso histórico sin inventar la salida.

## 1. Problema

Hoy el stock vive en `LoteStock.cantidad_restante` y los eventos están implícitos en compras, consumo FIFO + `consumos_lote`, merma, ajuste y soft-anulaciones. No había libro unificado.

## 2. Principios (vigentes)

1. **Append-only:** no editar ni borrar movimientos confirmados; correcciones = movimientos de reversión.
2. **Espejo / complementario:** el ledger explica; no sustituye `cantidad_restante` hasta decisión futura.
3. **Cantidad siempre > 0;** el sentido lo da `direccion` (`entrada` | `salida`).
4. **`cantidad_firmada`** es derivada (+entrada / −salida).
5. **Trazabilidad por lote:** cada movimiento referencia `lote_id`.
6. **Idempotencia** por clave estable (origen + línea + lote + tipo).
7. **Sin backfill** ni reconstrucción histórica automática.

## 3. Modelo implementado (7A.1)

```text
MovimientoInventario
  id, producto_id, lote_id
  tipo: TipoMovimiento
  direccion: DireccionMovimiento
  cantidad > 0
  fecha, hora?
  origen_tipo, origen_id, origen_linea_id?
  movimiento_revertido_id?
  usuario_id?, idempotency_key?
  coste_unitario_snapshot?, coste_total_snapshot?
  creado_en?
```

Prefijo de ID: `mov` vía generador central (`next_id`).

### Tipos iniciales

| Tipo | Dirección |
|------|-----------|
| `entrada_compra` | entrada |
| `consumo` | salida |
| `merma` | salida |
| `ajuste_entrada` | entrada |
| `ajuste_salida` | salida |
| `reversion_consumo` | entrada |
| `reversion_merma` | entrada |
| `reversion_entrada` | salida |

**No** incluidos aún: traslado, préstamo, retorno, recuento, baja, rectificación documental.

### Idempotencia

```text
{origen_tipo}:{origen_id}:{origen_linea_id}:{lote_id}:{tipo}
```

Ejemplo: `registro_servicio:reg001:detalle003:lot004:consumo`

Duplicado → rechazo controlado / devolución del movimiento existente (`duplicado=True`).

### Inmutabilidad

El servicio **no** expone edición ni eliminación. Solo listar, buscar, validar, crear (API interna).

## 4. Relación con lote y origen

- Un consumo repartido entre varios lotes → **un movimiento por lote** (cuando se active dual-write).
- `origen_*` enlaza registro operativo (compra/lote, registro, merma, ajuste, anulación).
- `movimiento_revertido_id` enlaza el movimiento original en reversiones.

## 5. Compatibilidad histórica

- JSON sin clave `movimientos` → lista vacía.
- Enums desconocidos se **conservan como string** y generan incidencia; **no** se remapean.
- No se generan movimientos al cargar.
- Campos 6A / 6B / 6C y espacios F5 intactos.

## 6. Reconciliación informativa (7A.1)

Consultas de solo lectura:

- total entradas / salidas por lote;
- saldo teórico ledger = entradas − salidas;
- comparación con `cantidad_restante`.

**No** corrige lotes, **no** bloquea la app, **no** sustituye el saldo real.  
Mientras no haya dual-write completo, la diferencia histórica es esperable.

## 7. Subfases futuras (documentadas, no implementadas)

### 7A.2 — Dual-write entradas y ajustes (**hecha**)

Escribe movimiento espejo al:

- crear lote / entrada actual → `entrada_compra`;
- ajuste positivo → `ajuste_entrada`;
- ajuste negativo → `ajuste_salida`.

Helpers: `espejo_entrada_lote`, `espejo_ajuste_linea` en `movimiento_service`.  
Atomicidad: fallo del espejo revierte lote/ajuste. Sin backfill.

### 7A.3 — Dual-write merma (**hecha**)

- merma → `merma` (salida) por línea;
- anulación → `reversion_merma` (entrada); histórico sin original → `anulacion_merma_historica`.

### 7A.4 — Dual-write consumos y anulaciones de registro (siguiente)

- consumos → un `consumo` por fragmento de `consumos_lote`;
- anulaciones de registros → `reversion_consumo` por fragmento exacto.

Tras 7A.4: reconciliación, tests, checklist, **STOP**.

**7B** (ledger como fuente de verdad / stock por ubicación / traslados): **no diseñar como implementación** hasta cerrar 7A y condiciones explícitas.

## 8. Condiciones antes de plantear ledger como fuente de verdad

1. Dual-write estable en entradas, ajustes, mermas, consumos y anulaciones.
2. Reconciliación operativa sin divergencias sistemáticas en datos nuevos.
3. Política clara para histórico pre-ledger (nunca backfill silencioso).
4. Decisión explícita de producto + periodo de convivencia.
5. Tests de invariantes stock(lote) = Σ firmados post-activación.
6. Plan de rollback que **no** recalcule lotes borrando movimientos a mano.

## 9. Fuera de alcance de 7A.1

- escritura espejo desde operaciones;
- stock por ubicación, traslados, préstamos, retornos, recuentos;
- documentos / albaranes / facturas / proveedores;
- cambios en FIFO, lotes, consumo, merma, ajustes, anulaciones;
- ledger como fuente de verdad;
- reconstrucción histórica.

## 10. Diseño conceptual ampliado (F2, referencia)

El diseño F2 original (documentos, traslados, stock por ubicación, tipos futuros) permanece como horizonte en las secciones históricas del repositorio; la implementación avanza solo por subfases 7A.x aprobadas.
