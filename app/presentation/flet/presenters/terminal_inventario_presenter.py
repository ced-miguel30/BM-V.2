"""Presenter Terminal Inventario ? alertas, caducidad, merma, stock,
traslados, recuentos, ajustes y economato (recepci?n/documentos/maestros/historial).
"""

from __future__ import annotations

from datetime import date

from app.bootstrap import get_container
from app.core.application.idempotency import (
    current_idempotency_token,
    rotate_idempotency_token,
)
from app.core.auth.permissions import AuthorizationError
from app.core.models import EstadoAlerta, MotivoAjuste, MotivoMerma, TipoDocumento
from app.core.models.enums import (
    ORIGEN_SERVICIO_MERMA_LABEL,
    TURNO_MERMA_LABEL,
    OrigenServicioMerma,
    TurnoMerma,
)
from app.core.services import (
    alert_service,
    ajuste_service,
    caducidad_service,
    merma_service,
    recuento_service,
    traslado_service,
)
from app.core.models.recuento import EstadoRecuento
from app.core.services.ubicacion_stock_service import (
    SIN_UBICACION_HISTORICA,
    saldo_en_ubicacion,
    saldos_por_ubicacion_lote,
)
from app.presentation.flet import session_bridge
from app.presentation.flet.inventory_viewmodels import (
    ESPACIOS,
    ESPACIOS_ECONOMATO,
    ESPACIOS_OPS,
    ETIQUETA_SIN_UBICACION_HISTORICA,
    AlertaVM,
    AjustePreviewVM,
    EspacioVM,
    InventarioScreenVM,
    LoteAjusteVM,
    LoteCaducidadVM,
    MermaLineaVM,
    MermaOpcionVM,
    RecuentoLineaVM,
    RecuentoPendienteVM,
    RecuentoPreviewVM,
    RecuentoRecienteVM,
    StockSaldoVM,
    TrasladoOpcionVM,
    TrasladoPreviewVM,
    TrasladoRecienteVM,
    assert_inventario_sin_economia,
)
from app.presentation.flet.mappers import (
    MermaLineaOperativa,
    map_error_recuperable,
    map_merma_registro_feedback,
    map_resultado,
)
from app.presentation.flet.presenters.inventario_economato_mixin import (
    InventarioEconomatoMixin,
)
from app.presentation.flet.viewmodels import FeedbackVM

_ETIQUETAS = {
    "compras_panel": "Panel",
    "compras_albaran": "Albarán",
    "compras_factura": "Factura",
    "compras_documentos": "Documentos",
    "compras_proveedores": "Maestros",
    "compras_historial": "Historial",
    "alertas": "Alertas",
    "caducidad": "Caducidad",
    "merma": "Merma",
    "stock": "Stock",
    "traslados": "Traslados",
    "recuentos": "Recuentos",
    "ajustes": "Ajustes",
}

_IDEMP_AJUSTE = "flet_inv_ajuste"
_IDEMP_MERMA = "flet_inv_merma"
_IDEMP_TRASLADO = "flet_inv_traslado"
_IDEMP_RECUENTO = "flet_inv_recuento"  # solo anti doble clic UI; sin clave de sesi?n

_COBERTURA_ETIQUETA = {
    "sin_ubicacion_historica": "Sin ubicaci?n hist?rica",
    "cobertura_parcial": "Cobertura parcial",
    "cobertura_completa": "Cobertura completa",
    "sin_movimientos": "Sin movimientos de ubicaci?n",
}


class TerminalInventarioPresenter(InventarioEconomatoMixin):
    def __init__(self) -> None:
        self._espacio = "alertas"
        self._feedback: FeedbackVM | None = None
        self._confirmando = False
        self._ajuste_preview: AjustePreviewVM | None = None
        self._ajuste_draft: dict | None = None
        self._responsable_seleccionado: str | None = None
        self._stock_busqueda = ""
        self._stock_filtro_ubicacion: str | None = None
        self._init_economato_state()
        self._traslado_producto_id: str | None = None
        self._traslado_lote_id: str | None = None
        self._traslado_origen_id: str | None = None
        self._traslado_destino_id: str | None = None
        self._traslado_cantidad = ""
        self._traslado_preview: TrasladoPreviewVM | None = None
        self._traslado_draft: dict | None = None
        self._rc_ubicacion_id: str | None = None
        self._rc_producto_id: str | None = None
        self._rc_lote_id: str | None = None
        self._rc_cantidad = ""
        self._rc_lineas: list[dict] = []
        self._rc_preview: RecuentoPreviewVM | None = None
        self._rc_pendiente_id: str | None = None
        self._rc_requiere_confirmacion_borrador = False
        self._rc_aviso_borrador = ""
        self._rc_motivo: str | None = None
        assert_inventario_sin_economia(
            AlertaVM,
            LoteCaducidadVM,
            MermaLineaVM,
            AjustePreviewVM,
            StockSaldoVM,
            TrasladoPreviewVM,
            TrasladoRecienteVM,
            RecuentoLineaVM,
            RecuentoPreviewVM,
            RecuentoPendienteVM,
            RecuentoRecienteVM,
        )

    def entrar(self) -> InventarioScreenVM:
        session, fb = session_bridge.enter_terminal_inventario()
        self._feedback = fb
        if session.authenticated:
            try:
                alert_service.sincronizar_alertas()
            except Exception as exc:  # noqa: BLE001
                self._feedback = map_error_recuperable(
                    f"No se pudieron sincronizar alertas: {exc}"
                )
        return self.screen()

    def denegar_demo(self, role: str) -> InventarioScreenVM:
        _, fb = session_bridge.deny_foreign_role(role)
        self._feedback = fb
        return self.screen()

    def logout(self) -> InventarioScreenVM:
        session_bridge.logout_terminal()
        self._feedback = FeedbackVM(ok=True, mensaje="Sesi?n cerrada.")
        self._confirmando = False
        self._ajuste_preview = None
        self._ajuste_draft = None
        self._responsable_seleccionado = None
        self._limpiar_traslado()
        # Memoria de recuento; el borrador persistido (si existe) permanece pendiente.
        self._limpiar_recuento_memoria(conservar_aviso_pendiente=True)
        return self.screen()

    def seleccionar_espacio(self, espacio_id: str) -> InventarioScreenVM:
        if espacio_id not in ESPACIOS:
            self._feedback = map_error_recuperable("Espacio no reconocido.")
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        aviso_abandon: FeedbackVM | None = None
        if espacio_id != self._espacio:
            self._responsable_seleccionado = None
            if self._espacio == "traslados":
                self._limpiar_traslado_preview_only()
            if self._espacio == "recuentos" and espacio_id != "recuentos":
                aviso_abandon = self._al_abandonar_recuentos()
        self._espacio = espacio_id
        if espacio_id == "compras_albaran":
            self._compra_tipo = TipoDocumento.ALBARAN.value
            self._albaranes_seleccionados = []
        elif espacio_id == "compras_factura":
            self._compra_tipo = TipoDocumento.FACTURA.value
        elif espacio_id == "compras_proveedores":
            self._maestro_tab = "proveedores"
        self._ajuste_preview = None
        self._ajuste_draft = None
        self._feedback = aviso_abandon or FeedbackVM(
            ok=True, mensaje=f"Espacio: {_ETIQUETAS[espacio_id]}"
        )
        if espacio_id == "alertas":
            alert_service.sincronizar_alertas()
        return self.screen()

    def seleccionar_responsable(self, responsable_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        rid = (responsable_id or "").strip() or None
        if rid is None:
            self._responsable_seleccionado = None
            return self.screen()
        activos = {r.id for r in merma_service.listar_responsables_merma(solo_activos=True)}
        if rid not in activos:
            self._responsable_seleccionado = None
            self._feedback = map_error_recuperable(
                "Seleccione un responsable activo.", codigo="VALIDACION"
            )
            return self.screen()
        self._responsable_seleccionado = rid
        return self.screen()

    # --- Alertas ------------------------------------------------------------

    def marcar_alerta(self, alerta_id: str, estado: str) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        r = alert_service.cambiar_estado_alerta(alerta_id, estado)
        self._feedback = map_resultado(r.ok, r.mensaje)
        if r.ok:
            alert_service.sincronizar_alertas()
        return self.screen()

    # --- Caducidad ----------------------------------------------------------

    def enviar_caducidad_a_merma(
        self,
        lote_id: str,
        cantidad: float,
        *,
        servicio: str = "general",
        turno: str = "manana",
        responsable_id: str | None = None,
        comentario: str = "",
    ) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        resp_id, resp_nombre = self._resolver_responsable(responsable_id)
        if not resp_id:
            self._feedback = map_error_recuperable(
                "Selecciona un responsable.", codigo="VALIDACION"
            )
            return self.screen()
        r = caducidad_service.registrar_salida_caducidad(
            lote_id,
            float(cantidad),
            tipo_servicio_snapshot=servicio,
            turno_snapshot=turno,
            responsable_id=resp_id,
            responsable_nombre=resp_nombre,
            comentario=comentario or None,
        )
        self._feedback = map_resultado(r.ok, r.mensaje)
        if r.ok:
            self._espacio = "merma"
        return self.screen()

    # --- Merma --------------------------------------------------------------

    def anadir_merma(
        self,
        lote_id: str,
        cantidad: float,
        motivo: str,
        *,
        servicio: str = "general",
        turno: str = "manana",
        responsable_id: str | None = None,
        comentario: str = "",
    ) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        resp_id, resp_nombre = self._resolver_responsable(responsable_id)
        if not resp_id:
            self._feedback = map_error_recuperable(
                "Selecciona un responsable.", codigo="VALIDACION"
            )
            return self.screen()
        r = merma_service.anadir_a_cesta_merma(
            lote_id,
            float(cantidad),
            motivo,
            servicio,
            comentario or None,
            turno_snapshot=turno,
            responsable_id=resp_id,
            responsable_nombre=resp_nombre,
        )
        self._feedback = map_resultado(r.ok, r.mensaje)
        return self.screen()

    def vaciar_cesta_merma(self) -> InventarioScreenVM:
        merma_service.limpiar_cesta_merma()
        self._feedback = FeedbackVM(ok=True, mensaje="Cesta de merma vaciada.")
        return self.screen()

    def confirmar_merma(self, *, fecha: date | None = None) -> InventarioScreenVM:
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Confirmaci?n en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable(
                "Sesi?n no autorizada.", codigo="DENEGADO"
            )
            return self.screen()
        cesta = merma_service.get_cesta_merma()
        if not cesta:
            self._feedback = map_merma_registro_feedback(
                ok=False, mensaje_backend="La cesta est? vac?a."
            )
            return self.screen()
        lineas_ops = tuple(
            MermaLineaOperativa(
                nombre=i.nombre,
                cantidad=float(i.cantidad),
                unidad=i.unidad,
                lote_id=i.lote_id,
                motivo=i.motivo,
                servicio=merma_service.etiqueta_servicio_merma(i.tipo_servicio_snapshot),
                responsable=i.responsable_nombre or "",
            )
            for i in cesta
        )
        self._confirmando = True
        try:
            _ = current_idempotency_token(_IDEMP_MERMA)
            r = merma_service.registrar_merma(fecha or date.today())
            if r.ok:
                rotate_idempotency_token(_IDEMP_MERMA)
                self._responsable_seleccionado = None
                self._feedback = map_merma_registro_feedback(
                    ok=True, lineas=lineas_ops
                )
            else:
                self._feedback = map_merma_registro_feedback(
                    ok=False,
                    mensaje_backend=r.mensaje,
                    codigo=getattr(r, "codigo", None),
                    lineas=lineas_ops,
                )
        finally:
            self._confirmando = False
        return self.screen()

    # --- Stock (lectura) ----------------------------------------------------

    def set_stock_busqueda(self, texto: str) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._stock_busqueda = (texto or "").strip()
        return self.screen()

    def set_stock_filtro_ubicacion(self, ubicacion_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        uid = (ubicacion_id or "").strip() or None
        if uid == "__todas__":
            uid = None
        self._stock_filtro_ubicacion = uid
        return self.screen()

    # --- Traslados ----------------------------------------------------------

    def set_traslado_producto(self, producto_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._traslado_producto_id = (producto_id or "").strip() or None
        self._traslado_lote_id = None
        self._traslado_origen_id = None
        self._traslado_destino_id = None
        self._limpiar_traslado_preview_only()
        return self.screen()

    def set_traslado_lote(self, lote_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._traslado_lote_id = (lote_id or "").strip() or None
        self._traslado_origen_id = None
        self._traslado_destino_id = None
        self._limpiar_traslado_preview_only()
        return self.screen()

    def set_traslado_origen(self, ubicacion_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._traslado_origen_id = (ubicacion_id or "").strip() or None
        if (
            self._traslado_destino_id
            and self._traslado_destino_id == self._traslado_origen_id
        ):
            self._traslado_destino_id = None
        self._limpiar_traslado_preview_only()
        return self.screen()

    def set_traslado_destino(self, ubicacion_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        dest = (ubicacion_id or "").strip() or None
        if dest and dest == self._traslado_origen_id:
            self._feedback = map_error_recuperable(
                "Origen y destino deben ser distintos.", codigo="VALIDACION"
            )
            return self.screen()
        self._traslado_destino_id = dest
        self._limpiar_traslado_preview_only()
        return self.screen()

    def set_traslado_cantidad(self, cantidad: str) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._traslado_cantidad = (cantidad or "").strip()
        self._limpiar_traslado_preview_only()
        return self.screen()

    def previsualizar_traslado(self) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        if not (
            self._traslado_lote_id
            and self._traslado_origen_id
            and self._traslado_destino_id
        ):
            self._feedback = map_error_recuperable(
                "Seleccione lote, origen y destino.", codigo="VALIDACION"
            )
            return self.screen()
        if self._traslado_origen_id == self._traslado_destino_id:
            self._feedback = map_error_recuperable(
                "Origen y destino deben ser distintos.", codigo="VALIDACION"
            )
            return self.screen()
        try:
            qty = float(self._traslado_cantidad or "0")
        except ValueError:
            self._feedback = map_error_recuperable(
                "Cantidad no v?lida.", codigo="VALIDACION"
            )
            return self.screen()
        data = get_container().app_data_store.get()
        preview = traslado_service.previsualizar_traslado(
            data,
            lote_id=self._traslado_lote_id,
            ubicacion_origen_id=self._traslado_origen_id,
            ubicacion_destino_id=self._traslado_destino_id,
            cantidad=qty,
        )
        if not preview.ok:
            self._traslado_preview = None
            self._traslado_draft = None
            self._feedback = map_error_recuperable(preview.mensaje)
            return self.screen()
        unidad = self._unidad_producto(data, preview.producto_id)
        self._traslado_preview = TrasladoPreviewVM(
            producto_id=preview.producto_id,
            producto_nombre=preview.producto_nombre,
            lote_id=preview.lote_id,
            ubicacion_origen_id=preview.ubicacion_origen_id,
            ubicacion_origen_etiqueta=self._etiqueta_ubicacion(
                data, preview.ubicacion_origen_id
            ),
            ubicacion_destino_id=preview.ubicacion_destino_id,
            ubicacion_destino_etiqueta=self._etiqueta_ubicacion(
                data, preview.ubicacion_destino_id
            ),
            cantidad=preview.cantidad,
            disponible_origen=preview.disponible_origen,
            unidad=unidad,
            mensaje=preview.mensaje,
            advertencia=preview.advertencia_destino or "",
        )
        self._traslado_draft = {
            "lote_id": preview.lote_id,
            "ubicacion_origen_id": preview.ubicacion_origen_id,
            "ubicacion_destino_id": preview.ubicacion_destino_id,
            "cantidad": float(preview.cantidad),
        }
        assert_inventario_sin_economia(self._traslado_preview)
        self._feedback = FeedbackVM(
            ok=True, mensaje="Revise el resumen y confirme el traslado."
        )
        return self.screen()

    def cancelar_traslado_preview(self) -> InventarioScreenVM:
        self._limpiar_traslado_preview_only()
        self._feedback = FeedbackVM(ok=True, mensaje="Traslado cancelado.")
        return self.screen()

    def confirmar_traslado(self, *, fecha: date | None = None) -> InventarioScreenVM:
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Confirmaci?n en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable(
                "Sesi?n no autorizada.", codigo="DENEGADO"
            )
            return self.screen()
        if not self._traslado_draft or not self._traslado_preview:
            self._feedback = map_error_recuperable(
                "Genere primero el resumen del traslado."
            )
            return self.screen()
        self._confirmando = True
        try:
            # Scope UI (doble env?o). El servicio revalida saldo en confirmar_traslado
            # y genera un traslado_id nuevo; no admite clave_idempotencia.
            _ = current_idempotency_token(_IDEMP_TRASLADO)
            draft = self._traslado_draft
            r = traslado_service.confirmar_traslado(
                lote_id=draft["lote_id"],
                ubicacion_origen_id=draft["ubicacion_origen_id"],
                ubicacion_destino_id=draft["ubicacion_destino_id"],
                cantidad=draft["cantidad"],
                fecha=fecha or date.today(),
            )
            if r.ok:
                rotate_idempotency_token(_IDEMP_TRASLADO)
                self._limpiar_traslado()
                self._feedback = map_resultado(True, r.mensaje)
            else:
                self._feedback = map_resultado(False, r.mensaje)
        finally:
            self._confirmando = False
        return self.screen()

    # --- Recuentos ----------------------------------------------------------

    def set_recuento_ubicacion(self, ubicacion_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        uid = (ubicacion_id or "").strip() or None
        if uid == SIN_UBICACION_HISTORICA:
            self._feedback = map_error_recuperable(
                "No se puede contar en ?sin ubicaci?n hist?rica?.",
                codigo="VALIDACION",
            )
            return self.screen()
        self._rc_ubicacion_id = uid
        self._rc_producto_id = None
        self._rc_lote_id = None
        self._rc_cantidad = ""
        self._rc_lineas = []
        self._rc_preview = None
        return self.screen()

    def set_recuento_producto(self, producto_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._rc_producto_id = (producto_id or "").strip() or None
        self._rc_lote_id = None
        self._rc_cantidad = ""
        self._rc_preview = None
        return self.screen()

    def set_recuento_lote(self, lote_id: str | None) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._rc_lote_id = (lote_id or "").strip() or None
        self._rc_cantidad = ""
        self._rc_preview = None
        return self.screen()

    def set_recuento_cantidad(self, cantidad: str) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._rc_cantidad = (cantidad or "").strip()
        self._rc_preview = None
        return self.screen()

    def anadir_linea_recuento(self) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        if self._rc_pendiente_id and self._rc_requiere_confirmacion_borrador:
            self._feedback = map_error_recuperable(
                "Hay un borrador pendiente de confirmaci?n autoritativa.",
                codigo="VALIDACION",
            )
            return self.screen()
        if not (self._rc_ubicacion_id and self._rc_producto_id and self._rc_lote_id):
            self._feedback = map_error_recuperable(
                "Seleccione ubicaci?n, producto y lote.", codigo="VALIDACION"
            )
            return self.screen()
        try:
            cont = float(self._rc_cantidad or "")
        except ValueError:
            self._feedback = map_error_recuperable(
                "Cantidad contada no v?lida.", codigo="VALIDACION"
            )
            return self.screen()
        if cont < 0:
            self._feedback = map_error_recuperable(
                "No se permiten cantidades negativas.", codigo="VALIDACION"
            )
            return self.screen()
        cont = round(cont, 4)
        for ln in self._rc_lineas:
            if ln["lote_id"] == self._rc_lote_id and ln["producto_id"] == self._rc_producto_id:
                self._feedback = map_error_recuperable(
                    "Esa combinaci?n producto/lote ya est? en el recuento.",
                    codigo="VALIDACION",
                )
                return self.screen()
        data = get_container().app_data_store.get()
        lote = next((l for l in data.lotes if l.id == self._rc_lote_id), None)
        if lote is None or getattr(lote, "anulado", False):
            self._feedback = map_error_recuperable("Lote inexistente o anulado.")
            return self.screen()
        if lote.producto_id != self._rc_producto_id:
            self._feedback = map_error_recuperable("Producto no coincide con el lote.")
            return self.screen()
        esperado = round(saldo_en_ubicacion(data, lote.id, self._rc_ubicacion_id), 4)
        prod = next((p for p in data.productos if p.id == self._rc_producto_id), None)
        unidad = self._unidad_producto(data, self._rc_producto_id)
        nombre = getattr(prod, "nombre", None) or self._rc_producto_id
        diff = round(cont - esperado, 4)
        self._rc_lineas.append(
            {
                "producto_id": self._rc_producto_id,
                "producto_nombre": nombre,
                "lote_id": lote.id,
                "unidad": unidad,
                "cantidad_esperada": esperado,
                "cantidad_contada": cont,
                "diferencia": diff,
            }
        )
        self._rc_lote_id = None
        self._rc_cantidad = ""
        self._rc_preview = None
        self._feedback = FeedbackVM(ok=True, mensaje="L?nea a?adida al recuento.")
        return self.screen()

    def quitar_linea_recuento(self, lote_id: str) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        self._rc_lineas = [ln for ln in self._rc_lineas if ln["lote_id"] != lote_id]
        self._rc_preview = None
        return self.screen()

    def previsualizar_recuento(self) -> InventarioScreenVM:
        """Preview orientativo en memoria. No llama a crear_borrador."""
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        if self._rc_pendiente_id and self._rc_requiere_confirmacion_borrador:
            self._feedback = map_error_recuperable(
                "Confirme o descarte el borrador autoritativo pendiente."
            )
            return self.screen()
        if not self._rc_ubicacion_id or not self._rc_lineas:
            self._feedback = map_error_recuperable(
                "A?ada al menos una l?nea de recuento.", codigo="VALIDACION"
            )
            return self.screen()
        data = get_container().app_data_store.get()
        lineas_vm = tuple(self._linea_vm_from_dict(ln) for ln in self._rc_lineas)
        self._rc_preview = RecuentoPreviewVM(
            ubicacion_id=self._rc_ubicacion_id,
            ubicacion_etiqueta=self._etiqueta_ubicacion(data, self._rc_ubicacion_id),
            lineas=lineas_vm,
            mensaje=(
                "Preview en memoria (orientativo). No reserva stock ni crea borrador. "
                "El dominio congelar? el esperado al crear el borrador."
            ),
            en_memoria=True,
        )
        assert_inventario_sin_economia(self._rc_preview)
        self._feedback = FeedbackVM(
            ok=True, mensaje="Revise el resumen y confirme el recuento."
        )
        return self.screen()

    def cancelar_recuento_memoria(self) -> InventarioScreenVM:
        if self._rc_pendiente_id:
            self._feedback = map_error_recuperable(
                f"Hay un borrador persistido ({self._rc_pendiente_id}). "
                "Conf?rmelo, descarte expresamente o abandone dejando el pendiente."
            )
            return self.screen()
        self._limpiar_recuento_memoria()
        self._feedback = FeedbackVM(ok=True, mensaje="Recuento en memoria cancelado.")
        return self.screen()

    def confirmar_recuento(self, *, fecha: date | None = None) -> InventarioScreenVM:
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Confirmaci?n en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable(
                "Sesi?n no autorizada.", codigo="DENEGADO"
            )
            return self.screen()
        if self._rc_requiere_confirmacion_borrador and self._rc_pendiente_id:
            return self.confirmar_borrador_pendiente(fecha=fecha)
        if not self._rc_preview or not self._rc_preview.en_memoria:
            self._feedback = map_error_recuperable(
                "Genere primero el preview en memoria."
            )
            return self.screen()
        if not self._rc_lineas or not self._rc_ubicacion_id:
            self._feedback = map_error_recuperable("No hay l?neas para confirmar.")
            return self.screen()

        self._confirmando = True
        try:
            _ = current_idempotency_token(_IDEMP_RECUENTO)
            lineas_tuple = [
                (ln["lote_id"], ln["producto_id"], float(ln["cantidad_contada"]))
                for ln in self._rc_lineas
            ]
            creado = recuento_service.crear_borrador(
                ubicacion_id=self._rc_ubicacion_id,
                lineas=lineas_tuple,
                fecha=fecha or date.today(),
                motivo=self._rc_motivo,
            )
            if not creado.ok or creado.sesion is None:
                self._feedback = map_resultado(False, creado.mensaje)
                return self.screen()

            self._rc_pendiente_id = creado.sesion.id
            if self._esperados_distintos(creado.sesion):
                self._cargar_preview_desde_sesion(creado.sesion, en_memoria=False)
                self._rc_requiere_confirmacion_borrador = True
                self._rc_aviso_borrador = (
                    f"Borrador {creado.sesion.id} creado. El esperado del dominio "
                    "difiere del preview en memoria. Revise los valores autoritativos "
                    "y confirme de nuevo (a?n no se ha ajustado el stock)."
                )
                self._feedback = map_error_recuperable(self._rc_aviso_borrador)
                return self.screen()

            conf = recuento_service.confirmar_recuento(recuento_id=creado.sesion.id)
            if conf.ok:
                rotate_idempotency_token(_IDEMP_RECUENTO)
                self._limpiar_recuento_memoria()
                self._feedback = map_resultado(True, conf.mensaje)
            else:
                self._rc_aviso_borrador = (
                    f"Confirmaci?n fallida. Stock no ajustado. "
                    f"Borrador {creado.sesion.id} sigue pendiente: puede reintentar "
                    "o descartarlo expresamente."
                )
                self._feedback = map_resultado(False, f"{conf.mensaje} | {self._rc_aviso_borrador}")
        finally:
            self._confirmando = False
        return self.screen()

    def confirmar_borrador_pendiente(
        self, *, fecha: date | None = None
    ) -> InventarioScreenVM:
        """Confirma un borrador ya persistido (reintento o tras preview obsoleto)."""
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Confirmaci?n en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        rid = self._rc_pendiente_id
        if not rid:
            self._feedback = map_error_recuperable("No hay borrador seleccionado.")
            return self.screen()
        self._confirmando = True
        try:
            _ = current_idempotency_token(_IDEMP_RECUENTO)
            conf = recuento_service.confirmar_recuento(recuento_id=rid)
            if conf.ok:
                rotate_idempotency_token(_IDEMP_RECUENTO)
                self._limpiar_recuento_memoria()
                self._feedback = map_resultado(True, conf.mensaje)
            else:
                self._rc_aviso_borrador = (
                    f"Confirmaci?n fallida. Borrador {rid} sigue pendiente."
                )
                self._feedback = map_resultado(False, f"{conf.mensaje} | {self._rc_aviso_borrador}")
        finally:
            self._confirmando = False
        return self.screen()

    def descartar_borrador_pendiente(self) -> InventarioScreenVM:
        """Anula solo BORRADOR del flujo actual (no confirmados)."""
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Operaci?n en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        rid = self._rc_pendiente_id
        if not rid:
            self._feedback = map_error_recuperable("No hay borrador que descartar.")
            return self.screen()
        self._confirmando = True
        try:
            an = recuento_service.anular_recuento(recuento_id=rid)
            if an.ok:
                self._limpiar_recuento_memoria()
                self._feedback = map_resultado(True, an.mensaje)
            else:
                self._rc_aviso_borrador = (
                    f"No se pudo descartar el borrador {rid}. Sigue pendiente."
                )
                self._feedback = map_resultado(False, f"{an.mensaje} | {self._rc_aviso_borrador}")
        finally:
            self._confirmando = False
        return self.screen()

    def seleccionar_borrador_pendiente(self, recuento_id: str) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        data = get_container().app_data_store.get()
        sesion = next(
            (
                r
                for r in recuento_service.listar_recuentos_pendientes(data)
                if r.id == recuento_id
            ),
            None,
        )
        if sesion is None:
            self._feedback = map_error_recuperable("Borrador no encontrado.")
            return self.screen()
        self._cargar_preview_desde_sesion(sesion, en_memoria=False)
        self._rc_pendiente_id = sesion.id
        self._rc_requiere_confirmacion_borrador = True
        self._rc_aviso_borrador = (
            f"Borrador {sesion.id} cargado. Confirme o descarte expresamente."
        )
        self._feedback = FeedbackVM(ok=True, mensaje=self._rc_aviso_borrador)
        return self.screen()

    def abandonar_recuento_dejando_pendiente(self) -> InventarioScreenVM:
        """Limpia UI dejando el borrador en pendientes (sin anular)."""
        rid = self._rc_pendiente_id
        self._limpiar_recuento_memoria()
        if rid:
            self._rc_aviso_borrador = (
                f"Se abandon? el formulario. El borrador {rid} sigue en Pendientes."
            )
            self._feedback = FeedbackVM(ok=True, mensaje=self._rc_aviso_borrador)
        else:
            self._feedback = FeedbackVM(ok=True, mensaje="Formulario de recuento limpio.")
        return self.screen()

    def preparar_salida(self) -> None:
        """Antes de Volver al men?: limpia memoria; no confirma ni anula borradores."""
        self._limpiar_traslado()
        self._al_abandonar_recuentos()
        self._ajuste_preview = None
        self._ajuste_draft = None
        self._confirmando = False

    def _al_abandonar_recuentos(self) -> FeedbackVM | None:
        if self._rc_pendiente_id:
            rid = self._rc_pendiente_id
            self._limpiar_recuento_memoria()
            msg = (
                f"Borrador {rid} permanece pendiente (no se confirm? ni anul?). "
                "Disponible en Pendientes."
            )
            self._rc_aviso_borrador = msg
            return FeedbackVM(ok=True, mensaje=msg)
        self._limpiar_recuento_memoria()
        return None

    def _limpiar_recuento_memoria(self, *, conservar_aviso_pendiente: bool = False) -> None:
        aviso = ""
        if conservar_aviso_pendiente and self._rc_pendiente_id:
            aviso = (
                f"Borrador {self._rc_pendiente_id} sigue pendiente "
                "(no se confirm? ni anul? al cerrar sesi?n)."
            )
        self._rc_ubicacion_id = None
        self._rc_producto_id = None
        self._rc_lote_id = None
        self._rc_cantidad = ""
        self._rc_lineas = []
        self._rc_preview = None
        self._rc_pendiente_id = None
        self._rc_requiere_confirmacion_borrador = False
        self._rc_aviso_borrador = aviso
        self._rc_motivo = None

    def _esperados_distintos(self, sesion) -> bool:
        mem = {ln["lote_id"]: round(float(ln["cantidad_esperada"]), 4) for ln in self._rc_lineas}
        for ln in sesion.lineas:
            esp = round(float(ln.cantidad_esperada), 4)
            if ln.lote_id not in mem or abs(mem[ln.lote_id] - esp) > 1e-9:
                return True
        return len(mem) != len(sesion.lineas)

    def _cargar_preview_desde_sesion(self, sesion, *, en_memoria: bool) -> None:
        data = get_container().app_data_store.get()
        self._rc_ubicacion_id = sesion.ubicacion_id
        self._rc_lineas = []
        for ln in sesion.lineas:
            self._rc_lineas.append(
                {
                    "producto_id": ln.producto_id,
                    "producto_nombre": ln.producto_nombre_snapshot or ln.producto_id,
                    "lote_id": ln.lote_id,
                    "unidad": ln.unidad_snapshot or self._unidad_producto(data, ln.producto_id),
                    "cantidad_esperada": float(ln.cantidad_esperada),
                    "cantidad_contada": float(ln.cantidad_contada),
                    "diferencia": float(ln.diferencia),
                }
            )
        textos = recuento_service.preview_confirmacion(sesion)
        self._rc_preview = RecuentoPreviewVM(
            ubicacion_id=sesion.ubicacion_id,
            ubicacion_etiqueta=self._etiqueta_ubicacion(data, sesion.ubicacion_id),
            lineas=tuple(self._linea_vm_from_dict(ln) for ln in self._rc_lineas),
            mensaje=" | ".join(textos),
            en_memoria=en_memoria,
        )

    def _linea_vm_from_dict(self, ln: dict) -> RecuentoLineaVM:
        diff = float(ln["diferencia"])
        if abs(diff) < 1e-9:
            efecto = "sin_cambio"
        elif diff > 0:
            efecto = "entrada"
        else:
            efecto = "salida"
        return RecuentoLineaVM(
            producto_id=ln["producto_id"],
            producto_nombre=ln["producto_nombre"],
            lote_id=ln["lote_id"],
            unidad=ln["unidad"],
            cantidad_esperada=float(ln["cantidad_esperada"]),
            cantidad_contada=float(ln["cantidad_contada"]),
            diferencia=diff,
            efecto=efecto,
        )

    def _efecto_label(self, efecto: str) -> str:
        return {
            "sin_cambio": "Sin cambio",
            "entrada": "Ajuste entrada",
            "salida": "Ajuste salida",
        }.get(efecto, efecto)

    # --- Ajustes ------------------------------------------------------------

    def previsualizar_ajuste(
        self,
        lote_id: str,
        cantidad_despues: float,
        motivo: str,
        comentario: str = "",
    ) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesi?n no autorizada.")
            return self.screen()
        preview, error = ajuste_service.previsualizar_ajuste(
            lote_id, float(cantidad_despues), motivo, comentario or None
        )
        if error or preview is None:
            self._ajuste_preview = None
            self._ajuste_draft = None
            self._feedback = map_error_recuperable(error or "No se pudo previsualizar.")
            return self.screen()
        self._ajuste_preview = AjustePreviewVM(
            lote_id=preview.lote_id,
            nombre=preview.nombre,
            unidad=preview.unidad,
            cantidad_antes=preview.cantidad_antes,
            cantidad_despues=preview.cantidad_despues,
            delta=preview.delta,
            motivo=preview.motivo,
            comentario=preview.comentario or "",
        )
        self._ajuste_draft = {
            "lote_id": lote_id,
            "cantidad_despues": float(cantidad_despues),
            "motivo": motivo,
            "comentario": comentario or None,
        }
        assert_inventario_sin_economia(self._ajuste_preview)
        self._feedback = FeedbackVM(ok=True, mensaje="Revise el resumen y confirme el ajuste.")
        return self.screen()

    def confirmar_ajuste(self, *, fecha: date | None = None) -> InventarioScreenVM:
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Confirmaci?n en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        if not self._ajuste_draft or not self._ajuste_preview:
            self._feedback = map_error_recuperable("Genere primero el resumen del ajuste.")
            return self.screen()
        self._confirmando = True
        try:
            token = current_idempotency_token(_IDEMP_AJUSTE)
            draft = self._ajuste_draft
            r = ajuste_service.aplicar_ajuste(
                fecha or date.today(),
                draft["lote_id"],
                draft["cantidad_despues"],
                draft["motivo"],
                draft.get("comentario"),
            )
            if r.ok:
                rotate_idempotency_token(_IDEMP_AJUSTE)
                self._ajuste_preview = None
                self._ajuste_draft = None
            self._feedback = map_resultado(r.ok, r.mensaje or f"OK ({token[:8]})")
        finally:
            self._confirmando = False
        return self.screen()

    def intentar_consulta_economica(self) -> FeedbackVM:
        from app.core.services import costes_service

        try:
            costes_service.resumen_periodo(date.today().replace(day=1), date.today(), [])
            return FeedbackVM(ok=True, mensaje="ERROR: se permiti? consulta econ?mica")
        except AuthorizationError as exc:
            return FeedbackVM(
                ok=False, mensaje=str(getattr(exc, "mensaje", exc)) or "Denegado"
            )
        except Exception as exc:  # noqa: BLE001
            return FeedbackVM(ok=False, mensaje=f"Denegado: {exc}")

    # --- Screen -------------------------------------------------------------

    def screen(self) -> InventarioScreenVM:
        try:
            from app.bootstrap import get_container

            get_container().app_data_store.refresh_if_stale()
        except Exception:  # noqa: BLE001
            pass
        session = session_bridge.current_session_vm()
        espacios = tuple(
            EspacioVM(id=e, etiqueta=_ETIQUETAS[e], activo=(e == self._espacio))
            for e in ESPACIOS
        )
        alertas: tuple[AlertaVM, ...] = ()
        caducidad: tuple[LoteCaducidadVM, ...] = ()
        cesta: tuple[MermaLineaVM, ...] = ()
        cesta_vacia = True
        lotes_aj: tuple[LoteAjusteVM, ...] = ()
        stock_filas: tuple[StockSaldoVM, ...] = ()
        stock_ubis: tuple[TrasladoOpcionVM, ...] = ()
        tr_prods: tuple[TrasladoOpcionVM, ...] = ()
        tr_lotes: tuple[TrasladoOpcionVM, ...] = ()
        tr_orig: tuple[TrasladoOpcionVM, ...] = ()
        tr_dest: tuple[TrasladoOpcionVM, ...] = ()
        tr_disp: float | None = None
        tr_recientes: tuple[TrasladoRecienteVM, ...] = ()
        rc_ubis: tuple[TrasladoOpcionVM, ...] = ()
        rc_prods: tuple[TrasladoOpcionVM, ...] = ()
        rc_lotes: tuple[TrasladoOpcionVM, ...] = ()
        rc_esp: float | None = None
        rc_unidad = ""
        rc_lineas: tuple[RecuentoLineaVM, ...] = ()
        rc_pend: tuple[RecuentoPendienteVM, ...] = ()
        rc_rec: tuple[RecuentoRecienteVM, ...] = ()
        if session.authenticated:
            data = get_container().app_data_store.get()
            if self._espacio == "alertas":
                alertas = self._alertas_vm()
            if self._espacio == "caducidad":
                caducidad = self._caducidad_vm()
            if self._espacio in ("merma", "caducidad"):
                cesta, cesta_vacia = self._merma_cesta_vm()
            if self._espacio in ("ajustes", "merma"):
                lotes_aj = self._lotes_ajuste_vm()
                if self._espacio == "ajustes":
                    cesta, cesta_vacia = self._merma_cesta_vm()
            if self._espacio == "stock":
                stock_filas = self._stock_filas_vm(data)
                stock_ubis = self._ubicaciones_filtro_vm(data)
            if self._espacio == "traslados":
                tr_prods = self._traslado_productos_vm(data)
                tr_lotes = self._traslado_lotes_vm(data)
                tr_orig = self._traslado_origenes_vm(data)
                tr_dest = self._traslado_destinos_vm(data)
                if self._traslado_lote_id and self._traslado_origen_id:
                    tr_disp = saldo_en_ubicacion(
                        data, self._traslado_lote_id, self._traslado_origen_id
                    )
                tr_recientes = self._traslados_recientes_vm(data)
            if self._espacio == "recuentos":
                rc_ubis = self._recuento_ubicaciones_vm(data)
                rc_prods = self._recuento_productos_vm(data)
                rc_lotes = self._recuento_lotes_vm(data)
                if self._rc_lote_id and self._rc_ubicacion_id:
                    rc_esp = saldo_en_ubicacion(
                        data, self._rc_lote_id, self._rc_ubicacion_id
                    )
                if self._rc_producto_id:
                    rc_unidad = self._unidad_producto(data, self._rc_producto_id)
                rc_lineas = tuple(self._linea_vm_from_dict(ln) for ln in self._rc_lineas)
                rc_pend = self._recuentos_pendientes_vm(data)
                rc_rec = self._recuentos_recientes_vm(data)
        economato = None
        if session.authenticated and self._espacio in ESPACIOS_ECONOMATO:
            data = get_container().app_data_store.get()
            economato = self._build_economato_panel(data)
        vm = InventarioScreenVM(
            session=session,
            espacios=espacios,
            espacio_activo=self._espacio,
            alertas=alertas,
            lotes_caducidad=caducidad,
            cesta_merma=cesta,
            cesta_merma_vacia=cesta_vacia,
            motivos_merma=tuple(m.value for m in MotivoMerma),
            servicios_merma=tuple(
                MermaOpcionVM(o.value, ORIGEN_SERVICIO_MERMA_LABEL[o])
                for o in OrigenServicioMerma
            ),
            turnos_merma=tuple(
                MermaOpcionVM(t.value, TURNO_MERMA_LABEL[t]) for t in TurnoMerma
            ),
            responsables_merma=self._responsables_vm(),
            responsable_seleccionado=self._responsable_efectivo(),
            lotes_ajuste=lotes_aj,
            motivos_ajuste=tuple(m.value for m in MotivoAjuste),
            ajuste_preview=self._ajuste_preview,
            stock_filas=stock_filas,
            stock_busqueda=self._stock_busqueda,
            stock_filtro_ubicacion=self._stock_filtro_ubicacion,
            stock_ubicaciones=stock_ubis,
            traslado_productos=tr_prods,
            traslado_lotes=tr_lotes,
            traslado_origenes=tr_orig,
            traslado_destinos=tr_dest,
            traslado_producto_id=self._traslado_producto_id,
            traslado_lote_id=self._traslado_lote_id,
            traslado_origen_id=self._traslado_origen_id,
            traslado_destino_id=self._traslado_destino_id,
            traslado_cantidad=self._traslado_cantidad,
            traslado_disponible=tr_disp,
            traslado_preview=self._traslado_preview,
            traslados_recientes=tr_recientes,
            recuento_ubicaciones=rc_ubis,
            recuento_productos=rc_prods,
            recuento_lotes=rc_lotes,
            recuento_ubicacion_id=self._rc_ubicacion_id,
            recuento_producto_id=self._rc_producto_id,
            recuento_lote_id=self._rc_lote_id,
            recuento_esperado=rc_esp,
            recuento_cantidad=self._rc_cantidad,
            recuento_unidad=rc_unidad,
            recuento_lineas=rc_lineas,
            recuento_preview=self._rc_preview,
            recuento_pendiente_id=self._rc_pendiente_id,
            recuento_requiere_confirmacion_borrador=self._rc_requiere_confirmacion_borrador,
            recuento_aviso_borrador=self._rc_aviso_borrador,
            recuentos_pendientes=rc_pend,
            recuentos_recientes=rc_rec,
            feedback=self._feedback,
            confirmando=self._confirmando,
            economato=economato,
        )
        if self._espacio in ESPACIOS_OPS:
            assert_inventario_sin_economia(vm)
        return vm

    def _limpiar_traslado_preview_only(self) -> None:
        self._traslado_preview = None
        self._traslado_draft = None

    def _limpiar_traslado(self) -> None:
        self._traslado_producto_id = None
        self._traslado_lote_id = None
        self._traslado_origen_id = None
        self._traslado_destino_id = None
        self._traslado_cantidad = ""
        self._limpiar_traslado_preview_only()

    def _resolver_responsable(self, responsable_id: str | None) -> tuple[str | None, str | None]:
        rid = (responsable_id or self._responsable_seleccionado or "").strip() or None
        if not rid:
            return None, None
        activos = merma_service.listar_responsables_merma(solo_activos=True)
        for r in activos:
            if r.id == rid:
                return r.id, r.nombre
        self._responsable_seleccionado = None
        return None, None

    def _responsable_efectivo(self) -> str | None:
        rid = self._responsable_seleccionado
        if not rid:
            return None
        activos = {r.id for r in merma_service.listar_responsables_merma(solo_activos=True)}
        if rid not in activos:
            self._responsable_seleccionado = None
            return None
        return rid

    def _responsables_vm(self) -> tuple[MermaOpcionVM, ...]:
        if not session_bridge.current_session_vm().authenticated:
            return ()
        return tuple(
            MermaOpcionVM(r.id, r.nombre)
            for r in merma_service.listar_responsables_merma(solo_activos=True)
        )

    def _alertas_vm(self) -> tuple[AlertaVM, ...]:
        data = get_container().app_data_store.get()
        items = alert_service.alertas_stock_activas(data)
        out: list[AlertaVM] = []
        for a in items:
            tipo = getattr(a.tipo, "value", str(a.tipo))
            out.append(
                AlertaVM(
                    id=a.id,
                    tipo=tipo,
                    titulo=a.titulo,
                    mensaje=a.mensaje,
                    estado=getattr(a, "estado", None) or EstadoAlerta.PENDIENTE.value,
                    producto_id=a.producto_id or "",
                    severidad=tipo,
                )
            )
        return tuple(out)

    def _caducidad_vm(self) -> tuple[LoteCaducidadVM, ...]:
        lotes = caducidad_service.listar_lotes_caducidad()
        return tuple(
            LoteCaducidadVM(
                lote_id=l.lote_id,
                producto_id=l.producto_id,
                nombre_producto=l.nombre_producto,
                unidad=l.unidad,
                cantidad_restante=l.cantidad_restante,
                fecha_expiracion=l.fecha_expiracion.isoformat(),
                dias_restantes=l.dias_restantes,
                estado=l.estado,
            )
            for l in lotes
        )

    def _merma_cesta_vm(self) -> tuple[tuple[MermaLineaVM, ...], bool]:
        raw = merma_service.get_cesta_merma()
        lineas = tuple(
            MermaLineaVM(
                lote_id=i.lote_id,
                producto_id=i.producto_id,
                nombre=i.nombre,
                unidad=i.unidad,
                cantidad=i.cantidad,
                motivo=i.motivo,
                servicio=merma_service.etiqueta_servicio_merma(i.tipo_servicio_snapshot),
                turno=merma_service.etiqueta_turno_merma(i.turno_snapshot),
                responsable=i.responsable_nombre,
            )
            for i in raw
        )
        return lineas, len(lineas) == 0

    def _lotes_ajuste_vm(self) -> tuple[LoteAjusteVM, ...]:
        out: list[LoteAjusteVM] = []
        for row in ajuste_service.lotes_ajustables():
            out.append(
                LoteAjusteVM(
                    lote_id=row["id"],
                    producto_id=row["producto_id"],
                    nombre=row["nombre"],
                    unidad=row["unidad"],
                    restante=float(row["restante"]),
                    etiqueta=(
                        f"{row['nombre']} ? {row['id']} ? "
                        f"restante {float(row['restante']):g} {row['unidad']}"
                    ),
                )
            )
        return tuple(out)

    def _mapa_productos(self, data) -> dict[str, object]:
        return {p.id: p for p in data.productos}

    def _mapa_ubicaciones(self, data) -> dict[str, object]:
        return {u.id: u for u in (getattr(data, "ubicaciones", None) or [])}

    def _etiqueta_ubicacion(self, data, ubicacion_id: str) -> str:
        if ubicacion_id == SIN_UBICACION_HISTORICA:
            return ETIQUETA_SIN_UBICACION_HISTORICA
        u = self._mapa_ubicaciones(data).get(ubicacion_id)
        if u is None:
            return ubicacion_id
        return getattr(u, "nombre", None) or ubicacion_id

    def _unidad_producto(self, data, producto_id: str) -> str:
        p = self._mapa_productos(data).get(producto_id)
        if p is None:
            return ""
        u = getattr(p, "unidad", "")
        return u.value if hasattr(u, "value") else str(u)

    def _ubicaciones_filtro_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        items = [TrasladoOpcionVM("__todas__", "Todas las ubicaciones")]
        for u in getattr(data, "ubicaciones", None) or []:
            if getattr(u, "activo", True):
                items.append(TrasladoOpcionVM(u.id, u.nombre))
        items.append(
            TrasladoOpcionVM(SIN_UBICACION_HISTORICA, ETIQUETA_SIN_UBICACION_HISTORICA)
        )
        return tuple(items)

    def _stock_filas_vm(self, data) -> tuple[StockSaldoVM, ...]:
        q = self._stock_busqueda.lower()
        filtro = self._stock_filtro_ubicacion
        prods = self._mapa_productos(data)
        filas: list[StockSaldoVM] = []
        for lote in data.lotes:
            if getattr(lote, "anulado", False):
                continue
            prod = prods.get(lote.producto_id)
            nombre = getattr(prod, "nombre", None) or lote.producto_id
            unidad = self._unidad_producto(data, lote.producto_id)
            if q and q not in nombre.lower() and q not in lote.id.lower():
                continue
            info = saldos_por_ubicacion_lote(data, lote.id)
            cob = getattr(info.cobertura, "value", str(info.cobertura))
            cob_lbl = _COBERTURA_ETIQUETA.get(cob, cob)
            if not info.por_ubicacion:
                if filtro:
                    continue
                # Sin movimientos de ubicaci?n: fila informativa (saldo 0).
                filas.append(
                    StockSaldoVM(
                        producto_id=lote.producto_id,
                        producto_nombre=nombre,
                        lote_id=lote.id,
                        ubicacion_id="",
                        ubicacion_etiqueta="-",
                        saldo=0.0,
                        unidad=unidad,
                        cobertura=cob_lbl,
                        es_historico_sin_ubicacion=False,
                    )
                )
                continue
            for uid, saldo_u in info.por_ubicacion.items():
                if abs(float(saldo_u.saldo)) < 1e-12:
                    continue
                if filtro and uid != filtro:
                    continue
                filas.append(
                    StockSaldoVM(
                        producto_id=lote.producto_id,
                        producto_nombre=nombre,
                        lote_id=lote.id,
                        ubicacion_id=uid,
                        ubicacion_etiqueta=self._etiqueta_ubicacion(data, uid),
                        saldo=float(saldo_u.saldo),
                        unidad=unidad,
                        cobertura=cob_lbl,
                        es_historico_sin_ubicacion=(uid == SIN_UBICACION_HISTORICA),
                    )
                )
        filas.sort(
            key=lambda r: (
                r.producto_nombre.lower(),
                r.lote_id,
                r.ubicacion_etiqueta.lower(),
            )
        )
        return tuple(filas)

    def _traslado_productos_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        out: list[TrasladoOpcionVM] = []
        seen: set[str] = set()
        for lote in data.lotes:
            if getattr(lote, "anulado", False):
                continue
            if lote.producto_id in seen:
                continue
            info = saldos_por_ubicacion_lote(data, lote.id)
            if not any(
                uid != SIN_UBICACION_HISTORICA and s.saldo > 1e-9
                for uid, s in info.por_ubicacion.items()
            ):
                continue
            seen.add(lote.producto_id)
            prod = self._mapa_productos(data).get(lote.producto_id)
            nombre = getattr(prod, "nombre", None) or lote.producto_id
            out.append(TrasladoOpcionVM(lote.producto_id, nombre))
        out.sort(key=lambda o: o.etiqueta.lower())
        return tuple(out)

    def _traslado_lotes_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        pid = self._traslado_producto_id
        if not pid:
            return ()
        out: list[TrasladoOpcionVM] = []
        unidad = self._unidad_producto(data, pid)
        for lote in data.lotes:
            if lote.producto_id != pid or getattr(lote, "anulado", False):
                continue
            info = saldos_por_ubicacion_lote(data, lote.id)
            disp = sum(
                s.saldo
                for uid, s in info.por_ubicacion.items()
                if uid != SIN_UBICACION_HISTORICA and s.saldo > 1e-9
            )
            if disp <= 1e-9:
                continue
            out.append(
                TrasladoOpcionVM(
                    lote.id,
                    f"{lote.id} ? disponible ubic. {disp:g} {unidad}".strip(),
                )
            )
        return tuple(out)

    def _traslado_origenes_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        lid = self._traslado_lote_id
        if not lid:
            return ()
        info = saldos_por_ubicacion_lote(data, lid)
        out: list[TrasladoOpcionVM] = []
        for uid, s in info.por_ubicacion.items():
            if uid == SIN_UBICACION_HISTORICA or s.saldo <= 1e-9:
                continue
            out.append(
                TrasladoOpcionVM(
                    uid,
                    f"{self._etiqueta_ubicacion(data, uid)} ? {s.saldo:g}",
                )
            )
        out.sort(key=lambda o: o.etiqueta.lower())
        return tuple(out)

    def _traslado_destinos_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        origen = self._traslado_origen_id
        pid = self._traslado_producto_id
        prod = self._mapa_productos(data).get(pid) if pid else None
        allowed = list(getattr(prod, "ubicacion_ids", None) or []) if prod else []
        out: list[TrasladoOpcionVM] = []
        for u in getattr(data, "ubicaciones", None) or []:
            if not getattr(u, "activo", True):
                continue
            if origen and u.id == origen:
                continue
            if allowed and u.id not in allowed:
                continue
            out.append(TrasladoOpcionVM(u.id, u.nombre))
        out.sort(key=lambda o: o.etiqueta.lower())
        return tuple(out)

    def _traslados_recientes_vm(self, data) -> tuple[TrasladoRecienteVM, ...]:
        movs = traslado_service.listar_traslados(data)
        movs_sorted = sorted(
            movs,
            key=lambda m: (
                getattr(m, "fecha", date.min),
                getattr(m, "id", ""),
            ),
            reverse=True,
        )
        out: list[TrasladoRecienteVM] = []
        for m in movs_sorted[:15]:
            pid = m.producto_id
            prod = self._mapa_productos(data).get(pid)
            nombre = getattr(prod, "nombre", None) or pid
            fecha = m.fecha.isoformat() if getattr(m, "fecha", None) else ""
            out.append(
                TrasladoRecienteVM(
                    traslado_id=m.origen_id or m.id,
                    producto_nombre=nombre,
                    lote_id=m.lote_id or "",
                    origen_etiqueta=self._etiqueta_ubicacion(
                        data, m.ubicacion_origen_id or ""
                    ),
                    destino_etiqueta=self._etiqueta_ubicacion(
                        data, m.ubicacion_destino_id or ""
                    ),
                    cantidad=float(m.cantidad),
                    unidad=self._unidad_producto(data, pid),
                    fecha=fecha,
                )
            )
        return tuple(out)

    def _recuento_ubicaciones_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        out: list[TrasladoOpcionVM] = []
        for u in getattr(data, "ubicaciones", None) or []:
            if getattr(u, "activo", True):
                out.append(TrasladoOpcionVM(u.id, u.nombre))
        out.sort(key=lambda o: o.etiqueta.lower())
        return tuple(out)

    def _recuento_productos_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        """Productos con al menos un lote no anulado (no se ofrecen sin lote)."""
        if not self._rc_ubicacion_id:
            return ()
        out: list[TrasladoOpcionVM] = []
        seen: set[str] = set()
        for lote in data.lotes:
            if getattr(lote, "anulado", False):
                continue
            if lote.producto_id in seen:
                continue
            seen.add(lote.producto_id)
            prod = self._mapa_productos(data).get(lote.producto_id)
            nombre = getattr(prod, "nombre", None) or lote.producto_id
            out.append(TrasladoOpcionVM(lote.producto_id, nombre))
        out.sort(key=lambda o: o.etiqueta.lower())
        return tuple(out)

    def _recuento_lotes_vm(self, data) -> tuple[TrasladoOpcionVM, ...]:
        pid = self._rc_producto_id
        uid = self._rc_ubicacion_id
        if not pid or not uid:
            return ()
        unidad = self._unidad_producto(data, pid)
        out: list[TrasladoOpcionVM] = []
        for lote in data.lotes:
            if lote.producto_id != pid or getattr(lote, "anulado", False):
                continue
            esp = saldo_en_ubicacion(data, lote.id, uid)
            out.append(
                TrasladoOpcionVM(
                    lote.id,
                    f"{lote.id} ? esperado {esp:g} {unidad}".strip(),
                )
            )
        return tuple(out)

    def _recuentos_pendientes_vm(self, data) -> tuple[RecuentoPendienteVM, ...]:
        out: list[RecuentoPendienteVM] = []
        for s in recuento_service.listar_recuentos_pendientes(data):
            n = len(s.lineas)
            fecha = s.fecha.isoformat() if getattr(s, "fecha", None) else ""
            out.append(
                RecuentoPendienteVM(
                    recuento_id=s.id,
                    ubicacion_id=s.ubicacion_id,
                    ubicacion_etiqueta=self._etiqueta_ubicacion(data, s.ubicacion_id),
                    resumen=f"{n} l?nea(s)",
                    fecha=fecha,
                )
            )
        return tuple(out)

    def _recuentos_recientes_vm(self, data) -> tuple[RecuentoRecienteVM, ...]:
        items = [
            r
            for r in (getattr(data, "recuentos", None) or [])
            if (r.estado.value if hasattr(r.estado, "value") else str(r.estado))
            == EstadoRecuento.CONFIRMADO.value
        ]
        items.sort(
            key=lambda r: (
                getattr(r, "fecha", date.min) or date.min,
                getattr(r, "id", ""),
            ),
            reverse=True,
        )
        out: list[RecuentoRecienteVM] = []
        for s in items[:15]:
            n = len(s.lineas)
            fecha = s.fecha.isoformat() if getattr(s, "fecha", None) else ""
            est = s.estado.value if hasattr(s.estado, "value") else str(s.estado)
            out.append(
                RecuentoRecienteVM(
                    recuento_id=s.id,
                    ubicacion_etiqueta=self._etiqueta_ubicacion(data, s.ubicacion_id),
                    resumen=f"{n} l?nea(s)",
                    fecha=fecha,
                    estado=est,
                )
            )
        return tuple(out)
