"""Conservative Olist review text cleaning, heuristic language ID, and extraction."""
from __future__ import annotations

import re
import unicodedata
from typing import Any

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")
CPF_RE = re.compile(r"\b\d{3}[.\s]?\d{3}[.\s]?\d{3}[-\s]?\d{2}\b")
DATE_PATTERNS = [re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")]
QUANTITY_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:unidades?|itens?|days?|dias?|hours?|horas?|kg|g|pcs?)\b", re.I)
PORTUGUESE_HINTS = {"não", "nao", "entrega", "produto", "pedido", "chegou", "ruim", "bom", "prazo"}
ENGLISH_HINTS = {"delivery", "product", "order", "arrived", "bad", "good", "late", "received"}


def redact_pii(text: str) -> str:
    """Regex-redact common email, phone, and Brazilian CPF patterns."""
    # Preserve date tokens before the broad phone pattern sees nearby digits.
    value = str(text)
    saved_dates: list[str] = []
    for pattern in DATE_PATTERNS:
        value = pattern.sub(lambda match: _save_date(match.group(0), saved_dates), value)
    value = EMAIL_RE.sub(" [REDACTED_EMAIL] ", value)
    value = CPF_RE.sub(" [REDACTED_ID] ", value)
    value = PHONE_RE.sub(" [REDACTED_PHONE] ", value)
    for index, date in enumerate(saved_dates):
        value = value.replace(f"__SAFE_DATE_{index}__", date)
    return value


def _save_date(date: str, saved_dates: list[str]) -> str:
    token = f"__SAFE_DATE_{len(saved_dates)}__"
    saved_dates.append(date)
    return token


def clean_text(text: Any) -> str:
    """Normalize review text as data; never interpret it as an instruction."""
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = redact_pii(value)
    value = re.sub(r"https?://\S+|www\.\S+", " [REDACTED_URL] ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def detect_language(text: str) -> str:
    """Small transparent lexicon heuristic; returns pt, en, or unknown (not a model)."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    words = set(re.findall(r"[a-zá-ú]+", normalized))
    pt, en = len(words & PORTUGUESE_HINTS), len(words & ENGLISH_HINTS)
    if pt == en == 0 or pt == en:
        return "unknown"
    return "pt" if pt > en else "en"


def extract_dates(text: str) -> list[str]:
    return [match.group(0) for pattern in DATE_PATTERNS for match in pattern.finditer(text)]


def extract_quantities(text: str) -> list[str]:
    return [match.group(0) for match in QUANTITY_RE.finditer(text)]


def process_review(text: Any) -> dict[str, Any]:
    cleaned = clean_text(text)
    return {"clean_text": cleaned, "language": detect_language(cleaned),
            "dates": extract_dates(cleaned), "quantities": extract_quantities(cleaned),
            "text_is_untrusted": True, "action_triggered": False}
