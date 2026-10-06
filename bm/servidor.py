"""Arranque del servidor:  python -m bm.servidor [--puerto 8000] [--db ruta\bm.sqlite]"""

import argparse
import os

import uvicorn

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--puerto", type=int, default=int(os.environ.get("BM_PORT") or os.environ.get("PORT") or 8000))
    ap.add_argument("--db", help="Base de datos (por defecto datos\bm.sqlite junto al programa)")
    a = ap.parse_args()
    if a.db:
        os.environ["BM_DB"] = a.db  # antes de importar bm.db
    uvicorn.run("bm.app:app", host=os.environ.get("BM_HOST", "0.0.0.0"), port=a.puerto)
