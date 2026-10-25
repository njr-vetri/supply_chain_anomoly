"""Authentication and security module: bcrypt hashing, JWT tokens, RBAC policy and API keys."""
from __future__ import annotations

import hashlib
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

SECRET_KEY = os.getenv("SECRET_KEY", "risk-system-local-dev-secret-key-32-bytes-minimum!!")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

ROLE_LEVELS: dict[str, int] = {
    "viewer": 1,
    "analyst": 2,
    "reviewer": 3,
    "admin": 4,
}

PERMISSIONS: dict[str, list[str]] = {
    "viewer": [
        "read:incidents",
        "read:predictions",
        "read:anomalies",
        "read:graph",
        "read:models",
        "read:recommendations",
        "read:actions",
        "read:alerts",
        "read:datasets",
    ],
    "analyst": [
        "read:incidents",
        "read:predictions",
        "read:anomalies",
        "read:graph",
        "read:models",
        "read:recommendations",
        "read:actions",
        "read:alerts",
        "read:datasets",
        "upload:datasets",
        "profile:datasets",
        "map:datasets",
        "run:pipeline",
        "create:hypotheses",
        "request:actions",
        "request:approvals",
    ],
    "reviewer": [
        "read:incidents",
        "read:predictions",
        "read:anomalies",
        "read:graph",
        "read:models",
        "read:recommendations",
        "read:actions",
        "read:alerts",
        "read:datasets",
        "upload:datasets",
        "profile:datasets",
        "map:datasets",
        "run:pipeline",
        "create:hypotheses",
        "request:actions",
        "request:approvals",
        "confirm:hypotheses",
        "approve:actions",
        "promote:models",
        "rollback:models",
    ],
    "admin": [
        "read:incidents",
        "read:predictions",
        "read:anomalies",
        "read:graph",
        "read:models",
        "read:recommendations",
        "read:actions",
        "read:alerts",
        "read:datasets",
        "upload:datasets",
        "profile:datasets",
        "map:datasets",
        "run:pipeline",
        "create:hypotheses",
        "request:actions",
        "request:approvals",
        "confirm:hypotheses",
        "approve:actions",
        "promote:models",
        "rollback:models",
        "manage:users",
        "manage:api_keys",
        "manage:kill_switch",
        "manage:scheduler",
        "manage:settings",
        "delete:datasets",
        "view:audit",
    ],
}


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(hours=TOKEN_EXPIRE_HOURS))
    to_encode.update({"iat": now, "exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def generate_temp_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    # Ensure at least one lower, upper, digit, symbol
    pwd = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    pwd += [secrets.choice(alphabet) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def generate_machine_api_key() -> tuple[str, str, str]:
    """Return (raw_api_key, prefix, key_hash)."""
    raw = f"ak_live_{secrets.token_hex(24)}"
    prefix = raw[:14] + "..."
    key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, prefix, key_hash
