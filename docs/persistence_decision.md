# Decisión de persistencia (sin implementar sustitución)

## Estado actual

- Fuente operativa: `AppData` en memoria + JSON (`data/demo/datos_hotel.json` o override de test).
- Acceso: `AppDataStore` del composition root (`FileBacked` / `Streamlit` / `Memory`).
- Atomicidad fichero: `json_atomic` / aislamiento demo en tests.
- Adjuntos documentales: filesystem + SHA-256.

## Riesgos multi-terminal con JSON

- Varios escritores concurrentes sobre el mismo fichero → pérdida de actualizaciones / corrupción.
- Streamlit multi-sesión en un solo proceso mitiga en parte; varios procesos (varios `.exe`) no.

## Alternativas (evaluación futura)

| Opción | Pros | Contras |
|--------|------|---------|
| SQLite local | Transacciones, un fichero, migración controlada | Diseño de esquema; backup distinto |
| API + PostgreSQL | Multi-terminal real, hotel centralizado | Infra, auth red, operación |
| Un solo servidor + clients thin | Compatible Flet/Streamlit | Requiere proceso servidor |

## Criterios de decisión (hotel)

1. ¿Cuántos dispositivos escriben a la vez?
2. ¿Se acepta un PC “servidor” permanente?
3. ¿Backup offline obligatorio diario?
4. ¿SLA ante corte de red?

## Recomendación provisional

- Corto plazo: **JSON + un proceso servidor** (Streamlit hoy; Flet o API mañana).
- Medio plazo si >1 escritor real: **SQLite embebido** o **API+SQLite/Postgres**.
- **No implementar** el cambio en esta preparación arquitectónica.

Ver también `docs/preparacion_persistencia_sqlite.md`.
