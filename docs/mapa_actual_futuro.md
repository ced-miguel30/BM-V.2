# Mapa modelo actual → modelo futuro

Fuente actual: `AppData` + JSON `data/demo/datos_hotel.json`.  
Futuro: dominio documentado en [modelo_dominio_objetivo.md](modelo_dominio_objetivo.md).

## Tabla de correspondencia

| Actual (código) | Futuro (concepto) | Estrategia |
|-----------------|-------------------|------------|
| `Producto` | Producto maestro | Ampliar campos aditivos; no renombrar a la ligera |
| `categoria_inventario` | Texto histórico / libre | **Conservar tal cual**; no sustituye `categoria_id` |
| `categoria_id` / `subcategoria_id` | Categoría / Subcategoría | **Fase 6A hecha** — opcional; sin backfill |
| `departamento_ids` | Departamentos de uso | **Fase 6A hecha** — N:M; **no** es ubicación ni stock |
| `ubicacion_ids` | Ubicaciones permitidas/habituales | **Fase 6B hecha** — N:M; **sin** cantidades ni stock por ubicación |
| `servicios_disponibles` | Servicios disponibles | Conservar semántica vacío ≠ todos |
| `es_bebida` | Atributo / tipo o flag | Conservar; no sustituir por adivinanza |
| `LoteStock` | Lote | Ampliar enlace a documento/entrada; soft-anulación ya existe |
| `marca_proveedor` | Snapshot texto proveedor | Conservar; Proveedor maestro en F8 |
| `Receta` / `IngredienteReceta` | Receta | Mantener; escalado ya existe |
| `RegistroDesayuno` | Registro consumo (desayuno) | Convivencia; unificación opcional posterior |
| `RegistroServicio` | Registro consumo | Mantener stack |
| `LineaDetalleOrigen` | Detalle de consumo | Mantener |
| `ConsumoLoteDetalle` | Traza FIFO / base de movimiento consumo | Mantener; ledger F7 la refleja |
| `RegistroMerma` / `LineaMerma` | Merma + snapshots | Mantener; generar movimientos en F7 |
| `RegistroAjuste` / `LineaAjuste` | Ajuste | Mantener |
| `AlertaOperativa` | Alerta operativa | Mantener workflow estados |
| `Actividad` | Auditoría | Ampliar |
| `Usuario` / `RolUsuario` | Usuario / Rol / Permiso | Hoy Owner/Admin sin password → F16 |
| `ResponsableMerma` | Catálogo merma | Mantener |
| `ConfiguracionHotel` | Config establecimiento | Mantener |
| `alertas_descartadas` | Preferencias / firmas | Mantener o migrar a estado alerta |
| `Departamento`, `Categoria`, `Subcategoria` | Catálogos estructurados | **Fase 6A completada** |
| `Ubicacion` | Maestro de ubicaciones | **Fase 6B completada** (catálogo + vínculo producto) |
| *(no existe)* | Stock cuantitativo por ubicación | **Aplazado (P02 → F7)** |
| *(no existe)* | Tipo de artículo | **F6C (siguiente)** |
| *(no existe)* | Proveedor, Impuesto, producto–proveedor | **F8 (única)** |
| *(no existe)* | Movimiento (ledger) | Diseño F2; código F7 |
| *(no existe)* | Documento, Archivo, Albarán, Factura, Rectificativa | F9–F12 |
| *(no existe)* | Terminal, sesión auth | F16–F19 |
| Compra = crear lote en Stock | Entrada vía albarán/factura | Transición F10–F11; dual durante convivencia |
| Stock = Σ `cantidad_restante` | Stock reconciliable con ledger | Dual-write F7 → fuente de verdad tras reconciliar |
| JSON + Streamlit session | PostgreSQL + API + auth | F3–F4, F14, F15, F16 |

## Dimensiones 6A / 6B (resumen)

| Concepto | Significado |
|----------|-------------|
| Departamento | Ámbito operativo de **uso** del producto. **No** lugar físico ni cantidad. |
| Ubicación | Lugar identificable donde puede **existir** inventario (Economato, Cámara…). |
| `ubicacion_ids` | Ubicaciones permitidas/habituales del producto. **No** cantidad, **no** ubicación actual del lote. |
| Categoría / Subcategoría | Clasificación estructurada; independiente de `categoria_inventario`. |
| Stock hotel | Sigue siendo Σ `cantidad_restante` de lotes. |

Pendiente futuro: jerarquía de ubicaciones y tipos (cámara / almacén / bar, etc.).

## Flujos críticos: hoy vs mañana

| Flujo | Hoy | Mañana |
|-------|-----|--------|
| Entrada mercancía | UI Compras → `LoteStock` | Albarán confirmado → lotes + movimientos |
| Consumo | FIFO + `consumos_lote` | Igual + movimiento `consumo` |
| Anulación registro | Soft + reposición traza | Soft + movimiento `reverso` |
| Factura | No existe | Conciliación sin re-entrada de stock |
| Multi-ubicación | Maestro + vínculo producto (6B); sin cantidades | Traslados + stock por ubicación (F7+) |

## Persistencia

| Hoy | Transición | Objetivo |
|-----|------------|----------|
| `session_store` + JSON rewrite | Adaptador JSON (F3) | PostgreSQL (F14A–D) |
| Doc SQLite diseño antiguo | Solo dev opcional | **PostgreSQL** operativo multiusuario |

Ver también: [preparacion_persistencia_sqlite.md](preparacion_persistencia_sqlite.md) (histórico de diseño; el plan maestro prioriza PostgreSQL).

## Próximo paso

**Fase 6C** — tipos de artículo + reglas iniciales consumible/reutilizable (tras aprobación de 6B).
