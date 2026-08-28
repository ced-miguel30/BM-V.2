"""Workers TPV en subproceso (sin Flet / sin WriterLock).

OCR:
  BM-Launcher.exe --bm-tpv-ocr <ruta> <out.json>
  python -m app.core.services.tpv_ocr_cli ocr <ruta> <out.json>

Import completo (OCR + parse + registro):
  BM-Launcher.exe --bm-tpv-import <ruta> <hotel.json> <out.json>
  python -m app.core.services.tpv_ocr_cli import <ruta> <hotel.json> <out.json>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def run_ocr_worker(ruta: str, out_json: str) -> int:
    """Ejecuta OCR y escribe resultado JSON. Código de salida 0/1."""
    out = Path(out_json)
    try:
        from app.core.services.tpv_documento_service import ocr_documento

        texto = ocr_documento(ruta)
        out.write_text(
            json.dumps({"ok": True, "text": texto}, ensure_ascii=False),
            encoding="utf-8",
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        msg = str(exc) or type(exc).__name__
        try:
            out.write_text(
                json.dumps({"ok": False, "error": msg}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
        return 1


def run_import_worker(ruta: str, hotel_path: str, out_json: str) -> int:
    """OCR+parse+registro en subproceso; escribe ResultadoImportTpv como JSON."""
    out = Path(out_json)
    os.environ["BM_TPV_WORKER"] = "1"
    try:
        from datetime import datetime, timezone

        from app.bootstrap import configure_for_flet, reset_container
        from app.core.auth.roles import ROL_DIRECCION
        from app.core.auth.session import (
            ACTOR_TYPE_USUARIO,
            AuthSession,
            save_auth_session,
        )
        from app.core.services.tpv_documento_service import (
            _resultado_to_dict,
            importar_documento_tpv,
        )

        reset_container()
        configure_for_flet(data_path=hotel_path)
        save_auth_session(
            AuthSession(
                authenticated=True,
                actor_type=ACTOR_TYPE_USUARIO,
                actor_id="tpv-worker",
                actor_label="TPV Worker",
                role=ROL_DIRECCION,
                session_id="tpv-worker",
                login_at=datetime.now(timezone.utc).isoformat(),
                terminal_id=None,
                login="tpv-worker",
            )
        )
        resultado = importar_documento_tpv(ruta)
        payload = _resultado_to_dict(resultado)
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return 0 if resultado.ok or resultado.lineas_detectadas else 1
    except Exception as exc:  # noqa: BLE001
        msg = str(exc) or type(exc).__name__
        try:
            out.write_text(
                json.dumps(
                    {
                        "ok": False,
                        "mensaje": f"Error en subproceso de importación: {msg}",
                        "lineas_detectadas": 0,
                        "registros_ok": 0,
                        "omitidos_idempotentes": 0,
                        "errores": [msg],
                        "pendientes_coctel": [],
                        "sin_mapear": [],
                        "fechas": [],
                        "registros_creados": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
        return 1


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print(
            "Uso: tpv_ocr_cli ocr <ruta> <out.json> | "
            "import <ruta> <hotel.json> <out.json>",
            file=sys.stderr,
        )
        return 2
    if args[0] == "ocr" and len(args) >= 3:
        return run_ocr_worker(args[1], args[2])
    if args[0] == "import" and len(args) >= 4:
        return run_import_worker(args[1], args[2], args[3])
    if len(args) >= 2 and args[0] not in ("ocr", "import"):
        return run_ocr_worker(args[0], args[1])
    print("Argumentos inválidos", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
