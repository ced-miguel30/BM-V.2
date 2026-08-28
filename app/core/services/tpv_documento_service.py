"""Importa registros de comida/bebidas desde documento TPV (PDF/imagen).

Flujo: OCR → parse líneas Dynamics → mismo mapeo/registro que el import manual.
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIX = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}


@dataclass
class ResultadoImportTpv:
    ok: bool
    mensaje: str
    lineas_detectadas: int = 0
    registros_ok: int = 0
    omitidos_idempotentes: int = 0
    errores: list[str] = field(default_factory=list)
    pendientes_coctel: list[dict] = field(default_factory=list)
    sin_mapear: list[str] = field(default_factory=list)
    fechas: list[str] = field(default_factory=list)
    registros_creados: list[dict] = field(default_factory=list)


def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def ocr_documento(ruta: str | Path) -> str:
    """Extrae texto OCR de PDF (páginas rasterizadas) o imagen."""
    path = Path(ruta)
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo: {path}")
    suf = path.suffix.lower()
    if suf not in _ALLOWED_SUFFIX:
        raise ValueError(
            f"Formato no soportado ({suf or 'sin extensión'}). "
            "Use PDF o imagen (png/jpg)."
        )

    engine = _ocr_engine()
    parts: list[str] = []

    if suf == ".pdf":
        import pymupdf

        doc = pymupdf.open(path)
        try:
            for i in range(doc.page_count):
                page = doc[i]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = Path(tmp.name)
                try:
                    pix.save(str(tmp_path))
                    result, _ = engine(str(tmp_path))
                finally:
                    tmp_path.unlink(missing_ok=True)
                parts.append(f"----- page_{i + 1:02d} -----")
                if result:
                    for item in result:
                        parts.append(item[1])
                parts.append("")
        finally:
            doc.close()
    else:
        result, _ = engine(str(path))
        parts.append(f"----- {path.name} -----")
        if result:
            for item in result:
                parts.append(item[1])

    return "\n".join(parts)


def parse_lineas_tpv(texto_ocr: str) -> list[dict]:
    from scripts.parse_tpv_ocr import parse_ocr

    return parse_ocr(texto_ocr)


def _file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:10]


def _resumen(report: dict, lineas: int, fechas: list[str]) -> ResultadoImportTpv:
    ok_list = report.get("ok") or []
    errors = [str(e) for e in (report.get("errors") or [])]
    skipped = report.get("skipped_idempotent") or []
    pending = report.get("tpv_pending_coctel_dia") or []
    unmapped = report.get("tpv_unmapped") or []
    names_um = sorted(
        {
            (u.get("nombre") if isinstance(u, dict) else str(u))
            for u in unmapped
            if u
        }
    )

    n_ok = len(ok_list)
    n_skip = len(skipped)
    parts = [
        f"Documento TPV: {lineas} líneas leídas",
        f"{n_ok} registro(s) confirmado(s)",
    ]
    if fechas:
        parts.append(f"fechas {', '.join(fechas[:8])}{'…' if len(fechas) > 8 else ''}")
    if n_skip:
        parts.append(f"{n_skip} ya existían (omitidos)")
    if pending:
        parts.append(f"{len(pending)} cóctel del día pendiente(s) de lista")
    if names_um:
        sample = ", ".join(names_um[:5])
        more = f" (+{len(names_um) - 5})" if len(names_um) > 5 else ""
        parts.append(f"sin mapear: {sample}{more}")
    if errors:
        parts.append(f"{len(errors)} error(es)")

    ok = n_ok > 0 and not errors
    if n_ok == 0 and n_skip > 0 and not errors:
        ok = True
        parts[1] = "sin cambios (ya importado)"
    elif n_ok == 0 and errors:
        ok = False
    elif n_ok == 0 and not pending and not names_um:
        ok = False
        parts.append("no se pudo registrar nada")

    return ResultadoImportTpv(
        ok=ok,
        mensaje=". ".join(parts) + ".",
        lineas_detectadas=lineas,
        registros_ok=n_ok,
        omitidos_idempotentes=n_skip,
        errores=errors[:20],
        pendientes_coctel=list(pending)[:50],
        sin_mapear=names_um[:30],
        fechas=fechas,
        registros_creados=[
            {
                "ref": item.get("ref"),
                "tipo": item.get("tipo"),
                "fecha": item.get("fecha"),
                "clave": item.get("clave"),
            }
            for item in ok_list
            if item.get("ref")
        ],
    )


@dataclass
class OcrParseTpvResult:
    """Resultado de OCR+parse (seguro en hilo de fondo, sin tocar AppData)."""

    ok: bool
    rows: list[dict] = field(default_factory=list)
    path: Path | None = None
    error: str = ""
    lineas_detectadas: int = 0


def ocr_documento_subprocess(ruta: str | Path) -> str:
    """OCR en subproceso: un crash nativo (onnx/cv2) no tumba Flet."""
    import json
    import subprocess
    import sys
    import tempfile

    path = Path(ruta)
    fd, out_name = tempfile.mkstemp(prefix="bm_tpv_ocr_", suffix=".json")
    os_close = __import__("os").close
    os_close(fd)
    out_path = Path(out_name)
    try:
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "--bm-tpv-ocr", str(path), str(out_path)]
        else:
            cmd = [
                sys.executable,
                "-m",
                "app.core.services.tpv_ocr_cli",
                str(path),
                str(out_path),
            ]
        flags = 0
        if sys.platform == "win32":
            flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=flags,
            cwd=str(Path(__file__).resolve().parents[2])
            if not getattr(sys, "frozen", False)
            else None,
        )
        payload: dict = {}
        if out_path.is_file():
            try:
                payload = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                payload = {}
        if proc.returncode != 0 and not payload.get("ok"):
            detail = (
                str(payload.get("error") or "").strip()
                or (proc.stderr or "").strip()
                or f"código {proc.returncode}"
            )
            if proc.returncode < 0 or proc.returncode in (139, 3221225477, 3221226505):
                detail = (
                    f"El motor OCR se cerró de forma inesperada ({detail}). "
                    "Pruebe de nuevo o use una imagen/PDF más ligero."
                )
            raise RuntimeError(detail)
        if not payload.get("ok"):
            raise RuntimeError(str(payload.get("error") or "OCR falló sin detalle"))
        return str(payload.get("text") or "")
    finally:
        out_path.unlink(missing_ok=True)


def procesar_documento_tpv_ocr(ruta: str | Path) -> OcrParseTpvResult:
    """Solo OCR + parse. No usar get_container ni persist_data aquí."""
    path = Path(ruta)
    # En worker ya estamos aislados: OCR inline (evita subproceso anidado).
    use_subprocess = (os.environ.get("BM_TPV_WORKER") or "").strip() != "1"
    try:
        texto = (
            ocr_documento_subprocess(path) if use_subprocess else ocr_documento(path)
        )
    except Exception as ocr_exc:  # noqa: BLE001
        ocr_msg = str(ocr_exc) or type(ocr_exc).__name__
        logger.exception("OCR TPV falló: %s", path)
        return OcrParseTpvResult(
            ok=False, path=path, error=f"No se pudo leer el documento: {ocr_msg}"
        )

    try:
        rows = parse_lineas_tpv(texto)
    except Exception as parse_exc:  # noqa: BLE001
        parse_msg = str(parse_exc) or type(parse_exc).__name__
        logger.exception("Parse TPV falló")
        return OcrParseTpvResult(
            ok=False, path=path, error=f"Error al interpretar el TPV: {parse_msg}"
        )

    if not rows:
        return OcrParseTpvResult(
            ok=False,
            path=path,
            error="No se detectaron líneas de venta en el documento.",
            lineas_detectadas=0,
        )
    return OcrParseTpvResult(ok=True, rows=rows, path=path, lineas_detectadas=len(rows))


def registrar_lineas_tpv(rows: list[dict], ruta: str | Path) -> ResultadoImportTpv:
    """Registra filas parseadas. Debe ejecutarse en el hilo principal de la app."""
    path = Path(ruta)
    fechas = sorted({str(r.get("fecha") or "") for r in rows if r.get("fecha")})
    content_key = _file_hash(path)

    import scripts.import_registros_agosto_2026 as imp

    report: dict = {}
    old_prefix = imp.CLAVE_PREFIX
    old_min, old_max = imp.TPV_FECHA_MIN, imp.TPV_FECHA_MAX
    imp.CLAVE_PREFIX = f"upload-tpv-{content_key}"
    imp.TPV_FECHA_MIN = None
    imp.TPV_FECHA_MAX = None
    try:
        imp.ensure_recipes_and_flags(report)
        imp.import_tpv(
            report,
            rows=rows,
            observaciones=f"Upload documento TPV ({path.name})",
        )
    except Exception as reg_exc:  # noqa: BLE001
        reg_msg = str(reg_exc) or type(reg_exc).__name__
        logger.exception("Import TPV desde documento falló")
        return ResultadoImportTpv(
            ok=False,
            mensaje=f"Error al registrar: {reg_msg}",
            lineas_detectadas=len(rows),
            fechas=fechas,
        )
    finally:
        imp.CLAVE_PREFIX = old_prefix
        imp.TPV_FECHA_MIN = old_min
        imp.TPV_FECHA_MAX = old_max

    return _resumen(report, len(rows), fechas)


def importar_documento_tpv(ruta: str | Path) -> ResultadoImportTpv:
    """OCR + parse + registro comida/bebidas en el hotel activo."""
    parsed = procesar_documento_tpv_ocr(ruta)
    if not parsed.ok:
        return ResultadoImportTpv(
            ok=False,
            mensaje=parsed.error,
            lineas_detectadas=parsed.lineas_detectadas,
        )
    return registrar_lineas_tpv(parsed.rows, parsed.path or ruta)


def importar_documento_tpv_aislado(ruta: str | Path, *, hotel_path: str | Path) -> ResultadoImportTpv:
    """Import TPV en subproceso (OCR+registro), para no tumbar la UI Flet.

    El padre solo espera el JSON de resultado; no ejecuta onnx/cv2 ni el import
    pesado en el mismo proceso que Flet.
    """
    import json
    import subprocess
    import sys
    import tempfile

    fd, out_name = tempfile.mkstemp(prefix="bm_tpv_import_", suffix=".json")
    os.close(fd)
    out_path = Path(out_name)
    try:
        if getattr(sys, "frozen", False):
            cmd = [
                sys.executable,
                "--bm-tpv-import",
                str(ruta),
                str(hotel_path),
                str(out_path),
            ]
        else:
            cmd = [
                sys.executable,
                "-m",
                "app.core.services.tpv_ocr_cli",
                "import",
                str(ruta),
                str(hotel_path),
                str(out_path),
            ]
        env = os.environ.copy()
        env["BM_DEPLOY_WRITER_HELD"] = "1"
        env["BM_DEPLOY_WRITER_PID"] = str(os.getpid())
        flags = 0
        if sys.platform == "win32":
            flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
            creationflags=flags,
            env=env,
            cwd=str(Path(__file__).resolve().parents[2])
            if not getattr(sys, "frozen", False)
            else None,
        )
        payload: dict = {}
        if out_path.is_file():
            try:
                payload = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                payload = {}
        if payload.get("mensaje") is not None or payload.get("ok") is not None:
            return _resultado_from_dict(payload)
        detail = (proc.stderr or "").strip() or f"código {proc.returncode}"
        return ResultadoImportTpv(
            ok=False,
            mensaje=f"Error al importar documento: {detail}",
        )
    except Exception as inline_exc:  # noqa: BLE001
        inline_msg = str(inline_exc) or type(inline_exc).__name__
        return ResultadoImportTpv(
            ok=False,
            mensaje=f"Error al importar documento: {inline_msg}",
        )
    finally:
        out_path.unlink(missing_ok=True)


def _resultado_to_dict(r: ResultadoImportTpv) -> dict:
    return {
        "ok": r.ok,
        "mensaje": r.mensaje,
        "lineas_detectadas": r.lineas_detectadas,
        "registros_ok": r.registros_ok,
        "omitidos_idempotentes": r.omitidos_idempotentes,
        "errores": list(r.errores),
        "pendientes_coctel": list(r.pendientes_coctel),
        "sin_mapear": list(r.sin_mapear),
        "fechas": list(r.fechas),
        "registros_creados": list(r.registros_creados),
    }


def _resultado_from_dict(d: dict) -> ResultadoImportTpv:
    return ResultadoImportTpv(
        ok=bool(d.get("ok")),
        mensaje=str(d.get("mensaje") or ""),
        lineas_detectadas=int(d.get("lineas_detectadas") or 0),
        registros_ok=int(d.get("registros_ok") or 0),
        omitidos_idempotentes=int(d.get("omitidos_idempotentes") or 0),
        errores=list(d.get("errores") or []),
        pendientes_coctel=list(d.get("pendientes_coctel") or []),
        sin_mapear=list(d.get("sin_mapear") or []),
        fechas=list(d.get("fechas") or []),
        registros_creados=list(d.get("registros_creados") or []),
    )
