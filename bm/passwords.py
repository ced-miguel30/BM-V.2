"""Derivación y verificación de contraseñas (F16).

Formato: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``
Usa PBKDF2-HMAC-SHA256 de la stdlib (sin dependencias extras).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PREFIX = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 200_000
_SALT_BYTES = 16
_DKLEN = 32

# Prefijo legacy plano (nunca se vuelve a escribir)
LEGACY_PLAIN_PREFIX = "plain:"


class PasswordError(ValueError):
    """Error de formato o verificación de contraseña."""


def hash_password(password: str, *, iterations: int = DEFAULT_ITERATIONS) -> str:
    if not isinstance(password, str) or not password:
        raise PasswordError("La contraseña no puede estar vacía.")
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=_DKLEN
    )
    return (
        f"{PREFIX}${iterations}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(dk).decode('ascii')}"
    )


def identify_hash_format(stored: str | None) -> str:
    if not stored:
        return "empty"
    if stored.startswith(f"{PREFIX}$"):
        return PREFIX
    if stored.startswith(LEGACY_PLAIN_PREFIX):
        return "legacy_plain"
    # Texto sin esquema → legacy inseguro
    if "$" not in stored:
        return "legacy_plain_raw"
    return "unknown"


def verify_password(password: str, stored: str | None) -> bool:
    """Verifica sin filtrar si el usuario existe (caller usa mensaje genérico)."""
    if not stored or not isinstance(password, str):
        return False
    fmt = identify_hash_format(stored)
    if fmt == PREFIX:
        try:
            _pref, iter_s, salt_b64, hash_b64 = stored.split("$", 3)
            iterations = int(iter_s)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(hash_b64.encode("ascii"))
        except (ValueError, TypeError):
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected)
        )
        return hmac.compare_digest(dk, expected)
    if fmt in ("legacy_plain", "legacy_plain_raw"):
        plain = stored[len(LEGACY_PLAIN_PREFIX) :] if stored.startswith(LEGACY_PLAIN_PREFIX) else stored
        return hmac.compare_digest(password.encode("utf-8"), plain.encode("utf-8"))
    return False


def needs_rehash(stored: str | None) -> bool:
    fmt = identify_hash_format(stored)
    if fmt != PREFIX:
        return True
    try:
        parts = stored.split("$")
        iterations = int(parts[1])
        return iterations < DEFAULT_ITERATIONS
    except (IndexError, ValueError, AttributeError):
        return True


def migrate_legacy_if_needed(password: str, stored: str | None) -> str | None:
    """Si la verificación legacy fue correcta, devuelve nuevo hash; si no, None."""
    if not verify_password(password, stored):
        return None
    if needs_rehash(stored):
        return hash_password(password)
    return None


def password_usable(stored: str | None) -> bool:
    """True si hay credencial verificable (hash o legacy)."""
    fmt = identify_hash_format(stored)
    return fmt in (PREFIX, "legacy_plain", "legacy_plain_raw")
