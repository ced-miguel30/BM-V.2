# Espacios de trabajo (diseño — Fase 2)

**No implementado.** La integración real es **Fase 5** (tras frontera de aplicación estable).  
Prototipo aislado opcional: no cablear a `main`/sidebar productiva en esta fase.

## Selector

Nombre preferente: **Espacio de trabajo**.

Opciones:

| Opción | Rol |
|--------|-----|
| Registro | Operación diaria rápida |
| Gestor | Dashboard, análisis, alertas, informes, auditoría |
| Inventario | Catálogos, compras, documentos, stock, movimientos |
| Configuración | Usuarios, hotel, diagnósticos (según permisos) |
| Cerrar sesión | Cuando exista autenticación real (Fase 16) |

El selector cambia la **navegación visible**, no la base de datos.

## Contenido previsto por modo

### Registro

- Desayuno, comida, cena, bebidas
- Consumos directos / salidas
- Mermas
- Consumos de otros departamentos (futuro)
- Orientado a velocidad; sin pantallas de compra/factura

### Gestor

- Dashboard operativo
- Costes, consumos, mermas, comparativas
- Costes por servicio / departamento (cuando exista depto)
- Alertas, predicciones, informes, exportaciones, auditoría

### Inventario

- Productos, categorías, subcategorías, departamentos
- Ubicaciones, tipos de artículo
- Proveedores, impuestos (Fase 8+)
- Compras / albaranes / facturas / archivos
- Lotes, stock, recetas, ajustes, mermas, movimientos, traslados, recuentos

## Matriz provisional de visibilidad

Hasta Fase 16, la matriz es **orientativa** (no seguridad):

| Capacidad | Registro | Gestor | Inventario | Config |
|-----------|----------|--------|------------|--------|
| Registrar consumo/merma | Sí | Lectura/enlace | Lectura | — |
| Ver costes/precios | No (terminal) / limitado | Sí | Sí | — |
| Compras / documentos | No | Resumen | Sí | — |
| Crear producto | No | No | Sí* | — |
| Usuarios / impuestos | No | No | Parcial* | Sí* |

\* Solo Dirección/Administración cuando existan permisos reales.

## Terminal de restaurante (futuro)

- Modo Registro fijado y restringido
- Mismo backend y catálogo
- Sin precios, compras ni configuración sensible
