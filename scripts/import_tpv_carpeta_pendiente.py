"""Importa todos los PDF TPV de docs/añadidos manual/tpv pendiente → D:\\work.

Uso:
  py -3 scripts/import_tpv_carpeta_pendiente.py
  py -3 scripts/import_tpv_carpeta_pendiente.py --dir \"ruta\\tpv pendiente\"
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HOTEL_DEFAULT = Path(r"D:\work\2-BM-DATOS\data\datos_hotel.json")


def _find_default_dir() -> Path:
    docs = ROOT / "docs"
    for p in docs.rglob("tpv pendiente"):
        if p.is_dir():
            return p
    return docs / "añadidos manual" / "tpv pendiente"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=None)
    parser.add_argument("--path", type=Path, default=HOTEL_DEFAULT)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    carpeta = args.dir or _find_default_dir()
    if not carpeta.is_dir():
        print("No existe carpeta:", carpeta)
        return 1
    if not args.path.exists():
        print("No existe datos:", args.path)
        return 1

    pdfs = sorted(carpeta.glob("*.pdf"))
    print("Carpeta:", carpeta.resolve())
    print("Datos:", args.path.resolve())
    print(f"PDFs: {len(pdfs)}")
    if not pdfs:
        print("Nada que importar (deja aqui 2308.pdf / 1409.pdf …).")
        return 0

    bak_dir = args.path.parent / "backups"
    bak_dir.mkdir(parents=True, exist_ok=True)
    bak = bak_dir / f"datos_hotel_pre_tpv_pendiente_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy2(args.path, bak)
    print("Backup:", bak)

    from app.bootstrap import configure_for_flet, reset_container
    from app.core.auth.roles import ROL_DIRECCION
    from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
    from app.core.services.tpv_documento_service import (
        _resultado_to_dict,
        importar_documento_tpv,
    )

    reset_container()
    configure_for_flet(data_path=str(args.path))
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="tpv-pendiente",
            actor_label="TPV pendiente",
            role=ROL_DIRECCION,
            session_id="tpv-pendiente",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="tpv-pendiente",
        )
    )

    results = []
    for pdf in pdfs:
        print(f"\n=== {pdf.name} ===")
        try:
            resultado = importar_documento_tpv(str(pdf))
            payload = _resultado_to_dict(resultado)
        except Exception as exc:  # noqa: BLE001
            payload = {"ok": False, "mensaje": str(exc), "archivo": pdf.name}
            print("ERROR", exc)
        else:
            print(
                f"ok={payload.get('ok')} regs={payload.get('registros_ok')} "
                f"fechas={payload.get('fechas')} sin_mapear={len(payload.get('sin_mapear') or [])}"
            )
        payload["archivo"] = pdf.name
        results.append(payload)

    out = args.out or (ROOT / "exports" / f"tpv_pendiente_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nInforme:", out)
    n_fail = sum(1 for r in results if not r.get("ok"))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
