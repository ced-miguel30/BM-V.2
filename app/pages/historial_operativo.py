"""Historial operativo unificado (consulta + detalle)."""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from app.core.auth.permissions import Permiso
from app.core.auth.session import session_tiene_permiso
from app.core.services import historial_operativo_service as hist
from app.core.services.formatting import formato_fecha
from app.core.services.data_service import get_repository
from app.ui.components import empty_state, page_header, section_divider


def render(*, mostrar_cabecera: bool = True) -> None:
    if mostrar_cabecera:
        page_header(
            "Historial operativo",
            "Consulta unificada de registros, merma y ajustes. "
            "Anulación solo donde el dominio la soporta.",
        )

    ver_costes = session_tiene_permiso(Permiso.CONSULTAR_COSTES)
    hoy = date.today()
    col_f1, col_f2, col_f3, col_f4 = st.columns(4)
    with col_f1:
        desde = st.date_input("Desde", value=hoy - timedelta(days=14), key="hist_desde")
    with col_f2:
        hasta = st.date_input("Hasta", value=hoy, key="hist_hasta")
    with col_f3:
        tipo = st.selectbox(
            "Tipo",
            ["Todos", "Desayuno", "Registro servicio", "Merma", "Ajuste"],
            key="hist_tipo",
        )
    with col_f4:
        servicio = st.text_input("Servicio (opcional)", key="hist_serv")

    busqueda = st.text_input("Buscar id / responsable / texto", key="hist_q")
    solo_activos = st.checkbox("Solo activos", value=False, key="hist_activos")

    mapa_tipo = {
        "Todos": None,
        "Desayuno": hist.TIPO_DESAYUNO,
        "Registro servicio": hist.TIPO_SERVICIO,
        "Merma": hist.TIPO_MERMA,
        "Ajuste": hist.TIPO_AJUSTE,
    }
    eventos = hist.listar_eventos_operativos(
        desde=desde,
        hasta=hasta,
        tipo=mapa_tipo[tipo],
        servicio=(servicio or "").strip() or None,
        solo_activos=solo_activos,
        busqueda=busqueda,
    )

    if not eventos:
        empty_state("Sin eventos en el rango.", icon="📋")
        return

    filas = {
        "Fecha": [formato_fecha(e.fecha) for e in eventos],
        "Hora": [e.hora.strftime("%H:%M") if e.hora else "—" for e in eventos],
        "Tipo": [e.tipo for e in eventos],
        "Id": [e.id for e in eventos],
        "Servicio": [e.servicio for e in eventos],
        "Resumen": [e.resumen for e in eventos],
        "Estado": [e.estado for e in eventos],
        "Responsable": [e.responsable for e in eventos],
    }
    if ver_costes:
        filas["Coste"] = [
            get_repository().formato_precio(e.coste) if e.coste is not None else "—"
            for e in eventos
        ]
    st.dataframe(filas, use_container_width=True, hide_index=True)

    section_divider()
    opciones = {
        f"{e.tipo}:{e.id} — {formato_fecha(e.fecha)} · {e.resumen}": e
        for e in eventos
    }
    sel = st.selectbox("Detalle", ["—"] + list(opciones.keys()), key="hist_det")
    if sel == "—":
        return
    ev = opciones[sel]
    det = hist.detalle_evento(ev.tipo, ev.id)
    if not det:
        st.error("Evento no encontrado.")
        return

    st.json({k: str(v) for k, v in det.items() if k not in ("lineas", "recetas")})
    if det.get("lineas"):
        st.dataframe(det["lineas"], use_container_width=True, hide_index=True)
    if det.get("recetas"):
        st.dataframe(det["recetas"], use_container_width=True, hide_index=True)

    st.info(f"Corrección: {det.get('correccion', '—')}")
    if det.get("puede_anular"):
        st.caption(
            "Para anular use el detalle del módulo origen "
            "(Registros → historial del servicio, o Merma)."
        )
    elif ev.tipo == hist.TIPO_AJUSTE:
        st.warning(
            "Los ajustes no admiten soft-anulación. "
            "Corrija con un ajuste compensatorio en Stock → Inventario."
        )
