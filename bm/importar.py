"""Carga inicial completa: BC + BM v2 + TPV histórico -> SQLite, y valoración.

    python -m bm.importar --productos Productos.xlsx --movs "Movs. productos.xlsx" \
        --bm2 datos_hotel.json --tpv-pdf a.pdf b.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

from bm import bc, bm2, costing, db, tpv

RAIZ = Path(__file__).resolve().parent.parent


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--productos")
    ap.add_argument("--movs")
    ap.add_argument("--bm2", help="datos_hotel.json de BM v2")
    ap.add_argument("--tpv-pdf", nargs="*", default=[])
    a = ap.parse_args(argv)
    con = db.connect(a.db)
    if a.productos:
        print("productos BC:", bc.importar_productos(con, a.productos))
    if a.movs:
        print("movimientos BC:", bc.importar_movimientos(con, a.movs))
    if a.bm2:
        manual = RAIZ / "docs" / "añadidos manual"
        print("BM v2:", bm2.migrar(con, a.bm2, manual / "_import_compras_prov_resumen.csv"))
        print("desayuno (atajos, buffet, recetas del día):", bm2.sembrar_desayuno(con, Path(__file__).parent / "semillas_desayuno.json"))
        print("TPV asignaciones heredadas:", bm2.sembrar_tpv(con, RAIZ / "scripts" / "import_registros_agosto_2026.py"))
        hist = manual / "_tpv_merged_reimport.json"
        if hist.exists():
            print("TPV agosto (v2):", {k: v for k, v in tpv.importar_lineas(con, bm2.ventas_tpv_historicas(hist)).items() if k != "dias"})
    for pdf in a.tpv_pdf:
        r = tpv.importar_lineas(con, tpv.leer_pdf(pdf))
        print(f"TPV {Path(pdf).name}: {len(r['dias'])} días, {r['lineas']} líneas, {r['importe']} EUR")
    print("TPV -> consumos:", tpv.regenerar(con))
    print("valoración:", costing.valorar(con))


if __name__ == "__main__":
    main()
