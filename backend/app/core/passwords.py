"""Web sign-in: password hashing and signed session tokens. Standard library only.

Passwords: scrypt (n=2**14, r=8, p=1), a fresh 16-byte salt per password, stored as
"scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>". Checking uses compare_digest (no timing leak).

Session token: "<user_id>.<expires unix>.<signature>", the signature is HMAC-SHA256 over the first
two parts with settings.web_session_secret. Nothing secret is inside the token, it only proves that
this backend issued it for that user and that it has not expired. No server-side session table:
signing out = the browser forgets the token (enough for the MVP, decision D83).
"""

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from app.core.config import settings

SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SALT_BYTES = 16
_DEV_SECRET = secrets.token_hex(32)  # used only when FIBO_WEB_SESSION_SECRET is not set (dev)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, salt, expected = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p))
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), expected)


def _secret() -> bytes:
    if settings.web_session_secret:
        return settings.web_session_secret.encode()
    if settings.env == "test":
        return _DEV_SECRET.encode()
    # Persist the local signing key so reloads and multiple workers keep sessions valid.
    path = Path(settings.data_dir) / "web-session.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes()
    candidate = path.with_name(f".web-session-{secrets.token_hex(8)}.key")
    fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(_DEV_SECRET.encode())
        try:
            os.link(
                candidate, path
            )  # Publish only the fully written key; never replace another worker's key.
        except FileExistsError:
            pass
        return path.read_bytes()
    finally:
        candidate.unlink(missing_ok=True)


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def issue_token(user_id: int, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + settings.web_session_hours * 3600)
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}"


def read_token(token: str, now: float | None = None) -> int | None:
    """The user id if the token is genuine and not expired, else None."""
    try:
        user_id, expires, signature = token.split(".")
        if not hmac.compare_digest(signature, _sign(f"{user_id}.{expires}")):
            return None
        if int(expires) < (time.time() if now is None else now):
            return None
        return int(user_id)
    except ValueError:
        return None


# --- Telegram link for web users (owners): t.me/<bot>?start=<token> -------------------------------
# Telegram start payloads allow only [A-Za-z0-9_-] and 64 characters, so the token is
# "own<user id>x<expires>x<24 hex of HMAC>" with its own purpose string in the signature.
LINK_TTL_S = 3600
LINK_PREFIX = "own"


def _sign_link(payload: str) -> str:
    return hmac.new(_secret(), f"tg-link:{payload}".encode(), hashlib.sha256).hexdigest()[:24]


def issue_link_token(user_id: int, now: float | None = None) -> tuple[str, int]:
    expires = int((time.time() if now is None else now) + LINK_TTL_S)
    payload = f"{user_id}x{expires}"
    return f"{LINK_PREFIX}{payload}x{_sign_link(payload)}", expires


def read_link_token(token: str, now: float | None = None) -> int | None:
    """The user id if the link token is genuine and not expired, else None."""
    if not token.startswith(LINK_PREFIX):
        return None
    try:
        user_id, expires, signature = token.removeprefix(LINK_PREFIX).split("x")
        if not hmac.compare_digest(signature, _sign_link(f"{user_id}x{expires}")):
            return None
        if int(expires) < (time.time() if now is None else now):
            return None
        return int(user_id)
    except ValueError:
        return None
