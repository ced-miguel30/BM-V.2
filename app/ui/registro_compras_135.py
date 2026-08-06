"""UI canónica de compras (Fase 13.5 / C1 — solo servicios productivos).

No crea lotes/movimientos ni calcula conversiones/costes en la UI.
Confirmación → compra_registro_service;
anulación/devolución/rectificativa → anulacion_documento_service.

Rejilla multi-línea tipo Excel + conciliación multi-albarán.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pandas as pd
import streamlit as st

from app.core.models import EstadoDocumento, TipoDocumento
from app.core.services import anulacion_documento_service as anul
from app.core.services import compra_registro_service as compra
from app.core.services.data_service import get_repository
from app.core.storage.session_store import get_demo_path, reload_from_disk
from app.ui import compra_grid_helpers as grid
from app.ui.components import section_divider

_GRID_SS = "reg135_grid"
_GRID_PREV = "reg135_grid_prev"
_GRID_DOC = "reg135_grid_doc_id"
_HEADER_DTO = "reg135_dto_cab"


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

    st.markdown("#### Compras y documentos")
    st.caption(
        "Flujo canónico de compras. Borrador SoT en JSON. Confirmación vía "
        "`compra_registro_service` (lock A2 + hash + UUID). "
        "La UI no crea lotes ni movimientos."
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


def _mapa_productos(data):
    productos = list(data.productos)
    mapa_prod = {
        f"{p.nombre} [{getattr(p, 'codigo', None) or '—'}] ({p.id})": p
        for p in productos
    }
    mapa_por_id = {p.id: p for p in productos}
    mapa_label_por_id = {p.id: lbl for lbl, p in mapa_prod.items()}
    return mapa_prod, mapa_por_id, mapa_label_por_id


def _ensure_grid(rows: list[dict] | None = None) -> list[dict]:
    if _GRID_SS not in st.session_state or rows is not None:
        st.session_state[_GRID_SS] = rows if rows is not None else [grid.empty_row()]
    if not st.session_state[_GRID_SS]:
        st.session_state[_GRID_SS] = [grid.empty_row()]
    return st.session_state[_GRID_SS]


def _render_totales_panel(rows: list[dict], dto_cab: float) -> None:
    res = grid.calcular_totales_grid(rows, descuento_cabecera=dto_cab)
    info = grid.totales_a_dict(res)
    st.markdown("##### Totales del documento")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total sin impuesto", f"{info['base_imponible']} €")
    c2.metric("Total impuestos", f"{info['impuesto_total']} €")
    c3.metric("Total documento", f"{info['total_documento']} €")
    if info["desglose"]:
        st.caption("Desglose por impuesto")
        st.dataframe(
            [
                {
                    "IGIC %": d["porcentaje"],
                    "Base": f"{d['base']} €",
                    "Cuota": f"{d['cuota']} €",
                }
                for d in info["desglose"]
            ],
            use_container_width=True,
            hide_index=True,
        )


def _render_grupos_albaran(rows: list[dict], data) -> None:
    mapa_alb = {
        d.id: d
        for d in data.documentos
        if _tipo_val(d) == TipoDocumento.ALBARAN.value
    }
    grupos = grid.agrupar_filas_por_albaran(rows, mapa_alb=mapa_alb)
    if not grupos:
        return
    st.markdown("##### Albaranes incorporados")
    for g in grupos:
        st.markdown(f"**{g['etiqueta']}** — {g['total']} €")
        st.caption(f"· {g['productos']}")


def _ui_borrador(data, path) -> None:
    proveedores = [p for p in data.proveedores if getattr(p, "activo", True)]
    mapa_prov = {
        f"{p.nombre_fiscal} [{p.codigo or '—'}] ({p.id})": p.id for p in proveedores
    }
    mapa_prod, mapa_por_id, mapa_label_por_id = _mapa_productos(data)
    labels_prod = list(mapa_prod.keys())

    borradores = [
        d
        for d in data.documentos
        if _estado_val(d) == EstadoDocumento.BORRADOR.value
        and _tipo_val(d)
        in (
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

    # --- Cabecera ---
    edit_lbl = st.selectbox(
        "Documento", list(mapa_edit.keys()), key="reg135_edit_doc"
    )
    doc_id = mapa_edit[edit_lbl]

    # Precargar rejilla al cambiar de documento (antes de otros widgets)
    if st.session_state.get(_GRID_DOC) != (doc_id or "__new__"):
        st.session_state[_GRID_DOC] = doc_id or "__new__"
        if doc_id:
            doc = next((d for d in data.documentos if d.id == doc_id), None)
            if doc is not None:
                filas = grid.lineas_documento_a_filas(
                    doc,
                    mapa_prod_por_id=mapa_por_id,
                    mapa_label_por_id=mapa_label_por_id,
                )
                _ensure_grid(filas)
                if _tipo_val(doc) in ("albaran", "factura"):
                    st.session_state["reg135_tipo"] = _tipo_val(doc)
                # Proveedor del documento si está en mapa
                if doc.proveedor_id:
                    for lbl, pid in mapa_prov.items():
                        if pid == doc.proveedor_id:
                            st.session_state["reg135_prov"] = lbl
                            break
            else:
                _ensure_grid([grid.empty_row()])
        else:
            _ensure_grid([grid.empty_row()])
        st.session_state.pop(_GRID_PREV, None)
        st.rerun()

    tipo = st.selectbox("Tipo", ["albaran", "factura"], key="reg135_tipo")
    prov_lbl = st.selectbox(
        "Proveedor", list(mapa_prov.keys()) or ["—"], key="reg135_prov"
    )
    proveedor_id = mapa_prov.get(prov_lbl) if mapa_prov else None
    ref = st.text_input("Referencia externa", key="reg135_ref")
    notas = st.text_area("Observaciones / notas", height=68, key="reg135_notas")
    dto_cab = st.number_input(
        "Descuento cabecera (€)",
        min_value=0.0,
        step=0.01,
        format="%.2f",
        key=_HEADER_DTO,
    )

    rows = _ensure_grid()

    # --- Conciliación multi-albarán (solo factura) ---
    if tipo == "factura" and proveedor_id:
        st.markdown("##### Conciliar albaranes del proveedor")
        disponibles = grid.albaranes_conciliables(
            data, proveedor_id=proveedor_id, excluir_factura_id=doc_id
        )
        mapa_alb_lbl = {grid.etiqueta_albaran(a): a for a in disponibles}
        if mapa_alb_lbl:
            sel_albs = st.multiselect(
                "Albaranes pendientes de facturar",
                list(mapa_alb_lbl.keys()),
                key="reg135_alb_multi",
            )
            if st.button("Incorporar albaranes seleccionados", key="reg135_alb_add"):
                nuevos = grid.expandir_albaranes_a_filas(
                    data,
                    [mapa_alb_lbl[k] for k in sel_albs],
                    mapa_label_por_id=mapa_label_por_id,
                    mapa_prod_por_id=mapa_por_id,
                    excluir_factura_id=doc_id,
                )
                # Evitar duplicar misma línea de albarán ya en rejilla
                ya = {
                    (r.get(grid.META_ALB_LN) or "")
                    for r in st.session_state[_GRID_SS]
                }
                for n in nuevos:
                    if n.get(grid.META_ALB_LN) and n[grid.META_ALB_LN] in ya:
                        continue
                    st.session_state[_GRID_SS].append(n)
                # Quitar filas vacías iniciales
                st.session_state[_GRID_SS] = [
                    r
                    for r in st.session_state[_GRID_SS]
                    if grid.fila_tiene_producto(r)
                    or (r.get(grid.META_ALB_LN) or "")
                ] or [grid.empty_row()]
                st.session_state.pop(_GRID_PREV, None)
                st.rerun()
        else:
            st.caption("No hay albaranes confirmados pendientes para este proveedor.")

    st.markdown("##### Líneas de compra")
    st.caption(
        "Importes en formato contable español (10,00 / 10.000,00). "
        "Escriba el número y pulse Enter o Tab para confirmar la celda. "
        "Los totales del documento se actualizan al vuelo; "
        "unitario y total de línea se alinean al guardar. "
        "Puede añadir varias filas vacías y rellenarlas con calma. "
        "Vaciar el producto elimina esa línea."
    )

    # DataFrame visible: números como texto ES (sin metadatos internos)
    visible_cols = grid.GRID_COLS
    rows_ui = [grid.fila_numeros_a_texto_es(r) for r in rows]
    df_src = pd.DataFrame(rows_ui)
    for col in visible_cols:
        if col not in df_src.columns:
            df_src[col] = None
    if "incluye_igic" in df_src.columns:
        df_src["incluye_igic"] = df_src["incluye_igic"].fillna(False).astype(bool)
    if "producto" in df_src.columns:
        df_src["producto"] = df_src["producto"].map(grid.celda_texto)
    if "unidad" in df_src.columns:
        df_src["unidad"] = df_src["unidad"].map(
            lambda v: grid.celda_texto(v) or "Ud"
        )
    for ncol in grid.GRID_NUM_FMT:
        if ncol in df_src.columns:
            dec = grid.GRID_NUM_FMT[ncol]
            df_src[ncol] = df_src[ncol].map(
                lambda v, d=dec: grid.formatear_numero_es(
                    grid.celda_numero(v), decimales=d
                )
            )

    edited = st.data_editor(
        df_src[visible_cols],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        height=380,
        key=f"reg135_data_editor_{st.session_state.get('reg135_editor_ver', 0)}",
        column_config={
            "producto": st.column_config.SelectboxColumn(
                "Producto",
                options=labels_prod or [""],
                required=False,
                width="medium",
            ),
            "cantidad": st.column_config.TextColumn("Cantidad", width="small"),
            "unidad": st.column_config.TextColumn("Ud", width="small"),
            "precio_unitario": st.column_config.TextColumn("P. unit.", width="small"),
            "precio_total": st.column_config.TextColumn("P. total", width="small"),
            "dto_pct": st.column_config.TextColumn("Dto %", width="small"),
            "dto_eur": st.column_config.TextColumn("Dto €", width="small"),
            "igic_pct": st.column_config.TextColumn("IGIC %", width="small"),
            "incluye_igic": st.column_config.CheckboxColumn(
                "c/IGIC", width="small"
            ),
        },
    )

    # Fusionar edición con metadatos previos (por índice / claves)
    prev_rows = list(st.session_state.get(_GRID_PREV) or rows)
    merged: list[dict] = []
    edited_records = edited.to_dict(orient="records")
    for i, rec in enumerate(edited_records):
        base = dict(prev_rows[i]) if i < len(prev_rows) else grid.empty_row()
        if i >= len(prev_rows):
            base = grid.empty_row()
        for col in visible_cols:
            if col not in rec:
                continue
            val = rec[col]
            if col in ("producto", "unidad"):
                base[col] = grid.celda_texto(val)
                if col == "unidad" and not base[col]:
                    base[col] = "Ud"
            elif col == "incluye_igic":
                base[col] = bool(val) if val is not None and not (
                    isinstance(val, float) and str(val) == "nan"
                ) else False
            elif col == "igic_pct":
                base[col] = grid.celda_numero(val, 7.0)
            elif col in grid.GRID_NUM_FMT:
                base[col] = grid.celda_numero(val)
            else:
                base[col] = val
        label = grid.celda_texto(base.get("producto"))
        base["producto"] = label
        if label in mapa_prod:
            prod = mapa_prod[label]
            base[grid.META_PROD_ID] = prod.id
            if not grid.celda_texto(base.get("unidad")):
                u = prod.unidad
                base["unidad"] = u.value if hasattr(u, "value") else str(u)
        elif not label:
            base[grid.META_PROD_ID] = ""
        merged.append(base)

    purged = grid.purgar_filas_sin_producto(merged, prev_rows)
    # Sync solo para totales / guardar — no remontar el editor (rompe la edición)
    synced = grid.sincronizar_precios_filas(purged, prev_rows)

    prev_prod_n = sum(1 for r in prev_rows if grid.fila_tiene_producto(r))
    purged_prod_n = sum(1 for r in purged if grid.fila_tiene_producto(r))
    needs_remount = purged_prod_n < prev_prod_n

    # Persistimos la edición del usuario; el panel usa la copia sync
    st.session_state[_GRID_SS] = purged
    st.session_state[_GRID_PREV] = [dict(r) for r in purged]
    if needs_remount:
        st.session_state["reg135_editor_ver"] = (
            int(st.session_state.get("reg135_editor_ver") or 0) + 1
        )
        st.rerun()

    _render_grupos_albaran(synced, data)
    _render_totales_panel(synced, float(dto_cab))

    if st.button("Guardar borrador", type="primary", key="reg135_guardar"):
        if not mapa_prov or not mapa_prod:
            st.error("Se requieren proveedor y producto en catálogo.")
            return
        lineas = grid.filas_a_payload_lineas(
            synced, mapa_prod_por_label=mapa_prod
        )
        if not lineas:
            st.error("Añada al menos una línea con producto y cantidad > 0.")
            return
        conc = grid.filas_a_conciliaciones(synced)
        if conc:
            st.session_state["reg135_conc"] = conc
        else:
            st.session_state.pop("reg135_conc", None)

        r = compra.guardar_borrador_persistente(
            json_path=path,
            tipo=tipo,
            proveedor_id=proveedor_id,
            referencia_externa=ref or None,
            notas=notas or None,
            descuento_cabecera_importe=dto_cab,
            lineas=lineas,
            documento_id=doc_id,
            fecha_documento=date.today(),
        )
        if r.ok:
            reload_from_disk()
            st.success(r.mensaje)
            if r.documento is not None:
                st.session_state[_GRID_DOC] = r.documento.id
                # Recargar desde persistido
                filas = grid.lineas_documento_a_filas(
                    r.documento,
                    mapa_prod_por_id=mapa_por_id,
                    mapa_label_por_id=mapa_label_por_id,
                )
                # Re-aplicar enlaces alb desde synced por client_line_key
                by_key = {r.get(grid.META_KEY): r for r in synced}
                for f in filas:
                    src = by_key.get(f.get(grid.META_KEY))
                    if src:
                        f[grid.META_ALB_LN] = src.get(grid.META_ALB_LN) or f.get(
                            grid.META_ALB_LN
                        )
                        f[grid.META_ALB_DOC] = src.get(grid.META_ALB_DOC) or f.get(
                            grid.META_ALB_DOC
                        )
                _ensure_grid(filas)
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

    # Totales persistidos
    st.markdown("###### Totales")
    t1, t2, t3 = st.columns(3)
    t1.metric("Total sin impuesto", f"{doc.base_imponible or 0} €")
    t2.metric("Total impuestos", f"{doc.impuesto_total or 0} €")
    t3.metric("Total documento", f"{doc.total_documento or 0} €")
    desglose = getattr(doc, "desglose_impuestos", None) or []
    if desglose:
        st.dataframe(
            [
                {
                    "IGIC %": str(d.porcentaje),
                    "Base": f"{d.base} €",
                    "Cuota": f"{d.cuota} €",
                }
                for d in desglose
            ],
            use_container_width=True,
            hide_index=True,
        )

    # Vista agrupada por albarán si hay enlaces
    rows_vista = []
    for ln in doc.lineas:
        rows_vista.append(
            {
                "producto": ln.producto_nombre_snapshot or ln.producto_id,
                "precio_total": float(
                    Decimal(str(ln.total_linea or ln.precio_total or 0))
                ),
                grid.META_ALB_DOC: ln.documento_origen_id or "",
                grid.META_ALB_LN: ln.linea_origen_id or "",
            }
        )
    _render_grupos_albaran(rows_vista, data)

    st.dataframe(
        [
            {
                "Producto": ln.producto_nombre_snapshot or ln.producto_id,
                "Cantidad": str(ln.cantidad_compra or ln.cantidad),
                "Unidad": ln.unidad_compra or "—",
                "P. unitario": str(ln.precio_unitario_compra or "—"),
                "Base": str(ln.base_imponible or "—"),
                "IGIC": str(ln.cuota_impuesto or "—"),
                "Total línea": str(ln.total_linea or ln.precio_total or "—"),
                "Albarán": ln.documento_origen_id or "—",
            }
            for ln in doc.lineas
        ],
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        f"Hash {h[:16]}… · confirmacion_id {token}"
        + (f" · {len(conc)} conciliación(es)" if conc else "")
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
        # Reconstruir conciliaciones desde líneas persistidas si no hay en session
        if not conc:
            conc = [
                {
                    "linea_factura_client_key": ln.client_line_key,
                    "linea_albaran_id": ln.linea_origen_id,
                    "cantidad_conciliada": str(
                        ln.cantidad_compra
                        if ln.cantidad_compra is not None
                        else ln.cantidad
                    ),
                }
                for ln in doc.lineas
                if ln.linea_origen_id and ln.client_line_key
            ] or None
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
