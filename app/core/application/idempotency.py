"""Tokens de idempotencia de confirmación (capa aplicación, sin UI)."""

from __future__ import annotations

import uuid

from app.bootstrap import get_container


def current_idempotency_token(scope: str) -> str:
    """Devuelve el token del ámbito; lo crea si no existe."""
    store = get_container().idempotency_store
    tok = store.get(scope)
    if not tok:
        tok = str(uuid.uuid4())
        store.set(scope, tok)
    return tok


def rotate_idempotency_token(scope: str) -> str:
    """Genera y fija un token nuevo (tras confirmación OK)."""
    tok = str(uuid.uuid4())
    get_container().idempotency_store.set(scope, tok)
    return tok
