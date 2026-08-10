"""Presenter Terminal Inventario — orquesta alertas, caducidad, merma y ajustes.

Sin cálculos FIFO/stock/coste. Sin información económica en viewmodels.
"""

from __future__ import annotations

from datetime import date

from app.core.application.idempotency import (
    current_idempotency_token,
    rotate_idempotency_token,
)
from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.models import EstadoAlerta, MotivoAjuste, MotivoMerma
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
)
from app.presentation.flet import session_bridge
from app.presentation.flet.inventory_viewmodels import (
    ESPACIOS,
    AlertaVM,
    AjustePreviewVM,
    EspacioVM,
    InventarioScreenVM,
    LoteAjusteVM,
    LoteCaducidadVM,
    MermaLineaVM,
    MermaOpcionVM,
    assert_inventario_sin_economia,
)
from app.presentation.flet.mappers import map_error_recuperable, map_resultado
from app.presentation.flet.viewmodels import FeedbackVM

_ETIQUETAS = {
    "alertas": "Alertas",
    "caducidad": "Caducidad",
    "merma": "Merma",
    "ajustes": "Ajustes",
}

_IDEMP_AJUSTE = "flet_inv_ajuste"
_IDEMP_MERMA = "flet_inv_merma"


class TerminalInventarioPresenter:
    def __init__(self) -> None:
        self._espacio = "alertas"
        self._feedback: FeedbackVM | None = None
        self._confirmando = False
        self._ajuste_preview: AjustePreviewVM | None = None
        self._ajuste_draft: dict | None = None
        assert_inventario_sin_economia(AlertaVM, LoteCaducidadVM, MermaLineaVM, AjustePreviewVM)

    def entrar(self) -> InventarioScreenVM:
        session, fb = session_bridge.enter_terminal_inventario()
        self._feedback = fb
        if session.authenticated:
            try:
                alert_service.sincronizar_alertas()
            except Exception as exc:  # noqa: BLE001
                self._feedback = map_error_recuperable(f"No se pudieron sincronizar alertas: {exc}")
        return self.screen()

    def denegar_demo(self, role: str) -> InventarioScreenVM:
        _, fb = session_bridge.deny_foreign_role(role)
        self._feedback = fb
        return self.screen()

    def logout(self) -> InventarioScreenVM:
        session_bridge.logout_terminal()
        self._feedback = FeedbackVM(ok=True, mensaje="Sesión cerrada.")
        self._confirmando = False
        self._ajuste_preview = None
        return self.screen()

    def seleccionar_espacio(self, espacio_id: str) -> InventarioScreenVM:
        if espacio_id not in ESPACIOS:
            self._feedback = map_error_recuperable("Espacio no reconocido.")
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        self._espacio = espacio_id
        self._ajuste_preview = None
        self._feedback = FeedbackVM(ok=True, mensaje=f"Espacio: {_ETIQUETAS[espacio_id]}")
        if espacio_id == "alertas":
            alert_service.sincronizar_alertas()
        return self.screen()

    # --- Alertas ------------------------------------------------------------

    def marcar_alerta(self, alerta_id: str, estado: str) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
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
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        resp_id, resp_nombre = self._resolver_responsable(responsable_id)
        if not resp_id:
            self._feedback = map_error_recuperable(
                "No hay responsables de merma activos. Configúrelos en Administración."
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
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        resp_id, resp_nombre = self._resolver_responsable(responsable_id)
        if not resp_id:
            self._feedback = map_error_recuperable(
                "No hay responsables de merma activos."
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
                "Confirmación en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        if not merma_service.get_cesta_merma():
            self._feedback = map_error_recuperable("La cesta de merma está vacía.")
            return self.screen()
        self._confirmando = True
        try:
            # Token de UI para rotar tras éxito (merma backend no usa clave aún).
            _ = current_idempotency_token(_IDEMP_MERMA)
            r = merma_service.registrar_merma(fecha or date.today())
            if r.ok:
                rotate_idempotency_token(_IDEMP_MERMA)
            self._feedback = map_resultado(r.ok, r.mensaje)
        finally:
            self._confirmando = False
        return self.screen()

    # --- Ajustes ------------------------------------------------------------

    def previsualizar_ajuste(
        self,
        lote_id: str,
        cantidad_despues: float,
        motivo: str,
        comentario: str = "",
    ) -> InventarioScreenVM:
        if not session_bridge.puede_usar_terminal_inventario():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        preview, error = ajuste_service.previsualizar_ajuste(
            lote_id, float(cantidad_despues), motivo, comentario or None
        )
        if error or preview is None:
            self._ajuste_preview = None
            self._ajuste_draft = None
            self._feedback = map_error_recuperable(error or "No se pudo previsualizar.")
            return self.screen()
        # Mapear SIN precio_total / campos económicos
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
                "Confirmación en curso.", codigo="CONFIRMANDO"
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
            return FeedbackVM(ok=True, mensaje="ERROR: se permitió consulta económica")
        except AuthorizationError as exc:
            return FeedbackVM(
                ok=False, mensaje=str(getattr(exc, "mensaje", exc)) or "Denegado"
            )
        except Exception as exc:  # noqa: BLE001
            return FeedbackVM(ok=False, mensaje=f"Denegado: {exc}")

    # --- Screen -------------------------------------------------------------

    def screen(self) -> InventarioScreenVM:
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
        if session.authenticated:
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
            lotes_ajuste=lotes_aj,
            motivos_ajuste=tuple(m.value for m in MotivoAjuste),
            ajuste_preview=self._ajuste_preview,
            feedback=self._feedback,
            confirmando=self._confirmando,
        )
        assert_inventario_sin_economia(vm)
        return vm

    def _resolver_responsable(self, responsable_id: str | None) -> tuple[str | None, str | None]:
        activos = merma_service.listar_responsables_merma(solo_activos=True)
        if not activos:
            return None, None
        if responsable_id:
            for r in activos:
                if r.id == responsable_id:
                    return r.id, r.nombre
        r0 = activos[0]
        return r0.id, r0.nombre

    def _responsables_vm(self) -> tuple[MermaOpcionVM, ...]:
        if not session_bridge.current_session_vm().authenticated:
            return ()
        return tuple(
            MermaOpcionVM(r.id, r.nombre)
            for r in merma_service.listar_responsables_merma(solo_activos=True)
        )

    def _alertas_vm(self) -> tuple[AlertaVM, ...]:
        from app.bootstrap import get_container

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
                        f"{row['nombre']} · {row['id']} · "
                        f"restante {float(row['restante']):g} {row['unidad']}"
                    ),
                )
            )
        return tuple(out)
