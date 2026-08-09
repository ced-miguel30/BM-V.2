"""Renderer genérico de página de registro de servicio (desayuno/comida/cena/bebidas)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

import streamlit as st

from app.core.auth.permissions import Permiso
from app.core.auth.session import get_auth_session, session_tiene_permiso
from app.core.models import CATEGORIA_RECETA_LABEL, CategoriaReceta
from app.core.services.data_service import get_repository
from app.core.services.exportacion_semanal_service import limite_semana
from app.core.services.formatting import formato_fecha
from app.core.services.inventory_batch_service import valorizar_cantidad_fifo
from app.core.services.receta_service import listar_recetas
from app.core.services.unidad_service import (
    formato_number_input,
    normalizar_cantidad,
    paso_unidad,
)
from app.core.storage.session_store import get_data
from app.core.services.registro_estado_service import estado_registro_dia
from app.ui.cesta_render import boton_exportar_semana, render_cesta_servicio
from app.ui.components import aviso_servicios_pendientes, empty_state, page_header, section_divider
from app.ui.search import render_buscador_producto

PASO_CANTIDAD = 1.0  # Compat; inputs usan paso_unidad().

_MODO_RECETAS = "Recetas / elaboraciones"
_MODO_PRODUCTOS = "Productos / otros consumos"
_MODO_BEBIDAS = "Bebidas"


def _lunes_semana_actual() -> date:
    lunes, _ = limite_semana(date.today())
    return lunes


def _responsable_actual() -> str:
    session = get_auth_session()
    if session and session.actor_label:
        return session.actor_label
    return "—"


def _etiqueta_categoria_receta(receta) -> str:
    try:
        return CATEGORIA_RECETA_LABEL.get(receta.categoria, str(receta.categoria))
    except Exception:
        return "—"


def _avisos_coste_incompleto(plan_stock) -> list[str]:
    """Mensajes operativos cuando hay stock pero la valoración FIFO es incompleta."""
    if plan_stock is None or not plan_stock.ok:
        return []
    data = get_data()
    avisos: list[str] = []
    for ln in plan_stock.lineas:
        if ln.salida <= 0 or not ln.ok:
            continue
        val = valorizar_cantidad_fifo(data, ln.producto_id, ln.salida)
        if val.incompleto:
            ud = f" {ln.unidad}" if ln.unidad else ""
            avisos.append(
                f"Coste incompleto para {ln.nombre}: valorado "
                f"{val.cantidad_valorada:g}{ud} de {ln.salida:g}{ud}."
            )
    return avisos


def _token_idempotencia(key_prefix: str) -> str:
    tok_key = f"{key_prefix}_clave_idempotencia"
    if tok_key not in st.session_state or not st.session_state[tok_key]:
        st.session_state[tok_key] = str(uuid.uuid4())
    return st.session_state[tok_key]


def _rotar_token_idempotencia(key_prefix: str) -> None:
    st.session_state[f"{key_prefix}_clave_idempotencia"] = str(uuid.uuid4())


def _render_detalle(servicio, registro) -> None:
    from app.core.services.anulacion_registro_service import (
        TIPO_DESAYUNO,
        TIPO_SERVICIO,
        anular_registro,
        puede_anular_registro,
        previsualizar_anulacion,
        registro_esta_anulado,
    )
    from app.core.storage.session_store import get_data

    data = get_data()
    tipo_reg = (
        TIPO_DESAYUNO
        if getattr(servicio, "tipo_servicio", "") == "desayuno"
        else TIPO_SERVICIO
    )

    if registro_esta_anulado(registro):
        st.warning("Estado: **Anulado**")
        st.caption(
            f"Fecha anulación: "
            f"{formato_fecha(registro.fecha_anulacion) if registro.fecha_anulacion else '—'} "
            f"{registro.hora_anulacion.strftime('%H:%M') if registro.hora_anulacion else ''} "
            f"· Por: {registro.anulado_por or '—'} "
            f"· Motivo: {registro.motivo_anulacion or '—'} "
            f"· Ref: {registro.referencia_anulacion or '—'}"
        )
    else:
        st.caption("Estado: Activo")

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
    obs = getattr(registro, "observaciones", "") or ""
    if obs:
        st.caption(f"Observaciones: {obs}")
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
    if idx_coste is not None and session_tiene_permiso(Permiso.CONSULTAR_COSTES):
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
    columnas_vis = list(reg.columnas)
    filas_vis = [list(f) for f in reg.filas]
    if not session_tiene_permiso(Permiso.CONSULTAR_COSTES) and "Coste" in columnas_vis:
        idx = columnas_vis.index("Coste")
        columnas_vis = [c for i, c in enumerate(columnas_vis) if i != idx]
        filas_vis = [[c for i, c in enumerate(fila) if i != idx] for fila in filas_vis]
    st.dataframe(
        {col: [fila[i] for fila in filas_vis] for i, col in enumerate(columnas_vis)},
        use_container_width=True,
        hide_index=True,
    )
    if reg.resumen:
        st.caption(" · ".join(f"{clave}: {valor}" for clave, valor in reg.resumen))

    st.markdown("##### Anulación")
    puede = puede_anular_registro(data, registro, tipo=tipo_reg)
    preview = previsualizar_anulacion(data, registro, tipo=tipo_reg)
    if preview.lineas:
        st.dataframe(
            {
                "Producto": [ln.nombre for ln in preview.lineas],
                "Lote": [ln.lote_id for ln in preview.lineas],
                "Consumido": [ln.cantidad_consumida for ln in preview.lineas],
                "Restante actual": [ln.cantidad_restante_actual for ln in preview.lineas],
                "A devolver": [ln.cantidad_a_devolver for ln in preview.lineas],
                "Resultante": [ln.cantidad_resultante for ln in preview.lineas],
                "Ud": [ln.unidad for ln in preview.lineas],
            },
            use_container_width=True,
            hide_index=True,
        )
    if not puede.ok:
        for motivo in puede.motivos_bloqueo:
            st.error(motivo)
        return

    motivo = st.text_input(
        "Motivo de anulación (obligatorio)",
        key=f"anul_motivo_{registro.id}",
    )
    referencia = st.text_input(
        "Referencia (opcional)",
        key=f"anul_ref_{registro.id}",
    )
    confirma = st.checkbox(
        "Confirmo que quiero anular este registro y reponer el stock a los lotes originales",
        key=f"anul_ok_{registro.id}",
    )
    if st.button(
        "Anular registro",
        type="primary",
        disabled=not confirma or not (motivo or "").strip(),
        key=f"anul_btn_{registro.id}",
    ):
        resultado = anular_registro(
            data, registro.id, tipo_reg, motivo, referencia,
        )
        if resultado.ok:
            st.success(resultado.mensaje)
            st.rerun()
        else:
            st.error(resultado.mensaje)


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
    ver_costes = session_tiene_permiso(Permiso.CONSULTAR_COSTES)

    if mostrar_cabecera:
        page_header(titulo_pagina, subtitulo)

    aviso_servicios_pendientes(key_prefix=f"{key_prefix}_aviso_serv")

    cesta_vacia = servicio.cesta_vacia()
    estado_reg = "Borrador (sin líneas)" if cesta_vacia else "Borrador (pendiente de confirmar)"
    col_h1, col_h2, col_h3, col_h4 = st.columns(4)
    with col_h1:
        fecha = st.date_input(
            "Fecha", value=date.today(), max_value=date.today(), key=f"{key_prefix}_fecha",
        )
    with col_h2:
        st.markdown("**Servicio**")
        st.write(etiqueta)
    with col_h3:
        st.markdown("**Responsable**")
        st.write(_responsable_actual())
    with col_h4:
        st.markdown("**Estado cesta**")
        st.write(estado_reg)

    dia = estado_registro_dia(
        get_data(),
        tipo_servicio=getattr(servicio, "tipo_servicio", ""),
        fecha=fecha,
    )
    if dia.registros_activos > 0:
        st.info(
            f"{dia.etiqueta}. Puede crear otro registro si el servicio lo requiere "
            "(por turnos); la confirmación no duplica el mismo contenido gracias "
            "al token de idempotencia."
        )
    else:
        st.caption(dia.etiqueta)

    num_huespedes = 0
    if mostrar_huespedes:
        num_huespedes = int(st.number_input(
            "Nº de huéspedes",
            min_value=min_huespedes,
            value=max(default_huespedes, min_huespedes),
            step=1,
            key=f"{key_prefix}_num_huespedes",
        ))

    st.caption(
        "Semántica de receta: la cantidad son **raciones** (no preparaciones completas). "
        "Factor = raciones ÷ rendimiento configurado. Solo elementos activos."
    )

    col_buscar, col_cesta = st.columns([2, 1])

    with col_buscar:
        modo = st.radio(
            "Tipo a registrar",
            [_MODO_RECETAS, _MODO_PRODUCTOS, _MODO_BEBIDAS],
            horizontal=True,
            key=f"{key_prefix}_modo_tipo",
        )

        if modo == _MODO_RECETAS:
            st.markdown(
                '##### Recetas / elaboraciones '
                '<span class="bm-cesta-tipo">Receta</span>',
                unsafe_allow_html=True,
            )
            recetas = listar_recetas(
                servicio_disponible=servicio.tipo_servicio, solo_activas=True,
            )
            if recetas:
                # Selección rápida: primeras recetas activas como botones compactos
                rapidas = recetas[:8]
                st.caption("Selección rápida")
                cols_r = st.columns(min(4, len(rapidas)))
                mapa_recetas = {
                    f"{r.nombre} · {_etiqueta_categoria_receta(r)}": r.id for r in recetas
                }
                for i, r in enumerate(rapidas):
                    etiqueta_opt = f"{r.nombre} · {_etiqueta_categoria_receta(r)}"
                    with cols_r[i % len(cols_r)]:
                        if st.button(
                            r.nombre,
                            key=f"{key_prefix}_rapida_{r.id}",
                            use_container_width=True,
                            help=(
                                f"{_etiqueta_categoria_receta(r)} · "
                                f"rend. {r.porciones_estandar:g}"
                                if r.porciones_estandar
                                else _etiqueta_categoria_receta(r)
                            ),
                        ):
                            st.session_state[f"{key_prefix}_sel_receta"] = etiqueta_opt
                            st.rerun()
                opciones = list(mapa_recetas.keys())
                receta_nombre = st.selectbox(
                    "Buscar receta",
                    opciones,
                    key=f"{key_prefix}_sel_receta",
                )
                receta_id = mapa_recetas[receta_nombre]
                receta_obj = next(r for r in recetas if r.id == receta_id)
                default_porciones = float(receta_obj.porciones_estandar or 0) or 1.0
                if receta_obj.porciones_estandar:
                    st.caption(
                        f"Rendimiento configurado: {receta_obj.porciones_estandar:g} raciones. "
                        "Ejemplo: 2 = 2 raciones (no 2 preparaciones completas)."
                    )
                else:
                    st.warning(
                        "Esta receta no tiene rendimiento configurado. "
                        "Configúrela en Recetas antes de añadirla."
                    )

                porciones = st.number_input(
                    "Raciones a registrar",
                    min_value=0.0,
                    value=default_porciones,
                    step=1.0,
                    format="%.0f",
                    key=f"{key_prefix}_porciones_{receta_id}",
                    help="Cantidad en raciones. Factor = pedidas / rendimiento.",
                )
                if receta_obj.porciones_estandar and porciones > 0:
                    factor_prev = porciones / receta_obj.porciones_estandar
                    st.caption(f"Factor previsto: {factor_prev:g}")

                with st.expander("Extras u omisiones (opcional)", expanded=False):
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
                            resultado = servicio.anadir_mod_pendiente_receta(
                                producto_mod["id"], cant_mod,
                            )
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
                            etiqueta_mod = (
                                f"c/ extra {mod.nombre}"
                                if mod.cantidad > 0
                                else f"s/ {mod.nombre}"
                            )
                            with col_txt:
                                st.markdown(
                                    f"- {etiqueta_mod} — {abs(mod.cantidad):g} {mod.unidad}"
                                )
                            with col_q:
                                if st.button("✕", key=f"{key_prefix}_quitar_mod_{mod.mod_id}"):
                                    servicio.quitar_mod_pendiente(mod.mod_id)
                                    st.rerun()

                if st.button(
                    "Añadir a la cesta",
                    type="primary",
                    use_container_width=True,
                    key=f"{key_prefix}_btn_receta",
                ):
                    mods = servicio.get_mods_pendientes()
                    resultado = servicio.anadir_receta_a_cesta(receta_id, porciones, list(mods))
                    if resultado.ok:
                        st.success(resultado.mensaje)
                        st.rerun()
                    else:
                        st.error(resultado.mensaje)
            else:
                empty_state(
                    "No hay recetas activas con este servicio disponible. "
                    "Configúrelas en Recetas.",
                    icon="📖",
                )

        else:
            es_bebida_modo = modo == _MODO_BEBIDAS
            tipo_lbl = "Bebida" if es_bebida_modo else "Producto / otro consumo"
            st.markdown(
                f'##### {modo} '
                f'<span class="bm-cesta-tipo">{tipo_lbl}</span>',
                unsafe_allow_html=True,
            )
            if not es_bebida_modo:
                st.caption(
                    "Consumo directo de inventario sin receta "
                    "(no usar merma para consumo normal)."
                )
            if es_bebida_modo and getattr(servicio, "tipo_servicio", "") != "bebidas":
                st.caption(
                    f"Estas bebidas pertenecen al servicio {etiqueta} "
                    "(no se registran como servicio independiente Bebidas)."
                )
            elif es_bebida_modo:
                st.caption("Servicio independiente Bebidas.")
            todos_productos = [
                p for p in servicio.productos_catalogo("")
                if bool(p.get("es_bebida")) == es_bebida_modo
            ]
            producto_sel = render_buscador_producto(
                todos_productos,
                f"{key_prefix}_{'beb' if es_bebida_modo else 'prod'}",
                label="Buscar por nombre",
                placeholder="Escriba el nombre...",
            )
            if producto_sel:
                unidad_prod = producto_sel.get("unidad", "Ud")
                st.caption(
                    f"Unidad: {unidad_prod} · Stock: {producto_sel.get('stock', 0):g}"
                )
                cantidad = st.number_input(
                    "Cantidad",
                    min_value=0.0,
                    value=float(paso_unidad(unidad_prod)),
                    step=paso_unidad(unidad_prod),
                    format=formato_number_input(unidad_prod),
                    key=f"{key_prefix}_cantidad_{'beb' if es_bebida_modo else 'prod'}",
                )
                cantidad = normalizar_cantidad(cantidad, unidad_prod)
                if st.button(
                    "Añadir a la cesta",
                    type="primary",
                    use_container_width=True,
                    key=f"{key_prefix}_btn_anadir_{'beb' if es_bebida_modo else 'prod'}",
                ):
                    if cantidad <= 0:
                        st.error("La cantidad debe ser mayor que 0.")
                    else:
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
                    f"No hay {'bebidas' if es_bebida_modo else 'productos'} activos "
                    "con este servicio disponible.",
                    icon="🔍",
                )

    with col_cesta:
        render_cesta_servicio(
            servicio,
            repo,
            titulo_cesta="Resumen",
            key_prefix=key_prefix,
            vacio_mensaje=f"Todavía no has añadido líneas a {etiqueta.lower()}.",
        )

        plan_stock = None
        if hasattr(servicio, "previsualizar_stock") and not servicio.cesta_vacia():
            plan_stock = servicio.previsualizar_stock()
            if plan_stock.lineas:
                st.caption("Vista previa de stock (antes de confirmar)")
                st.dataframe(
                    {
                        "Producto": [ln.nombre for ln in plan_stock.lineas],
                        "Actual": [
                            f"{ln.actual:g} {ln.unidad}".strip() for ln in plan_stock.lineas
                        ],
                        "Salida": [
                            f"{ln.salida:g} {ln.unidad}".strip() for ln in plan_stock.lineas
                        ],
                        "Resultante": [
                            f"{ln.resultante:g} {ln.unidad}".strip() for ln in plan_stock.lineas
                        ],
                    },
                    use_container_width=True,
                    hide_index=True,
                )
                if not plan_stock.ok:
                    st.error("Stock insuficiente: no se confirmará nada hasta corregir.")
                    for linea in plan_stock.deficits:
                        st.markdown(f"- {linea}")
                for aviso in _avisos_coste_incompleto(plan_stock):
                    st.warning(aviso)

        observaciones = st.text_area(
            "Observaciones (opcional)",
            key=f"{key_prefix}_observaciones",
            height=68,
            placeholder="Notas del servicio…",
        )
        confirma = st.checkbox(
            f"Confirmo el registro de {etiqueta.lower()}",
            key=f"{key_prefix}_confirma_reg",
            disabled=servicio.cesta_vacia() or bool(plan_stock is not None and not plan_stock.ok),
        )
        if st.button(
            f"Registrar {etiqueta.lower()}",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_btn_registrar",
            disabled=(
                not confirma
                or servicio.cesta_vacia()
                or bool(plan_stock is not None and not plan_stock.ok)
            ),
        ):
            token = _token_idempotencia(key_prefix)
            resultado = servicio.registrar(
                fecha,
                num_huespedes,
                clave_idempotencia=token,
                observaciones=observaciones or "",
            )
            if resultado.ok:
                st.session_state.pop(stock_key, None)
                _rotar_token_idempotencia(key_prefix)
                st.session_state[f"{key_prefix}_confirma_reg"] = False
                st.session_state[f"{key_prefix}_observaciones"] = ""
                st.success(resultado.mensaje)
                st.rerun()
            elif resultado.codigo == "STOCK_INSUFICIENTE":
                st.session_state.pop(stock_key, None)
                st.error(resultado.mensaje)
                if resultado.detalle_stock:
                    for linea in resultado.detalle_stock:
                        st.markdown(f"- {linea}")
            else:
                st.session_state.pop(stock_key, None)
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
    registros_activos = [
        r for r in registros_semana if not getattr(r, "anulado", False)
    ]
    registros_anulados_semana = [
        r for r in registros_semana if getattr(r, "anulado", False)
    ]
    if registros_activos:
        columnas = {
            "Fecha": [formato_fecha(r.fecha) for r in registros_activos],
            "Hora": [r.hora.strftime("%H:%M") if r.hora else "—" for r in registros_activos],
        }
        if mostrar_huespedes:
            columnas["Huéspedes"] = [
                getattr(r, "num_huespedes", 0) for r in registros_activos
            ]
        columnas.update({
            "Elementos": [len(r.lineas) + len(r.registros_recetas) for r in registros_activos],
            "Cantidad total": [
                round(sum(abs(l.cantidad) for l in r.lineas), 2) for r in registros_activos
            ],
            "Ref.": [r.id for r in registros_activos],
            "Registrado por": [r.registrado_por for r in registros_activos],
        })
        if ver_costes:
            columnas["Coste"] = [repo.formato_precio(r.coste_total) for r in registros_activos]
        st.dataframe(columnas, use_container_width=True, hide_index=True)
    elif not registros_semana:
        empty_state(mensaje_vacio_historial, icon="📅")
    else:
        st.caption("No hay registros activos esta semana (solo anulados).")

    if registros_anulados_semana:
        st.caption(
            f"{len(registros_anulados_semana)} registro(s) anulado(s) esta semana "
            "(visibles en el selector de detalle)."
        )

    if registros_semana:
        opciones_detalle = {}
        for r in registros_semana:
            marca = " [Anulado]" if getattr(r, "anulado", False) else ""
            clave = (
                f"{r.id}{marca} — {formato_fecha(r.fecha)} "
                f"{r.hora.strftime('%H:%M') if r.hora else ''}"
            ).strip()
            opciones_detalle[clave] = r
        etiqueta_sel = st.selectbox(
            "Ver detalle de un registro",
            ["—"] + list(opciones_detalle.keys()),
            key=f"{key_prefix}_detalle_sel",
        )
        if etiqueta_sel != "—":
            _render_detalle(servicio, opciones_detalle[etiqueta_sel])
    elif not registros_activos:
        pass  # empty_state ya mostrado si no hay semana
