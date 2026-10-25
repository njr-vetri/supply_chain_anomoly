"""Small conservative sanitizer for local operational logs."""
from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY_PARTS = {
    "email", "phone", "telephone", "address", "street", "customer", "customerid",
    "customeremail", "customername", "fname", "lname", "firstname", "lastname",
    "fullname", "password", "passwd", "secret", "token", "authorization", "apikey",
    "ip", "ipaddress",
}
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)\+?\d[\d ().-]{8,}\d(?!\w)")


def sanitize_for_log(value: Any, key: str = "") -> Any:
    """Redact sensitive fields and common email/telephone patterns recursively."""
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    tokens = set(filter(None, re.split(r"[^a-z0-9]+", key.lower())))
    if tokens.intersection(_SENSITIVE_KEY_PARTS) or any(
        part in normalized for part in _SENSITIVE_KEY_PARTS if len(part) > 3
    ) or normalized in {"ip", "ipaddress"}:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(name): sanitize_for_log(item, str(name)) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_log(item) for item in value]
    if isinstance(value, str):
        without_email = _EMAIL.sub("[REDACTED_EMAIL]", value)
        return _PHONE.sub("[REDACTED_PHONE]", without_email)
    return value
