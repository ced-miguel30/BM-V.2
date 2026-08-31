"""Presenter de Terminal Restaurante — orquesta UI Flet y casos de uso.

Sin cálculos de dominio en esta capa. Sin información económica.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from app.bootstrap import get_container
from app.core.application.idempotency import (
    current_idempotency_token,
    rotate_idempotency_token,
)
from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import session_tiene_permiso
from app.core.services import anulacion_registro_service as anul
from app.core.services import bebida_service, cena_service, comida_service
from app.core.services.desayuno_service import desayuno_registro
from app.core.services.receta_service import listar_recetas
from app.core.services.text_search import coincide_busqueda
from app.presentation.flet import session_bridge
from app.presentation.flet.mappers import map_error_recuperable, map_resultado
from app.presentation.flet.viewmodels import (
    AnulacionPendienteVM,
    BasketExtraVM,
    BasketLineVM,
    BasketVM,
    CatalogItemVM,
    EdicionLineaVM,
    EdicionRegistroVM,
    FeedbackVM,
    HistorialRegistroVM,
    ImportacionTpvVM,
    ServicioVM,
    TerminalScreenVM,
    assert_sin_campos_economicos,
)

SERVICIOS: tuple[tuple[str, str], ...] = (
    ("desayuno", "Desayuno"),
    ("comida", "Comida"),
    ("cena", "Cena"),
    ("bebidas", "Bebidas independientes"),
)

# Límite solo de presentación; el servicio no pagina.
_HISTORIAL_LIMITE = 25


@dataclass
class _ServicioBind:
    id: str
    etiqueta: str
    api: object
    idempotency_scope: str
    requiere_huespedes: bool


def _binds() -> dict[str, _ServicioBind]:
    return {
        "desayuno": _ServicioBind(
            "desayuno", "Desayuno", desayuno_registro, "desayuno", True
        ),
        "comida": _ServicioBind(
            "comida", "Comida", comida_service.servicio, "comida", False
        ),
        "cena": _ServicioBind("cena", "Cena", cena_service.servicio, "cena", False),
        "bebidas": _ServicioBind(
            "bebidas",
            "Bebidas independientes",
            bebida_service.servicio,
            "bebidas",
            False,
        ),
    }


class TerminalRestaurantePresenter:
    def __init__(self) -> None:
        self._servicio_id: str | None = None
        self._busqueda: str = ""
        self._catalogo_tipo: str = "recetas"  # todas|recetas|productos|bebidas
        self._feedback: FeedbackVM | None = None
        self._confirmando: bool = False
        self._anulando: bool = False
        self._num_huespedes: int = 30
        self._anulacion_pendiente: AnulacionPendienteVM | None = None
        self._importacion_tpv: ImportacionTpvVM | None = None
        self._historial_expandido: bool = False
        self._importacion_tpv_activa: bool = False
        self._edicion: dict | None = None  # {registro_id, tipo, etiqueta, lineas: list[dict]}
        self._editando: bool = False
        assert_sin_campos_economicos(CatalogItemVM)
        assert_sin_campos_economicos(BasketLineVM)
        assert_sin_campos_economicos(BasketVM)
        assert_sin_campos_economicos(HistorialRegistroVM)
        assert_sin_campos_economicos(AnulacionPendienteVM)

    def entrar(self) -> TerminalScreenVM:
        session, fb = session_bridge.enter_terminal_restaurante()
        self._feedback = fb
        if session.authenticated:
            self._servicio_id = self._servicio_id or "desayuno"
        return self.screen()

    def denegar_demo(self, role: str) -> TerminalScreenVM:
        _, fb = session_bridge.deny_foreign_role(role)
        self._feedback = fb
        self._servicio_id = None
        return self.screen()

    def logout(self) -> TerminalScreenVM:
        session_bridge.logout_terminal()
        self._servicio_id = None
        self._feedback = FeedbackVM(ok=True, mensaje="Sesión cerrada.")
        self._confirmando = False
        self._anulando = False
        self._anulacion_pendiente = None
        return self.screen()

    def preparar_salida(self) -> None:
        """Antes de Volver al menú: limpia UI; no anula ni confirma."""
        self._anulacion_pendiente = None
        self._confirmando = False
        self._anulando = False
        self._importacion_tpv = None
        self._historial_expandido = False

    def set_importacion_tpv_activa(self, activa: bool) -> None:
        self._importacion_tpv_activa = bool(activa)

    def ejecutar_importacion_tpv_completa_sync(self, ruta: str):
        """OCR + registro en un solo hilo de fondo (sin refrescos UI intermedios)."""
        from app.core.services.tpv_documento_service import ResultadoImportTpv
        if not session_bridge.puede_usar_terminal():
            return ResultadoImportTpv(ok=False, mensaje="Sesión no autorizada.")
        if not session_tiene_permiso(Permiso.ACCEDER_REGISTRO):
            return ResultadoImportTpv(ok=False, mensaje="No autorizado para registrar.")
        path = (ruta or "").strip()
        if not path:
            return ResultadoImportTpv(ok=False, mensaje="No se seleccionó ningún archivo.")
        parsed = self.procesar_documento_tpv_ocr_sync(path)
        if not parsed.ok:
            return ResultadoImportTpv(
                ok=False,
                mensaje=parsed.error,
                lineas_detectadas=parsed.lineas_detectadas,
            )
        return self.registrar_lineas_tpv_sync(parsed.rows, str(parsed.path or path))

    def procesar_documento_tpv_ocr_sync(self, ruta: str):
        """OCR+parse en hilo de fondo (sin AppData)."""
        from app.core.services.tpv_documento_service import procesar_documento_tpv_ocr

        return procesar_documento_tpv_ocr(ruta)

    def registrar_lineas_tpv_sync(self, rows: list, ruta: str):
        """Registro en hilo principal (AppData / persist)."""
        from app.core.services.tpv_documento_service import (
            ResultadoImportTpv,
            registrar_lineas_tpv,
        )

        if not session_bridge.puede_usar_terminal():
            return ResultadoImportTpv(ok=False, mensaje="Sesión no autorizada.")
        if not session_tiene_permiso(Permiso.ACCEDER_REGISTRO):
            return ResultadoImportTpv(ok=False, mensaje="No autorizado para registrar.")
        return registrar_lineas_tpv(rows, ruta)

    def importar_documento_tpv_sync(self, ruta: str):
        """Compat: OCR+registro completo."""
        return self.ejecutar_importacion_tpv_completa_sync(ruta)

    def aplicar_resultado_importacion_tpv(self, resultado) -> TerminalScreenVM:
        """Aplica el resultado del import TPV y deja visible el panel de revisión."""
        self._confirmando = False
        self._historial_expandido = True
        try:
            get_container().app_data_store.reload_from_disk()
        except Exception:  # noqa: BLE001
            pass
        self._importacion_tpv = self._importacion_tpv_vm(resultado)
        self._feedback = FeedbackVM(ok=resultado.ok, mensaje=resultado.mensaje)
        if resultado.registros_creados:
            tipos = {str(x.get("tipo") or "") for x in resultado.registros_creados}
            if "comida" in tipos:
                self._servicio_id = "comida"
            elif "bebidas" in tipos:
                self._servicio_id = "bebidas"
        return self.screen()

    def cerrar_panel_importacion_tpv(self) -> TerminalScreenVM:
        self._importacion_tpv = None
        return self.screen()

    def confirmar_revision_historial(self, registro_id: str) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        if not session_tiene_permiso(Permiso.ACCEDER_REGISTRO):
            self._feedback = map_error_recuperable("No autorizado para confirmar.")
            return self.screen()
        tipo = self._tipo_registro_bind(bind)
        try:
            r = anul.confirmar_revision_registro(registro_id, tipo_registro=tipo)
            self._feedback = map_resultado(r.ok, r.mensaje)
        except Exception as exc:  # noqa: BLE001
            self._feedback = map_error_recuperable(
                str(exc) or "Error al confirmar el registro.",
                codigo="ERROR",
            )
        return self.screen()

    def marcar_importando_tpv(self, activo: bool) -> TerminalScreenVM:
        self._confirmando = bool(activo)
        if activo:
            self._feedback = FeedbackVM(
                ok=True,
                mensaje=(
                    "Importando documento TPV (OCR + registro). "
                    "Puede tardar 1-2 minutos; no cierre la ventana."
                ),
            )
        return self.screen()

    def importar_documento_tpv(self, ruta: str) -> TerminalScreenVM:
        """Compat: import síncrono (preferir sync + aplicar_resultado en UI)."""
        try:
            resultado = self.importar_documento_tpv_sync(ruta)
        except Exception as exc:  # noqa: BLE001
            self._confirmando = False
            self._feedback = map_error_recuperable(f"Error al importar documento: {exc}")
            return self.screen()
        return self.aplicar_resultado_importacion_tpv(resultado)

    def seleccionar_servicio(self, servicio_id: str) -> TerminalScreenVM:
        if servicio_id not in _binds():
            self._feedback = map_error_recuperable("Servicio no reconocido.")
            return self.screen()
        if not session_bridge.puede_usar_terminal():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        self._servicio_id = servicio_id
        self._busqueda = ""
        self._catalogo_tipo = "recetas"
        self._anulacion_pendiente = None
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Servicio activo: {_binds()[servicio_id].etiqueta}"
        )
        return self.screen()

    def set_busqueda(self, texto: str) -> TerminalScreenVM:
        self._busqueda = (texto or "").strip()
        return self.screen()

    def set_catalogo_tipo(self, tipo: str) -> TerminalScreenVM:
        clave = (tipo or "").strip().lower()
        if self._servicio_id == "bebidas":
            # Sin productos sueltos: solo recetas.
            self._catalogo_tipo = "recetas"
            return self.screen()
        if clave in ("todas", "recetas", "productos", "bebidas"):
            self._catalogo_tipo = clave
        return self.screen()

    def set_num_huespedes(self, n: int) -> TerminalScreenVM:
        self._num_huespedes = max(0, int(n))
        return self.screen()

    def anadir_receta(self, receta_id: str, porciones: float = 1.0) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        try:
            resultado = bind.api.anadir_receta_a_cesta(receta_id, float(porciones))
        except TypeError:
            resultado = bind.api.anadir_receta_a_cesta(receta_id, float(porciones), None)
        self._feedback = map_resultado(resultado.ok, resultado.mensaje, resultado.codigo)
        return self.screen()

    def anadir_producto_directo(
        self, producto_id: str, cantidad: float = 1.0
    ) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        # Si hay edición abierta, el catálogo alimenta el registro en edición.
        if self._edicion is not None:
            return self.anadir_producto_edicion(producto_id, float(cantidad))
        qty = float(cantidad)
        # Cantidad negativa = omisión «Sin …» sobre la receta en cesta (o pendiente).
        if qty < 0 and hasattr(bind.api, "anadir_mod_a_receta_en_cesta"):
            resultado = bind.api.anadir_mod_a_receta_en_cesta(producto_id, qty)
        else:
            resultado = bind.api.anadir_a_cesta(producto_id, qty)
        self._feedback = map_resultado(resultado.ok, resultado.mensaje, resultado.codigo)
        return self.screen()

    def anadir_extra_o_omision(
        self, producto_id: str, cantidad: float
    ) -> TerminalScreenVM:
        """Extra (+) u omisión (−) ligada a la receta en cesta."""
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        if hasattr(bind.api, "anadir_mod_a_receta_en_cesta"):
            resultado = bind.api.anadir_mod_a_receta_en_cesta(
                producto_id, float(cantidad),
            )
        else:
            resultado = bind.api.anadir_mod_pendiente_receta(
                producto_id, float(cantidad),
            )
        self._feedback = map_resultado(resultado.ok, resultado.mensaje, resultado.codigo)
        return self.screen()

    def ajustar_linea_producto(self, linea_id: str, delta: float) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        resultado = bind.api.ajustar_cantidad_suelto(linea_id, float(delta))
        self._feedback = map_resultado(resultado.ok, resultado.mensaje, resultado.codigo)
        return self.screen()

    def ajustar_porciones_receta(self, grupo_id: str, delta: float) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        resultado = bind.api.ajustar_porciones_grupo(grupo_id, float(delta))
        self._feedback = map_resultado(resultado.ok, resultado.mensaje, resultado.codigo)
        return self.screen()

    def quitar_linea_producto(self, linea_id: str) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        nombre = bind.api.quitar_linea_suelta(linea_id)
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Retirado: {nombre}" if nombre else "Línea retirada."
        )
        return self.screen()

    def quitar_grupo_receta(self, grupo_id: str) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        nombre = bind.api.quitar_grupo_receta(grupo_id)
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Retirado: {nombre}" if nombre else "Receta retirada."
        )
        return self.screen()

    def vaciar_cesta(self) -> TerminalScreenVM:
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        bind.api.limpiar_cesta()
        self._feedback = FeedbackVM(ok=True, mensaje="Cesta vaciada.")
        return self.screen()

    def confirmar(self, *, fecha: date | None = None) -> TerminalScreenVM:
        if self._confirmando or self._anulando:
            self._feedback = map_error_recuperable(
                "Operación en curso. Espere un momento.", codigo="CONFIRMANDO"
            )
            return self.screen()
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        if not session_tiene_permiso(Permiso.ACCEDER_REGISTRO):
            self._feedback = map_error_recuperable("No autorizado para registrar.")
            return self.screen()
        if bind.api.cesta_vacia():
            self._feedback = map_error_recuperable("La cesta está vacía.")
            return self.screen()
        if bind.requiere_huespedes and self._num_huespedes < 1:
            self._feedback = map_error_recuperable(
                "Indique el número de huéspedes (mínimo 1) para Desayuno."
            )
            return self.screen()

        self._confirmando = True
        try:
            token = current_idempotency_token(bind.idempotency_scope)
            dia = fecha or date.today()
            resultado = bind.api.registrar(
                dia,
                self._num_huespedes if bind.requiere_huespedes else 0,
                clave_idempotencia=token,
            )
            if resultado.ok:
                rotate_idempotency_token(bind.idempotency_scope)
                if not bind.api.cesta_vacia():
                    bind.api.limpiar_cesta()
                self._feedback = map_resultado(
                    True, resultado.mensaje or "Registro confirmado.", resultado.codigo
                )
            else:
                self._feedback = map_error_recuperable(
                    resultado.mensaje, codigo=resultado.codigo
                )
        finally:
            self._confirmando = False
        return self.screen()

    # --- Historial / anulación ---------------------------------------------

    def iniciar_anulacion(self, registro_id: str) -> TerminalScreenVM:
        if self._confirmando or self._anulando:
            self._feedback = map_error_recuperable(
                "Operación en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        bind = self._require_bind()
        if bind is None:
            return self.screen()
        if not session_tiene_permiso(Permiso.ACCEDER_REGISTRO):
            self._feedback = map_error_recuperable("No autorizado para anular.")
            return self.screen()
        data = get_container().app_data_store.get()
        tipo = self._tipo_registro_bind(bind)
        registro = self._buscar_registro(data, registro_id, tipo)
        if registro is None:
            self._feedback = map_error_recuperable("Registro no encontrado.")
            self._anulacion_pendiente = None
            return self.screen()
        puede = anul.puede_anular_registro(data, registro, tipo=tipo)
        vm_item = self._historial_item_vm(data, registro, tipo, bind.etiqueta)
        if not puede.ok:
            self._anulacion_pendiente = None
            motivo = " ".join(puede.motivos_bloqueo) or "No anulable."
            self._feedback = map_error_recuperable(motivo, codigo="NO_ANULABLE")
            return self.screen()
        self._anulacion_pendiente = AnulacionPendienteVM(
            registro_id=registro_id,
            tipo_registro=tipo,
            etiqueta_corta=vm_item.etiqueta_corta,
            resumen=vm_item.resumen,
            motivo="",
        )
        self._feedback = FeedbackVM(
            ok=True,
            mensaje="Confirme la anulación e indique el motivo.",
        )
        return self.screen()

    def set_motivo_anulacion(self, motivo: str) -> TerminalScreenVM:
        if self._anulacion_pendiente is None:
            return self.screen()
        p = self._anulacion_pendiente
        self._anulacion_pendiente = AnulacionPendienteVM(
            registro_id=p.registro_id,
            tipo_registro=p.tipo_registro,
            etiqueta_corta=p.etiqueta_corta,
            resumen=p.resumen,
            motivo=(motivo or "").strip(),
        )
        return self.screen()

    def cancelar_anulacion(self) -> TerminalScreenVM:
        self._anulacion_pendiente = None
        self._feedback = FeedbackVM(ok=True, mensaje="Anulación cancelada.")
        return self.screen()

    def confirmar_anulacion(self) -> TerminalScreenVM:
        if self._anulando or self._confirmando:
            self._feedback = map_error_recuperable(
                "Anulación en curso.", codigo="ANULANDO"
            )
            return self.screen()
        if not session_bridge.puede_usar_terminal():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        if not session_tiene_permiso(Permiso.ACCEDER_REGISTRO):
            self._feedback = map_error_recuperable("No autorizado para anular.")
            return self.screen()
        pend = self._anulacion_pendiente
        if pend is None:
            self._feedback = map_error_recuperable(
                "Seleccione un registro y confirme la anulación."
            )
            return self.screen()
        motivo = (pend.motivo or "").strip()
        if not motivo:
            self._feedback = map_error_recuperable(
                "El motivo de anulación es obligatorio.", codigo="VALIDACION"
            )
            return self.screen()

        self._anulando = True
        try:
            if pend.tipo_registro == anul.TIPO_DESAYUNO:
                r = anul.anular_desayuno(pend.registro_id, motivo)
            else:
                r = anul.anular_servicio(pend.registro_id, motivo)
            if r.ok:
                self._anulacion_pendiente = None
                self._feedback = map_resultado(True, r.mensaje)
            else:
                self._feedback = map_resultado(False, r.mensaje)
        except Exception as exc:  # noqa: BLE001 — feedback operativo, sin falso éxito
            self._feedback = map_error_recuperable(
                str(exc) or "Error al anular el registro.",
                codigo="ERROR",
            )
        finally:
            self._anulando = False
        return self.screen()

    def intentar_consulta_economica(self) -> FeedbackVM:
        from app.core.services import costes_service

        try:
            costes_service.resumen_periodo(
                date.today().replace(day=1), date.today(), []
            )
            return FeedbackVM(ok=True, mensaje="ERROR: se permitió consulta económica")
        except AuthorizationError as exc:
            return FeedbackVM(
                ok=False, mensaje=str(getattr(exc, "mensaje", exc)) or "Denegado"
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if (
                "autoriz" in msg.lower()
                or "permiso" in msg.lower()
                or "No autorizado" in msg
            ):
                return FeedbackVM(ok=False, mensaje=msg)
            return FeedbackVM(ok=False, mensaje=f"Denegado: {msg}")

    def screen(self) -> TerminalScreenVM:
        # Multiclinte: recargar si otro PC avanzó la revisión.
        if not self._importacion_tpv_activa:
            try:
                get_container().app_data_store.refresh_if_stale()
            except Exception:  # noqa: BLE001
                pass
        session = session_bridge.current_session_vm()
        servicios = tuple(
            ServicioVM(id=sid, etiqueta=etq, activo=(sid == self._servicio_id))
            for sid, etq in SERVICIOS
        )
        catalogo: tuple[CatalogItemVM, ...] = ()
        cesta: BasketVM | None = None
        historial: tuple[HistorialRegistroVM, ...] = ()
        requiere_h = False
        if session.authenticated and self._servicio_id:
            bind = _binds()[self._servicio_id]
            requiere_h = bind.requiere_huespedes
            catalogo = self._catalogo(bind)
            cesta = self._cesta_vm(bind)
            historial = self._historial_vm(bind)
        vm = TerminalScreenVM(
            session=session,
            servicios=servicios,
            servicio_activo=self._servicio_id,
            catalogo=catalogo,
            cesta=cesta,
            feedback=self._feedback,
            confirmando=self._confirmando,
            num_huespedes=self._num_huespedes,
            requiere_huespedes=requiere_h,
            busqueda=self._busqueda,
            catalogo_tipo=self._catalogo_tipo,
            historial=historial,
            historial_expandido=self._historial_expandido,
            importacion_tpv=self._importacion_tpv,
            anulacion_pendiente=self._anulacion_pendiente,
            anulando=self._anulando,
            edicion=self._edicion_vm(),
            editando=self._editando,
        )
        assert_sin_campos_economicos(vm)
        return vm

    def _edicion_vm(self) -> EdicionRegistroVM | None:
        if not self._edicion:
            return None
        lineas = tuple(
            EdicionLineaVM(
                producto_id=str(ln["producto_id"]),
                nombre=str(ln.get("nombre") or ln["producto_id"]),
                cantidad=float(ln["cantidad"]),
                unidad=str(ln.get("unidad") or ""),
            )
            for ln in self._edicion.get("lineas") or []
            if float(ln.get("cantidad") or 0) > 0
        )
        return EdicionRegistroVM(
            registro_id=str(self._edicion["registro_id"]),
            tipo_registro=str(self._edicion["tipo_registro"]),
            etiqueta_corta=str(self._edicion.get("etiqueta") or ""),
            lineas=lineas,
            busqueda_producto=str(self._edicion.get("busqueda") or ""),
        )

    def iniciar_edicion(self, registro_id: str) -> TerminalScreenVM:
        from app.core.services.rectificacion_registro_service import (
            lineas_actuales_registro,
        )

        bind = self._require_bind()
        if bind is None:
            return self.screen()
        data = get_container().app_data_store.get()
        tipo = self._tipo_registro_bind(bind)
        reg = self._buscar_registro(data, registro_id, tipo)
        if reg is None:
            self._feedback = map_error_recuperable("Registro no encontrado.")
            return self.screen()
        puede = anul.puede_anular_registro(data, reg, tipo=tipo)
        if not puede.ok or anul.registro_esta_anulado(reg):
            self._feedback = map_error_recuperable(
                "No se puede editar: "
                + (" ".join(puede.motivos_bloqueo) if not puede.ok else "anulado.")
            )
            return self.screen()
        lineas = lineas_actuales_registro(registro_id, tipo_registro=tipo)
        etiqueta = f"{bind.etiqueta} · {getattr(reg, 'fecha', '')}"
        self._edicion = {
            "registro_id": registro_id,
            "tipo_registro": tipo,
            "etiqueta": etiqueta,
            "busqueda": "",
            "lineas": [
                {
                    "producto_id": ln.producto_id,
                    "nombre": ln.nombre,
                    "cantidad": ln.cantidad,
                    "unidad": ln.unidad,
                }
                for ln in lineas
            ],
        }
        self._historial_expandido = True
        self._feedback = FeedbackVM(
            ok=True,
            mensaje="Edición abierta: sume, reste o añada productos y pulse Guardar.",
        )
        return self.screen()

    def cancelar_edicion(self) -> TerminalScreenVM:
        self._edicion = None
        self._editando = False
        self._feedback = FeedbackVM(ok=True, mensaje="Edición cancelada.")
        return self.screen()

    def ajustar_linea_edicion(self, producto_id: str, delta: float) -> TerminalScreenVM:
        if not self._edicion:
            return self.screen()
        lineas = list(self._edicion.get("lineas") or [])
        found = False
        for ln in lineas:
            if ln["producto_id"] == producto_id:
                ln["cantidad"] = round(float(ln["cantidad"]) + float(delta), 4)
                found = True
                break
        if found:
            self._edicion["lineas"] = [
                ln for ln in lineas if float(ln.get("cantidad") or 0) > 0
            ]
        return self.screen()

    def quitar_linea_edicion(self, producto_id: str) -> TerminalScreenVM:
        if not self._edicion:
            return self.screen()
        self._edicion["lineas"] = [
            ln
            for ln in (self._edicion.get("lineas") or [])
            if ln["producto_id"] != producto_id
        ]
        return self.screen()

    def anadir_producto_edicion(
        self, producto_id: str, cantidad: float = 1.0
    ) -> TerminalScreenVM:
        if not self._edicion:
            return self.screen()
        from app.core.services.data_service import get_repository

        repo = get_repository()
        prod = repo.get_producto(producto_id)
        if prod is None:
            self._feedback = map_error_recuperable("Producto no encontrado.")
            return self.screen()
        qty = max(float(cantidad), 0.0)
        if qty <= 0:
            return self.screen()
        lineas = list(self._edicion.get("lineas") or [])
        for ln in lineas:
            if ln["producto_id"] == producto_id:
                ln["cantidad"] = round(float(ln["cantidad"]) + qty, 4)
                self._edicion["lineas"] = lineas
                return self.screen()
        lineas.append(
            {
                "producto_id": producto_id,
                "nombre": prod.nombre,
                "cantidad": qty,
                "unidad": prod.unidad.value,
            }
        )
        self._edicion["lineas"] = lineas
        return self.screen()

    def guardar_edicion(self) -> TerminalScreenVM:
        from app.core.services.rectificacion_registro_service import (
            rectificar_lineas_registro,
        )

        if not self._edicion:
            return self.screen()
        self._editando = True
        try:
            lineas = [
                (str(ln["producto_id"]), float(ln["cantidad"]))
                for ln in (self._edicion.get("lineas") or [])
                if float(ln.get("cantidad") or 0) > 0
            ]
            r = rectificar_lineas_registro(
                str(self._edicion["registro_id"]),
                lineas,
                tipo_registro=str(self._edicion["tipo_registro"]),
            )
            self._feedback = map_resultado(r.ok, r.mensaje, r.codigo)
            if r.ok:
                self._edicion = None
        finally:
            self._editando = False
        return self.screen()

    def _require_bind(self) -> _ServicioBind | None:
        if not session_bridge.puede_usar_terminal():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return None
        if not self._servicio_id:
            self._feedback = map_error_recuperable("Seleccione un servicio.")
            return None
        return _binds()[self._servicio_id]

    def _tipo_registro_bind(self, bind: _ServicioBind) -> str:
        return anul.TIPO_DESAYUNO if bind.id == "desayuno" else anul.TIPO_SERVICIO

    def _buscar_registro(self, data, registro_id: str, tipo: str):
        if tipo == anul.TIPO_DESAYUNO:
            return next((d for d in data.desayunos if d.id == registro_id), None)
        return next((r for r in data.registros_servicio if r.id == registro_id), None)

    def _historial_vm(self, bind: _ServicioBind) -> tuple[HistorialRegistroVM, ...]:
        data = get_container().app_data_store.get()
        tipo = self._tipo_registro_bind(bind)
        regs = list(bind.api.historial_ordenado())
        out: list[HistorialRegistroVM] = []
        for reg in regs[:_HISTORIAL_LIMITE]:
            out.append(self._historial_item_vm(data, reg, tipo, bind.etiqueta))
        return tuple(out)

    def _historial_item_vm(
        self, data, registro, tipo: str, servicio_etiqueta: str
    ) -> HistorialRegistroVM:
        anulado = anul.registro_esta_anulado(registro)
        fecha = registro.fecha.isoformat() if getattr(registro, "fecha", None) else ""
        hora_v = getattr(registro, "hora", None)
        hora = (
            hora_v.strftime("%H:%M")
            if isinstance(hora_v, time)
            else (str(hora_v)[:5] if hora_v else "")
        )
        n_rec = len(getattr(registro, "registros_recetas", None) or [])
        n_prod = len(
            [
                ln
                for ln in (getattr(registro, "lineas_detalle", None) or [])
                if getattr(ln, "cantidad", 0) > 0
            ]
        )
        hues = getattr(registro, "num_huespedes", 0) or 0
        partes = [f"{n_rec} receta(s)" if n_rec else "", f"{n_prod} línea(s)"]
        if tipo == anul.TIPO_DESAYUNO and hues:
            partes.insert(0, f"{hues} huésped(es)")
        resumen = " · ".join(p for p in partes if p) or "Sin detalle operativo"
        etiqueta = f"{servicio_etiqueta} · {fecha}" + (f" {hora}" if hora else "")
        if anulado:
            estado = "anulado"
            puede = False
            motivo = "Registro ya anulado."
        elif bool(getattr(registro, "revision_confirmada", False)):
            estado = "confirmado"
            puede = False
            motivo = "Registro revisado y confirmado."
        else:
            puede_r = anul.puede_anular_registro(data, registro, tipo=tipo)
            if puede_r.ok:
                estado = "activo"
                puede = True
                motivo = ""
            else:
                estado = "no_anulable"
                puede = False
                motivo = " ".join(puede_r.motivos_bloqueo)
        return HistorialRegistroVM(
            registro_id=registro.id,
            tipo_registro=tipo,
            etiqueta_corta=etiqueta,
            fecha=fecha,
            hora=hora,
            resumen=resumen,
            estado=estado,
            puede_anular=puede,
            motivo_bloqueo=motivo,
            detalle_lineas=self._detalle_historial_lineas(data, registro),
            observaciones=str(getattr(registro, "observaciones", "") or ""),
            puede_confirmar_revision=(
                not anulado and not bool(getattr(registro, "revision_confirmada", False))
            ),
            revision_confirmada=bool(getattr(registro, "revision_confirmada", False)),
            puede_editar=puede,
        )

    def _detalle_historial_lineas(self, data, registro) -> tuple[str, ...]:
        from collections import defaultdict

        from app.core.repositories.data_repository import DataRepository

        dr = DataRepository(data)
        out: list[str] = []
        for rec in getattr(registro, "registros_recetas", None) or []:
            extras = []
            for ex in getattr(rec, "extras", None) or []:
                extras.append(
                    f"+ {dr.get_nombre_producto(ex.producto_id)} ({float(ex.cantidad):g})"
                )
            omisiones = []
            for om in getattr(rec, "omisiones", None) or []:
                omisiones.append(f"sin {dr.get_nombre_producto(om.producto_id)}")
            suf = ""
            mods = extras + omisiones
            if mods:
                suf = " · " + ", ".join(mods)
            out.append(f"Receta: {rec.nombre_receta} x{float(rec.porciones):g}{suf}")

        directos: dict[str, float] = defaultdict(float)
        for lin in getattr(registro, "lineas", None) or []:
            if getattr(lin, "es_extra", False):
                continue
            directos[lin.producto_id] += float(lin.cantidad)
        for pid, qty in sorted(directos.items(), key=lambda kv: dr.get_nombre_producto(kv[0]).lower()):
            out.append(f"Producto: {dr.get_nombre_producto(pid)} x{qty:g}")

        extras_sueltos: dict[str, float] = defaultdict(float)
        for lin in getattr(registro, "lineas", None) or []:
            if not getattr(lin, "es_extra", False):
                continue
            extras_sueltos[lin.producto_id] += float(lin.cantidad)
        for pid, qty in sorted(extras_sueltos.items(), key=lambda kv: dr.get_nombre_producto(kv[0]).lower()):
            out.append(f"Extra: {dr.get_nombre_producto(pid)} x{qty:g}")
        return tuple(out[:40])

    def _importacion_tpv_vm(self, resultado) -> ImportacionTpvVM:
        lineas: list[str] = []
        if resultado.lineas_detectadas:
            lineas.append(f"{resultado.lineas_detectadas} líneas leídas del documento")
        if resultado.registros_ok:
            lineas.append(f"{resultado.registros_ok} registro(s) confirmado(s)")
        if resultado.fechas:
            lineas.append(
                "Fechas: "
                + ", ".join(resultado.fechas[:10])
                + ("…" if len(resultado.fechas) > 10 else "")
            )
        for item in resultado.registros_creados[:20]:
            tipo = str(item.get("tipo") or "servicio").capitalize()
            fecha = item.get("fecha") or "—"
            ref = item.get("ref") or "—"
            lineas.append(f"· {tipo} {fecha} · ref. {ref}")
        if resultado.omitidos_idempotentes:
            lineas.append(
                f"{resultado.omitidos_idempotentes} registro(s) ya existían (sin duplicar)"
            )

        advertencias: list[str] = []
        for nombre in resultado.sin_mapear[:15]:
            advertencias.append(f"Sin mapear: {nombre}")
        if len(resultado.sin_mapear) > 15:
            advertencias.append(
                f"… y {len(resultado.sin_mapear) - 15} producto(s) más sin mapear"
            )
        if resultado.pendientes_coctel:
            advertencias.append(
                f"{len(resultado.pendientes_coctel)} cóctel del día pendiente(s) de lista"
            )
        for err in resultado.errores[:10]:
            advertencias.append(str(err))

        titulo = (
            "Documento TPV registrado"
            if resultado.ok
            else "Importación TPV con incidencias"
        )
        historial = self._historial_desde_refs_tpv(resultado.registros_creados)
        if not lineas and not advertencias:
            lineas = ["No se registró ninguna venta."]
        return ImportacionTpvVM(
            ok=resultado.ok,
            titulo=titulo,
            lineas=tuple(lineas),
            advertencias=tuple(advertencias),
            historial=historial,
        )

    def _historial_desde_refs_tpv(
        self, refs: list[dict]
    ) -> tuple[HistorialRegistroVM, ...]:
        if not refs:
            return ()
        data = get_container().app_data_store.get()
        etiquetas = {"comida": "Comida", "bebidas": "Bebidas independientes"}
        out: list[HistorialRegistroVM] = []
        for item in refs:
            ref = item.get("ref")
            if not ref:
                continue
            reg = next((r for r in data.registros_servicio if r.id == ref), None)
            if reg is None:
                continue
            tipo_srv = str(item.get("tipo") or "comida")
            out.append(
                self._historial_item_vm(
                    data,
                    reg,
                    anul.TIPO_SERVICIO,
                    etiquetas.get(tipo_srv, tipo_srv.capitalize()),
                )
            )
        return tuple(out)

    def _catalogo(self, bind: _ServicioBind) -> tuple[CatalogItemVM, ...]:
        from datetime import date as _date

        from app.core.services.receta_service import (
            ETIQUETA_TOSTADA_DEL_DIA,
            es_receta_tostada_weekday,
            listar_recetas,
            receta_tostada_del_dia,
        )

        items: list[CatalogItemVM] = []
        q = self._busqueda
        tipo = self._catalogo_tipo or "recetas"

        # Desayuno → Bebidas: cafés/tés/Cola Cao (recetas) + leches + frias.
        if bind.id == "desayuno" and tipo == "bebidas":
            from app.core.models import CategoriaReceta
            from app.core.services.desayuno_service import (
                bebidas_frias_rapidas_desayuno,
                es_receta_bebida_desayuno,
                leches_rapidas_desayuno,
            )

            recetas = listar_recetas(
                categorias=[CategoriaReceta.BEBIDAS],
                servicio_disponible="desayuno",
                solo_activas=True,
            )
            for r in recetas:
                if not es_receta_bebida_desayuno(r.nombre):
                    continue
                if q and not coincide_busqueda(r.nombre, q):
                    continue
                items.append(
                    CatalogItemVM(
                        id=r.id,
                        nombre=r.nombre,
                        tipo="receta",
                        categoria="bebidas",
                    )
                )
            stock_por_id = {
                str(p["id"]): float(p["stock"]) if p.get("stock") is not None else 0.0
                for p in bind.api.productos_catalogo("")
            }
            # Stock de frias/leches puede estar solo en servicio «bebidas».
            from app.core.services import bebida_service as _beb_svc

            for p in _beb_svc.servicio.productos_catalogo(""):
                stock_por_id.setdefault(
                    str(p["id"]),
                    float(p["stock"]) if p.get("stock") is not None else 0.0,
                )
            for ex in leches_rapidas_desayuno():
                label = str(ex.get("label") or "")
                nombre_prod = str(ex.get("nombre") or "")
                if q and not (
                    coincide_busqueda(label, q) or coincide_busqueda(nombre_prod, q)
                ):
                    continue
                pid = str(ex["producto_id"])
                cant = float(ex.get("cantidad") or 0)
                cant_m = float(ex.get("cantidad_mostrar") or cant)
                uni_m = str(ex.get("unidad_mostrar") or ex.get("unidad") or "")
                items.append(
                    CatalogItemVM(
                        id=pid,
                        nombre=label or nombre_prod,
                        tipo="producto_directo",
                        unidad=str(ex.get("unidad") or ""),
                        stock_disponible=stock_por_id.get(pid),
                        es_bebida=False,
                        cantidad_default=cant if cant > 0 else None,
                        hint_extra=(
                            f"ración {cant_m:g} {uni_m} · con Espresso si es vegetal"
                        ),
                    )
                )
            for ex in bebidas_frias_rapidas_desayuno():
                label = str(ex.get("label") or "")
                nombre_prod = str(ex.get("nombre") or "")
                if q and not (
                    coincide_busqueda(label, q) or coincide_busqueda(nombre_prod, q)
                ):
                    continue
                pid = str(ex["producto_id"])
                cant = float(ex.get("cantidad") or 0)
                items.append(
                    CatalogItemVM(
                        id=pid,
                        nombre=label or nombre_prod,
                        tipo="producto_directo",
                        unidad=str(ex.get("unidad") or "Ud"),
                        stock_disponible=stock_por_id.get(pid),
                        es_bebida=True,
                        cantidad_default=cant if cant > 0 else None,
                        hint_extra="1 botella/lata = 1 Ud inventario",
                    )
                )
            return tuple(items)

        # Comida/Cena «Bebidas»: mismas recetas que Bebidas independientes (sin sueltos).
        if bind.id in ("comida", "cena") and tipo == "bebidas":
            from app.core.models import CategoriaReceta

            for r in listar_recetas(
                categorias=[CategoriaReceta.BEBIDAS],
                servicio_disponible="bebidas",
                solo_activas=True,
            ):
                if q and not coincide_busqueda(r.nombre, q):
                    continue
                items.append(
                    CatalogItemVM(
                        id=r.id,
                        nombre=r.nombre,
                        tipo="receta",
                        categoria="bebidas",
                    )
                )
            return tuple(items)

        # Bebidas independientes: solo recetas (sin productos sueltos).
        if bind.id == "bebidas":
            incluir_recetas = True
            incluir_productos = False
        else:
            incluir_recetas = tipo in ("todas", "recetas")
            # «bebidas» en comida/cena ya retornó arriba; desayuno tiene rama propia.
            incluir_productos = tipo in ("todas", "productos")

        if incluir_recetas:
            from app.core.models import CategoriaReceta

            if bind.id in ("comida", "cena") and tipo == "todas":
                cats_plato = (
                    {CategoriaReceta.COMIDA}
                    if bind.id == "comida"
                    else {CategoriaReceta.CENA}
                )
                vistos: set[str] = set()
                for r in listar_recetas(
                    servicio_disponible=bind.id, solo_activas=True
                ):
                    if r.categoria not in cats_plato:
                        continue
                    if q and not coincide_busqueda(r.nombre, q):
                        continue
                    vistos.add(r.id)
                    items.append(
                        CatalogItemVM(
                            id=r.id,
                            nombre=r.nombre,
                            tipo="receta",
                            categoria=getattr(r.categoria, "value", str(r.categoria)),
                        )
                    )
                for r in listar_recetas(
                    categorias=[CategoriaReceta.BEBIDAS],
                    servicio_disponible="bebidas",
                    solo_activas=True,
                ):
                    if r.id in vistos:
                        continue
                    if q and not coincide_busqueda(r.nombre, q):
                        continue
                    items.append(
                        CatalogItemVM(
                            id=r.id,
                            nombre=r.nombre,
                            tipo="receta",
                            categoria="bebidas",
                        )
                    )
            else:
                recetas = listar_recetas(
                    servicio_disponible=bind.id, solo_activas=True
                )
                cats = getattr(bind.api, "categorias_permitidas", None)
                if cats is None and bind.id == "desayuno":
                    cats = [CategoriaReceta.DESAYUNO]
                if cats is not None:
                    allowed = set(cats)
                    # Plato: no mezclar bebidas en «Recetas» (van al chip Bebidas).
                    if bind.id == "desayuno" and tipo == "recetas":
                        allowed = {CategoriaReceta.DESAYUNO}
                    elif bind.id == "comida" and tipo == "recetas":
                        allowed = {CategoriaReceta.COMIDA}
                    elif bind.id == "cena" and tipo == "recetas":
                        allowed = {CategoriaReceta.CENA}
                    elif bind.id == "bebidas":
                        allowed = {CategoriaReceta.BEBIDAS}
                    recetas = [r for r in recetas if r.categoria in allowed]
                # Desayuno: 7 tostadas weekday → una ficha «Tostada del dia».
                if bind.id == "desayuno":
                    del_dia = receta_tostada_del_dia(_date.today())
                    recetas = [
                        r for r in recetas if not es_receta_tostada_weekday(r.nombre)
                    ]
                    if del_dia is not None and (
                        not q or coincide_busqueda(ETIQUETA_TOSTADA_DEL_DIA, q)
                    ):
                        items.append(
                            CatalogItemVM(
                                id=del_dia.id,
                                nombre=ETIQUETA_TOSTADA_DEL_DIA,
                                tipo="receta",
                                categoria=getattr(
                                    del_dia.categoria, "value", str(del_dia.categoria)
                                ),
                            )
                        )
                # Bebidas: calendario semanal → una ficha «Cóctel del día».
                if bind.id == "bebidas":
                    from app.core.services.receta_service import (
                        ETIQUETA_COCTEL_DEL_DIA,
                        es_receta_coctel_del_calendario,
                        receta_coctel_del_dia,
                    )

                    coctel = receta_coctel_del_dia(_date.today())
                    # No ocultar los cócteles del calendario: siguen listables.
                    # Solo prioriza la ficha del día arriba.
                    if coctel is not None and (
                        not q or coincide_busqueda(ETIQUETA_COCTEL_DEL_DIA, q)
                        or coincide_busqueda(coctel.nombre, q)
                    ):
                        items.append(
                            CatalogItemVM(
                                id=coctel.id,
                                nombre=f"{ETIQUETA_COCTEL_DEL_DIA} ({coctel.nombre})",
                                tipo="receta",
                                categoria=getattr(
                                    coctel.categoria, "value", str(coctel.categoria)
                                ),
                            )
                        )
                for r in recetas:
                    if bind.id == "desayuno" and tipo == "todas":
                        from app.core.services.desayuno_service import (
                            es_receta_bebida_desayuno,
                        )

                        if r.categoria == CategoriaReceta.BEBIDAS and not es_receta_bebida_desayuno(
                            r.nombre
                        ):
                            continue
                    if q and not coincide_busqueda(r.nombre, q):
                        continue
                    items.append(
                        CatalogItemVM(
                            id=r.id,
                            nombre=r.nombre,
                            tipo="receta",
                            categoria=getattr(r.categoria, "value", str(r.categoria)),
                        )
                    )
        if incluir_productos:
            # Desayuno: lista corta de extras con cantidad estándar (más cómoda).
            if bind.id == "desayuno" and tipo in ("productos", "todas"):
                from app.core.services.desayuno_service import extras_rapidos_desayuno

                stock_por_id = {
                    str(p["id"]): float(p["stock"]) if p.get("stock") is not None else 0.0
                    for p in bind.api.productos_catalogo("")
                }
                ids_rapidos: set[str] = set()
                for ex in extras_rapidos_desayuno():
                    label = str(ex.get("label") or "")
                    nombre_prod = str(ex.get("nombre") or "")
                    if q and not (
                        coincide_busqueda(label, q) or coincide_busqueda(nombre_prod, q)
                    ):
                        continue
                    pid = str(ex["producto_id"])
                    ids_rapidos.add(pid)
                    unidad = str(ex.get("unidad") or "")
                    cant = float(ex.get("cantidad") or 0)
                    cant_m = float(ex.get("cantidad_mostrar") or cant)
                    uni_m = str(ex.get("unidad_mostrar") or unidad)
                    items.append(
                        CatalogItemVM(
                            id=pid,
                            nombre=label or nombre_prod,
                            tipo="producto_directo",
                            unidad=unidad,
                            stock_disponible=stock_por_id.get(pid),
                            es_bebida=False,
                            cantidad_default=cant if cant > 0 else None,
                            hint_extra=f"porción {cant_m:g} {uni_m}",
                        )
                    )
                # En «Extras / productos» de desayuno solo la lista rápida.
                if tipo == "productos":
                    return tuple(items)
            else:
                ids_rapidos = set()
            for p in bind.api.productos_catalogo(q):
                es_bebida = bool(p.get("es_bebida"))
                # Comida/cena: nunca productos sueltos de bebida (usar chip Bebidas = recetas).
                if bind.id in ("comida", "cena") and es_bebida:
                    continue
                if tipo == "bebidas" and not es_bebida:
                    continue
                if tipo == "productos" and es_bebida:
                    continue
                if bind.id == "desayuno" and tipo == "todas" and p["id"] in ids_rapidos:
                    continue
                items.append(
                    CatalogItemVM(
                        id=p["id"],
                        nombre=p["nombre"],
                        tipo="producto_directo",
                        unidad=str(p.get("unidad") or ""),
                        stock_disponible=(
                            float(p["stock"]) if p.get("stock") is not None else None
                        ),
                        es_bebida=es_bebida,
                    )
                )
        # Bebidas independientes: agua / soda / refrescos (1 Ud).
        if bind.id == "bebidas":
            from app.core.services.desayuno_service import bebidas_frias_rapidas_desayuno

            stock_por_id = {
                str(p["id"]): float(p["stock"]) if p.get("stock") is not None else 0.0
                for p in bind.api.productos_catalogo("")
            }
            for ex in bebidas_frias_rapidas_desayuno():
                label = str(ex.get("label") or "")
                nombre_prod = str(ex.get("nombre") or "")
                if q and not (
                    coincide_busqueda(label, q) or coincide_busqueda(nombre_prod, q)
                ):
                    continue
                pid = str(ex["producto_id"])
                cant = float(ex.get("cantidad") or 0)
                items.append(
                    CatalogItemVM(
                        id=pid,
                        nombre=label or nombre_prod,
                        tipo="producto_directo",
                        unidad=str(ex.get("unidad") or "Ud"),
                        stock_disponible=stock_por_id.get(pid),
                        es_bebida=True,
                        cantidad_default=cant if cant > 0 else None,
                        hint_extra="1 botella/lata = 1 Ud inventario",
                    )
                )
        return tuple(items)

    def _cesta_vm(self, bind: _ServicioBind) -> BasketVM:
        from app.core.services.receta_service import obtener_receta
        from app.core.services.data_service import get_repository

        lineas: list[BasketLineVM] = []
        extras: list[BasketExtraVM] = []
        vistos_extra: set[str] = set()
        repo = get_repository()
        for g in bind.api.get_cesta_recetas():
            lineas.append(
                BasketLineVM(
                    kind="receta",
                    line_id=g.grupo_id,
                    nombre=g.nombre_receta,
                    cantidad=float(g.porciones),
                    unidad="raciones",
                )
            )
            for ing in getattr(g, "ingredientes", None) or []:
                if getattr(ing, "es_base_receta", False) and not (
                    getattr(ing, "es_omision", False) or float(ing.cantidad) < 0
                ):
                    continue
                if not (
                    getattr(ing, "es_extra", False)
                    or getattr(ing, "es_omision", False)
                    or float(ing.cantidad) < 0
                    or (not getattr(ing, "es_base_receta", True) and float(ing.cantidad) != 0)
                ):
                    continue
                pref = "s/" if (getattr(ing, "es_omision", False) or float(ing.cantidad) < 0) else "c/"
                lineas.append(
                    BasketLineVM(
                        kind="mod",
                        line_id=str(getattr(ing, "linea_id", "") or ""),
                        nombre=f"{pref} {ing.nombre}",
                        cantidad=abs(float(ing.cantidad)),
                        unidad=str(getattr(ing, "unidad", "") or ""),
                    )
                )
            rec = obtener_receta(getattr(g, "receta_id", "") or "")
            if rec is None:
                continue
            for ex in getattr(rec, "extras_sugeridos", None) or []:
                if ex.producto_id in vistos_extra:
                    continue
                prod = repo.get_producto(ex.producto_id)
                if prod is None or not getattr(prod, "activo", True):
                    continue
                vistos_extra.add(ex.producto_id)
                extras.append(
                    BasketExtraVM(
                        producto_id=ex.producto_id,
                        nombre=prod.nombre,
                        cantidad=float(ex.cantidad),
                        unidad=str(getattr(prod, "unidad", "") or ""),
                        receta_nombre=rec.nombre,
                    )
                )
        for lin in bind.api.get_cesta():
            lineas.append(
                BasketLineVM(
                    kind="producto",
                    line_id=lin.linea_id,
                    nombre=lin.nombre,
                    cantidad=float(lin.cantidad),
                    unidad=str(lin.unidad or ""),
                )
            )
        return BasketVM(
            lineas=tuple(lineas),
            vacia=bind.api.cesta_vacia(),
            servicio_id=bind.id,
            servicio_etiqueta=bind.etiqueta,
            extras_sugeridos=tuple(extras),
        )
