# Pre-Flet readiness — BM-V.2 Streamlit closure

Documento de cierre técnico antes de la fase Flet. **No implementa Flet.**

## Estado de referencia

- Rama: `main`
- Persistencia: JSON (`data/demo/datos_hotel.json` canónico protegido) + adjuntos
- UI: Streamlit (`app/main.py`, `app/pages/*`, `app/ui/*`)
- Dominio: `app/core/services/*` + modelos + serialización

## Arquitectura funcional actual

```
UI Streamlit → servicios de dominio → AppData / UoW → serializers JSON
                 ↘ inventory_batch (FIFO) → movimientos
```

Una sola fuente de verdad por regla: UI no debe recalcular costes ni FIFO.

## Módulos reutilizables (independientes de Streamlit)

- Inventario / FIFO: `inventory_batch_service`, `inventory_ops`
- Registro: `desayuno_service`, `servicio_registro_service`, `cesta_service`
- Merma / caducidad vía merma: `merma_service`, `caducidad_service`
- Histórico unificado (lectura): `historial_operativo_service`
- Analítica: `analitica_consumo_service`, `costes_service`, `dashboard_service`
- Compras: `compra_registro_service`, `conversion_compra`, documentos
- Auth: `app/core/auth/*` (permisos, sesión, usecase_guard)
- Backup/restore: `backup_service`, `restore_backup_service`

## Dependencias directas de Streamlit

- `st.session_state` en cestas (`cesta_service`, merma), navegación, auth flag `bm_force_hide_costes`
- Páginas en `app/pages/*` y helpers `app/ui/*`
- Terminales: `terminal_restaurante`, `terminal_inventario`

## session_state relevante

| Clave / prefijo | Uso |
|-----------------|-----|
| `bm_auth_session` | Sesión auth |
| `bm_cesta_*` / motor cesta | Cestas por servicio |
| `bm_cesta_merma` | Cesta merma |
| `nav_section*` / `bm_espacio_trabajo` | Navegación |
| `bm_force_hide_costes` | Terminal Inventario oculta economía |
| `*_clave_idempotencia` | Anti doble confirmación registro |

## Decisiones de dominio cerradas (Streamlit)

- **Otros consumos** = `PRODUCTO_DIRECTO` dentro del servicio activo (no 5ª categoría).
- **Caducidad** = workbench sobre merma + `MotivoMerma.EXPIRACION` (sin entidad nueva).
- **Ajustes** = corrección mediante ajuste compensatorio (sin soft-anulación).
- **coste_general** = Desayuno + Comida + Cena + Bebidas independientes.
- Bebidas transversales = métrica aparte; no sumar otra vez a `coste_general`.

## Servicios que requieren extracción mañana (Flet)

1. Quitar `import streamlit` de `cesta_service` / merma cesta (inyectar store).
2. Extraer tokens de idempotencia y flags de UI a capa de aplicación.
3. Adaptadores de terminal / navegación sin Streamlit widgets.
4. Decidir JSON vs SQLite vs API para multi-terminal concurrente.

## Riesgos de concurrencia JSON

- Un fichero demo/producción compartido no es seguro con varios escritores.
- Estrategia recomendada: un proceso servidor + API o SQLite con transacciones; terminales thin-client.

## Matriz pantallas Streamlit → futura Flet

| Streamlit | Flet piloto sugerido |
|-----------|----------------------|
| Terminal Restaurante / Registros | Pantalla piloto registro |
| Terminal Inventario / Caducidad | Inventario móvil |
| Stock Compras 13.5 | Desktop compras |
| Dashboard / Análisis | Desktop gestoría |
| Configuración / Backup | Admin |

## Orden recomendado de migración

1. Desacoplar cestas y session_state del dominio.
2. Decidir persistencia.
3. Arquitectura Flet + pantalla piloto Registro.
4. Migrar por módulos (Registros → Inventario → Compras → Analítica → Settings).
5. Empaquetado `.exe` e instalación hotel.

## Deuda explícita (no hoy)

- Importación CSV/Excel de catálogo.
- Módulo Recepción completo.
- Soft-anulación de ajustes.
- Historial UI de semanas antiguas (hoy: semana + export).
- Revisión manual Streamlit con navegador (checklist aparte).

## Checklist puesta en marcha (hotel)

1. Crear usuario Dirección (bootstrap).
2. Configurar hotel / moneda / categorías / ubicaciones.
3. Crear responsables de merma.
4. Importar o crear productos y stock inicial.
5. Proveedores + vínculos de conversión.
6. Recetas activas con servicios.
7. Probar compra con conversión.
8. Probar registros Desayuno/Comida/Cena/Bebidas.
9. Probar merma y caducidad.
10. Probar dashboard / costes (rol autorizado).
11. Backup inicial verificado.
12. Terminal Restaurante + Terminal Inventario validados en tablet.

## Criterio para retirar Streamlit

- Paridad funcional Flet en flujos críticos.
- Persistencia multi-terminal segura.
- Backup/restore equivalentes.
- Suite de tests verde sobre el mismo dominio.
- Periodo de coexistencia documentado.

## Criterios para empezar mañana

- Este documento leído.
- `main` verde y demo intacto.
- No abrir Flet hasta completar desacoplamiento de `session_state` en cestas.
