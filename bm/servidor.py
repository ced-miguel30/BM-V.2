"""Arranque del servidor:  python -m bm.servidor   (http://<servidor>:8000)"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("bm.app:app", host=os.environ.get("BM_HOST", "0.0.0.0"),
                port=int(os.environ.get("BM_PORT") or os.environ.get("PORT") or "8000"))
