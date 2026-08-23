"""Anula import-ago26*, limpia lotes repo fantasma, reimporta con PACK_KG y genera Word post.

Uso:
  .\\.venv\\Scripts\\python.exe scripts\\reimport_agosto_corregido.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.bootstrap import configure_for_flet, get_container, reset_container
from app.core.auth.roles import ROL_DIRECCION
from app.core.auth.session import ACTOR_TYPE_USUARIO, AuthSession, save_auth_session
from app.core.services.anulacion_merma_service import anular_merma
from app.core.services.anulacion_registro_service import anular_desayuno, anular_servicio
from app.core.storage.session_store import persist_data

import scripts.import_registros_agosto_2026 as imp
import scripts.seed_buffet_desayuno_diario_agosto as buffet

HOTEL = Path(os.environ["LOCALAPPDATA"]) / "BM-V2-local" / "data" / "datos_hotel.json"
TPV_OLD = ROOT / "docs" / "añadidos manual" / "_tpv_parsed.json"
TPV_NEW = ROOT / "docs" / "añadidos manual" / "_tpv_nuevos_parsed.json"
TPV_MERGED = ROOT / "docs" / "añadidos manual" / "_tpv_merged_reimport.json"
REPORT = ROOT / "docs" / "añadidos manual" / "_reimport_corregido_report.json"
CLAVE = "import-ago26"
REPO_MARKS = ("IMPORT-AGO26", "BUFFET-AGO26")


def _auth() -> None:
    save_auth_session(
        AuthSession(
            authenticated=True,
            actor_type=ACTOR_TYPE_USUARIO,
            actor_id="seed-dir",
            actor_label="Seed Dirección",
            role=ROL_DIRECCION,
            session_id="seed-session",
            login_at=datetime.now(timezone.utc).isoformat(),
            terminal_id=None,
            login="seed",
        )
    )


def _boot():
    reset_container()
    configure_for_flet(data_path=str(HOTEL))
    _auth()
    return get_container()


def merge_tpv() -> Path:
    old = json.loads(TPV_OLD.read_text(encoding="utf-8")) if TPV_OLD.exists() else []
    new = json.loads(TPV_NEW.read_text(encoding="utf-8")) if TPV_NEW.exists() else []
    # old: 01-15; new: 12-19 → keep old for <=15, new for >=16
    merged = [r for r in old if _d(r["fecha"]) <= date(2026, 8, 15)]
    merged += [r for r in new if _d(r["fecha"]) >= date(2026, 8, 16)]
    TPV_MERGED.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return TPV_MERGED


def _d(s: str) -> date:
    return datetime.strptime(s.strip(), "%d/%m/%Y").date()


def annul_all(report: dict) -> None:
    data = get_container().app_data_store.get()
    # Desayunos
    for d in list(data.desayunos):
        if d.anulado:
            continue
        clave = getattr(d, "clave_idempotencia", None) or ""
        if not clave.startswith(CLAVE):
            continue
        r = anular_desayuno(d.id, "Corrección conversión PACK_KG", "reimport-pack-kg")
        report.setdefault("anulados_desayuno", []).append({"id": d.id, "ok": r.ok, "msg": r.mensaje})

    data = get_container().app_data_store.get()
    for reg in list(data.registros_servicio):
        if reg.anulado:
            continue
        clave = getattr(reg, "clave_idempotencia", None) or ""
        if not clave.startswith(CLAVE):
            continue
        r = anular_servicio(reg.id, "Corrección conversión PACK_KG", "reimport-pack-kg")
        report.setdefault("anulados_servicio", []).append(
            {"id": reg.id, "tipo": reg.tipo_servicio, "ok": r.ok, "msg": r.mensaje}
        )

    # Mermas hielo
    data = get_container().app_data_store.get()
    for m in list(getattr(data, "mermas", None) or []):
        if getattr(m, "anulado", False):
            continue
        hit = False
        for lin in m.lineas or []:
            com = getattr(lin, "comentario", None) or ""
            if CLAVE in com and "merma-hielo" in com:
                hit = True
                break
        if not hit:
            continue
        try:
            r = anular_merma(None, m.id, "Corrección import PACK_KG", "reimport-pack-kg")
            report.setdefault("anulados_merma", []).append(
                {"id": m.id, "ok": r.ok, "msg": r.mensaje}
            )
        except Exception as e:
            report.setdefault("anulados_merma", []).append({"id": m.id, "ok": False, "msg": str(e)})


def clean_repo_lots(report: dict) -> None:
    data = get_container().app_data_store.get()
    n = 0
    rest_before = 0.0
    for l in data.lotes:
        marca = getattr(l, "marca_proveedor", None) or ""
        if marca not in REPO_MARKS:
            continue
        rest = float(l.cantidad_restante or 0)
        if rest <= 0:
            continue
        rest_before += rest
        l.cantidad_restante = 0.0
        n += 1
    persist_data(data)
    report["lotes_repo_zeroed"] = n
    report["lotes_repo_restante_limpiado"] = round(rest_before, 4)


def main() -> int:
    _boot()
    report: dict = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "ok": [],
        "errors": [],
        "reposiciones": [],
        "skipped_idempotent": [],
    }

    print("== 1. Anular import-ago26* ==")
    annul_all(report)
    print(
        "  desayuno",
        len(report.get("anulados_desayuno", [])),
        "servicio",
        len(report.get("anulados_servicio", [])),
        "merma",
        len(report.get("anulados_merma", [])),
    )

    print("== 2. Limpiar lotes repo fantasma ==")
    _boot()
    clean_repo_lots(report)
    print("  zeroed", report["lotes_repo_zeroed"], "restante", report["lotes_repo_restante_limpiado"])

    print("== 3. Merge TPV + reimport ==")
    merged = merge_tpv()
    print("  TPV merged", merged, "lines", len(json.loads(merged.read_text(encoding="utf-8"))))

    # Desayunos 1-11, 14-18
    _boot()
    imp.DESAYUNO_DIAS = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18}
    imp.TPV_JSON = merged
    imp.TPV_FECHA_MIN = date(2026, 8, 1)
    imp.TPV_FECHA_MAX = date(2026, 8, 19)
    print("  recetas/flags")
    imp.ensure_recipes_and_flags(report)
    print("  desayunos")
    _boot()
    imp.import_desayunos(report)
    print("  tpv")
    _boot()
    imp.import_tpv(report)

    # Buffet 1-19
    print("== 4. Buffet 1-19 ==")
    buffet.FECHA_INI = date(2026, 8, 1)
    buffet.FECHA_FIN = date(2026, 8, 19)
    code = buffet.main()
    if code != 0:
        report.setdefault("errors", []).append(f"buffet exit {code}")

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["summary"] = {
        "ok": len(report.get("ok", [])),
        "errors": len(report.get("errors", [])),
        "unmapped": len(report.get("tpv_unmapped", [])),
        "pending_coctel": len(report.get("tpv_pending_coctel_dia", [])),
        "parse_notes": report.get("desayuno_parse_notes_total"),
        "lotes_repo_zeroed": report.get("lotes_repo_zeroed"),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if report.get("errors"):
        print("ERRORS:", *report["errors"][:20], sep="\n  ")

    print("== 5. Word post-corrección ==")
    import scripts.export_auditoria_costes_agosto_docx as audit

    # re-run as module main with suffix
    sys.argv = [
        "export_auditoria_costes_agosto_docx.py",
        "--suffix",
        "_post_correccion",
        "--titulo",
        "Post-corrección PACK_KG (gr→Ud)",
    ]
    audit.main()

    print("Report:", REPORT)
    return 0 if not report.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
