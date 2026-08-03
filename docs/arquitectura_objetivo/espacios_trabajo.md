# Espacios de trabajo (Fase 5 — implementado)

**Estado:** implementado en navegación Streamlit.  
**Alcance F5:** solo filtra la navegación visible. No cambia JSON, AppData, modelos, servicios de dominio, FIFO ni serializers.

## Selector

Nombre: **Espacio de trabajo** (`st.session_state["bm_espacio_trabajo"]`).

Opciones (ids estables en `app/core/application/espacios.py`):

| Id | Etiqueta | Secciones operativas |
|----|----------|----------------------|
| `registro` | Registro | Registros |
| `gestor` | Gestor (**predeterminado**) | Dashboard, Análisis |
| `inventario` | Inventario | Stock, Recetas |

## Configuración (global, no es un cuarto espacio)

- **Configuración es global y provisionalmente visible** en esta fase.
- Aparece en el bloque «Global» del sidebar, separada de la navegación operativa.
- Si el usuario está en Configuración y cambia el espacio: **permanece en Configuración**; el nuevo espacio queda seleccionado para cuando abandone Configuración.
- Un deep-link a Configuración **conserva el espacio actual**.

## Matriz de navegación (F5)

| Espacio | Secciones |
|---------|-----------|
| Registro | Registros |
| Gestor | Dashboard, Análisis |
| Inventario | Stock, Recetas |
| Global | Configuración |

## Persistencia

- Solo `st.session_state` (clave `bm_espacio_trabajo`).
- **No** se guarda en AppData, JSON, ni vía `persist_data` / serializers.

## Seguridad y límites explícitos

- El selector **no concede permisos**.
- La seguridad real (login, roles, ocultación) se implementará en la **Fase 16**.
- F5 **no oculta** todavía precios ni información económica dentro de las páginas.
- La **terminal de restaurante** no se implementa en esta fase.

## Deep-links

Sigue usándose `nav_section_pending` (etiquetas de menú). La lógica pura en `espacios.py` resuelve espacio + sección **antes** de instanciar widgets; como máximo un `st.rerun()` (p. ej. botón Configuración).

## Contenido previsto a futuro (no F5)

### Registro

- Desayuno, comida, cena, bebidas, mermas; orientación a velocidad.

### Gestor

- Dashboard, costes, alertas, informes, auditoría.

### Inventario

- Catálogos, compras/documentos, lotes, stock, recetas, movimientos.

## Terminal de restaurante (futuro, fuera de F5)

- Modo Registro fijado y restringido; mismo backend; sin precios ni configuración sensible.
