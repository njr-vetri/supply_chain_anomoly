"""Cryptographic security utilities for authentication, passwords, and tokens.

Uses bcrypt for password hashing and signed expiring HMAC-SHA256 tokens for
enterprise multi-tenant identity verification.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import secrets
from typing import Any

import bcrypt
import jwt

# Roles allowed across the system in increasing privilege order
ROLES: dict[str, int] = {"viewer": 1, "analyst": 2, "reviewer": 3, "admin": 4}

# Ephemeral secret generated once per process lifetime if no env variable is provided
_EPHEMERAL_SECRET: str | None = None


def get_jwt_secret() -> str:
    """Retrieve token signing secret from environment; fallback to ephemeral process secret."""
    secret = os.getenv("JWT_SECRET_KEY") or os.getenv("AUTH_SECRET_KEY")
    if secret and secret.strip():
        return secret.strip()
    global _EPHEMERAL_SECRET
    if _EPHEMERAL_SECRET is None:
        _EPHEMERAL_SECRET = secrets.token_hex(32)
    return _EPHEMERAL_SECRET


def is_local_dev_mode() -> bool:
    """Return whether the explicit local development authentication bypass is enabled."""
    return os.getenv("AUTH_LOCAL_DEV_MODE", "false").lower() in ("true", "1", "yes")


def validate_password_strength(plain_password: str) -> None:
    """Enforce minimum password length and non-empty constraint."""
    if not plain_password or len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long")


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt with a generated salt."""
    validate_password_strength(plain_password)
    # bcrypt expects bytes; returns utf-8 decoded string hash
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    user_id: str,
    username: str,
    company_id: str,
    role: str,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed, expiring JWT token bound to a specific user, company, and role."""
    if role not in ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {list(ROLES.keys())}")
    if not company_id or not company_id.strip():
        raise ValueError("company_id is required")

    now = datetime.now(timezone.utc)
    expiry_seconds = int(os.getenv("AUTH_TOKEN_EXPIRE_SECONDS", "3600"))
    expires_at = now + (expires_delta if expires_delta is not None else timedelta(seconds=expiry_seconds))

    payload: dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "company_id": company_id.strip(),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "supply-chain-risk-system",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a signed JWT token; raises ValueError if expired or invalid."""
    try:
        payload = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=["HS256"],
            issuer="supply-chain-risk-system",
            options={"require": ["exp", "iat", "sub", "company_id", "role"]},
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError("Invalid authentication token") from exc
