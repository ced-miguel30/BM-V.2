# Checklist manual Streamlit — regresión post-preparación arquitectónica

Usar **copia / almacenamiento temporal**. Nunca confirmar contra el demo canónico compartido sin aislamiento.

Para cada prueba: marcar **OK / FALLO / OBSERVACIÓN**.

---

## Plantilla de fila

| Campo | Contenido |
|-------|-----------|
| Rol | |
| Datos | |
| Pasos | |
| Esperado | |
| Riesgo | |
| Resultado | OK / FALLO / OBSERVACIÓN |

---

## 1. Identidad

| ID | Rol | Datos | Pasos | Esperado | Riesgo |
|----|-----|-------|-------|----------|--------|
| L1 | — | usuarios demo | Login correcto | Entra al espacio adecuado | Auth |
| L2 | — | credencial mala | Login | Mensaje genérico, sin sesión | Auth |
| L3 | cualquiera | sesión activa | Logout | Tokens peligro/nav limpios | Auth |
| L4 | Dirección | — | Acceso total menú | Todas las secciones | Permisos |
| L5 | Administración | — | Menú | Sin restore/destructivo dirección | Matriz |
| L6 | Restaurante | — | App | Solo registro; sin € | Economía |
| L7 | Terminal Restaurante | botón terminal | Entrar | UI terminal registros | Terminal |
| L8 | Terminal Inventario | botón terminal | Entrar | Stock/caducidad; sin €/config | Terminal |

## 2. Catálogo

| ID | Rol | Pasos | Esperado | Riesgo |
|----|-----|-------|----------|--------|
| P1 | Admin | CRUD producto | Persistido tras reinicio | Persistencia |
| P2 | Admin | Desactivar producto | No en registros nuevos; histórico legible | Lifecycle |
| R1 | Admin | CRUD receta 2 ings | Coste/ración coherente | Coste |
| R2 | Admin | Desactivar receta | Fuera de catálogo activo | Filtros |

## 3. Compras / conversión

| ID | Rol | Pasos | Esperado | Riesgo |
|----|-----|-------|----------|--------|
| C1 | Admin | Vínculo 1 caja=6 L; compra 2 cajas | Preview 12 L; lote OK | Conversión |
| C2 | Admin | Sin factor, unidades distintas | Bloqueo | Validación |

## 4. Inventario

| ID | Rol | Pasos | Esperado | Riesgo |
|----|-----|-------|----------|--------|
| I1 | Admin | Ajuste +/− | Stock y movimientos | Ajustes |
| I2 | Admin | Corregir ajuste | Nuevo ajuste compensatorio | Compensatorio |
| I3 | Admin | Traslado / recuento | Saldos coherentes | Ledger |
| I4 | Term Inv | Caducidad → merma EXPIRACIÓN → confirmar | Stock baja solo al confirmar | Caducidad |

## 5. Registros

| ID | Rol | Pasos | Esperado | Riesgo |
|----|-----|-------|----------|--------|
| D1 | Rest. | Desayuno receta+producto+bebida | Confirmación sin € en mensaje | UX/perm |
| D2 | Admin | Mismo + coste | Mensaje con coste | Permisos |
| D3 | Admin | Comida / Cena / Bebidas ind. | Buckets correctos | Multi-servicio |
| D4 | Admin | Producto directo («otros») | En bucket del servicio | PRODUCTO_DIRECTO |
| D5 | Admin | Doble clic confirmar | Una sola persistencia | Idempotencia |
| D6 | Admin | Anular desde módulo | Soft + reposición lotes | Anulación |

## 6. Merma / historial / analítica

| ID | Rol | Pasos | Esperado | Riesgo |
|----|-----|-------|----------|--------|
| M1 | Admin | Merma servicio+general | Coste merma | Merma |
| H1 | Admin | Historial filtros+detalle | Eventos visibles | Consulta |
| A1 | Admin | Dashboard mes | coste_general = 4 buckets | Reconciliación |
| A2 | Rest. | Intentar ver costes | Denegado / sin datos € | Auth use case |

## 7. Documentos / continuidad

| ID | Rol | Pasos | Esperado | Riesgo |
|----|-----|-------|----------|--------|
| Doc1 | Admin | Adjunto + consulta | SHA / archivo | Docs |
| B1 | Dirección | Backup ZIP | Descarga OK | Backup |
| B2 | Dirección | Restore en temporal | Hashes coherentes | Restore |
| N1 | Admin | Deep-link sección no permitida | Remap + aviso | Nav |

## 8. Persistencia / UX

| ID | Rol | Pasos | Esperado | Riesgo |
|----|-----|-------|----------|--------|
| X1 | Admin | Confirmar → reiniciar Streamlit | Datos siguen | AppDataStore |
| X2 | Admin | Estados vacíos / errores | Mensajes claros | UX |
| X3 | Admin | Exportación / búsqueda | Archivos en exports | Export |

---

Fin del checklist. Tras marcar todo OK: validación manual completa.
