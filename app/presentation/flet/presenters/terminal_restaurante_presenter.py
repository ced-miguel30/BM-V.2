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
    FeedbackVM,
    HistorialRegistroVM,
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

    def seleccionar_servicio(self, servicio_id: str) -> TerminalScreenVM:
        if servicio_id not in _binds():
            self._feedback = map_error_recuperable("Servicio no reconocido.")
            return self.screen()
        if not session_bridge.puede_usar_terminal():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        self._servicio_id = servicio_id
        self._busqueda = ""
        self._catalogo_tipo = "recetas" if servicio_id != "bebidas" else "todas"
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
        resultado = bind.api.anadir_a_cesta(producto_id, float(cantidad))
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
            anulacion_pendiente=self._anulacion_pendiente,
            anulando=self._anulando,
        )
        assert_sin_campos_economicos(vm)
        return vm

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
        )

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
        incluir_recetas = tipo in ("todas", "recetas")
        incluir_productos = tipo in ("todas", "productos", "bebidas")
        if incluir_recetas:
            recetas = listar_recetas(servicio_disponible=bind.id, solo_activas=True)
            cats = getattr(bind.api, "categorias_permitidas", None)
            if cats is None and bind.id == "desayuno":
                from app.core.models import CategoriaReceta

                cats = [CategoriaReceta.DESAYUNO]
            if cats is not None:
                allowed = set(cats)
                recetas = [r for r in recetas if r.categoria in allowed]
            # Desayuno: 7 tostadas weekday → una ficha «Tostada del dia».
            if bind.id == "desayuno":
                del_dia = receta_tostada_del_dia(_date.today())
                recetas = [r for r in recetas if not es_receta_tostada_weekday(r.nombre)]
                if del_dia is not None:
                    if not q or coincide_busqueda(ETIQUETA_TOSTADA_DEL_DIA, q):
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
            for r in recetas:
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
            for p in bind.api.productos_catalogo(q):
                es_bebida = bool(p.get("es_bebida"))
                if tipo == "bebidas" and not es_bebida:
                    continue
                if tipo == "productos" and es_bebida:
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
