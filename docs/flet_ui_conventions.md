# Convenciones de interfaz Flet (BM‑V.2)

## Sistema de diseño

- Tokens: `app/presentation/flet/theme.py` (navy / teal / dorado discreto).
- Componentes: `app/presentation/flet/ui_components.py`.
- Gráficos: `app/presentation/flet/charts.py` (colores del tema).

## Arquitectura de presentación

```text
Vista Flet → callbacks → presenter → servicios → dominio
```

Las vistas no calculan costes ni tocan JSON.

## Dashboard

- Builder: `dashboard_builder.build_dashboard_panel`.
- VM anidado: `DashboardPanelVM` (valores económicos ya formateados).
- Visible en Administración → Inicio cuando hay `CONSULTAR_COSTES`.

## Navegación Admin

Grupos en `ADMIN_NAV_GROUPS`: Resumen, Operación, Catálogos, Administración.

## Paneles alineados al kit

Usar `page_header`, `card_surface`, `metric_card`, `status_chip`, `empty_state`,
`alert_banner` y botones del kit en: Inicio, Análisis, Productos, Recetas,
Usuarios, Responsables, Proveedores, Compras, Documentos, Inventario,
Configuración y Servidor.
