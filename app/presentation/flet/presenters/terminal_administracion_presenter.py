"""Presenter Administración operativa — responsables de merma.

Reutiliza merma_service. Sin economía, sin JSON directo, sin reglas de dominio.
"""

from __future__ import annotations

from app.core.models import MotivoMerma
from app.core.services import merma_service
from app.presentation.flet import session_bridge
from app.presentation.flet.admin_viewmodels import (
    AdminScreenVM,
    PendingChangeVM,
    ResponsableMermaVM,
    assert_admin_sin_economia,
)
from app.presentation.flet.mappers import (
    map_admin_operacion_feedback,
    map_error_recuperable,
)
from app.presentation.flet.viewmodels import FeedbackVM


class TerminalAdministracionPresenter:
    def __init__(self) -> None:
        self._feedback: FeedbackVM | None = None
        self._filtro = ""
        self._pending: PendingChangeVM | None = None
        self._mutando = False
        assert_admin_sin_economia(ResponsableMermaVM, PendingChangeVM, AdminScreenVM)

    def login(self, login: str, password: str) -> AdminScreenVM:
        session, fb = session_bridge.login_administracion(login, password)
        self._feedback = fb
        self._pending = None
        if session.authenticated and fb is None:
            self._feedback = FeedbackVM(ok=True, mensaje="Sesión administrativa iniciada.")
        return self.screen()

    def logout(self) -> AdminScreenVM:
        session_bridge.logout_terminal()
        self._feedback = FeedbackVM(ok=True, mensaje="Sesión cerrada.")
        self._pending = None
        self._mutando = False
        return self.screen()

    def set_filtro(self, texto: str) -> AdminScreenVM:
        self._filtro = (texto or "").strip()
        return self.screen()

    def proponer_creacion(self, nombre: str) -> AdminScreenVM:
        if not session_bridge.puede_usar_administracion():
            self._feedback = map_error_recuperable(
                "Sesión no autorizada.", codigo="DENEGADO"
            )
            return self.screen()
        texto = (nombre or "").strip()
        if not texto:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Indique un nombre de responsable."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="crear",
            resumen=f"Crear responsable «{texto}» (activo).",
            nombre=texto,
        )
        self._feedback = FeedbackVM(
            ok=True, mensaje="Revise el resumen y confirme la creación."
        )
        return self.screen()

    def proponer_renombre(self, responsable_id: str, nombre: str) -> AdminScreenVM:
        if not session_bridge.puede_usar_administracion():
            self._feedback = map_error_recuperable(
                "Sesión no autorizada.", codigo="DENEGADO"
            )
            return self.screen()
        texto = (nombre or "").strip()
        actual = next(
            (r for r in merma_service.listar_responsables_merma() if r.id == responsable_id),
            None,
        )
        if not actual:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Responsable no encontrado."
            )
            return self.screen()
        if not texto:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Indique un nombre de responsable."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="renombrar",
            resumen=(
                f"Renombrar «{actual.nombre}» → «{texto}». "
                "El histórico conserva el nombre capturado en cada línea."
            ),
            responsable_id=responsable_id,
            nombre=texto,
        )
        self._feedback = FeedbackVM(
            ok=True, mensaje="Revise el resumen y confirme el renombre."
        )
        return self.screen()

    def proponer_desactivacion(self, responsable_id: str) -> AdminScreenVM:
        if not session_bridge.puede_usar_administracion():
            self._feedback = map_error_recuperable(
                "Sesión no autorizada.", codigo="DENEGADO"
            )
            return self.screen()
        actual = next(
            (r for r in merma_service.listar_responsables_merma() if r.id == responsable_id),
            None,
        )
        if not actual:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Responsable no encontrado."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="desactivar",
            resumen=(
                f"Desactivar «{actual.nombre}». No estará disponible en operaciones nuevas; "
                "el histórico no se altera."
            ),
            responsable_id=responsable_id,
            nombre=actual.nombre,
        )
        self._feedback = FeedbackVM(
            ok=True, mensaje="Confirme la desactivación."
        )
        return self.screen()

    def proponer_reactivacion(self, responsable_id: str) -> AdminScreenVM:
        if not session_bridge.puede_usar_administracion():
            self._feedback = map_error_recuperable(
                "Sesión no autorizada.", codigo="DENEGADO"
            )
            return self.screen()
        actual = next(
            (r for r in merma_service.listar_responsables_merma() if r.id == responsable_id),
            None,
        )
        if not actual:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Responsable no encontrado."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="reactivar",
            resumen=f"Reactivar «{actual.nombre}» para operaciones nuevas.",
            responsable_id=responsable_id,
            nombre=actual.nombre,
        )
        self._feedback = FeedbackVM(
            ok=True, mensaje="Confirme la reactivación."
        )
        return self.screen()

    def cancelar_pendiente(self) -> AdminScreenVM:
        self._pending = None
        self._feedback = FeedbackVM(ok=True, mensaje="Cambio cancelado.")
        return self.screen()

    def confirmar_pendiente(self) -> AdminScreenVM:
        if not session_bridge.puede_usar_administracion():
            self._feedback = map_error_recuperable(
                "Sesión no autorizada.", codigo="DENEGADO"
            )
            self._pending = None
            return self.screen()
        if self._mutando:
            self._feedback = map_error_recuperable(
                "Operación en curso.", codigo="CONFIRMANDO"
            )
            return self.screen()
        pending = self._pending
        if pending is None:
            self._feedback = map_error_recuperable("No hay cambio pendiente.")
            return self.screen()
        self._mutando = True
        try:
            if pending.kind == "crear":
                r = merma_service.crear_responsable_merma(pending.nombre)
            elif pending.kind == "renombrar":
                r = merma_service.renombrar_responsable_merma(
                    pending.responsable_id, pending.nombre
                )
            elif pending.kind == "desactivar":
                r = merma_service.desactivar_responsable_merma(pending.responsable_id)
            elif pending.kind == "reactivar":
                r = merma_service.reactivar_responsable_merma(pending.responsable_id)
            else:
                self._feedback = map_error_recuperable("Operación no reconocida.")
                return self.screen()
            self._feedback = map_admin_operacion_feedback(
                ok=r.ok, mensaje_backend=r.mensaje
            )
            if r.ok:
                self._pending = None
        finally:
            self._mutando = False
        return self.screen()

    def screen(self) -> AdminScreenVM:
        sess = session_bridge.current_session_vm()
        items: tuple[ResponsableMermaVM, ...] = ()
        if sess.authenticated and session_bridge.puede_usar_administracion():
            q = self._filtro.lower()
            lista = []
            for r in merma_service.listar_responsables_merma(solo_activos=False):
                if q and q not in r.nombre.lower() and q not in r.id.lower():
                    continue
                lista.append(
                    ResponsableMermaVM(id=r.id, nombre=r.nombre, activo=r.activo)
                )
            items = tuple(lista)
        return AdminScreenVM(
            session=sess,
            responsables=items,
            filtro=self._filtro,
            feedback=self._feedback,
            pending=self._pending,
            mutando=self._mutando,
            motivos_fijos=tuple(m.value for m in MotivoMerma),
        )
