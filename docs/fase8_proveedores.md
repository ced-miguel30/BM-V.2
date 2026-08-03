# Fase 8 — Proveedores e impuestos

**Estado:** implementada en código. **Sin facturas ni albaranes.**

## Alcance

| Pieza | Estado |
|-------|--------|
| `Proveedor` | Hecho |
| `Impuesto` (`Decimal`) | Hecho |
| `RelacionProductoProveedor` + snapshots | Hecho |
| Soft-delete (activo/inactivo) | Hecho |
| UI Configuración → Proveedores e impuestos | Hecho |
| Conservar `marca_proveedor` en lotes | Hecho (no se reescribe) |
| Albarán / factura / conciliación | **Fuera** (F9+) |

## Persistencia

Colecciones aditivas en JSON: `proveedores`, `impuestos`, `relaciones_producto_proveedor`.  
JSON antiguo sin claves → listas vacías.

## Versión

`BM-V.2 · Ledger · Proveedores e impuestos`
