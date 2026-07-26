"""Renderer genérico de página de registro de servicio (desayuno/comida/cena/bebidas)."""

from __future__ import annotations

from datetime import date, datetime, time

import streamlit as st

from app.core.models import CategoriaReceta
from app.core.services.data_service import get_repository
from app.core.services.exportacion_semanal_service import limite_semana
from app.core.services.formatting import formato_fecha
from app.core.services.receta_service import listar_recetas
from app.core.services.unidad_service import (
    formato_number_input,
    normalizar_cantidad,
    paso_unidad,
)
from app.ui.cesta_render import boton_exportar_semana, render_cesta_servicio
from app.ui.components import aviso_servicios_pendientes, empty_state, page_header, section_divider
from app.ui.search import render_buscador_producto

PASO_CANTIDAD = 1.0  # Compat; inputs usan paso_unidad().


def _lunes_semana_actual() -> date:
    lunes, _ = limite_semana(date.today())
    return lunes


def _render_detalle(servicio, registro) -> None:
    hasta = datetime.combine(registro.fecha, time.max)
    registros = [
        r for r in servicio.registros_exportables(registro.fecha, hasta)
        if r.identificador == registro.id
    ]
    if not registros:
        return
    reg = registros[0]
    hora_txt = reg.hora.strftime("%H:%M") if reg.hora else "—"
    st.caption(f"Nº {reg.identificador} · Hora {hora_txt} · {reg.usuario or '—'}")
    idx_tipo = reg.columnas.index("Tipo") if "Tipo" in reg.columnas else None
    idx_detalle = reg.columnas.index("Detalle") if "Detalle" in reg.columnas else None
    idx_coste = reg.columnas.index("Coste") if "Coste" in reg.columnas else None
    if idx_tipo is not None and idx_detalle is not None:
        factores = [
            fila[idx_detalle]
            for fila in reg.filas
            if fila[idx_tipo] == "Receta" and fila[idx_detalle]
        ]
        if factores:
            st.caption("Escalado: " + " · ".join(str(f) for f in factores))
    if idx_coste is not None:
        costes = []
        for fila in reg.filas:
            raw = fila[idx_coste]
            if raw in ("", None):
                continue
            try:
                costes.append(float(raw))
            except (TypeError, ValueError):
                continue
        if costes:
            st.caption(
                f"Coste líneas de detalle: "
                f"{get_repository().formato_precio(sum(costes))}"
            )
    st.dataframe(
        {col: [fila[i] for fila in reg.filas] for i, col in enumerate(reg.columnas)},
        use_container_width=True,
        hide_index=True,
    )
    if reg.resumen:
        st.caption(" · ".join(f"{clave}: {valor}" for clave, valor in reg.resumen))


def render_pagina_registro_servicio(
    servicio,
    *,
    titulo_pagina: str,
    subtitulo: str,
    etiqueta: str,
    key_prefix: str,
    categorias_receta: list[CategoriaReceta],
    mensaje_vacio_historial: str,
    mostrar_huespedes: bool = False,
    mostrar_cabecera: bool = True,
    min_huespedes: int = 0,
    default_huespedes: int = 0,
) -> None:
    """Página completa de registro + historial + exportación para un tipo."""
    _ = categorias_receta  # Conservado por compat; el filtro activo es servicios_disponibles.
    repo = get_repository()
    stock_key = f"bm_stock_pendiente_{key_prefix}"

    if mostrar_cabecera:
        page_header(titulo_pagina, subtitulo)

    st.markdown(f"#### Registro rápido de {etiqueta.lower()}")
    st.caption(
        "Patrón: fecha → receta o producto directo → cantidad → cesta → confirmar. "
        "Cantidades positivas (c/ extra) o negativas (s/) ajustan ingredientes."
    )
    aviso_servicios_pendientes(key_prefix=f"{key_prefix}_aviso_serv")

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        fecha = st.date_input(
            "Fecha", value=date.today(), max_value=date.today(), key=f"{key_prefix}_fecha",
        )
        num_huespedes = 0
        if mostrar_huespedes:
            num_huespedes = int(st.number_input(
                "Nº de huéspedes",
                min_value=min_huespedes,
                value=max(default_huespedes, min_huespedes),
                step=1,
                key=f"{key_prefix}_num_huespedes",
            ))

        section_divider()
        st.markdown(
            '##### Añadir receta '
            '<span class="bm-cesta-tipo">Receta</span>',
            unsafe_allow_html=True,
        )
        recetas = listar_recetas(servicio_disponible=servicio.tipo_servicio)
        if recetas:
            mapa_recetas = {r.nombre: r.id for r in recetas}
            receta_nombre = st.selectbox(
                "Receta",
                list(mapa_recetas.keys()),
                key=f"{key_prefix}_sel_receta",
            )
            receta_id = mapa_recetas[receta_nombre]
            receta_obj = next(r for r in recetas if r.id == receta_id)
            default_porciones = float(receta_obj.porciones_estandar or 0) or 1.0
            if receta_obj.porciones_estandar:
                st.caption(
                    f"Porciones estándar: {receta_obj.porciones_estandar:g}. "
                    "El factor será porciones pedidas ÷ estándar (igual que el simulador)."
                )
            else:
                st.warning(
                    "Esta receta no tiene porciones estándar. "
                    "Configúrela en Recetas antes de añadirla a la cesta."
                )

            porciones = st.number_input(
                "Porciones a preparar",
                min_value=0.0,
                value=default_porciones,
                step=1.0,
                format="%.0f",
                key=f"{key_prefix}_porciones_{receta_id}",
                help="Rendimiento deseado. Factor = pedidas / estándar.",
            )
            if receta_obj.porciones_estandar and porciones > 0:
                factor_prev = porciones / receta_obj.porciones_estandar
                st.caption(f"Factor previsto: {factor_prev:g}")

            st.caption("Extras u omisiones para esta receta (antes de añadir a la cesta)")
            catalogo = servicio.productos_catalogo("")
            producto_mod = render_buscador_producto(
                catalogo,
                f"{key_prefix}_mod_receta",
                label="Buscar producto",
                placeholder="Escriba para buscar producto...",
            )
            if producto_mod:
                unidad_mod = producto_mod.get("unidad", "Ud")
                cant_mod = st.number_input(
                    "Cantidad (+ extra / − omitir)",
                    value=float(paso_unidad(unidad_mod)),
                    step=paso_unidad(unidad_mod),
                    format=formato_number_input(unidad_mod),
                    key=f"{key_prefix}_cant_mod",
                )
                cant_mod = normalizar_cantidad(cant_mod, unidad_mod)
                if st.button(
                    "Añadir extra/omisión",
                    key=f"{key_prefix}_btn_mod",
                    use_container_width=True,
                ):
                    resultado = servicio.anadir_mod_pendiente_receta(producto_mod["id"], cant_mod)
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)

            mods = servicio.get_mods_pendientes()
            if mods:
                st.markdown("**Pendientes para esta receta:**")
                for mod in mods:
                    col_txt, col_q = st.columns([5, 1])
                    etiqueta_mod = f"c/ extra {mod.nombre}" if mod.cantidad > 0 else f"s/ {mod.nombre}"
                    with col_txt:
                        st.markdown(f"- {etiqueta_mod} — {abs(mod.cantidad):g} {mod.unidad}")
                    with col_q:
                        if st.button("✕", key=f"{key_prefix}_quitar_mod_{mod.mod_id}"):
                            servicio.quitar_mod_pendiente(mod.mod_id)
                            st.rerun()

            if st.button(
                "Añadir receta a la cesta",
                type="secondary",
                use_container_width=True,
                key=f"{key_prefix}_btn_receta",
            ):
                resultado = servicio.anadir_receta_a_cesta(receta_id, porciones, list(mods))
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        else:
            empty_state(
                "No hay recetas con este servicio disponible. "
                "Configúrelas en Recetas (servicios disponibles).",
                icon="📖",
            )

        section_divider()
        st.markdown(
            '##### Añadir producto suelto '
            '<span class="bm-cesta-tipo">Producto directo</span>',
            unsafe_allow_html=True,
        )
        todos_productos = servicio.productos_catalogo("")
        producto_sel = render_buscador_producto(
            todos_productos,
            key_prefix,
            label="Buscar producto",
            placeholder="Escriba el nombre del producto...",
        )
        if producto_sel:
            unidad_prod = producto_sel.get("unidad", "Ud")
            cantidad = st.number_input(
                "Cantidad (+ extra / − omitir)",
                value=float(paso_unidad(unidad_prod)),
                step=paso_unidad(unidad_prod),
                format=formato_number_input(unidad_prod),
                key=f"{key_prefix}_cantidad",
            )
            cantidad = normalizar_cantidad(cantidad, unidad_prod)
            if st.button(
                "Añadir producto a la cesta",
                type="secondary",
                use_container_width=True,
                key=f"{key_prefix}_btn_anadir",
            ):
                resultado = servicio.anadir_a_cesta(producto_sel["id"], cantidad)
                if resultado.ok:
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)
        elif todos_productos:
            empty_state("No hay coincidencias para la búsqueda.", icon="🔍")
        else:
            empty_state(
                "No hay productos con este servicio disponible. "
                "Configúrelos en Stock (servicios disponibles).",
                icon="🔍",
            )

    with col_cesta:
        render_cesta_servicio(
            servicio,
            repo,
            titulo_cesta=etiqueta,
            key_prefix=key_prefix,
            vacio_mensaje=f"Todavía no has añadido productos a {etiqueta.lower()}.",
        )

        if st.button(
            f"Registrar {etiqueta.lower()}",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_btn_registrar",
        ):
            resultado = servicio.registrar(fecha, num_huespedes)
            if resultado.ok:
                st.session_state.pop(stock_key, None)
                st.success(resultado.mensaje)
                st.rerun()
            elif resultado.codigo == "STOCK_INSUFICIENTE":
                st.session_state[stock_key] = True
                st.error(resultado.mensaje)
                if resultado.detalle_stock:
                    for linea in resultado.detalle_stock:
                        st.markdown(f"- {linea}")
            else:
                st.session_state.pop(stock_key, None)
                st.error(resultado.mensaje)

        if st.session_state.get(stock_key):
            st.warning("Hay productos sin stock suficiente. Puede ignorar la validación y registrar igual.")
            if st.button(
                "Ignorar y registrar igual",
                type="secondary",
                use_container_width=True,
                key=f"{key_prefix}_btn_ignorar_stock",
            ):
                resultado = servicio.registrar(fecha, num_huespedes, ignorar_stock=True)
                if resultado.ok:
                    st.session_state.pop(stock_key, None)
                    st.success(resultado.mensaje)
                    st.rerun()
                else:
                    st.error(resultado.mensaje)

    section_divider()
    st.markdown(f"#### Historial de {etiqueta.lower()}")
    st.caption(
        "Solo se muestran los registros de la semana en curso. "
        "Las semanas anteriores quedan archivadas y disponibles en las exportaciones."
    )
    boton_exportar_semana(servicio.configuracion_exportacion(), key_prefix)

    registros = servicio.historial_ordenado()
    registros_semana = [r for r in registros if r.fecha >= _lunes_semana_actual()]
    if registros_semana:
        columnas = {
            "Fecha": [formato_fecha(r.fecha) for r in registros_semana],
            "Hora": [r.hora.strftime("%H:%M") if r.hora else "—" for r in registros_semana],
        }
        if mostrar_huespedes:
            columnas["Huéspedes"] = [
                getattr(r, "num_huespedes", 0) for r in registros_semana
            ]
        columnas.update({
            "Elementos": [len(r.lineas) + len(r.registros_recetas) for r in registros_semana],
            "Cantidad total": [
                round(sum(abs(l.cantidad) for l in r.lineas), 2) for r in registros_semana
            ],
            "Coste": [repo.formato_precio(r.coste_total) for r in registros_semana],
            "Registrado por": [r.registrado_por for r in registros_semana],
        })
        st.dataframe(columnas, use_container_width=True, hide_index=True)

        opciones_detalle = {
            f"{r.id} — {formato_fecha(r.fecha)} {r.hora.strftime('%H:%M') if r.hora else ''}".strip(): r
            for r in registros_semana
        }
        etiqueta_sel = st.selectbox(
            "Ver detalle de un registro",
            ["—"] + list(opciones_detalle.keys()),
            key=f"{key_prefix}_detalle_sel",
        )
        if etiqueta_sel != "—":
            _render_detalle(servicio, opciones_detalle[etiqueta_sel])
    else:
        empty_state(mensaje_vacio_historial, icon="📅")
