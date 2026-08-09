"""Workbench de caducidad — listados y cola hacia cesta de merma (Expiración)."""

from __future__ import annotations

import streamlit as st

from app.core.auth.permissions import Permiso
from app.core.auth.session import session_tiene_permiso
from app.core.services import caducidad_service as cad
from app.core.services import merma_service as merma
from app.core.services.formatting import formato_fecha
from app.core.services.unidad_service import formato_number_input, paso_unidad
from app.ui.components import empty_state, page_header, section_divider


def render_caducidad_workbench(*, mostrar_cabecera: bool = True) -> None:
    if mostrar_cabecera:
        page_header(
            "Caducidad",
            "Lotes vencidos y próximos; la salida confirmada usa Merma (motivo Expiración).",
        )

    st.caption(
        "No existe una entidad Caducidad separada. "
        "Registrar salida añade líneas a la cesta de merma con motivo Expiración; "
        "confirme luego en Registros → Merma."
    )

    vencidos = cad.listar_lotes_caducidad(incluir_proximos=False, incluir_vencidos=True)
    proximos = cad.listar_lotes_caducidad(incluir_proximos=True, incluir_vencidos=False)

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Lotes vencidos con stock", len(vencidos))
    with col_b:
        st.metric("Próximos a vencer", len(proximos))

    section_divider()
    _tabla_lotes("Vencidos", vencidos, key_prefix="cad_venc")
    section_divider()
    _tabla_lotes("Próximos a vencer", proximos, key_prefix="cad_prox")

    section_divider()
    st.markdown("#### Encolar salida por caducidad")
    todos = vencidos + proximos
    if not todos:
        empty_state("No hay lotes caducados ni próximos con stock.", icon="✅")
        return

    responsables = merma.listar_responsables_merma()
    if not responsables:
        st.warning("Configure al menos un responsable de merma en Configuración.")
        return

    mapa_lotes = {
        f"{ln.nombre_producto} · lote {ln.lote_id} · "
        f"{ln.cantidad_restante:g} {ln.unidad} · "
        f"cad. {formato_fecha(ln.fecha_expiracion)} ({ln.estado})": ln
        for ln in todos
    }
    sel = st.selectbox("Lote", list(mapa_lotes.keys()), key="cad_sel_lote")
    lote = mapa_lotes[sel]

    col1, col2, col3 = st.columns(3)
    with col1:
        servicio_ui = st.selectbox(
            "Ámbito",
            merma.OPCIONES_SERVICIO_UI,
            key="cad_servicio",
        )
    with col2:
        turno_ui = st.selectbox(
            "Turno",
            merma.OPCIONES_TURNO_UI,
            key="cad_turno",
        )
    with col3:
        mapa_resp = {r.nombre: r for r in responsables}
        resp_nombre = st.selectbox(
            "Responsable",
            list(mapa_resp.keys()),
            key="cad_resp",
        )
    resp = mapa_resp[resp_nombre]

    cantidad = st.number_input(
        f"Cantidad ({lote.unidad})",
        min_value=0.0,
        max_value=float(lote.cantidad_restante),
        value=float(lote.cantidad_restante),
        step=paso_unidad(lote.unidad),
        format=formato_number_input(lote.unidad),
        key=f"cad_cant_{lote.lote_id}",
    )
    comentario = st.text_input("Comentario", value="Salida por caducidad", key="cad_com")

    ver_costes = session_tiene_permiso(Permiso.CONSULTAR_COSTES)
    if ver_costes:
        est = merma.calcular_coste_lote(lote.lote_id, cantidad)
        st.caption(f"Coste estimado: {est:.2f} €")

    confirma = st.checkbox(
        "Confirmo encolar esta salida en la cesta de merma (Expiración)",
        key="cad_ok",
    )
    if st.button(
        "Añadir a cesta de merma",
        type="primary",
        disabled=not confirma or cantidad <= 0,
        key="cad_btn",
    ):
        svc = merma.valor_servicio_desde_ui(servicio_ui)
        turno = merma.valor_turno_desde_ui(turno_ui)
        if not svc or not turno:
            st.error("Seleccione ámbito y turno válidos.")
            return
        r = cad.registrar_salida_caducidad(
            lote.lote_id,
            float(cantidad),
            tipo_servicio_snapshot=svc,
            turno_snapshot=turno,
            responsable_id=resp.id,
            responsable_nombre=resp.nombre,
            comentario=comentario,
        )
        if r.ok:
            st.success(
                f"{r.mensaje} Confirme la merma en Registros → Merma "
                f"({len(merma.get_cesta_merma())} línea(s) en cesta)."
            )
        else:
            st.error(r.mensaje)


def _tabla_lotes(titulo: str, lineas, *, key_prefix: str) -> None:
    st.markdown(f"##### {titulo}")
    if not lineas:
        st.caption("Ninguno.")
        return
    st.dataframe(
        {
            "Producto": [ln.nombre_producto for ln in lineas],
            "Lote": [ln.lote_id for ln in lineas],
            "Restante": [f"{ln.cantidad_restante:g} {ln.unidad}" for ln in lineas],
            "Caducidad": [formato_fecha(ln.fecha_expiracion) for ln in lineas],
            "Días": [ln.dias_restantes for ln in lineas],
            "Estado": [ln.estado for ln in lineas],
        },
        use_container_width=True,
        hide_index=True,
        key=f"{key_prefix}_df",
    )
