"""Presenter de Terminal Restaurante — orquesta UI Flet y casos de uso.

Sin cálculos de dominio en esta capa. Sin información económica.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.application.idempotency import (
    current_idempotency_token,
    rotate_idempotency_token,
)
from app.core.auth.permissions import AuthorizationError, Permiso
from app.core.auth.session import session_tiene_permiso
from app.core.services import bebida_service, cena_service, comida_service
from app.core.services.desayuno_service import desayuno_registro
from app.core.services.receta_service import listar_recetas
from app.core.services.text_search import coincide_busqueda
from app.presentation.flet import session_bridge
from app.presentation.flet.mappers import map_error_recuperable, map_resultado
from app.presentation.flet.viewmodels import (
    BasketLineVM,
    BasketVM,
    CatalogItemVM,
    FeedbackVM,
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
        self._feedback: FeedbackVM | None = None
        self._confirmando: bool = False
        self._num_huespedes: int = 30
        assert_sin_campos_economicos(CatalogItemVM)
        assert_sin_campos_economicos(BasketLineVM)
        assert_sin_campos_economicos(BasketVM)

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
        return self.screen()

    def seleccionar_servicio(self, servicio_id: str) -> TerminalScreenVM:
        if servicio_id not in _binds():
            self._feedback = map_error_recuperable("Servicio no reconocido.")
            return self.screen()
        if not session_bridge.puede_usar_terminal():
            self._feedback = map_error_recuperable("Sesión no autorizada.")
            return self.screen()
        self._servicio_id = servicio_id
        self._busqueda = ""
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Servicio activo: {_binds()[servicio_id].etiqueta}"
        )
        return self.screen()

    def set_busqueda(self, texto: str) -> TerminalScreenVM:
        self._busqueda = (texto or "").strip()
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
        if self._confirmando:
            self._feedback = map_error_recuperable(
                "Confirmación en curso. Espere un momento.", codigo="CONFIRMANDO"
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
        session = session_bridge.current_session_vm()
        servicios = tuple(
            ServicioVM(id=sid, etiqueta=etq, activo=(sid == self._servicio_id))
            for sid, etq in SERVICIOS
        )
        catalogo: tuple[CatalogItemVM, ...] = ()
        cesta: BasketVM | None = None
        requiere_h = False
        if session.authenticated and self._servicio_id:
            bind = _binds()[self._servicio_id]
            requiere_h = bind.requiere_huespedes
            catalogo = self._catalogo(bind)
            cesta = self._cesta_vm(bind)
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

    def _catalogo(self, bind: _ServicioBind) -> tuple[CatalogItemVM, ...]:
        items: list[CatalogItemVM] = []
        q = self._busqueda
        recetas = listar_recetas(servicio_disponible=bind.id, solo_activas=True)
        cats = getattr(bind.api, "categorias_permitidas", None)
        if cats is None and bind.id == "desayuno":
            from app.core.models import CategoriaReceta

            cats = [CategoriaReceta.DESAYUNO, CategoriaReceta.BEBIDAS]
        if cats is not None:
            allowed = set(cats)
            recetas = [r for r in recetas if r.categoria in allowed]
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
        for p in bind.api.productos_catalogo(q):
            items.append(
                CatalogItemVM(
                    id=p["id"],
                    nombre=p["nombre"],
                    tipo="producto_directo",
                    unidad=str(p.get("unidad") or ""),
                    stock_disponible=(
                        float(p["stock"]) if p.get("stock") is not None else None
                    ),
                    es_bebida=bool(p.get("es_bebida")),
                )
            )
        return tuple(items)

    def _cesta_vm(self, bind: _ServicioBind) -> BasketVM:
        lineas: list[BasketLineVM] = []
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
        )
