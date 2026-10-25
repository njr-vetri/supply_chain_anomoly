"""Automated schema mapper suggesting canonical roles with confidence scores without auto-confirming."""

from __future__ import annotations

import difflib
import re
from pydantic import BaseModel, ConfigDict, Field

from src.data.profile import CANONICAL_ROLES, TIMESTAMP_ROLES
from src.data.profiler import ColumnProfile, DatasetProfileReport


# Synonyms and keyword patterns for each canonical role
ROLE_KEYWORDS: dict[str, list[str]] = {
    "order_id": [
        "order_id", "orderid", "order_number", "ord_id", "order_item_id", "invoice",
        "invoiceno", "order_code", "purchase_id", "order_item_id", "order item id",
    ],
    "order_ts": [
        "order_purchase_timestamp", "order_date", "dateorders", "invoicedate",
        "purchase_date", "order_time", "created_at", "trans_date", "order date (dateorders)",
    ],
    "promised_ts": [
        "order_estimated_delivery_date", "estimated_delivery", "promised_date",
        "due_date", "scheduled_date", "target_delivery", "estimated_arrival",
    ],
    "delivered_ts": [
        "order_delivered_customer_date", "actual_delivery_date", "shipping_date",
        "delivered_at", "delivered_date", "shipment_date", "shipping date (dateorders)",
    ],
    "supplier_id": [
        "seller_id", "vendor_id", "supplier_id", "vendor", "supplier", "seller",
        "merchant_id", "producer_id",
    ],
    "product_id": [
        "product_id", "item_id", "sku", "stockcode", "part_number", "product_code",
        "stock_code", "item_code",
    ],
    "carrier": [
        "carrier", "shipping_mode", "courier", "logistics_provider", "delivery_method",
        "carrier_name", "shipping_carrier", "shipment_mode",
    ],
    "quantity": [
        "quantity", "order_item_quantity", "qty", "count", "units", "items", "num_items",
    ],
    "price": [
        "price", "order_item_total", "unit_price", "amount", "total", "cost",
        "freight_value", "order_total", "sale_amount",
    ],
    "status": [
        "order_status", "delivery_status", "status", "stage", "late_delivery_risk",
        "shipping_status", "state_status",
    ],
    "region": [
        "customer_state", "customer_city", "country", "order_region", "order_country",
        "region", "state", "city", "zip_code", "postal_code", "delivery_region",
    ],
    "route": [
        "route", "lane", "shipping_route", "transit_lane", "corridor", "transport_route",
    ],
}


class RoleCandidate(BaseModel):
    """Candidate canonical role with associated confidence score."""
    model_config = ConfigDict(extra="forbid")
    role: str
    confidence: float
    reason: str


class ColumnRoleSuggestion(BaseModel):
    """Role suggestion for a specific column."""
    model_config = ConfigDict(extra="forbid")
    column_name: str
    suggested_role: str | None = None
    confidence: float = 0.0
    alternative_roles: list[RoleCandidate] = Field(default_factory=list)
    reason: str = "No strong pattern match"
    needs_clarification: bool = False
    auto_accepted: bool = False
    is_custom_field: bool = False


class MappingSuggestionReport(BaseModel):
    """Full dataset schema suggestion report. Strictly unconfirmed by design."""
    model_config = ConfigDict(extra="forbid")
    dataset_name: str
    source_filename: str
    suggestions: list[ColumnRoleSuggestion]
    auto_confirmed: bool = False
    status: str = "PENDING_REVIEW"
    note: str = "Suggestions require explicit human confirmation via PUT confirm-mapping."
    auto_accepted_mappings: dict[str, str] = Field(default_factory=dict)
    ambiguous_columns: list[str] = Field(default_factory=list)
    unmapped_columns: list[str] = Field(default_factory=list)


ROLE_DESCRIPTIONS: dict[str, str] = {
    "order_id": "order identifier purchase order id invoice number transaction code purchase id",
    "order_ts": "order purchase timestamp order date invoice date transaction time created at purchase date",
    "promised_ts": "promised delivery date scheduled arrival date due date estimated delivery date target date",
    "delivered_ts": "actual delivery date delivered timestamp shipment arrival date delivered at shipping date",
    "supplier_id": "supplier vendor seller merchant producer seller id vendor code vendor id",
    "product_id": "product item stock code SKU part number merchandise item code stock code",
    "carrier": "shipping carrier logistics courier delivery provider shipping mode transport carrier",
    "quantity": "order item quantity units sold count of items number of units units qty",
    "price": "unit price item amount total value currency cost freight amount total price",
    "status": "order fulfillment status delivery state delivery status late risk flag",
    "region": "customer state destination country region postal code delivery territory state city",
    "route": "transit route shipping corridor transport lane origin destination route transit corridor",
}

_EMBEDDING_MODEL = None
_EMBEDDINGS_TRIED = False


def _get_embedding_similarity(text1: str, text2: str) -> float:
    """Compute cosine similarity using sentence-transformers (all-MiniLM-L6-v2) or deterministic sub-word TF-IDF."""
    global _EMBEDDING_MODEL, _EMBEDDINGS_TRIED
    if not _EMBEDDINGS_TRIED:
        _EMBEDDINGS_TRIED = True
        try:
            from sentence_transformers import SentenceTransformer
            _EMBEDDING_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        except Exception:
            _EMBEDDING_MODEL = None

    if _EMBEDDING_MODEL is not None:
        try:
            import numpy as np
            embs = _EMBEDDING_MODEL.encode([text1, text2])
            dot = float(np.dot(embs[0], embs[1]))
            norm1 = float(np.linalg.norm(embs[0]))
            norm2 = float(np.linalg.norm(embs[1]))
            if norm1 > 0 and norm2 > 0:
                return max(0.0, min(1.0, dot / (norm1 * norm2)))
        except Exception:
            pass

    # Deterministic local TF-IDF n-gram cosine similarity fallback
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        matrix = vec.fit_transform([text1, text2])
        sim = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
        return max(0.0, min(1.0, sim))
    except Exception:
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())
        union = tokens1 | tokens2
        return len(tokens1 & tokens2) / len(union) if union else 0.0


def _clean_text(text: str) -> str:
    """Normalize column name for fuzzy keyword matching."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _score_role(col: ColumnProfile, role: str) -> tuple[float, str]:
    """Calculate match confidence [0.0, 1.0] between a column profile and a canonical role."""
    clean_col = _clean_text(col.name)
    keywords = ROLE_KEYWORDS.get(role, [])

    # 1. Base score from name similarity and synonyms
    name_score = 0.0
    match_reason = ""

    for kw in keywords:
        clean_kw = _clean_text(kw)
        if clean_col == clean_kw:
            name_score = max(name_score, 0.95)
            match_reason = f"Exact match with known synonym '{kw}'"
            break
        elif clean_kw in clean_col or clean_col in clean_kw:
            name_score = max(name_score, 0.75)
            match_reason = f"Contains keyword '{kw}'"
        else:
            ratio = difflib.SequenceMatcher(None, clean_col, clean_kw).ratio()
            if ratio > 0.8:
                name_score = max(name_score, 0.65)
                match_reason = f"Fuzzy similarity ({ratio:.2f}) with '{kw}'"

    # Embedding similarity augmentation
    role_desc = ROLE_DESCRIPTIONS.get(role, role)
    emb_sim = _get_embedding_similarity(col.name, role_desc)
    if emb_sim > 0.60:
        if name_score == 0.0:
            name_score = round(emb_sim * 0.70, 4)
            match_reason = f"Semantic sentence-embedding similarity ({emb_sim:.2f}) with {role}"
        else:
            name_score = min(1.0, max(name_score, round(0.7 * name_score + 0.3 * emb_sim, 4)))

    if name_score == 0.0:
        return 0.0, "No name or semantic similarity"

    # 2. Value pattern validation & adjustment
    score = name_score
    reasons: list[str] = [match_reason]

    is_timestamp = role in TIMESTAMP_ROLES
    is_numeric_metric = role in {"quantity", "price"}

    if is_timestamp:
        if col.date_parse_success_rate >= 0.7:
            score = min(score + 0.05, 1.0)
            reasons.append(f"Confirmed by date parse rate ({col.date_parse_success_rate:.0%})")
        elif col.date_parse_success_rate < 0.2:
            score = max(score - 0.50, 0.0)
            reasons.append("Contradicted: column does not parse as datetimes")

    if is_numeric_metric:
        if col.numeric_stats is not None:
            score = min(score + 0.05, 1.0)
            reasons.append("Confirmed numeric datatype")
        else:
            score = max(score - 0.50, 0.0)
            reasons.append("Contradicted: column is not numeric")

    if role == "order_id":
        if col.uniqueness_ratio > 0.05:
            score = min(score + 0.03, 1.0)
        else:
            score = max(score - 0.30, 0.0)
            reasons.append("Low uniqueness for an identifier")

    if role in {"status", "carrier"}:
        if col.uniqueness_ratio < 0.25:
            score = min(score + 0.05, 1.0)
            reasons.append("Low uniqueness typical of categorical roles")

    return round(score, 4), "; ".join(reasons)


def suggest_mappings(report: DatasetProfileReport) -> MappingSuggestionReport:
    """Analyze all columns in a dataset profile report and generate role suggestions.

    Confident matches are flagged auto_accepted=True; ambiguous matches are flagged
    needs_clarification=True. Columns without a canonical match are preserved as custom fields.
    CRITICAL RULE: The returned report has status='PENDING_REVIEW' and auto_confirmed=False.
    """
    suggestions: list[ColumnRoleSuggestion] = []
    auto_accepted_dict: dict[str, str] = {}
    ambiguous_list: list[str] = []
    unmapped_list: list[str] = []

    for col in report.columns:
        candidates: list[RoleCandidate] = []
        for role in CANONICAL_ROLES:
            confidence, reason = _score_role(col, role)
            if confidence >= 0.35:
                candidates.append(RoleCandidate(role=role, confidence=confidence, reason=reason))

        candidates.sort(key=lambda c: c.confidence, reverse=True)

        if candidates and candidates[0].confidence >= 0.40:
            top = candidates[0]
            alternatives = candidates[1:4]
            margin = (top.confidence - candidates[1].confidence) if len(candidates) > 1 else 1.0
            is_ambiguous = (top.confidence < 0.75 or margin < 0.12)

            suggestion = ColumnRoleSuggestion(
                column_name=col.name,
                suggested_role=top.role,
                confidence=top.confidence,
                alternative_roles=alternatives,
                reason=("needs clarification: " + top.reason) if is_ambiguous else top.reason,
                needs_clarification=is_ambiguous,
                auto_accepted=not is_ambiguous,
                is_custom_field=False,
            )
            suggestions.append(suggestion)

            if not is_ambiguous:
                auto_accepted_dict[col.name] = top.role
            else:
                ambiguous_list.append(col.name)
        else:
            suggestion = ColumnRoleSuggestion(
                column_name=col.name,
                suggested_role=None,
                confidence=0.0,
                alternative_roles=candidates[:3],
                reason="Insufficient pattern confidence to suggest a role (preserved as custom field)",
                needs_clarification=False,
                auto_accepted=False,
                is_custom_field=True,
            )
            suggestions.append(suggestion)
            unmapped_list.append(col.name)

    return MappingSuggestionReport(
        dataset_name=report.dataset_name,
        source_filename=report.source_filename,
        suggestions=suggestions,
        auto_confirmed=False,
        status="PENDING_REVIEW",
        auto_accepted_mappings=auto_accepted_dict,
        ambiguous_columns=ambiguous_list,
        unmapped_columns=unmapped_list,
    )
