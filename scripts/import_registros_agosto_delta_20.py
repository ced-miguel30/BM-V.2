"""Import delta: desayunos 14–18 + TPV 16–19 + buffet 16–19.

Fuentes actualizadas:
  docs/añadidos manual/registro desayuno.xlsx (hojas 14–18)
  docs/añadidos manual/REGISATRO COMIDAS NUEVOS.pdf → _tpv_nuevos_parsed.json
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.import_registros_agosto_2026 as imp
import scripts.seed_buffet_desayuno_diario_agosto as buffet

REPORT = ROOT / "docs" / "añadidos manual" / "_import_delta_ago20_report.json"
TPV_NUEVOS = ROOT / "docs" / "añadidos manual" / "_tpv_nuevos_parsed.json"


def main() -> int:
    if not TPV_NUEVOS.exists():
        print("Falta", TPV_NUEVOS, "— ejecuta scripts/parse_tpv_ocr.py primero")
        return 1

    report: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "ok": [],
        "errors": [],
        "reposiciones": [],
        "skipped_idempotent": [],
    }

    # --- Desayunos huéspedes 14–18 ---
    print("== Desayunos 14-18 ==")
    imp._boot()
    imp.DESAYUNO_DIAS = {14, 15, 16, 17, 18}
    imp.import_desayunos(report)

    # --- TPV solo días nuevos (16–19; 12–15 ya importados del PDF anterior) ---
    print("== TPV 16-19 ==")
    imp._boot()
    imp.TPV_JSON = TPV_NUEVOS
    imp.TPV_FECHA_MIN = date(2026, 8, 16)
    imp.TPV_FECHA_MAX = date(2026, 8, 19)
    imp.ensure_recipes_and_flags(report)
    imp._boot()
    imp.import_tpv(report)

    # --- Buffet estándar 16–19 ---
    print("== Buffet 16-19 ==")
    buffet.FECHA_INI = date(2026, 8, 16)
    buffet.FECHA_FIN = date(2026, 8, 19)
    # seed_buffet main() crea report propio; lo ejecutamos y capturamos vía re-run ligero
    code = buffet.main()
    if code != 0:
        report.setdefault("errors", []).append(f"buffet.main exit={code}")

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    unmapped = sorted({imp._norm(x.get("nombre", "")) for x in report.get("tpv_unmapped", [])})
    report["summary"] = {
        "ok": len(report.get("ok", [])),
        "errors": len(report.get("errors", [])),
        "unmapped_names": unmapped,
        "pending_coctel_dia": len(report.get("tpv_pending_coctel_dia", [])),
        "mermas_hielo": len(report.get("mermas_hielo", [])),
        "skipped_idempotent": len(report.get("skipped_idempotent", [])),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if report.get("errors"):
        print("ERRORS:", *report["errors"][:25], sep="\n  ")
    if unmapped:
        print("UNMAPPED:", unmapped)
    print("Report:", REPORT)
    return 0 if not report.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
