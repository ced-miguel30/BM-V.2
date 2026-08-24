"""Mixin economato — recepción, documentos, maestros e historial en Terminal Inventario.

Reutiliza compra_registro_service + compra_grid_helpers (sin Streamlit).
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from typing import TYPE_CHECKING

from app.bootstrap import get_container
from app.core.application.idempotency import (
    current_idempotency_token,
    rotate_idempotency_token,
)
from app.core.models import EstadoDocumento, TipoDocumento
from app.core.services.text_search import contiene_texto
from app.core.services import (
    anulacion_documento_service,
    catalogo_service,
    compra_registro_service,
    documento_consulta_service,
    proveedor_service,
    rectificativa_service,
)
from app.core.services.documento_consulta_service import FiltroDocumentos
from app.core.storage.demo_files import get_demo_file
from app.core.storage.session_store import reload_from_disk
from app.presentation.flet import session_bridge
from app.presentation.flet.inventory_document_viewmodels import (
    MAESTRO_TABS,
    AlbaranConciliableVM,
    CompraLineaDocVM,
    DepartamentoMaestroVM,
    DocumentoDetalleLineaVM,
    DocumentoDetalleVM,
    DocumentoListaVM,
    EconomatoPanelVM,
    HistorialEventoVM,
    ImpuestoMaestroVM,
    OpcionDocVM,
    ProveedorMaestroVM,
    TotalesCompraVM,
    UbicacionMaestroVM,
    VinculoMaestroVM,
)
from app.presentation.flet.mappers import map_error_recuperable, map_resultado
from app.presentation.flet.viewmodels import FeedbackVM
from app.ui import compra_grid_helpers as grid

if TYPE_CHECKING:
    from app.presentation.flet.inventory_viewmodels import InventarioScreenVM

_IDEMP_COMPRA = "flet_inv_compra"


class InventarioEconomatoMixin:
    """Estado y acciones documentales. Mezclar con TerminalInventarioPresenter."""

    def _init_economato_state(self) -> None:
        self._maestro_tab = "departamentos"
        self._compra_tipo = TipoDocumento.ALBARAN.value
        self._compra_proveedor_id = ""
        self._compra_referencia = ""
        self._compra_notas = ""
        self._compra_descuento_cabecera = "0"
        self._compra_ubicacion_entrada_id = ""
        self._compra_documento_id = ""
        self._compra_lineas: list[dict] = []
        self._compra_prod_busqueda = ""
        self._albaranes_seleccionados: list[str] = []
        self._doc_filtro_texto = ""
        self._doc_filtro_tipo = ""
        self._doc_filtro_estado = ""
        self._documento_detalle_id: str | None = None
        self._hist_texto = ""
        self._hist_ubicacion_id = ""
        self._hist_proveedor_id = ""

    def _gate_economato(self) -> bool:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable(
                "Sesión no autorizada.", codigo="DENEGADO"
            )
            return False
        return True

    def set_maestro_tab(self, tab: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        t = (tab or "").strip().lower()
        if t not in MAESTRO_TABS:
            self._feedback = map_error_recuperable("Pestaña de maestros no válida.")
            return self.screen()
        self._maestro_tab = t
        self._espacio = "maestros"
        return self.screen()

    # ── Recepción ─────────────────────────────────────────────────────────

    def set_compra_cabecera(
        self,
        *,
        proveedor_id: str | None = None,
        referencia: str | None = None,
        notas: str | None = None,
        descuento_cabecera: str | None = None,
        ubicacion_entrada_id: str | None = None,
        tipo: str | None = None,
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if proveedor_id is not None:
            self._compra_proveedor_id = (proveedor_id or "").strip()
            self._albaranes_seleccionados = []
        if referencia is not None:
            self._compra_referencia = (referencia or "").strip()
        if notas is not None:
            self._compra_notas = (notas or "").strip()
        if descuento_cabecera is not None:
            self._compra_descuento_cabecera = (descuento_cabecera or "0").strip() or "0"
        if ubicacion_entrada_id is not None:
            self._compra_ubicacion_entrada_id = (ubicacion_entrada_id or "").strip()
        if tipo is not None:
            return self.set_compra_tipo(tipo)
        self._espacio = "recepcion"
        return self.screen()

    def set_compra_tipo(self, tipo: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        t = (tipo or "").strip().lower()
        if t not in (TipoDocumento.ALBARAN.value, TipoDocumento.FACTURA.value):
            self._feedback = map_error_recuperable("Tipo debe ser albarán o factura.")
            return self.screen()
        self._compra_tipo = t
        if t != TipoDocumento.FACTURA.value:
            self._albaranes_seleccionados = []
        self._espacio = "recepcion"
        return self.screen()

    def set_compra_prod_busqueda(self, texto: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        self._compra_prod_busqueda = (texto or "").strip()
        self._espacio = "recepcion"
        return self.screen()

    def añadir_linea_compra(
        self,
        producto_id: str,
        *,
        cantidad: str = "1",
        precio_unitario: str = "0",
        dto_pct: str = "0",
        dto_eur: str = "0",
        igic_pct: str = "",
        incluye_igic: bool = False,
        ubicacion_destino_id: str = "",
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        pid = (producto_id or "").strip()
        if not pid:
            self._feedback = map_error_recuperable("Seleccione un producto.")
            return self.screen()
        data = get_container().app_data_store.get()
        prod = next((p for p in data.productos if p.id == pid and p.activo), None)
        if prod is None:
            self._feedback = map_error_recuperable("Producto no encontrado.")
            return self.screen()
        unidad = (
            prod.unidad.value if hasattr(prod.unidad, "value") else str(prod.unidad)
        )
        igic = (igic_pct or "").strip() or self._igic_default(data)
        row = {
            grid.META_KEY: str(uuid.uuid4()),
            grid.META_PROD_ID: pid,
            "producto": prod.nombre,
            "cantidad": grid.parsear_numero_es(cantidad, 1.0),
            "unidad": unidad,
            "precio_unitario": grid.parsear_numero_es(precio_unitario, 0.0),
            "dto_pct": grid.parsear_numero_es(dto_pct, 0.0),
            "dto_eur": grid.parsear_numero_es(dto_eur, 0.0),
            "igic_pct": grid.parsear_numero_es(igic, 7.0),
            "incluye_igic": bool(incluye_igic),
            "ubicacion_destino_id": (
                ubicacion_destino_id or self._compra_ubicacion_entrada_id or ""
            ),
            grid.META_ALB_DOC: "",
            grid.META_ALB_LN: "",
        }
        row = grid.aplicar_defaults_vinculo_fila(
            row,
            prod,
            data=data,
            proveedor_id=self._compra_proveedor_id or None,
            forzar_unidad=False,
        )
        self._compra_lineas.append(row)
        self._compra_prod_busqueda = ""
        self._feedback = FeedbackVM(ok=True, mensaje=f"Línea «{prod.nombre}» añadida.")
        self._espacio = "recepcion"
        return self.screen()

    def añadir_linea_compra_por_busqueda(
        self,
        texto: str,
        *,
        cantidad: str = "1",
        precio_unitario: str = "0",
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        prod, err = self._resolver_producto_compra(texto)
        if prod is None:
            self._compra_prod_busqueda = (texto or "").strip()
            self._feedback = map_error_recuperable(err or "Producto no encontrado.")
            self._espacio = "recepcion"
            return self.screen()
        return self.añadir_linea_compra(
            prod.id, cantidad=cantidad, precio_unitario=precio_unitario
        )

    def update_linea_compra(
        self,
        index: int,
        *,
        cantidad: str | None = None,
        precio_unitario: str | None = None,
        dto_pct: str | None = None,
        dto_eur: str | None = None,
        igic_pct: str | None = None,
        incluye_igic: bool | None = None,
        ubicacion_destino_id: str | None = None,
        unidad: str | None = None,
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if index < 0 or index >= len(self._compra_lineas):
            self._feedback = map_error_recuperable("Índice de línea inválido.")
            return self.screen()
        row = dict(self._compra_lineas[index])
        if cantidad is not None:
            row["cantidad"] = grid.parsear_numero_es(cantidad, 0.0)
        if precio_unitario is not None:
            row["precio_unitario"] = grid.parsear_numero_es(precio_unitario, 0.0)
        if dto_pct is not None:
            row["dto_pct"] = grid.parsear_numero_es(dto_pct, 0.0)
        if dto_eur is not None:
            row["dto_eur"] = grid.parsear_numero_es(dto_eur, 0.0)
        if igic_pct is not None:
            row["igic_pct"] = grid.parsear_numero_es(igic_pct, 0.0)
        if incluye_igic is not None:
            row["incluye_igic"] = bool(incluye_igic)
        if ubicacion_destino_id is not None:
            row["ubicacion_destino_id"] = (ubicacion_destino_id or "").strip()
        if unidad is not None:
            row["unidad"] = (unidad or "").strip() or row.get("unidad") or "Ud"
        self._compra_lineas[index] = row
        self._espacio = "recepcion"
        return self.screen()

    def quitar_linea_compra(self, index: int) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if index < 0 or index >= len(self._compra_lineas):
            self._feedback = map_error_recuperable("Índice de línea inválido.")
            return self.screen()
        quitada = self._compra_lineas.pop(index)
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Línea «{quitada.get('producto', '')}» eliminada."
        )
        self._espacio = "recepcion"
        return self.screen()

    def limpiar_borrador_compra(self) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        self._reset_compra_draft()
        self._feedback = FeedbackVM(ok=True, mensaje="Borrador de compra limpiado.")
        self._espacio = "recepcion"
        return self.screen()

    def toggle_albaran_conciliacion(self, albaran_id: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        aid = (albaran_id or "").strip()
        if not aid:
            return self.screen()
        if aid in self._albaranes_seleccionados:
            self._albaranes_seleccionados = [
                x for x in self._albaranes_seleccionados if x != aid
            ]
        else:
            self._albaranes_seleccionados.append(aid)
        self._espacio = "recepcion"
        return self.screen()

    def incorporar_albaranes_seleccionados(self) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if self._compra_tipo != TipoDocumento.FACTURA.value:
            self._feedback = map_error_recuperable(
                "Cambie el tipo a factura para conciliar albaranes."
            )
            return self.screen()
        if not self._compra_proveedor_id:
            self._feedback = map_error_recuperable("Seleccione proveedor primero.")
            return self.screen()
        if not self._albaranes_seleccionados:
            self._feedback = map_error_recuperable("Seleccione al menos un albarán.")
            return self.screen()
        data = get_container().app_data_store.get()
        disponibles = {
            a.id: a
            for a in grid.albaranes_conciliables(
                data,
                proveedor_id=self._compra_proveedor_id,
                excluir_factura_id=self._compra_documento_id or None,
            )
        }
        albs = [disponibles[i] for i in self._albaranes_seleccionados if i in disponibles]
        if not albs:
            self._feedback = map_error_recuperable("Ningún albarán conciliable válido.")
            return self.screen()
        mapa_prod = {p.id: p for p in data.productos}
        mapa_lbl = {p.id: p.nombre for p in data.productos}
        nuevos = grid.expandir_albaranes_a_filas(
            data,
            albs,
            mapa_label_por_id=mapa_lbl,
            mapa_prod_por_id=mapa_prod,
            excluir_factura_id=self._compra_documento_id or None,
            igic_default=float(self._igic_default(data)),
        )
        # Evitar duplicar líneas ya incorporadas del mismo albarán
        existentes = {
            (r.get(grid.META_ALB_DOC), r.get(grid.META_ALB_LN))
            for r in self._compra_lineas
        }
        added = 0
        for row in nuevos:
            key = (row.get(grid.META_ALB_DOC), row.get(grid.META_ALB_LN))
            if key in existentes and key[0]:
                continue
            if self._compra_ubicacion_entrada_id and not row.get("ubicacion_destino_id"):
                row["ubicacion_destino_id"] = self._compra_ubicacion_entrada_id
            self._compra_lineas.append(row)
            added += 1
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Incorporadas {added} línea(s) de {len(albs)} albarán(es)."
        )
        self._espacio = "recepcion"
        return self.screen()

    def guardar_borrador_compra(self) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if not self._compra_proveedor_id:
            self._feedback = map_error_recuperable("Indique proveedor.")
            return self.screen()
        if not self._compra_lineas:
            self._feedback = map_error_recuperable("Añada al menos una línea.")
            return self.screen()
        r = self._persistir_borrador_compra()
        if r.ok and r.documento is not None:
            self._compra_documento_id = r.documento.id
            self._feedback = map_resultado(True, r.mensaje or "Borrador guardado.")
        else:
            self._feedback = map_resultado(False, r.mensaje or "No se pudo guardar.")
        self._espacio = "recepcion"
        return self.screen()

    def confirmar_compra_borrador(self) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Confirmación en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        self._confirmando = True
        try:
            if not self._compra_documento_id:
                if not self._compra_proveedor_id or not self._compra_lineas:
                    self._feedback = map_error_recuperable(
                        "Indique proveedor y líneas, o cargue un borrador."
                    )
                    return self.screen()
                r = self._persistir_borrador_compra()
                if not r.ok or r.documento is None:
                    self._feedback = map_resultado(False, r.mensaje or "Error al guardar.")
                    return self.screen()
                self._compra_documento_id = r.documento.id
            data = get_container().app_data_store.get()
            doc = next(
                (d for d in (data.documentos or []) if d.id == self._compra_documento_id),
                None,
            )
            if doc is None:
                self._feedback = map_error_recuperable("Documento no encontrado.")
                return self.screen()
            conc = self._conciliaciones_propuestas(data, doc)
            h = compra_registro_service.construir_hash_documento(
                doc, conciliaciones=conc or None
            )
            token = current_idempotency_token(_IDEMP_COMPRA)
            res = compra_registro_service.confirmar_compra(
                self._compra_documento_id,
                confirmacion_id=token,
                contenido_hash=h,
                json_path=get_demo_file(),
                conciliaciones_propuestas=conc or None,
            )
            if res.ok:
                rotate_idempotency_token(_IDEMP_COMPRA)
                self._reset_compra_draft()
                msg = res.mensaje or "Compra confirmada."
                if res.alerta_precio:
                    msg = f"{msg} · {'; '.join(res.alerta_precio)}"
                self._feedback = map_resultado(True, msg)
            else:
                if res.codigo == compra_registro_service.CONFIRMACION_IDEMPOTENTE:
                    rotate_idempotency_token(_IDEMP_COMPRA)
                    self._reset_compra_draft()
                    self._feedback = map_resultado(True, res.mensaje or "Ya confirmado.")
                else:
                    self._feedback = map_resultado(False, res.mensaje or "Error al confirmar.")
        finally:
            self._confirmando = False
        self._espacio = "recepcion"
        return self.screen()

    def cargar_borrador_compra(self, documento_id: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        did = (documento_id or "").strip()
        data = get_container().app_data_store.get()
        doc = next((d for d in (data.documentos or []) if d.id == did), None)
        if doc is None:
            self._feedback = map_error_recuperable("Borrador no encontrado.")
            return self.screen()
        estado = (
            doc.estado.value if hasattr(doc.estado, "value") else str(doc.estado)
        )
        if estado != EstadoDocumento.BORRADOR.value:
            self._feedback = map_error_recuperable("Solo se cargan borradores.")
            return self.screen()
        tipo = doc.tipo.value if hasattr(doc.tipo, "value") else str(doc.tipo)
        mapa_prod = {p.id: p for p in data.productos}
        mapa_lbl = {p.id: p.nombre for p in data.productos}
        self._compra_documento_id = doc.id
        self._compra_tipo = tipo
        self._compra_proveedor_id = getattr(doc, "proveedor_id", None) or ""
        self._compra_referencia = getattr(doc, "referencia_externa", None) or ""
        self._compra_notas = getattr(doc, "notas", None) or ""
        self._compra_descuento_cabecera = str(
            getattr(doc, "descuento_cabecera_importe", None) or 0
        )
        self._compra_ubicacion_entrada_id = (
            getattr(doc, "ubicacion_entrada_id", None) or ""
        )
        self._compra_lineas = grid.lineas_documento_a_filas(
            doc, mapa_prod_por_id=mapa_prod, mapa_label_por_id=mapa_lbl
        )
        self._albaranes_seleccionados = []
        self._feedback = FeedbackVM(ok=True, mensaje=f"Borrador {doc.id} cargado.")
        self._espacio = "recepcion"
        return self.screen()

    def anular_borrador_compra(self, documento_id: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        did = (documento_id or "").strip()
        if not did:
            self._feedback = map_error_recuperable("Seleccione un borrador a anular.")
            return self.screen()
        from app.core.services.persistencia_appdata import transactional_update_appdata
        from datetime import datetime

        holder: dict = {"msg": ""}

        def _mutate(data):
            d = next((x for x in (data.documentos or []) if x.id == did), None)
            if d is None:
                raise RuntimeError("Borrador no encontrado.")
            est = (
                d.estado.value if hasattr(d.estado, "value") else str(d.estado)
            ).lower()
            if est != "borrador":
                raise RuntimeError("Solo se anulan borradores aquí.")
            d.estado = EstadoDocumento.ANULADO
            d.anulado_en = datetime.now()
            d.motivo_anulacion = "Borrador descartado desde Terminal Inventario"
            holder["msg"] = f"Borrador {did} anulado."
            return data

        try:
            transactional_update_appdata(get_demo_file(), _mutate)
            reload_from_disk()
            if self._compra_documento_id == did:
                self._reset_compra_draft()
            self._feedback = FeedbackVM(ok=True, mensaje=holder["msg"])
        except RuntimeError as exc:
            self._feedback = map_error_recuperable(str(exc))
        self._espacio = "recepcion"
        return self.screen()

    def crear_rectificativa(
        self, documento_id: str, motivo: str = "Rectificación"
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = rectificativa_service.crear_borrador_rectificativa(
            (documento_id or "").strip(),
            motivo=(motivo or "").strip() or "Rectificación desde Terminal Inventario",
        )
        if r.ok and r.documento is not None:
            reload_from_disk()
            self._feedback = map_resultado(True, r.mensaje or "Rectificativa creada.")
            self._documento_detalle_id = r.documento.id
        else:
            self._feedback = map_resultado(False, r.mensaje or "No se pudo rectificar.")
        self._espacio = "documentos"
        return self.screen()

    # ── Documentos ────────────────────────────────────────────────────────

    def set_doc_filtros(
        self,
        *,
        texto: str | None = None,
        tipo: str | None = None,
        estado: str | None = None,
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if texto is not None:
            self._doc_filtro_texto = (texto or "").strip()
        if tipo is not None:
            self._doc_filtro_tipo = (tipo or "").strip().lower()
        if estado is not None:
            self._doc_filtro_estado = (estado or "").strip().lower()
        self._espacio = "documentos"
        return self.screen()

    def seleccionar_documento(self, documento_id: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        self._documento_detalle_id = (documento_id or "").strip() or None
        self._espacio = "documentos"
        return self.screen()

    def anular_documento_confirmado(
        self, documento_id: str, motivo: str
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Operación en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        self._confirmando = True
        try:
            r = anulacion_documento_service.anular_documento_confirmado(
                (documento_id or "").strip(),
                motivo=(motivo or "").strip() or "Anulación desde Terminal Inventario",
                json_path=get_demo_file(),
                actor=session_bridge.current_session_vm().actor_label or "Inventario",
            )
            self._feedback = map_resultado(r.ok, r.mensaje)
            if r.ok:
                reload_from_disk()
                self._documento_detalle_id = documento_id
        finally:
            self._confirmando = False
        self._espacio = "documentos"
        return self.screen()

    # ── Maestros ──────────────────────────────────────────────────────────

    def crear_departamento_maestro(self, nombre: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = catalogo_service.crear_departamento(nombre)
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "departamentos"
        self._espacio = "maestros"
        return self.screen()

    def renombrar_departamento_maestro(
        self, departamento_id: str, nombre: str
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = catalogo_service.renombrar_departamento(departamento_id, nombre)
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "departamentos"
        self._espacio = "maestros"
        return self.screen()

    def crear_ubicacion_maestro(
        self, nombre: str, codigo: str, tipo: str = "otro"
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = catalogo_service.crear_ubicacion(nombre, codigo=codigo, tipo=tipo)
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "ubicaciones"
        self._espacio = "maestros"
        return self.screen()

    def set_tipo_ubicacion_maestro(
        self, ubicacion_id: str, tipo: str
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = catalogo_service.establecer_tipo_ubicacion(ubicacion_id, tipo)
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "ubicaciones"
        self._espacio = "maestros"
        return self.screen()

    def crear_proveedor_maestro(
        self, nombre_fiscal: str, codigo: str, *, nif_cif: str = ""
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = proveedor_service.crear_proveedor(
            nombre_fiscal, codigo=codigo, nif_cif=nif_cif or None
        )
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "proveedores"
        self._espacio = "maestros"
        return self.screen()

    def crear_impuesto_maestro(
        self, nombre: str, porcentaje: str
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = proveedor_service.crear_impuesto(nombre, porcentaje)
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "impuestos"
        self._espacio = "maestros"
        return self.screen()

    def desactivar_impuesto_maestro(self, impuesto_id: str) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = proveedor_service.desactivar_impuesto(impuesto_id)
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "impuestos"
        self._espacio = "maestros"
        return self.screen()

    def vincular_producto_proveedor_maestro(
        self,
        producto_id: str,
        proveedor_id: str,
        *,
        unidad_compra: str = "",
        factor_compra: str = "1",
        ultimo_precio: str = "",
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        r = proveedor_service.vincular_producto_proveedor(
            producto_id,
            proveedor_id,
            unidad_compra=unidad_compra or None,
            factor_compra=factor_compra or None,
            ultimo_precio_unitario_compra=ultimo_precio or None,
        )
        self._feedback = map_resultado(r.ok, r.mensaje)
        self._maestro_tab = "vinculos"
        self._espacio = "maestros"
        return self.screen()

    # ── Historial ─────────────────────────────────────────────────────────

    def set_historial_filtros(
        self,
        *,
        texto: str | None = None,
        ubicacion_id: str | None = None,
        proveedor_id: str | None = None,
    ) -> InventarioScreenVM:
        if not self._gate_economato():
            return self.screen()
        if texto is not None:
            self._hist_texto = (texto or "").strip()
        if ubicacion_id is not None:
            self._hist_ubicacion_id = (ubicacion_id or "").strip()
        if proveedor_id is not None:
            self._hist_proveedor_id = (proveedor_id or "").strip()
        self._espacio = "historial"
        return self.screen()

    def exportar_historial_csv(self) -> tuple[str, str]:
        """Devuelve (nombre_archivo, contenido_csv)."""
        panel = self._build_economato_panel(get_container().app_data_store.get())
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(
            ["fecha", "tipo", "producto", "ubicacion", "cantidad", "documento", "detalle"]
        )
        for e in panel.historial:
            w.writerow(
                [e.fecha, e.tipo, e.producto, e.ubicacion, e.cantidad, e.documento, e.detalle]
            )
        return f"historial_inventario_{date.today().isoformat()}.csv", buf.getvalue()

    # ── Build panel ───────────────────────────────────────────────────────

    def _build_economato_panel(self, data) -> EconomatoPanelVM:
        if self._espacio not in (
            "maestros",
            "recepcion",
            "documentos",
            "historial",
        ):
            return EconomatoPanelVM()

        proveedores_op = tuple(
            OpcionDocVM(id=p.id, etiqueta=p.nombre_fiscal or p.id)
            for p in (data.proveedores or [])
            if getattr(p, "activo", True)
        )
        ubicaciones_op = tuple(
            OpcionDocVM(
                id=u.id,
                etiqueta=f"{getattr(u, 'codigo', '') or '—'} · {u.nombre}",
            )
            for u in (data.ubicaciones or [])
            if getattr(u, "activo", True)
        )
        productos_op = tuple(
            OpcionDocVM(id=p.id, etiqueta=p.nombre)
            for p in (data.productos or [])
            if getattr(p, "activo", True)
        )[:200]

        lineas_vm = tuple(self._linea_row_to_vm(r) for r in self._compra_lineas)
        totales = self._totales_vm(data)
        borradores = self._borradores_vm(data)
        albs = self._albaranes_vm(data)
        sug = self._sugerencias_producto(data)

        docs: tuple[DocumentoListaVM, ...] = ()
        detalle: DocumentoDetalleVM | None = None
        if self._espacio == "documentos":
            docs = self._documentos_lista_vm(data)
            if self._documento_detalle_id:
                detalle = self._documento_detalle_vm(data, self._documento_detalle_id)

        deps = cats = ()  # noqa: F841 — departamentos only for maestros
        departamentos = tuple(
            DepartamentoMaestroVM(id=d.id, nombre=d.nombre, activo=d.activo)
            for d in (data.departamentos or [])
        )
        ubicaciones_m = tuple(
            UbicacionMaestroVM(
                id=u.id,
                nombre=u.nombre,
                codigo=getattr(u, "codigo", None) or "",
                tipo=getattr(u, "tipo", None) or "otro",
                activo=u.activo,
            )
            for u in (data.ubicaciones or [])
        )
        proveedores_m = tuple(
            ProveedorMaestroVM(
                id=p.id,
                codigo=getattr(p, "codigo", None) or "",
                nombre_fiscal=p.nombre_fiscal or "",
                nif=getattr(p, "nif_cif", None) or "",
                activo=getattr(p, "activo", True),
            )
            for p in (data.proveedores or [])
        )
        impuestos_m = tuple(
            ImpuestoMaestroVM(
                id=i.id,
                nombre=i.nombre,
                porcentaje=str(getattr(i, "porcentaje", "") or ""),
                activo=getattr(i, "activo", True),
            )
            for i in (data.impuestos or [])
        )
        mapa_prod = {p.id: p.nombre for p in (data.productos or [])}
        mapa_prov = {
            p.id: (p.nombre_fiscal or p.id) for p in (data.proveedores or [])
        }
        vinculos_m = tuple(
            VinculoMaestroVM(
                id=r.id,
                producto=mapa_prod.get(r.producto_id, r.producto_id),
                proveedor=mapa_prov.get(r.proveedor_id, r.proveedor_id),
                unidad_compra=getattr(r, "unidad_compra", None) or "",
                factor=str(getattr(r, "factor_compra", "") or ""),
                ultimo_precio=str(
                    getattr(r, "ultimo_precio_unitario_compra", "") or ""
                ),
                activo=getattr(r, "activo", True),
            )
            for r in (data.relaciones_producto_proveedor or [])
        )

        historial: tuple[HistorialEventoVM, ...] = ()
        if self._espacio == "historial":
            historial = self._historial_vm(data)

        return EconomatoPanelVM(
            maestro_tab=self._maestro_tab,
            compra_tipo=self._compra_tipo,
            compra_proveedor_id=self._compra_proveedor_id,
            compra_referencia=self._compra_referencia,
            compra_notas=self._compra_notas,
            compra_descuento_cabecera=self._compra_descuento_cabecera,
            compra_ubicacion_entrada_id=self._compra_ubicacion_entrada_id,
            compra_documento_id=self._compra_documento_id,
            compra_lineas=lineas_vm,
            compra_totales=totales,
            compra_prod_busqueda=self._compra_prod_busqueda,
            compra_prod_sugerencias=sug,
            compra_proveedores=proveedores_op,
            compra_ubicaciones=ubicaciones_op,
            compra_impuestos_default=self._igic_default(data),
            compra_borradores=borradores,
            albaranes_conciliables=albs,
            albaranes_seleccionados=tuple(self._albaranes_seleccionados),
            doc_filtro_texto=self._doc_filtro_texto,
            doc_filtro_tipo=self._doc_filtro_tipo,
            doc_filtro_estado=self._doc_filtro_estado,
            documentos=docs,
            documento_detalle=detalle,
            departamentos=departamentos,
            ubicaciones_maestro=ubicaciones_m,
            proveedores_maestro=proveedores_m,
            impuestos_maestro=impuestos_m,
            vinculos_maestro=vinculos_m,
            productos_opciones=productos_op,
            hist_texto=self._hist_texto,
            hist_ubicacion_id=self._hist_ubicacion_id,
            hist_proveedor_id=self._hist_proveedor_id,
            historial=historial,
        )

    # ── helpers privados ──────────────────────────────────────────────────

    def _reset_compra_draft(self) -> None:
        self._compra_lineas = []
        self._compra_proveedor_id = ""
        self._compra_referencia = ""
        self._compra_notas = ""
        self._compra_descuento_cabecera = "0"
        self._compra_ubicacion_entrada_id = ""
        self._compra_documento_id = ""
        self._compra_tipo = TipoDocumento.ALBARAN.value
        self._compra_prod_busqueda = ""
        self._albaranes_seleccionados = []

    def _igic_default(self, data) -> str:
        activos = [
            i
            for i in (data.impuestos or [])
            if getattr(i, "activo", True)
        ]
        if not activos:
            return "7"
        # Preferir 7% si existe
        for i in activos:
            try:
                if float(i.porcentaje) == 7.0:
                    return "7"
            except (TypeError, ValueError):
                continue
        return str(activos[0].porcentaje)

    def _linea_row_to_vm(self, row: dict) -> CompraLineaDocVM:
        calc = None
        try:
            from app.core.services.money import calcular_linea

            calc = calcular_linea(
                cantidad_compra=grid.celda_numero(row.get("cantidad")),
                precio_unitario_compra=grid.celda_numero(row.get("precio_unitario")),
                factor_conversion=1,
                precio_incluye_igic=bool(row.get("incluye_igic")),
                impuesto_porcentaje=grid.celda_numero(row.get("igic_pct")),
                descuento_linea_porcentaje=grid.celda_numero(row.get("dto_pct")),
                descuento_linea_importe=grid.celda_numero(row.get("dto_eur")),
            )
        except Exception:  # noqa: BLE001
            calc = None
        total = (
            grid.formatear_numero_es(calc.total_linea)
            if calc is not None
            else "0,00"
        )
        return CompraLineaDocVM(
            key=str(row.get(grid.META_KEY) or ""),
            producto_id=str(row.get(grid.META_PROD_ID) or ""),
            producto_nombre=str(row.get("producto") or ""),
            cantidad=grid.formatear_numero_es(row.get("cantidad")),
            unidad=str(row.get("unidad") or "Ud"),
            precio_unitario=grid.formatear_numero_es(row.get("precio_unitario")),
            dto_pct=grid.formatear_numero_es(row.get("dto_pct")),
            dto_eur=grid.formatear_numero_es(row.get("dto_eur")),
            igic_pct=grid.formatear_numero_es(row.get("igic_pct")),
            incluye_igic=bool(row.get("incluye_igic")),
            total_linea=total,
            ubicacion_destino_id=str(row.get("ubicacion_destino_id") or ""),
            documento_origen_id=str(row.get(grid.META_ALB_DOC) or ""),
            linea_origen_id=str(row.get(grid.META_ALB_LN) or ""),
        )

    def _totales_vm(self, data) -> TotalesCompraVM | None:
        if not self._compra_lineas:
            return TotalesCompraVM("0,00", "0,00", "0,00", self._compra_descuento_cabecera)
        mapa_prod = {p.id: p for p in data.productos}
        res = grid.calcular_totales_grid(
            self._compra_lineas,
            descuento_cabecera=self._compra_descuento_cabecera,
            mapa_prod_por_id=mapa_prod,
            data=data,
            proveedor_id=self._compra_proveedor_id or None,
        )
        d = grid.totales_a_dict(res)
        return TotalesCompraVM(
            base_imponible=d["base_imponible"],
            impuesto_total=d["impuesto_total"],
            total=d["total_documento"],
            descuento_cabecera=grid.formatear_numero_es(self._compra_descuento_cabecera),
        )

    def _borradores_vm(self, data) -> tuple[DocumentoListaVM, ...]:
        items: list[DocumentoListaVM] = []
        for d in data.documentos or []:
            estado = d.estado.value if hasattr(d.estado, "value") else str(d.estado)
            tipo = d.tipo.value if hasattr(d.tipo, "value") else str(d.tipo)
            if estado != EstadoDocumento.BORRADOR.value:
                continue
            if tipo not in (
                TipoDocumento.ALBARAN.value,
                TipoDocumento.FACTURA.value,
            ):
                continue
            items.append(self._doc_lista_item(d, data))
        return tuple(items[:40])

    def _albaranes_vm(self, data) -> tuple[AlbaranConciliableVM, ...]:
        if (
            self._compra_tipo != TipoDocumento.FACTURA.value
            or not self._compra_proveedor_id
        ):
            return ()
        sel = set(self._albaranes_seleccionados)
        out: list[AlbaranConciliableVM] = []
        for a in grid.albaranes_conciliables(
            data,
            proveedor_id=self._compra_proveedor_id,
            excluir_factura_id=self._compra_documento_id or None,
        ):
            out.append(
                AlbaranConciliableVM(
                    id=a.id,
                    etiqueta=grid.etiqueta_albaran(a),
                    referencia=getattr(a, "referencia_externa", None) or "",
                    total=str(getattr(a, "total_documento", None) or ""),
                    seleccionado=a.id in sel,
                )
            )
        return tuple(out)

    def _sugerencias_producto(self, data) -> tuple[OpcionDocVM, ...]:
        q = (self._compra_prod_busqueda or "").strip()
        if len(q) < 2:
            return ()
        sug: list[OpcionDocVM] = []
        for p in data.productos or []:
            if not getattr(p, "activo", True):
                continue
            codigo = getattr(p, "codigo", None) or ""
            if contiene_texto(p.nombre or "", q) or contiene_texto(codigo, q):
                sug.append(OpcionDocVM(id=p.id, etiqueta=f"{codigo} · {p.nombre}" if codigo else p.nombre))
            if len(sug) >= 12:
                break
        return tuple(sug)

    def _documentos_lista_vm(self, data) -> tuple[DocumentoListaVM, ...]:
        filtro = FiltroDocumentos(
            texto=self._doc_filtro_texto or None,
            tipo=self._doc_filtro_tipo or None,
            estado=self._doc_filtro_estado or None,
        )
        try:
            docs = documento_consulta_service.buscar_documentos(filtro, data=data)
        except Exception as exc:  # noqa: BLE001
            self._feedback = map_error_recuperable(str(exc))
            return ()
        return tuple(self._doc_lista_item(d, data) for d in docs[:80])

    def _doc_lista_item(self, d, data) -> DocumentoListaVM:
        tipo = d.tipo.value if hasattr(d.tipo, "value") else str(d.tipo)
        estado = d.estado.value if hasattr(d.estado, "value") else str(d.estado)
        prov = getattr(d, "proveedor_nombre_snapshot", None) or ""
        if not prov and getattr(d, "proveedor_id", None):
            p = next(
                (x for x in (data.proveedores or []) if x.id == d.proveedor_id),
                None,
            )
            prov = p.nombre_fiscal if p else d.proveedor_id
        fecha = ""
        fd = getattr(d, "fecha_documento", None)
        if fd is not None:
            fecha = fd.isoformat() if hasattr(fd, "isoformat") else str(fd)
        return DocumentoListaVM(
            id=d.id,
            tipo=tipo,
            estado=estado,
            proveedor=prov or "—",
            referencia=getattr(d, "referencia_externa", None) or "",
            fecha=fecha,
            total=str(getattr(d, "total_documento", None) or "—"),
            lineas=len(getattr(d, "lineas", None) or []),
        )

    def _documento_detalle_vm(self, data, documento_id: str) -> DocumentoDetalleVM | None:
        doc = next((d for d in (data.documentos or []) if d.id == documento_id), None)
        if doc is None:
            return None
        tipo = doc.tipo.value if hasattr(doc.tipo, "value") else str(doc.tipo)
        estado = doc.estado.value if hasattr(doc.estado, "value") else str(doc.estado)
        mapa = {p.id: p.nombre for p in (data.productos or [])}
        lineas = tuple(
            DocumentoDetalleLineaVM(
                producto=mapa.get(ln.producto_id, ln.producto_id),
                cantidad=str(
                    getattr(ln, "cantidad_compra", None) or ln.cantidad or ""
                ),
                precio_unitario=str(
                    getattr(ln, "precio_unitario_compra", None) or ""
                ),
                igic=str(getattr(ln, "cuota_impuesto", None) or ""),
                total=str(
                    getattr(ln, "total_linea", None)
                    or getattr(ln, "precio_total", None)
                    or ""
                ),
                origen_albaran=getattr(ln, "documento_origen_id", None) or "",
            )
            for ln in (doc.lineas or [])
        )
        fecha = ""
        fd = getattr(doc, "fecha_documento", None)
        if fd is not None:
            fecha = fd.isoformat() if hasattr(fd, "isoformat") else str(fd)
        return DocumentoDetalleVM(
            id=doc.id,
            tipo=tipo,
            estado=estado,
            proveedor=getattr(doc, "proveedor_nombre_snapshot", None) or "—",
            referencia=getattr(doc, "referencia_externa", None) or "",
            fecha=fecha,
            notas=getattr(doc, "notas", None) or "",
            base=str(getattr(doc, "base_imponible", None) or "—"),
            impuesto=str(getattr(doc, "impuesto_total", None) or "—"),
            total=str(getattr(doc, "total_documento", None) or "—"),
            lineas=lineas,
        )

    def _historial_vm(self, data) -> tuple[HistorialEventoVM, ...]:
        mapa_prod = {p.id: p.nombre for p in (data.productos or [])}
        mapa_ubi = {u.id: u.nombre for u in (data.ubicaciones or [])}
        q = (self._hist_texto or "").strip().casefold()
        ubi_f = self._hist_ubicacion_id
        eventos: list[HistorialEventoVM] = []

        for m in reversed(list(data.movimientos or [])):
            tipo = (
                m.tipo.value if hasattr(getattr(m, "tipo", None), "value") else str(getattr(m, "tipo", ""))
            )
            pid = getattr(m, "producto_id", None) or ""
            uid = getattr(m, "ubicacion_id", None) or ""
            prod = mapa_prod.get(pid, pid)
            ubi = mapa_ubi.get(uid, uid or "—")
            if ubi_f and uid != ubi_f:
                continue
            if q and q not in (prod or "").casefold() and q not in (tipo or "").casefold():
                continue
            fecha = ""
            fd = getattr(m, "fecha", None) or getattr(m, "creado_en", None)
            if fd is not None:
                fecha = fd.isoformat() if hasattr(fd, "isoformat") else str(fd)
            eventos.append(
                HistorialEventoVM(
                    fecha=fecha[:19],
                    tipo=tipo,
                    producto=prod or "—",
                    ubicacion=ubi,
                    cantidad=str(getattr(m, "cantidad", "") or ""),
                    documento=getattr(m, "documento_id", None) or "",
                    detalle=getattr(m, "motivo", None)
                    or getattr(m, "comentario", None)
                    or "",
                )
            )
            if len(eventos) >= 120:
                break

        # Documentos recientes si filtro proveedor
        if self._hist_proveedor_id or q:
            for d in reversed(list(data.documentos or [])):
                if self._hist_proveedor_id and getattr(d, "proveedor_id", None) != self._hist_proveedor_id:
                    continue
                tipo = d.tipo.value if hasattr(d.tipo, "value") else str(d.tipo)
                ref = getattr(d, "referencia_externa", None) or d.id
                if q and q not in ref.casefold() and q not in tipo.casefold():
                    continue
                fecha = ""
                fd = getattr(d, "fecha_documento", None)
                if fd is not None:
                    fecha = fd.isoformat() if hasattr(fd, "isoformat") else str(fd)
                eventos.append(
                    HistorialEventoVM(
                        fecha=fecha,
                        tipo=f"doc:{tipo}",
                        producto="—",
                        ubicacion="—",
                        cantidad=str(len(d.lineas or [])),
                        documento=d.id,
                        detalle=ref,
                    )
                )
                if len(eventos) >= 160:
                    break

        eventos.sort(key=lambda e: e.fecha, reverse=True)
        return tuple(eventos[:120])

    def _resolver_producto_compra(self, texto: str):
        raw = (texto or "").strip()
        if not raw:
            return None, "Indique código o nombre de producto."
        data = get_container().app_data_store.get()
        activos = [p for p in (data.productos or []) if getattr(p, "activo", True)]
        by_id = next((p for p in activos if p.id == raw), None)
        if by_id is not None:
            return by_id, None
        key = raw.casefold()
        by_cod = [
            p
            for p in activos
            if (getattr(p, "codigo", None) or "").strip().casefold() == key
        ]
        if len(by_cod) == 1:
            return by_cod[0], None
        if len(by_cod) > 1:
            return None, "Código ambiguo; use el selector."
        matches = [
            p
            for p in activos
            if contiene_texto(p.nombre or "", raw)
            or contiene_texto(getattr(p, "codigo", None) or "", raw)
        ]
        if len(matches) == 1:
            return matches[0], None
        if not matches:
            return None, "Sin coincidencias de producto."
        return (
            None,
            f"{len(matches)} coincidencias: elija una sugerencia.",
        )

    def _persistir_borrador_compra(self):
        data = get_container().app_data_store.get()
        mapa_prod = {p.id: p for p in data.productos}
        mapa_lbl = {p.id: p.nombre for p in data.productos}
        # Asegurar labels en filas
        rows = []
        for r in self._compra_lineas:
            row = dict(r)
            pid = row.get(grid.META_PROD_ID)
            if pid and not row.get("producto"):
                row["producto"] = mapa_lbl.get(pid, pid)
            rows.append(row)
        lineas = grid.filas_a_payload_lineas(rows, mapa_prod_por_label={
            mapa_lbl[pid]: mapa_prod[pid] for pid in mapa_prod
        })
        # Completar ubicaciones / origen albarán desde meta
        for i, raw in enumerate(lineas):
            if i < len(rows):
                row = rows[i]
                if row.get("ubicacion_destino_id"):
                    raw["ubicacion_destino_id"] = row["ubicacion_destino_id"]
                elif self._compra_ubicacion_entrada_id:
                    raw["ubicacion_destino_id"] = self._compra_ubicacion_entrada_id
                if row.get(grid.META_ALB_DOC):
                    raw["documento_origen_id"] = row[grid.META_ALB_DOC]
                if row.get(grid.META_ALB_LN):
                    raw["linea_origen_id"] = row[grid.META_ALB_LN]
        return compra_registro_service.guardar_borrador_persistente(
            json_path=get_demo_file(),
            tipo=self._compra_tipo or TipoDocumento.ALBARAN.value,
            proveedor_id=self._compra_proveedor_id,
            referencia_externa=self._compra_referencia or None,
            notas=self._compra_notas or None,
            descuento_cabecera_importe=self._compra_descuento_cabecera or 0,
            ubicacion_entrada_id=self._compra_ubicacion_entrada_id or None,
            lineas=lineas,
            documento_id=self._compra_documento_id or None,
        )

    def _conciliaciones_propuestas(self, data, doc) -> list[dict]:
        if (
            (self._compra_tipo or "") != TipoDocumento.FACTURA.value
            and str(getattr(doc.tipo, "value", doc.tipo)) != TipoDocumento.FACTURA.value
        ):
            return []
        props: list[dict] = []
        for ln in doc.lineas or []:
            alb_ln = getattr(ln, "linea_origen_id", None)
            clk = getattr(ln, "client_line_key", None)
            if not alb_ln or not clk:
                continue
            qty = getattr(ln, "cantidad_compra", None)
            if qty is None:
                qty = ln.cantidad
            props.append(
                {
                    "linea_factura_client_key": str(clk),
                    "linea_albaran_id": alb_ln,
                    "cantidad_conciliada": str(qty),
                }
            )
        return props
