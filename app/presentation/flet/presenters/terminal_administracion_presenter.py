"""Presenter Administración operativa — maestros, proveedores, compras, backup, cierre.

Reutiliza stock/receta/settings/backup/restore/merma/proveedor/compra_registro/
catalogo/dashboard/destructive_ops/documento_consulta/instance_config.
Sin reglas de dominio nuevas.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from app.bootstrap import get_container
from app.core.auth.permissions import Permiso
from app.core.auth.roles import roles_asignables
from app.core.auth.session import session_tiene_permiso
from app.core.models import IngredienteReceta, MotivoMerma, TipoDocumento
from app.core.models.enums import (
    CategoriaReceta,
    SERVICIOS_DISPONIBLES_VALORES,
    TIPO_ARTICULO_VALORES,
    UnidadProducto,
)
from app.core.repositories.data_repository import DataRepository
from app.core.services import (
    caducidad_service,
    catalogo_service,
    compra_registro_service,
    dashboard_service,
    documento_consulta_service,
    destructive_ops_service,
    merma_service,
    proveedor_service,
    receta_service,
    settings_service,
    stock_service,
)
from app.core.services.backup_service import generar_backup_zip
from app.core.services.restore_backup_service import (
    inspeccionar_backup,
    restaurar_desde_bytes,
)
from app.core.storage.demo_files import get_demo_file
from app.core.storage.instance_config import (
    InstanceConfigError,
    apply_shared_root,
    load_client_config,
    resolve_data_file_from_shared_root,
    resolve_shared_root,
    save_client_config,
    validate_shared_root,
)
from app.core.storage.session_store import reload_from_disk
from app.core.storage.shared_coordinator import (
    SharedPathUnavailable,
    assert_data_path_usable,
)
from app.presentation.flet import session_bridge
from app.presentation.flet.admin_viewmodels import (
    ADMIN_SECCIONES,
    ActividadAdminVM,
    AdminScreenVM,
    BackupItemVM,
    CatalogoItemVM,
    CompraLineaVM,
    DestructivaOpVM,
    DocumentoAdminVM,
    LoteAltaVM,
    PendingChangeVM,
    ProductoAdminVM,
    ProveedorAdminVM,
    RecetaAdminVM,
    ResponsableMermaVM,
    UsuarioAdminVM,
    assert_admin_sin_economia,
    assert_compra_linea_permite_precio_unitario,
    assert_lote_alta_permite_solo_precio_total,
)
from app.presentation.flet.mappers import (
    map_admin_operacion_feedback,
    map_error_recuperable,
)
from app.presentation.flet.viewmodels import FeedbackVM


def _backups_dir() -> Path:
    data_file = get_demo_file()
    try:
        base = data_file.parent
    except Exception:  # noqa: BLE001
        import tempfile

        base = Path(tempfile.gettempdir()) / "bm_backups"
    dest = base / "backups"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


class TerminalAdministracionPresenter:
    def __init__(self) -> None:
        self._feedback: FeedbackVM | None = None
        self._filtro = ""
        self._pending: PendingChangeVM | None = None
        self._mutando = False
        self._seccion = "inicio"
        self._lote_alta: LoteAltaVM | None = None
        self._inspeccion_backup = ""
        self._compra_lineas: list[CompraLineaVM] = []
        self._compra_proveedor_id = ""
        self._compra_referencia = ""
        self._compra_documento_id = ""
        assert_admin_sin_economia(
            ResponsableMermaVM,
            PendingChangeVM,
            ProductoAdminVM,
            RecetaAdminVM,
            UsuarioAdminVM,
            ProveedorAdminVM,
            BackupItemVM,
            CatalogoItemVM,
            ActividadAdminVM,
            DestructivaOpVM,
            DocumentoAdminVM,
            AdminScreenVM,
        )
        assert_lote_alta_permite_solo_precio_total()
        assert_compra_linea_permite_precio_unitario()

    # ── Auth ──────────────────────────────────────────────────────────────

    def login(self, login: str, password: str) -> AdminScreenVM:
        session, fb = session_bridge.login_administracion(login, password)
        self._feedback = fb
        self._pending = None
        self._seccion = "inicio"
        if session.authenticated and fb is None:
            self._feedback = FeedbackVM(ok=True, mensaje="Sesión administrativa iniciada.")
        return self.screen()

    def logout(self) -> AdminScreenVM:
        session_bridge.logout_terminal()
        self._feedback = FeedbackVM(ok=True, mensaje="Sesión cerrada.")
        self._pending = None
        self._mutando = False
        self._seccion = "inicio"
        self._lote_alta = None
        self._inspeccion_backup = ""
        self._compra_lineas = []
        self._compra_proveedor_id = ""
        self._compra_referencia = ""
        self._compra_documento_id = ""
        return self.screen()

    def set_seccion(self, seccion: str) -> AdminScreenVM:
        if seccion in ADMIN_SECCIONES:
            self._seccion = seccion
        return self.screen()

    def set_filtro(self, texto: str) -> AdminScreenVM:
        self._filtro = (texto or "").strip()
        return self.screen()

    # ── Responsables (piloto existente) ───────────────────────────────────

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
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la desactivación.")
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
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la reactivación.")
        return self.screen()

    # ── Productos ─────────────────────────────────────────────────────────

    def crear_producto(
        self,
        nombre: str,
        unidad: str,
        stock_minimo: float | None,
        codigo: str,
        tipo_articulo: str,
        *,
        es_bebida: bool = False,
        servicios_disponibles: list[str] | None = None,
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = stock_service.crear_producto(
                nombre,
                unidad,
                stock_minimo,
                codigo=codigo,
                tipo_articulo=tipo_articulo,
                es_bebida=es_bebida,
                servicios_disponibles=servicios_disponibles,
            )
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
            if r.ok:
                self._seccion = "productos"
        finally:
            self._mutando = False
        return self.screen()

    def proponer_desactivar_producto(self, producto_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        prod = next(
            (p for p in get_container().app_data_store.get().productos if p.id == producto_id),
            None,
        )
        if not prod:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Producto no encontrado."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="desactivar_producto",
            resumen=(
                f"Desactivar producto «{prod.nombre}». "
                "No aparecerá en compras ni recetas nuevas."
            ),
            producto_id=producto_id,
            nombre=prod.nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la desactivación del producto.")
        return self.screen()

    def proponer_reactivar_producto(self, producto_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        prod = next(
            (p for p in get_container().app_data_store.get().productos if p.id == producto_id),
            None,
        )
        if not prod:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Producto no encontrado."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="reactivar_producto",
            resumen=f"Reactivar producto «{prod.nombre}».",
            producto_id=producto_id,
            nombre=prod.nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la reactivación del producto.")
        return self.screen()

    # ── Recetas ───────────────────────────────────────────────────────────

    def crear_receta(
        self,
        nombre: str,
        ingredientes: list[tuple[str, float]],
        categoria: str,
        porciones_estandar: float | None,
        *,
        servicios_disponibles: list[str] | None = None,
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        ings: list[IngredienteReceta] = []
        for pid, cant in ingredientes:
            pid_n = (pid or "").strip()
            if not pid_n or cant <= 0:
                continue
            ings.append(IngredienteReceta(pid_n, float(cant)))
        if not ings:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Indique al menos un ingrediente válido."
            )
            return self.screen()
        self._mutando = True
        try:
            r = receta_service.crear_receta(
                nombre,
                ings,
                categoria,
                servicios_disponibles=servicios_disponibles,
                porciones_estandar=porciones_estandar,
            )
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
            if r.ok:
                self._seccion = "recetas"
        finally:
            self._mutando = False
        return self.screen()

    def proponer_desactivar_receta(self, receta_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        rec = receta_service.obtener_receta(receta_id)
        if not rec:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Receta no encontrada."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="desactivar_receta",
            resumen=f"Desactivar receta «{rec.nombre}». No aparecerá en registros nuevos.",
            receta_id=receta_id,
            nombre=rec.nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la desactivación de la receta.")
        return self.screen()

    def proponer_reactivar_receta(self, receta_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        rec = receta_service.obtener_receta(receta_id)
        if not rec:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Receta no encontrada."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="reactivar_receta",
            resumen=f"Reactivar receta «{rec.nombre}».",
            receta_id=receta_id,
            nombre=rec.nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la reactivación de la receta.")
        return self.screen()

    # ── Usuarios ──────────────────────────────────────────────────────────

    def crear_usuario(
        self,
        nombre: str,
        rol: str,
        *,
        login: str = "",
        password: str = "",
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if not session_tiene_permiso(Permiso.GESTIONAR_USUARIOS):
            self._feedback = map_error_recuperable(
                "Sin permiso para gestionar usuarios.", codigo="DENEGADO"
            )
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = settings_service.crear_usuario(
                nombre, rol, login=login, password=password
            )
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
            if r.ok:
                self._seccion = "usuarios"
        finally:
            self._mutando = False
        return self.screen()

    def editar_usuario(self, usuario_id: str, nuevo_nombre: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = settings_service.editar_usuario(usuario_id, nuevo_nombre)
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    def cambiar_rol_usuario(self, usuario_id: str, nuevo_rol: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = settings_service.cambiar_rol_usuario(usuario_id, nuevo_rol)
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    def proponer_desactivar_usuario(self, usuario_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        user = next(
            (u for u in get_container().app_data_store.get().usuarios if u.id == usuario_id),
            None,
        )
        if not user:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Usuario no encontrado."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="desactivar_usuario",
            resumen=f"Desactivar usuario «{user.nombre}» ({user.login}).",
            usuario_id=usuario_id,
            nombre=user.nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la desactivación del usuario.")
        return self.screen()

    def proponer_reactivar_usuario(self, usuario_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        user = next(
            (u for u in get_container().app_data_store.get().usuarios if u.id == usuario_id),
            None,
        )
        if not user:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Usuario no encontrado."
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="reactivar_usuario",
            resumen=f"Reactivar usuario «{user.nombre}» ({user.login}).",
            usuario_id=usuario_id,
            nombre=user.nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la reactivación del usuario.")
        return self.screen()

    def restablecer_password(self, usuario_id: str, nueva_password: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = settings_service.restablecer_password(usuario_id, nueva_password)
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    # ── Inventario inicial ────────────────────────────────────────────────

    # ── Proveedores ───────────────────────────────────────────────────────

    def crear_proveedor(
        self,
        nombre_fiscal: str,
        codigo: str,
        *,
        nombre_comercial: str = "",
        nif_cif: str = "",
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = proveedor_service.crear_proveedor(
                nombre_fiscal,
                codigo=codigo,
                nombre_comercial=nombre_comercial or None,
                nif_cif=nif_cif or None,
            )
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
            if r.ok:
                self._seccion = "proveedores"
        finally:
            self._mutando = False
        return self.screen()

    def editar_proveedor(
        self,
        proveedor_id: str,
        *,
        nombre_fiscal: str | None = None,
        codigo: str | None = None,
        nombre_comercial: str | None = None,
        nif_cif: str | None = None,
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = proveedor_service.editar_proveedor(
                proveedor_id,
                nombre_fiscal=nombre_fiscal,
                codigo=codigo,
                nombre_comercial=nombre_comercial,
                nif_cif=nif_cif,
            )
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    def proponer_desactivar_proveedor(self, proveedor_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        actual = next(
            (p for p in proveedor_service.listar_proveedores() if p.id == proveedor_id),
            None,
        )
        if not actual:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Proveedor no encontrado."
            )
            return self.screen()
        nombre = actual.nombre_comercial or actual.nombre_fiscal
        self._pending = PendingChangeVM(
            kind="desactivar_proveedor",
            resumen=f"Desactivar proveedor «{nombre}». No estará disponible en compras nuevas.",
            proveedor_id=proveedor_id,
            nombre=nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la desactivación del proveedor.")
        return self.screen()

    def proponer_reactivar_proveedor(self, proveedor_id: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        actual = next(
            (p for p in proveedor_service.listar_proveedores() if p.id == proveedor_id),
            None,
        )
        if not actual:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Proveedor no encontrado."
            )
            return self.screen()
        nombre = actual.nombre_comercial or actual.nombre_fiscal
        self._pending = PendingChangeVM(
            kind="reactivar_proveedor",
            resumen=f"Reactivar proveedor «{nombre}».",
            proveedor_id=proveedor_id,
            nombre=nombre,
        )
        self._feedback = FeedbackVM(ok=True, mensaje="Confirme la reactivación del proveedor.")
        return self.screen()

    # ── Compras (borrador → confirmar) ────────────────────────────────────

    def set_compra_cabecera(
        self, proveedor_id: str, referencia: str = ""
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        self._compra_proveedor_id = (proveedor_id or "").strip()
        self._compra_referencia = (referencia or "").strip()
        return self.screen()

    def añadir_linea_compra(
        self,
        producto_id: str,
        cantidad: float,
        precio_unitario: float,
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        pid = (producto_id or "").strip()
        if not pid:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Seleccione un producto."
            )
            return self.screen()
        if cantidad <= 0 or precio_unitario < 0:
            self._feedback = map_admin_operacion_feedback(
                ok=False,
                mensaje_backend="Cantidad debe ser > 0 y precio unitario ≥ 0.",
            )
            return self.screen()
        data = get_container().app_data_store.get()
        prod = next((p for p in data.productos if p.id == pid), None)
        if prod is None:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Producto no encontrado."
            )
            return self.screen()
        self._compra_lineas.append(
            CompraLineaVM(
                producto_id=pid,
                nombre=prod.nombre,
                cantidad=float(cantidad),
                precio_unitario=float(precio_unitario),
            )
        )
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Línea «{prod.nombre}» añadida al borrador."
        )
        self._seccion = "compras"
        return self.screen()

    def quitar_linea_compra(self, index: int) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if index < 0 or index >= len(self._compra_lineas):
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Índice de línea inválido."
            )
            return self.screen()
        quitada = self._compra_lineas.pop(index)
        self._feedback = FeedbackVM(
            ok=True, mensaje=f"Línea «{quitada.nombre}» eliminada."
        )
        return self.screen()

    def limpiar_borrador_compra(self) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        self._compra_lineas = []
        self._compra_proveedor_id = ""
        self._compra_referencia = ""
        self._compra_documento_id = ""
        self._feedback = FeedbackVM(ok=True, mensaje="Borrador de compra limpiado.")
        return self.screen()

    def guardar_borrador_compra(self) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        if not self._compra_proveedor_id:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Seleccione un proveedor."
            )
            return self.screen()
        if not self._compra_lineas:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend="Añada al menos una línea de compra."
            )
            return self.screen()
        self._mutando = True
        try:
            r = self._persistir_borrador_compra()
            if r.ok and r.documento is not None:
                self._compra_documento_id = r.documento.id
                reload_from_disk()
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
            self._seccion = "compras"
        finally:
            self._mutando = False
        return self.screen()

    def confirmar_compra_borrador(self) -> AdminScreenVM:
        """Guarda borrador si hace falta y confirma (crea lotes/movimientos)."""
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        if not session_tiene_permiso(Permiso.ACCEDER_COMPRAS_DOCUMENTOS):
            self._feedback = map_error_recuperable(
                "Sin permiso de compras/documentos.", codigo="DENEGADO"
            )
            return self.screen()
        self._mutando = True
        try:
            if not self._compra_documento_id:
                if not self._compra_proveedor_id or not self._compra_lineas:
                    self._feedback = map_admin_operacion_feedback(
                        ok=False,
                        mensaje_backend="Indique proveedor y al menos una línea.",
                    )
                    return self.screen()
                r = self._persistir_borrador_compra()
                if not r.ok or r.documento is None:
                    self._feedback = map_admin_operacion_feedback(
                        ok=False, mensaje_backend=r.mensaje
                    )
                    return self.screen()
                self._compra_documento_id = r.documento.id
                reload_from_disk()

            path = get_demo_file()
            data = reload_from_disk()
            doc = next(
                (d for d in (data.documentos or []) if d.id == self._compra_documento_id),
                None,
            )
            if doc is None:
                self._feedback = map_admin_operacion_feedback(
                    ok=False, mensaje_backend="Borrador no encontrado tras guardar."
                )
                return self.screen()
            h = compra_registro_service.construir_hash_documento(doc)
            token = str(uuid.uuid4())
            res = compra_registro_service.confirmar_compra(
                doc.id,
                confirmacion_id=token,
                contenido_hash=h,
                json_path=path,
            )
            if res.ok:
                reload_from_disk()
                self._compra_lineas = []
                self._compra_documento_id = ""
                self._compra_referencia = ""
                msg = res.mensaje or "Compra confirmada."
                if res.codigo == compra_registro_service.CONFIRMACION_IDEMPOTENTE:
                    msg = f"{msg} (idempotente)"
                self._feedback = FeedbackVM(ok=True, mensaje=msg)
            else:
                self._feedback = map_admin_operacion_feedback(
                    ok=False, mensaje_backend=res.mensaje
                )
            self._seccion = "compras"
        finally:
            self._mutando = False
        return self.screen()

    def _persistir_borrador_compra(self):
        data = get_container().app_data_store.get()
        lineas_payload: list[dict] = []
        for ln in self._compra_lineas:
            prod = next((p for p in data.productos if p.id == ln.producto_id), None)
            unidad = "Ud"
            if prod is not None:
                unidad = (
                    prod.unidad.value
                    if hasattr(prod.unidad, "value")
                    else str(prod.unidad)
                )
            lineas_payload.append(
                {
                    "producto_id": ln.producto_id,
                    "client_line_key": str(uuid.uuid4()),
                    "cantidad_compra": str(ln.cantidad),
                    "unidad_compra": unidad,
                    "unidad_inventario": unidad,
                    "precio_unitario_compra": str(ln.precio_unitario),
                    "impuesto_porcentaje": "0",
                }
            )
        return compra_registro_service.guardar_borrador_persistente(
            json_path=get_demo_file(),
            tipo=TipoDocumento.ALBARAN.value,
            proveedor_id=self._compra_proveedor_id,
            referencia_externa=self._compra_referencia or None,
            lineas=lineas_payload,
            documento_id=self._compra_documento_id or None,
        )

    # ── Inventario inicial ────────────────────────────────────────────────

    def registrar_lote_inicial(
        self,
        producto_id: str,
        cantidad: float,
        precio_total: float,
        *,
        marca_proveedor: str = "",
        ubicacion_destino_id: str = "",
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        data = get_container().app_data_store.get()
        prod = next((p for p in data.productos if p.id == producto_id), None)
        nombre = prod.nombre if prod else producto_id
        self._lote_alta = LoteAltaVM(
            producto_id=producto_id,
            producto_nombre=nombre,
            cantidad=cantidad,
            precio_total=precio_total,
            marca_proveedor=marca_proveedor or "",
            ubicacion_destino_id=ubicacion_destino_id or "",
        )
        self._mutando = True
        try:
            r = stock_service.registrar_lote(
                producto_id,
                precio_total,
                cantidad,
                marca_proveedor=marca_proveedor or None,
                ubicacion_destino_id=ubicacion_destino_id or None,
            )
            # Feedback operativo: evitar fuga de «precio» vía sanitize genérico.
            if r.ok:
                self._feedback = FeedbackVM(
                    ok=True, mensaje=f"Lote inicial de «{nombre}» registrado."
                )
                self._lote_alta = None
            else:
                msg = r.mensaje or "No se pudo registrar el lote."
                low = msg.lower()
                if "precio" in low or "importe" in low:
                    msg = "Indique cantidad e importe de lote válidos (> 0)."
                self._feedback = FeedbackVM(ok=False, mensaje=msg, codigo="VALIDACION")
        finally:
            self._mutando = False
        return self.screen()

    # ── Backup ────────────────────────────────────────────────────────────

    def generar_backup(self) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if not session_tiene_permiso(Permiso.EXPORTAR_BACKUP):
            self._feedback = map_error_recuperable(
                "Sin permiso para exportar backup.", codigo="DENEGADO"
            )
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            data = get_container().app_data_store.get()
            resultado = generar_backup_zip(data)
            dest = _backups_dir() / resultado.nombre_archivo
            dest.write_bytes(resultado.contenido)
            self._feedback = FeedbackVM(
                ok=True,
                mensaje=f"Backup generado: {resultado.nombre_archivo}",
            )
            self._seccion = "backup"
        except Exception as exc:  # noqa: BLE001
            msg = getattr(exc, "mensaje", None) or str(exc) or "Error al generar backup."
            self._feedback = map_error_recuperable(msg, codigo="BACKUP")
        finally:
            self._mutando = False
        return self.screen()

    def inspeccionar_backup_archivo(self, ruta: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if not session_tiene_permiso(Permiso.RESTAURAR_BACKUP):
            self._feedback = map_error_recuperable(
                "Solo Dirección puede inspeccionar/restaurar backups.",
                codigo="DENEGADO",
            )
            return self.screen()
        path = Path(ruta)
        if not path.is_file():
            self._feedback = map_error_recuperable("Archivo de backup no encontrado.")
            return self.screen()
        try:
            insp = inspeccionar_backup(path.read_bytes(), nombre=path.name)
            if insp.ok:
                self._inspeccion_backup = (
                    f"OK · {path.name} · schema {getattr(insp, 'schema_version', '?')} · "
                    f"{insp.mensaje or 'válido'}"
                )
                self._feedback = FeedbackVM(ok=True, mensaje="Backup válido.")
            else:
                self._inspeccion_backup = f"Rechazado · {path.name}: {insp.mensaje}"
                self._feedback = FeedbackVM(
                    ok=False, mensaje=insp.mensaje or "Backup no válido.", codigo="BACKUP"
                )
        except Exception as exc:  # noqa: BLE001
            self._inspeccion_backup = ""
            self._feedback = map_error_recuperable(str(exc), codigo="BACKUP")
        return self.screen()

    def proponer_restaurar_backup(self, ruta: str, confirmacion: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if not session_tiene_permiso(Permiso.RESTAURAR_BACKUP):
            self._feedback = map_error_recuperable(
                "Solo Dirección puede restaurar backups.", codigo="DENEGADO"
            )
            return self.screen()
        path = Path(ruta)
        if not path.is_file():
            self._feedback = map_error_recuperable("Archivo de backup no encontrado.")
            return self.screen()
        token = (confirmacion or "").strip().upper()
        if token != "RESTAURAR":
            self._feedback = map_admin_operacion_feedback(
                ok=False,
                mensaje_backend="Indique la confirmación RESTAURAR para continuar.",
            )
            return self.screen()
        self._pending = PendingChangeVM(
            kind="restaurar_backup",
            resumen=(
                f"RESTAURAR desde «{path.name}». "
                "Sustituye los datos operativos actuales. Esta acción es irreversible "
                "sin un backup previo."
            ),
            backup_nombre=path.name,
            backup_ruta=str(path),
            confirmacion="RESTAURAR",
        )
        self._feedback = FeedbackVM(
            ok=True, mensaje="Confirme la restauración del backup."
        )
        return self.screen()

    # ── Configuración ─────────────────────────────────────────────────────

    def guardar_hotel(self, nombre: str, moneda_key: str = "EUR") -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = settings_service.guardar_configuracion(nombre, moneda_key or "EUR")
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    # ── Dashboard / datos compartidos ─────────────────────────────────────

    def refresh_datos(self) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        try:
            get_container().app_data_store.refresh_if_stale()
            self._feedback = FeedbackVM(ok=True, mensaje="Datos actualizados desde disco.")
        except SharedPathUnavailable as exc:
            self._feedback = map_error_recuperable(
                f"Ruta compartida no disponible: {exc}",
                codigo="SHARED_PATH",
            )
        except Exception as exc:  # noqa: BLE001
            self._feedback = map_error_recuperable(
                f"No se pudo refrescar: {exc}",
                codigo="REFRESH",
            )
        return self.screen()

    def guardar_shared_root(self, path: str) -> AdminScreenVM:
        """Valida y guarda solo config de cliente (nunca copia datos)."""
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        texto = (path or "").strip()
        if not texto:
            self._feedback = map_admin_operacion_feedback(
                ok=False,
                mensaje_backend="Indique una ruta compartida (UNC o local).",
            )
            return self.screen()
        self._mutando = True
        try:
            root = validate_shared_root(texto)
            data_file = resolve_data_file_from_shared_root(root)
            assert_data_path_usable(data_file)
            save_client_config(shared_root=root)
            apply_shared_root(root)
            get_container().app_data_store.reload_from_disk()
            self._feedback = FeedbackVM(
                ok=True,
                mensaje=(
                    f"Raíz compartida guardada (solo config de cliente): {root}. "
                    "No se copiaron datos."
                ),
            )
        except InstanceConfigError as exc:
            self._feedback = map_admin_operacion_feedback(
                ok=False, mensaje_backend=str(exc)
            )
        except SharedPathUnavailable as exc:
            self._feedback = map_error_recuperable(
                f"Ruta compartida no disponible (sin fallback local): {exc}",
                codigo="SHARED_PATH",
            )
        except Exception as exc:  # noqa: BLE001
            self._feedback = map_error_recuperable(
                f"No se pudo guardar la raíz compartida: {exc}",
                codigo="SHARED_ROOT",
            )
        finally:
            self._mutando = False
        return self.screen()

    # ── Catálogos ─────────────────────────────────────────────────────────

    def crear_departamento_catalogo(self, nombre: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = catalogo_service.crear_departamento(nombre)
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    def crear_categoria_catalogo(self, nombre: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = catalogo_service.crear_categoria(nombre)
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    def crear_ubicacion_catalogo(self, nombre: str, codigo: str) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = catalogo_service.crear_ubicacion(nombre, codigo=codigo)
            self._feedback = map_admin_operacion_feedback(ok=r.ok, mensaje_backend=r.mensaje)
        finally:
            self._mutando = False
        return self.screen()

    # ── Zona de peligro ───────────────────────────────────────────────────

    def ejecutar_op_destructiva(
        self,
        op_id: str,
        frase: str,
        checkbox_aceptado: bool,
    ) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if not (
            session_tiene_permiso(Permiso.EJECUTAR_OPERACION_DESTRUCTIVA)
            or session_tiene_permiso(Permiso.VER_ZONA_PELIGRO)
        ):
            self._feedback = map_error_recuperable(
                "Solo Dirección puede ejecutar operaciones destructivas.",
                codigo="DENEGADO",
            )
            return self.screen()
        if self._mutando:
            return self._busy()
        if op_id != "restablecer_mock":
            self._feedback = map_admin_operacion_feedback(
                ok=False,
                mensaje_backend="Operación no expuesta en Zona de peligro.",
            )
            return self.screen()
        self._mutando = True
        try:
            res = destructive_ops_service.restablecer_a_datos_mock(
                confirmacion_escrita=frase,
                checkbox_aceptado=bool(checkbox_aceptado),
                operation_token=str(uuid.uuid4()),
                recargar_sesion=True,
            )
            msg = res.mensaje
            if res.backup_preventivo:
                msg = f"{msg} Preventivo: {res.backup_preventivo}."
            self._feedback = map_admin_operacion_feedback(ok=res.ok, mensaje_backend=msg)
            if res.ok:
                get_container().app_data_store.reload_from_disk()
        finally:
            self._mutando = False
        return self.screen()

    # ── Documentos export ─────────────────────────────────────────────────

    def exportar_documentos_csv(self) -> AdminScreenVM:
        if not self._gate_admin():
            return self.screen()
        if self._mutando:
            return self._busy()
        self._mutando = True
        try:
            r = documento_consulta_service.exportar_documentos_csv(guardar=True)
            if r.ok and r.ruta:
                self._feedback = FeedbackVM(
                    ok=True,
                    mensaje=f"{r.mensaje} Guardado en: {r.ruta}",
                )
            else:
                self._feedback = map_admin_operacion_feedback(
                    ok=r.ok, mensaje_backend=r.mensaje
                )
        finally:
            self._mutando = False
        return self.screen()

    # ── Confirmación pendiente ────────────────────────────────────────────

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
            r = self._ejecutar_pendiente(pending)
            if r is None:
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

    def _ejecutar_pendiente(self, pending: PendingChangeVM):
        if pending.kind == "crear":
            return merma_service.crear_responsable_merma(pending.nombre)
        if pending.kind == "renombrar":
            return merma_service.renombrar_responsable_merma(
                pending.responsable_id, pending.nombre
            )
        if pending.kind == "desactivar":
            return merma_service.desactivar_responsable_merma(pending.responsable_id)
        if pending.kind == "reactivar":
            return merma_service.reactivar_responsable_merma(pending.responsable_id)
        if pending.kind == "desactivar_producto":
            return stock_service.desactivar_producto(pending.producto_id)
        if pending.kind == "reactivar_producto":
            return stock_service.reactivar_producto(pending.producto_id)
        if pending.kind == "desactivar_receta":
            return receta_service.desactivar_receta(pending.receta_id)
        if pending.kind == "reactivar_receta":
            return receta_service.reactivar_receta(pending.receta_id)
        if pending.kind == "desactivar_usuario":
            return settings_service.set_usuario_activo(pending.usuario_id, False)
        if pending.kind == "reactivar_usuario":
            return settings_service.set_usuario_activo(pending.usuario_id, True)
        if pending.kind == "desactivar_proveedor":
            return proveedor_service.desactivar_proveedor(pending.proveedor_id)
        if pending.kind == "reactivar_proveedor":
            return proveedor_service.reactivar_proveedor(pending.proveedor_id)
        if pending.kind == "restaurar_backup":
            if not session_tiene_permiso(Permiso.RESTAURAR_BACKUP):
                return settings_service.ResultadoOperacion(
                    False, "Solo Dirección puede restaurar backups."
                )
            path = Path(pending.backup_ruta)
            if not path.is_file():
                return settings_service.ResultadoOperacion(
                    False, "Archivo de backup no encontrado."
                )
            resultado = restaurar_desde_bytes(
                path.read_bytes(),
                nombre_backup=pending.backup_nombre or path.name,
                recargar_sesion=True,
            )
            return settings_service.ResultadoOperacion(
                resultado.ok, resultado.mensaje or ("Restaurado." if resultado.ok else "Falló.")
            )
        return None

    # ── Screen ────────────────────────────────────────────────────────────

    def screen(self) -> AdminScreenVM:
        sess = session_bridge.current_session_vm()
        auth = sess.authenticated and session_bridge.puede_usar_administracion()
        q = self._filtro.lower()

        responsables: tuple[ResponsableMermaVM, ...] = ()
        productos: tuple[ProductoAdminVM, ...] = ()
        recetas: tuple[RecetaAdminVM, ...] = ()
        usuarios: tuple[UsuarioAdminVM, ...] = ()
        proveedores: tuple[ProveedorAdminVM, ...] = ()
        documentos: tuple[DocumentoAdminVM, ...] = ()
        backups: tuple[BackupItemVM, ...] = ()
        departamentos: tuple[CatalogoItemVM, ...] = ()
        categorias: tuple[CatalogoItemVM, ...] = ()
        ubicaciones: tuple[CatalogoItemVM, ...] = ()
        actividades: tuple[ActividadAdminVM, ...] = ()
        ops_destructivas: tuple[DestructivaOpVM, ...] = ()
        hotel_nombre = ""
        hotel_moneda = "EUR"
        periodo = ""
        consumo_count = 0
        merma_count = 0
        stock_bajo = 0
        caducidades = 0
        alerta_registro = ""
        revision = 0
        data_path_label = ""
        shared_root_label = ""
        puede_zona = False

        if auth:
            data = get_container().app_data_store.get()
            if data.configuracion:
                hotel_nombre = data.configuracion.nombre_establecimiento or ""
                hotel_moneda = data.configuracion.moneda or "EUR"

            revision = int(getattr(data, "revision", 0) or 0)
            try:
                data_path_label = str(get_demo_file())
            except Exception:  # noqa: BLE001
                data_path_label = ""
            shared = resolve_shared_root()
            if shared is not None:
                shared_root_label = str(shared)
            else:
                cfg = load_client_config()
                shared_root_label = str(cfg.get("shared_root") or data_path_label or "—")

            # Dashboard operativo (conteos; sin €)
            try:
                periodo_obj = dashboard_service.resolver_periodo("Este mes")
                periodo = periodo_obj.etiqueta
                consumo_count = dashboard_service.total_registros(
                    periodo_obj.desde, periodo_obj.hasta, data=data
                )
                merma_count = sum(
                    1
                    for m in data.mermas
                    if periodo_obj.desde <= m.fecha <= periodo_obj.hasta
                    and not getattr(m, "anulado", False)
                )
                repo = DataRepository(data)
                stock_bajo = len(repo.productos_stock_bajo())
                caducidades = len(caducidad_service.listar_lotes_caducidad())
                alerta_registro = (
                    "Desayuno de hoy registrado"
                    if repo.desayuno_registrado_hoy()
                    else "Falta registro de desayuno hoy"
                )
            except Exception:  # noqa: BLE001
                periodo = periodo or "Este mes"
                alerta_registro = alerta_registro or "—"

            lista_r = []
            for r in merma_service.listar_responsables_merma(solo_activos=False):
                if q and q not in r.nombre.lower() and q not in r.id.lower():
                    continue
                lista_r.append(
                    ResponsableMermaVM(id=r.id, nombre=r.nombre, activo=r.activo)
                )
            responsables = tuple(lista_r)

            lista_p = []
            for p in data.productos:
                codigo = getattr(p, "codigo", None) or ""
                if self._seccion == "productos" and q:
                    if q not in p.nombre.lower() and q not in codigo.lower() and q not in p.id.lower():
                        continue
                tipo = getattr(p, "tipo_articulo", None)
                tipo_s = getattr(tipo, "value", None) or (str(tipo) if tipo else "")
                lista_p.append(
                    ProductoAdminVM(
                        id=p.id,
                        nombre=p.nombre,
                        codigo=codigo,
                        unidad=p.unidad.value if hasattr(p.unidad, "value") else str(p.unidad),
                        stock_minimo=float(p.stock_minimo or 0),
                        tipo_articulo=tipo_s,
                        es_bebida=bool(getattr(p, "es_bebida", False)),
                        activo=bool(getattr(p, "activo", True)),
                        servicios=tuple(getattr(p, "servicios_disponibles", None) or ()),
                    )
                )
            productos = tuple(lista_p)

            lista_rec = []
            for r in receta_service.listar_recetas(solo_activas=False):
                if self._seccion == "recetas" and q:
                    if q not in r.nombre.lower() and q not in r.id.lower():
                        continue
                cat = r.categoria.value if hasattr(r.categoria, "value") else str(r.categoria)
                lista_rec.append(
                    RecetaAdminVM(
                        id=r.id,
                        nombre=r.nombre,
                        categoria=cat,
                        porciones_estandar=getattr(r, "porciones_estandar", None),
                        n_ingredientes=len(r.ingredientes or []),
                        activo=bool(getattr(r, "activo", True)),
                        servicios=tuple(getattr(r, "servicios_disponibles", None) or ()),
                    )
                )
            recetas = tuple(lista_rec)

            lista_u = []
            for u in data.usuarios:
                if self._seccion == "usuarios" and q:
                    blob = f"{u.nombre} {u.login} {u.rol}".lower()
                    if q not in blob:
                        continue
                rol = u.rol.value if hasattr(u.rol, "value") else str(u.rol)
                lista_u.append(
                    UsuarioAdminVM(
                        id=u.id,
                        nombre=u.nombre,
                        login=getattr(u, "login", "") or "",
                        rol=rol,
                        activo=bool(u.activo),
                    )
                )
            usuarios = tuple(lista_u)

            lista_prov = []
            for prv in proveedor_service.listar_proveedores(solo_activos=False):
                if self._seccion == "proveedores" and q:
                    blob = (
                        f"{prv.nombre_fiscal} {prv.nombre_comercial or ''} "
                        f"{prv.codigo or ''} {prv.nif_cif or ''}"
                    ).lower()
                    if q not in blob and q not in prv.id.lower():
                        continue
                lista_prov.append(
                    ProveedorAdminVM(
                        id=prv.id,
                        nombre_fiscal=prv.nombre_fiscal,
                        nombre_comercial=prv.nombre_comercial or "",
                        codigo=getattr(prv, "codigo", None) or "",
                        nif_cif=prv.nif_cif or "",
                        activo=bool(prv.activo),
                    )
                )
            proveedores = tuple(lista_prov)

            lista_docs: list[DocumentoAdminVM] = []
            try:
                docs = documento_consulta_service.buscar_documentos()
            except Exception:  # noqa: BLE001 — sin permiso / vacío
                docs = []
            for d in docs[:100]:
                tipo = getattr(d.tipo, "value", None) or str(d.tipo or "")
                estado = getattr(d.estado, "value", None) or str(d.estado or "")
                fecha = (
                    d.fecha_documento.isoformat()
                    if getattr(d, "fecha_documento", None)
                    else ""
                )
                prov = getattr(d, "proveedor_nombre_snapshot", None) or d.proveedor_id or ""
                ref = getattr(d, "referencia", None) or getattr(d, "numero", None) or ""
                n_lineas = len(getattr(d, "lineas", None) or [])
                if self._seccion == "documentos" and q:
                    blob = f"{d.id} {tipo} {estado} {prov} {ref}".lower()
                    if q not in blob:
                        continue
                lista_docs.append(
                    DocumentoAdminVM(
                        id=d.id,
                        tipo=tipo,
                        estado=estado,
                        fecha=fecha,
                        proveedor=str(prov),
                        referencia=str(ref),
                        n_lineas=n_lineas,
                    )
                )
            documentos = tuple(lista_docs)

            departamentos = tuple(
                CatalogoItemVM(id=d.id, nombre=d.nombre, activo=bool(d.activo))
                for d in catalogo_service.listar_departamentos(solo_activos=False)
            )
            categorias = tuple(
                CatalogoItemVM(id=c.id, nombre=c.nombre, activo=bool(c.activo))
                for c in catalogo_service.listar_categorias(solo_activos=False)
            )
            ubicaciones = tuple(
                CatalogoItemVM(
                    id=u.id,
                    nombre=u.nombre,
                    activo=bool(u.activo),
                    codigo=getattr(u, "codigo", None) or "",
                )
                for u in catalogo_service.listar_ubicaciones(solo_activos=False)
            )

            acts: list[ActividadAdminVM] = []
            for a in list(data.actividades or [])[:50]:
                fh = getattr(a, "fecha_hora", None)
                fecha_s = fh.isoformat(timespec="seconds") if fh is not None else ""
                acts.append(
                    ActividadAdminVM(
                        fecha=fecha_s,
                        usuario=getattr(a, "usuario", "") or "",
                        accion=getattr(a, "accion", "") or "",
                        detalle=getattr(a, "detalle", "") or "",
                    )
                )
            actividades = tuple(acts)

            puede_zona = session_tiene_permiso(
                Permiso.EJECUTAR_OPERACION_DESTRUCTIVA
            ) or session_tiene_permiso(Permiso.VER_ZONA_PELIGRO)
            if puede_zona:
                ops: list[DestructivaOpVM] = []
                for item in destructive_ops_service.inventario_acciones_destructivas_visibles():
                    if item.get("expuesta_en") != "Zona de peligro":
                        continue
                    frase = item.get("frase") or ""
                    if not frase:
                        continue
                    ops.append(
                        DestructivaOpVM(
                            id=str(item.get("id") or ""),
                            etiqueta="Restablecer a datos mock",
                            frase=str(frase),
                            nota=str(item.get("nota") or ""),
                        )
                    )
                ops_destructivas = tuple(ops)

            backups = self._listar_backups()

        return AdminScreenVM(
            session=sess,
            responsables=responsables,
            seccion=self._seccion if auth else "inicio",
            productos=productos,
            recetas=recetas,
            usuarios=usuarios,
            proveedores=proveedores,
            compra_lineas=tuple(self._compra_lineas) if auth else (),
            compra_proveedor_id=self._compra_proveedor_id if auth else "",
            compra_referencia=self._compra_referencia if auth else "",
            compra_documento_id=self._compra_documento_id if auth else "",
            documentos=documentos,
            backups=backups,
            unidades=tuple(u.value for u in UnidadProducto),
            categorias_receta=tuple(c.value for c in CategoriaReceta),
            servicios_disponibles=tuple(sorted(SERVICIOS_DISPONIBLES_VALORES)),
            tipos_articulo=tuple(sorted(TIPO_ARTICULO_VALORES)),
            roles_asignables=tuple(roles_asignables(incluye_direccion=True)),
            hotel_nombre=hotel_nombre,
            hotel_moneda=hotel_moneda,
            lote_alta=self._lote_alta,
            filtro=self._filtro,
            feedback=self._feedback,
            pending=self._pending,
            mutando=self._mutando,
            motivos_fijos=tuple(m.value for m in MotivoMerma),
            puede_gestionar_usuarios=auth and session_tiene_permiso(Permiso.GESTIONAR_USUARIOS),
            puede_exportar_backup=auth and session_tiene_permiso(Permiso.EXPORTAR_BACKUP),
            puede_restaurar_backup=auth and session_tiene_permiso(Permiso.RESTAURAR_BACKUP),
            inspeccion_backup=self._inspeccion_backup if auth else "",
            periodo=periodo if auth else "",
            consumo_count=consumo_count if auth else 0,
            merma_count=merma_count if auth else 0,
            stock_bajo=stock_bajo if auth else 0,
            caducidades=caducidades if auth else 0,
            alerta_registro=alerta_registro if auth else "",
            revision=revision if auth else 0,
            data_path_label=data_path_label if auth else "",
            shared_root_label=shared_root_label if auth else "",
            departamentos=departamentos,
            categorias=categorias,
            ubicaciones=ubicaciones,
            actividades=actividades,
            puede_zona_peligro=auth and puede_zona,
            ops_destructivas=ops_destructivas if auth and puede_zona else (),
        )

    def _listar_backups(self) -> tuple[BackupItemVM, ...]:
        items: list[BackupItemVM] = []
        try:
            folder = _backups_dir()
            for path in sorted(folder.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
                st = path.stat()
                items.append(
                    BackupItemVM(
                        nombre=path.name,
                        ruta=str(path),
                        tamano_bytes=int(st.st_size),
                        modificado=datetime.fromtimestamp(st.st_mtime).isoformat(
                            timespec="seconds"
                        ),
                    )
                )
        except Exception:  # noqa: BLE001
            return ()
        return tuple(items)

    def _gate_admin(self) -> bool:
        if session_bridge.puede_usar_administracion():
            return True
        self._feedback = map_error_recuperable(
            "Sesión no autorizada.", codigo="DENEGADO"
        )
        return False

    def _busy(self) -> AdminScreenVM:
        self._feedback = map_error_recuperable(
            "Operación en curso.", codigo="CONFIRMANDO"
        )
        return self.screen()
