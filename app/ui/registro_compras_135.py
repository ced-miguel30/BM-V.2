"""UI B4 — Registro de compras Fase 13.5 (solo servicios productivos).

No crea lotes/movimientos ni calcula conversiones/costes en la UI.
Confirmación → compra_registro_service; anulación/devolución → anulacion_compra_service.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import streamlit as st

from app.core.models import EstadoDocumento, TipoDocumento
from app.core.services import anulacion_documento_service as anul
from app.core.services import compra_registro_service as compra
from app.core.services.data_service import get_repository
from app.core.storage.session_store import get_demo_path, reload_from_disk
from app.ui.components import section_divider


def _json_path():
    return get_demo_path()


def _token_key(documento_id: str) -> str:
    return f"reg135_confirmacion_id:{documento_id}"


def _ensure_token(documento_id: str) -> str:
    key = _token_key(documento_id)
    if key not in st.session_state:
        st.session_state[key] = str(uuid.uuid4())
    return st.session_state[key]


def _estado_val(doc) -> str:
    e = doc.estado
    return e.value if hasattr(e, "value") else str(e)


def _tipo_val(doc) -> str:
    t = doc.tipo
    return t.value if hasattr(t, "value") else str(t)


def render_registro_compras_135() -> None:
    """Pestaña B4: borrador → resumen → confirmar / anular / devolver."""
    repo = get_repository()
    data = repo.data
    path = _json_path()

    st.markdown("#### Registro de compras (13.5)")
    st.caption(
        "Borrador SoT en JSON. Confirmación vía `compra_registro_service` "
        "(lock A2 + hash + UUID). La UI no crea lotes ni movimientos."
    )

    modo = st.radio(
        "Operación",
        [
            "Nuevo / editar borrador",
            "Confirmar borrador",
            "Anular / devolver / rectificar",
            "Consultar",
        ],
        horizontal=True,
        key="reg135_modo",
    )

    if modo == "Nuevo / editar borrador":
        _ui_borrador(data, path)
    elif modo == "Confirmar borrador":
        _ui_confirmar(data, path)
    elif modo == "Anular / devolver / rectificar":
        _ui_reversiones(data, path)
    else:
        _ui_consultar(data)


def _ui_borrador(data, path) -> None:
    proveedores = [p for p in data.proveedores if getattr(p, "activo", True)]
    mapa_prov = {f"{p.nombre_fiscal} [{p.codigo or '—'}] ({p.id})": p.id for p in proveedores}
    productos = list(data.productos)
    mapa_prod = {
        f"{p.nombre} [{getattr(p, 'codigo', None) or '—'}] ({p.id})": p for p in productos
    }

    borradores = [
        d
        for d in data.documentos
        if _estado_val(d) == EstadoDocumento.BORRADOR.value
        and _tipo_val(d) in (
            TipoDocumento.ALBARAN.value,
            TipoDocumento.FACTURA.value,
        )
    ]
    mapa_edit = {"— Nuevo documento —": None}
    mapa_edit.update(
        {
            f"{d.id} · {_tipo_val(d)} · ref={d.referencia_externa or '—'}": d.id
            for d in borradores
        }
    )

    with st.form("reg135_borrador", clear_on_submit=False):
        edit_lbl = st.selectbox("Documento", list(mapa_edit.keys()))
        tipo = st.selectbox("Tipo", ["albaran", "factura"])
        prov_lbl = st.selectbox("Proveedor", list(mapa_prov.keys()) or ["—"])
        ref = st.text_input("Referencia externa")
        notas = st.text_area("Observaciones / notas", height=68)
        dto_cab = st.number_input(
            "Descuento cabecera (€)", min_value=0.0, step=0.01, format="%.2f"
        )
        st.markdown("##### Línea de compra")
        c1, c2, c3 = st.columns(3)
        with c1:
            prod_lbl = st.selectbox("Producto", list(mapa_prod.keys()) or ["—"])
            qty = st.number_input("Cantidad compra", min_value=0.0, step=0.1, value=1.0)
            unidad_compra = st.text_input("Unidad compra", value="Ud")
        with c2:
            precio = st.number_input(
                "Precio unitario compra", min_value=0.0, step=0.01, format="%.4f"
            )
            factor = st.number_input(
                "Factor → inventario (1 si misma unidad)",
                min_value=0.0,
                step=0.1,
                value=1.0,
            )
            unidad_inv = st.text_input("Unidad inventario", value="Ud")
        with c3:
            dto_pct = st.number_input("Dto. línea %", min_value=0.0, step=0.1, value=0.0)
            dto_imp = st.number_input(
                "Dto. línea €", min_value=0.0, step=0.01, format="%.2f", value=0.0
            )
            igic = st.number_input("IGIC %", min_value=0.0, step=0.1, value=7.0)
            incluye_igic = st.checkbox("Precio incluye IGIC")
        conc_alb = st.text_input(
            "Conciliación: id línea albarán (solo factura vinculada; vacío = directa)",
            value="",
        )
        submitted = st.form_submit_button("Guardar borrador", type="primary")

    if submitted:
        if not mapa_prov or not mapa_prod:
            st.error("Se requieren proveedor y producto en catálogo.")
            return
        prod = mapa_prod[prod_lbl]
        lineas = [
            {
                "producto_id": prod.id,
                "client_line_key": st.session_state.get(
                    "reg135_line_key", str(uuid.uuid4())
                ),
                "cantidad_compra": str(qty),
                "unidad_compra": unidad_compra or "Ud",
                "unidad_inventario": unidad_inv
                or (
                    prod.unidad.value
                    if hasattr(prod.unidad, "value")
                    else str(prod.unidad)
                ),
                "factor_conversion": str(factor) if factor > 0 else None,
                "precio_unitario_compra": str(precio),
                "precio_incluye_igic": incluye_igic,
                "descuento_porcentaje": str(dto_pct),
                "descuento_importe": str(dto_imp),
                "impuesto_porcentaje": str(igic),
            }
        ]
        st.session_state["reg135_line_key"] = lineas[0]["client_line_key"]
        if conc_alb.strip():
            st.session_state["reg135_conc"] = [
                {
                    "linea_factura_client_key": lineas[0]["client_line_key"],
                    "linea_albaran_id": conc_alb.strip(),
                    "cantidad_conciliada": str(
                        Decimal(str(qty)) * Decimal(str(factor or 1))
                    ),
                }
            ]
        else:
            st.session_state.pop("reg135_conc", None)

        r = compra.guardar_borrador_persistente(
            json_path=path,
            tipo=tipo,
            proveedor_id=mapa_prov[prov_lbl],
            referencia_externa=ref or None,
            notas=notas or None,
            descuento_cabecera_importe=dto_cab,
            lineas=lineas,
            documento_id=mapa_edit[edit_lbl],
            fecha_documento=date.today(),
        )
        if r.ok:
            reload_from_disk()
            st.success(r.mensaje)
            if r.alerta_precio:
                for a in r.alerta_precio:
                    st.warning(a)
            st.rerun()
        else:
            st.error(r.mensaje)


def _ui_confirmar(data, path) -> None:
    borradores = [
        d
        for d in data.documentos
        if _estado_val(d) == EstadoDocumento.BORRADOR.value
    ]
    if not borradores:
        st.info("No hay borradores para confirmar.")
        return

    mapa = {
        f"{d.id} · {_tipo_val(d)} · {d.proveedor_nombre_snapshot or '—'} · "
        f"ref={d.referencia_externa or '—'} · {len(d.lineas)} línea(s)": d
        for d in borradores
    }
    sel = st.selectbox("Borrador", list(mapa.keys()), key="reg135_conf_sel")
    doc = mapa[sel]
    token = _ensure_token(doc.id)
    conc = st.session_state.get("reg135_conc")
    h = compra.construir_hash_documento(doc, conc)

    st.markdown("##### Resumen antes de confirmar")
    st.write(
        {
            "id": doc.id,
            "tipo": _tipo_val(doc),
            "proveedor": doc.proveedor_nombre_snapshot,
            "referencia": doc.referencia_externa,
            "base": str(doc.base_imponible),
            "impuesto": str(doc.impuesto_total),
            "total": str(doc.total_documento),
            "contenido_hash": h[:16] + "…",
            "confirmacion_id": token,
            "conciliaciones": conc or [],
            "líneas": [
                {
                    "producto": ln.producto_id,
                    "qty_compra": str(ln.cantidad_compra),
                    "unidad": ln.unidad_compra,
                    "factor": str(ln.factor_conversion),
                    "qty_inv": str(ln.cantidad_inventario),
                    "precio": str(ln.precio_unitario_compra),
                    "base": str(ln.base_imponible),
                    "igic": str(ln.cuota_impuesto),
                    "coste_inv": str(ln.coste_inventariable_linea),
                }
                for ln in doc.lineas
            ],
        }
    )

    uploaded = st.file_uploader(
        "Adjuntos (opcionales; se publican en la misma confirmación)",
        accept_multiple_files=True,
        key=f"reg135_up_{doc.id}",
    )

    c1, c2 = st.columns(2)
    with c1:
        confirmar = st.button("Confirmar compra", type="primary", key="reg135_btn_conf")
    with c2:
        if st.button("Nueva clave idempotente", key="reg135_new_token"):
            st.session_state[_token_key(doc.id)] = str(uuid.uuid4())
            st.rerun()

    if confirmar:
        adjuntos = None
        if uploaded:
            adjuntos = [
                compra.AdjuntoEntrada(
                    contenido=f.getvalue(),
                    nombre_original=f.name,
                    mime_type=getattr(f, "type", None),
                )
                for f in uploaded
            ]
        res = compra.confirmar_compra(
            doc.id,
            confirmacion_id=token,
            contenido_hash=h,
            json_path=path,
            conciliaciones_propuestas=conc,
            adjuntos=adjuntos,
        )
        if res.ok:
            reload_from_disk()
            msg = res.mensaje
            if res.codigo == compra.CONFIRMACION_IDEMPOTENTE:
                st.info(msg + " (idempotente: sin doble stock)")
            else:
                st.success(msg)
            if getattr(res, "adjuntos_estado", None) and res.adjuntos_estado != "ok":
                st.warning(
                    f"Adjuntos en estado «{res.adjuntos_estado}» "
                    "(JSON y binario no son atómicos)."
                )
            st.session_state.pop("reg135_conc", None)
            st.rerun()
        else:
            st.error(f"{res.mensaje} [{res.codigo}]")


def _ui_reversiones(data, path) -> None:
    confirmados = [
        d
        for d in data.documentos
        if _estado_val(d) == EstadoDocumento.CONFIRMADO.value
        and _tipo_val(d)
        in (
            TipoDocumento.ALBARAN.value,
            TipoDocumento.FACTURA.value,
        )
    ]
    if not confirmados:
        st.info("No hay documentos confirmados.")
        return

    mapa = {
        f"{d.id} · {_tipo_val(d)} · ref={d.referencia_externa or '—'} · "
        f"impacto_stock={d.impacto_stock}": d
        for d in confirmados
    }
    sel = st.selectbox("Documento", list(mapa.keys()), key="reg135_rev_sel")
    doc = mapa[sel]
    motivo = st.text_input("Motivo", key="reg135_motivo")
    accion = st.radio(
        "Acción",
        ["Anular documento", "Devolución parcial", "Rectificativa económica"],
        key="reg135_accion",
    )

    if accion == "Anular documento":
        if st.button("Anular", type="primary", key="reg135_anular"):
            r = anul.anular_documento_confirmado(
                doc.id, motivo=motivo or "", json_path=path
            )
            if r.ok:
                reload_from_disk()
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)

    elif accion == "Devolución parcial":
        lotes = anul.lotes_de_documento(data, doc.id)
        if not lotes:
            st.warning("Sin lotes trazables para devolución.")
            return
        mapa_l = {
            f"{l.id} · rest={l.cantidad_restante:g}/{l.cantidad:g}": l for l in lotes
        }
        lote_lbl = st.selectbox("Lote", list(mapa_l.keys()))
        qty = st.number_input("Cantidad a devolver", min_value=0.0, step=0.1)
        if "reg135_dev_token" not in st.session_state:
            st.session_state["reg135_dev_token"] = str(uuid.uuid4())
        st.caption(f"Idempotency: {st.session_state['reg135_dev_token']}")
        if st.button("Registrar devolución", type="primary", key="reg135_dev"):
            r = anul.registrar_devolucion(
                documento_origen_id=doc.id,
                lineas=[{"lote_id": mapa_l[lote_lbl].id, "cantidad": qty}],
                json_path=path,
                motivo=motivo or "Devolución",
                confirmacion_id=st.session_state["reg135_dev_token"],
            )
            if r.ok:
                reload_from_disk()
                st.session_state["reg135_dev_token"] = str(uuid.uuid4())
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)

    else:
        if st.button("Emitir rectificativa económica", type="primary", key="reg135_rect"):
            r = anul.registrar_rectificativa_economica(
                documento_rectificado_id=doc.id,
                motivo=motivo or "",
                json_path=path,
                confirmacion_id=str(uuid.uuid4()),
            )
            if r.ok:
                reload_from_disk()
                st.success(r.mensaje)
                st.rerun()
            else:
                st.error(r.mensaje)


def _ui_consultar(data) -> None:
    section_divider()
    docs = sorted(data.documentos, key=lambda d: d.id, reverse=True)[:40]
    if not docs:
        st.info("Sin documentos.")
        return
    rows = [
        {
            "ID": d.id,
            "Tipo": _tipo_val(d),
            "Estado": _estado_val(d),
            "Ref": d.referencia_externa or "—",
            "Proveedor": d.proveedor_nombre_snapshot or "—",
            "Total": str(d.total_documento or "—"),
            "Stock": d.impacto_stock,
            "Token": (d.confirmacion_id or "—")[:8],
            "Hash": (d.contenido_hash or "—")[:10],
        }
        for d in docs
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)
    concs = getattr(data, "conciliaciones_documento", []) or []
    if concs:
        st.markdown("##### Conciliaciones")
        st.dataframe(
            [
                {
                    "id": c.id,
                    "factura_ln": c.linea_factura_id,
                    "albarán_ln": c.linea_albaran_id,
                    "qty": str(c.cantidad_conciliada),
                    "estado": c.estado.value
                    if hasattr(c.estado, "value")
                    else str(c.estado),
                }
                for c in concs
            ],
            use_container_width=True,
            hide_index=True,
        )
