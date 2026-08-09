# Checklist manual Streamlit — cierre pre-Flet

Usar datos temporales / copia aislada. **Nunca** confirmar contra el demo canónico de producción compartida sin aislamiento.

## A. Conversiones / compras
1. Vínculo 1 Caja = 6 L
2. Compra 2 cajas → preview 12 L
3. Coste total y unitario base coherentes
4. Bloqueo sin factor si unidades distintas

## B. Productos
1. Crear / buscar / editar / stock mínimo
2. Desactivar / reactivar
3. Bloqueo cambio unidad con histórico

## C. Recetas
1. Crear con 2 ingredientes; coste total y por ración
2. Quitar ingrediente (nombre visible)
3. Desactivar → no aparece en registros nuevos; histórico legible

## D. Registro
1. Desayuno: receta + producto + bebida; editar/quitar; filtros sin perder cesta
2. Comida / Cena / Bebidas independientes
3. Confirmar; stock; movimientos; doble confirmación no duplica
4. Rol Restaurante sin €; Admin/Dirección con €

## E. Merma / caducidad / ajustes
1. Merma por servicio + general
2. Caducidad: listar vencidos/próximos → encolar Expiración → confirmar en Merma
3. Ajuste positivo/negativo; corrección = nuevo ajuste compensatorio

## F. Historial
1. Registros → Historial: filtros y detalle
2. Anular desde módulo origen; comprobar reposición

## G. Analítica
1. Dashboard mes; costes por servicio; bebidas transversal ≠ 5ª categoría

## H. Terminales / auth
1. Terminal Restaurante
2. Terminal Inventario (sin €)
3. Deep-link bloqueado por rol

## I. Continuidad
1. Backup → cambio → restore → hashes

Marcar cada ítem: OK / Fallo / N/A.
