# Preparación de persistencia (SQLite) — Fase 18

**Estado:** documento de diseño. **No implementar** en esta fase.  
La aplicación sigue en JSON (`data/demo/datos_hotel.json`). Sin cambiar el arranque en Render ni el `streamlit run` actual.

---

## 1. Resumen del modelo actual (JSON)

Fuente de verdad en memoria: `AppData` (`app/core/models/app_data.py`), serializado por `app/data/serializers.py`, cargado/guardado vía `session_store` → `demo_files.DEMO_FILE`.

| Colección | Entidad principal | Rol |
|-----------|-------------------|-----|
| `productos` | `Producto` | Catálogo (unidad, mínimo, `es_bebida`, `servicios_disponibles`, categoría inventario) |
| `lotes` | `LoteStock` | Compras / stock por lote FIFO; soft-anulación compra |
| `recetas` | `Receta` + `IngredienteReceta` | Catálogo recetas + porciones estándar |
| `desayunos` | `RegistroDesayuno` | Consumo desayuno (stack legacy) |
| `registros_servicio` | `RegistroServicio` | Comida / cena / bebidas |
| `mermas` | `RegistroMerma` + `LineaMerma` | Merma / expiración |
| `ajustes` | `RegistroAjuste` + `LineaAjuste` | Ajustes de inventario |
| `alertas` / `alertas_descartadas` | `AlertaOperativa` + firmas | Alertas + workflow / descartes |
| `actividades` | `Actividad` | Auditoría operativa |
| `usuarios` | `Usuario` | Operadores |
| `responsables_merma` | `ResponsableMerma` | Catálogo merma |
| `configuracion` | `ConfiguracionHotel` | Establecimiento / moneda / logo / **ledger_*** (7B) |
| `proveedores` | `Proveedor` | Maestro comercial (Fase 8) |
| `impuestos` | `Impuesto` | % Decimal versionado (Fase 8) |
| `relaciones_producto_proveedor` | `RelacionProductoProveedor` | Vínculo + snapshots (Fase 8) |
| meta | `usuario_actual_id` | Sesión lógica |

---

## 2. Relaciones e IDs

- IDs string con prefijos (`p…`, `l…`, `r…`, `d…`, `rs…`, `m…`, `a…`, `act…`). Generación en servicios (`_next_id`), no secuencias DB hoy.
- **Producto ← Lote** (`lote.producto_id`)
- **Receta ← Ingredientes** (`ingrediente.producto_id`)
- **Registro → líneas detalle** (`LineaDetalleOrigen`) + **consumos_lote** (`ConsumoLoteDetalle`: `lote_id`, cantidad, coste)
- **Merma línea →** `producto_id`, `lote_id` (opcional), snapshots servicio/turno/responsable
- **Ajuste →** lote concreto
- Soft-delete: flags `anulado*` en registros servicio/desayuno, merma y lotes (compra); no borrar filas históricas

Regla de migración: **conservar IDs string** como PK / UNIQUE para no romper exportaciones ni firmas de alerta.

---

## 3. Snapshots e histórico a conservar (inmutable)

Campos aditivos; ausencia = histórico incompleto (UI advierte; **prohibido backfill** masivo).

| Ámbito | Campos críticos |
|--------|-----------------|
| Detalle consumo | `lineas_detalle`, costes por línea, `es_bebida_snapshot`, `categoria_receta_snapshot`, `consumos_lote` |
| Receta en registro | `factor_aplicado`, porciones, nombres snapshot |
| Merma | `tipo_servicio_snapshot`, `turno_snapshot`, `responsable_*`, `producto_nombre_snapshot`, `unidad_snapshot` |
| Compra / lote | precio, fechas, `cantidad` vs `cantidad_restante`, flags anulación |
| Alertas | `estado`, `lote_id`, firmas en `alertas_descartadas` |
| Actividad | fecha_hora, usuario, acción, detalle, módulo |

Cualquier esquema SQLite debe permitir **NULL** en snapshots opcionales y no reinterpretar NULL como valor por defecto de negocio (p. ej. lista vacía ≠ todos en `servicios_disponibles`).

---

## 4. Movimientos de stock (lógica a portar, no tablas inventadas)

Hoy el stock es **derivado** de `lotes.cantidad_restante` + eventos:

1. Compra → crea lote  
2. Consumo (desayuno/servicio) → FIFO + `consumos_lote`  
3. Merma → descuenta lote (con `lote_id` en línea)  
4. Ajuste → cambia restante con trazabilidad  
5. Anulación registro/merma → repone según trazabilidad; sin trazabilidad → bloqueo  
6. Anulación compra → solo si lote intacto y sin dependencias activas  

En SQLite conviene:

- Tabla `lotes` + opcionalmente `movimientos_stock` (append-only) **o** seguir recalculando restante en transacción única como ahora.
- Transacciones ACID por operación de registro/anulación (hoy: un `persist_data` = rewrite JSON completo).

---

## 5. Índices sugeridos (futuro)

| Uso | Índice |
|-----|--------|
| Stock por producto | `(producto_id)` en lotes; filtro `anulado` / `cantidad_restante > 0` |
| Registros por fecha/servicio | `(fecha)`, `(tipo_servicio, fecha)` |
| Detalle / consumos | `(registro_id)`, `(lote_id)`, `(producto_id)` |
| Merma | `(fecha)`, `(producto_id)`, `(lote_id)` |
| Alertas | `(activa, estado)`, `(tipo, producto_id)` |
| Actividad | `(fecha_hora DESC)` |

---

## 6. Migración JSON → SQLite (pasos, sin ejecutar)

1. Congelar versión app; backup de `datos_hotel.json` (+ exports meta).  
2. Definir DDL 1:1 con serializers (tipos: TEXT fechas ISO, REAL cantidades, INTEGER bool).  
3. Script de importación de **una sola pasada** leyendo el JSON actual (sin reescribir histórico).  
4. Validar conteos: productos, lotes, registros, suma `coste_total`, stock por producto.  
5. Dual-read opcional (feature flag) → luego write SQLite only.  
6. Rollback = restaurar JSON + flag.

**No** migrar inventando `consumos_lote` ni snapshots ausentes.

---

## 7. Backups

| Ahora | Futuro SQLite |
|-------|----------------|
| Copia del JSON + carpeta `exports/` | Dump `.sqlite` + JSON de contingencia las primeras semanas |
| Riesgo: escritura no atómica histórica mitigada parcialmente | Usar backup antes de migrar; WAL mode; no sustituir Render start sin plan |

Recomendación operativa: backup diario del archivo de datos en el host (Render disk / volumen) antes de cualquier cambio de storage.

---

## 8. Riesgos en Render

- Disco efímero vs disco persistente: el JSON actual **debe** vivir en volumen persistente; igual para SQLite.  
- Varias réplicas: JSON/SQLite local **no** es multi-instancia; hace falta sticky session o DB gestionada.  
- Arranque: **no cambiar** el comando `streamlit run app/main.py` en esta fase.  
- Cold start + carga completa del JSON en memoria: SQLite permitirá consultas, pero la app Streamlit sigue siendo proceso único.  
- Logo / paths relativos: mantener rutas bajo el mismo root de datos.

---

## 9. Fuera de alcance (aplazado)

- Implementar SQLite / ORM / migraciones Alembic  
- Cambiar `session_store` o `DEMO_FILE`  
- Login / multi-tenant / Postgres  
- Fusionar stacks desayuno vs `registros_servicio`  
- Rehacer analítica sobre SQL  
- Cambiar IDs a UUID/autoincrement  

---

## 10. Criterio de cierre de este documento

- Entidades, relaciones, snapshots, movimientos, índices, migración, backups y riesgos Render descritos.  
- App permanece en JSON.  
- Sin código de persistencia nueva en Fase 18.

**Siguiente trabajo (futuro, fuera de este plan de estabilización):** RFC de implementación SQLite con spike de lectura dual y checklist de conteos.
