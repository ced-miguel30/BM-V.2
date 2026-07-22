"""Helpers visuales compartidos para cestas de registro de servicio."""

from __future__ import annotations

import unicodedata
from datetime import datetime

import streamlit as st

from app.core.services.cesta_service import (
    cantidad_texto_linea_receta,
    etiqueta_linea_receta,
    etiqueta_linea_suelta,
)
from app.core.services.exportacion_semanal_service import exportar_semana_actual


def clave_orden(texto: str) -> str:
    """Clave de orden alfabético insensible a mayúsculas/minúsculas y acentos."""
    normalizado = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in normalizado if not unicodedata.combining(c))
    return sin_acentos.casefold()


def ok_o_error(resultado) -> None:
    if resultado.ok:
        st.rerun()
    else:
        st.error(resultado.mensaje)


def quitar_y_rerun(accion, *args) -> None:
    accion(*args)
    st.rerun()


def boton_exportar_semana(config, key_prefix: str) -> None:
    """Exportación manual: lunes 00:00 de la semana actual → ahora."""
    col_btn, _ = st.columns([1, 2])
    with col_btn:
        if st.button("Exportar semana actual", use_container_width=True, key=f"{key_prefix}_exportar_semana"):
            resultado = exportar_semana_actual(config, datetime.now())
            if resultado.ok:
                st.session_state[f"{key_prefix}_export_dl"] = (
                    resultado.ruta.read_bytes(), resultado.nombre_archivo,
                )
                st.success(f"{resultado.mensaje}")
            else:
                st.error(resultado.mensaje)

    dl = st.session_state.get(f"{key_prefix}_export_dl")
    if dl:
        contenido, nombre = dl
        st.download_button(
            "Descargar Excel",
            data=contenido,
            file_name=nombre,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"{key_prefix}_export_dl_btn",
        )


def fila_cesta(
    nombre_html: str,
    key_prefix: str,
    on_quitar,
    *,
    cantidad_texto: str | None = None,
    on_menos=None,
    on_mas=None,
    ayuda_quitar: str = "Eliminar",
) -> None:
    """Fila uniforme de cesta: nombre + (− cantidad +) + eliminar, o solo eliminar."""
    if cantidad_texto is not None:
        col_nombre, col_menos, col_qty, col_mas, col_quitar = st.columns(
            [5, 1, 1, 1, 1], vertical_alignment="center",
        )
        with col_nombre:
            st.markdown(nombre_html, unsafe_allow_html=True)
        with col_menos:
            if st.button("−", key=f"{key_prefix}_menos", use_container_width=True, help="Disminuir"):
                on_menos()
        with col_qty:
            st.markdown(f'<div class="bm-cesta-qty">{cantidad_texto}</div>', unsafe_allow_html=True)
        with col_mas:
            if st.button("+", key=f"{key_prefix}_mas", use_container_width=True, help="Aumentar"):
                on_mas()
        with col_quitar:
            if st.button(
                "",
                key=f"{key_prefix}_quitar",
                icon=":material/delete:",
                help=ayuda_quitar,
                use_container_width=True,
            ):
                on_quitar()
    else:
        col_nombre, col_quitar = st.columns([8, 1], vertical_alignment="center")
        with col_nombre:
            st.markdown(nombre_html, unsafe_allow_html=True)
        with col_quitar:
            if st.button(
                "",
                key=f"{key_prefix}_quitar",
                icon=":material/delete:",
                help=ayuda_quitar,
                use_container_width=True,
            ):
                on_quitar()


def render_cesta_servicio(
    servicio,
    repo,
    *,
    titulo_cesta: str,
    key_prefix: str,
    vacio_mensaje: str,
) -> None:
    """Panel de desglose compartido (recetas indentadas + productos sueltos)."""
    grupos = servicio.get_cesta_recetas()
    cesta = servicio.get_cesta()
    hay_contenido = bool(grupos or cesta)

    with st.container(border=True):
        st.markdown(
            f'<div class="bm-cesta-scope"></div>'
            f'<div class="bm-cesta-title">{titulo_cesta}</div>',
            unsafe_allow_html=True,
        )

        if not hay_contenido:
            st.markdown(
                f'<p class="bm-cesta-empty">{vacio_mensaje}</p>',
                unsafe_allow_html=True,
            )
            return

        elementos = [("receta", g) for g in grupos] + [("suelto", l) for l in cesta]
        elementos.sort(
            key=lambda e: clave_orden(e[1].nombre_receta if e[0] == "receta" else e[1].nombre)
        )

        for indice, (tipo, elemento) in enumerate(elementos):
            if indice > 0:
                st.markdown('<div class="bm-cesta-divider"></div>', unsafe_allow_html=True)

            if tipo == "receta":
                grupo = elemento
                fila_cesta(
                    f'<div class="bm-cesta-nombre">{grupo.nombre_receta}</div>',
                    f"{key_prefix}_grp_{grupo.grupo_id}",
                    lambda g=grupo: quitar_y_rerun(servicio.quitar_grupo_receta, g.grupo_id),
                    cantidad_texto=f"{grupo.porciones:g}",
                    on_menos=lambda g=grupo: ok_o_error(servicio.ajustar_porciones_grupo(g.grupo_id, -1)),
                    on_mas=lambda g=grupo: ok_o_error(
                        servicio.modificar_porciones_grupo(g.grupo_id, g.porciones + 1)
                    ),
                    ayuda_quitar="Eliminar receta",
                )
                for ing in grupo.ingredientes:
                    paso = servicio.paso_linea_grupo(grupo.grupo_id, ing.linea_id)
                    fila_cesta(
                        f'<div class="bm-cesta-detalle">{etiqueta_linea_receta(ing)}</div>',
                        f"{key_prefix}_ing_{grupo.grupo_id}_{ing.linea_id}",
                        lambda g=grupo, i=ing: quitar_y_rerun(
                            servicio.quitar_linea_grupo, g.grupo_id, i.linea_id
                        ),
                        cantidad_texto=cantidad_texto_linea_receta(ing),
                        on_menos=lambda g=grupo, i=ing, p=paso: ok_o_error(
                            servicio.ajustar_linea_grupo(g.grupo_id, i.linea_id, -p)
                        ),
                        on_mas=lambda g=grupo, i=ing, p=paso: ok_o_error(
                            servicio.ajustar_linea_grupo(g.grupo_id, i.linea_id, p)
                        ),
                        ayuda_quitar="Eliminar ingrediente",
                    )
            else:
                linea = elemento
                paso = servicio.paso_linea_suelta(linea.linea_id)
                fila_cesta(
                    f'<div class="bm-cesta-nombre">{etiqueta_linea_suelta(linea)}</div>',
                    f"{key_prefix}_suelto_{linea.linea_id}",
                    lambda l=linea: quitar_y_rerun(servicio.quitar_linea_suelta, l.linea_id),
                    cantidad_texto=f"{abs(linea.cantidad):g}",
                    on_menos=lambda l=linea, p=paso: ok_o_error(
                        servicio.ajustar_cantidad_suelto(l.linea_id, -p)
                    ),
                    on_mas=lambda l=linea, p=paso: ok_o_error(
                        servicio.ajustar_cantidad_suelto(l.linea_id, p)
                    ),
                    ayuda_quitar="Eliminar producto",
                )

        total = servicio.coste_total_cesta()
        st.markdown(
            '<div class="bm-cesta-total">'
            "<span>Coste estimado</span>"
            f"<span>{repo.formato_precio(total)}</span>"
            "</div>",
            unsafe_allow_html=True,
        )
        st.caption("Coste calculado por FIFO según lotes actuales.")

        if st.button("Vaciar cesta", use_container_width=True, key=f"{key_prefix}_vaciar_cesta"):
            servicio.limpiar_cesta()
            st.rerun()
