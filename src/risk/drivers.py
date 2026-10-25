"""Descriptive driver analysis. Associations are hypotheses, never causes."""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import comb
from typing import Any, Iterable


DIMENSIONS = {
    "supplier": ("supplier_id", "supplier"),
    "carrier": ("carrier_id", "carrier"),
    "product": ("product_id", "product"),
    "region": ("region", "destination", "region_id"),
    "mode": ("mode", "shipping_mode", "transport_mode"),
    "week": ("event_timestamp", "timestamp", "date"),
}


def _value(row: dict[str, Any], dimension: str) -> str | None:
    for key in DIMENSIONS[dimension]:
        value = row.get(key)
        if value is None or value == "":
            continue
        if dimension == "week":
            try:
                parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return parsed.strftime("%G-W%V")
            except (ValueError, TypeError):
                continue
        return str(value)
    return None


def _fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Small exact two-sided Fisher p-value for a 2x2 table."""
    row1, col1, total = a + b, a + c, a + b + c + d
    lo, hi = max(0, row1 - (total - col1)), min(row1, col1)
    denominator = comb(total, row1)
    observed = comb(col1, a) * comb(total - col1, row1 - a) / denominator
    probability = 0.0
    for x in range(lo, hi + 1):
        p = comb(col1, x) * comb(total - col1, row1 - x) / denominator
        if p <= observed + 1e-12:
            probability += p
    return min(1.0, probability)


def _bh_adjust(items: list[dict[str, Any]]) -> None:
    ordered = sorted(range(len(items)), key=lambda i: items[i]["p_value"])
    n = len(ordered)
    adjusted = [1.0] * n
    running = 1.0
    for rank_index in range(n - 1, -1, -1):
        original = ordered[rank_index]
        running = min(running, items[original]["p_value"] * n / (rank_index + 1))
        adjusted[original] = running
    for i, item in enumerate(items):
        item["adjusted_p_value"] = adjusted[i]


def _change_point(rows: list[dict[str, Any]], affected_refs: set[str], min_segment: int) -> dict[str, Any] | None:
    points = []
    for row in rows:
        week = _value(row, "week")
        if week:
            points.append((week, str(row.get("source_record_ref") or row.get("event_id") or "")))
    counts = Counter(week for week, _ in points)
    weeks = sorted(counts)
    if len(weeks) < 2:
        return None
    totals = [counts[week] for week in weeks]
    flagged = Counter(week for week, ref in points if ref in affected_refs)
    total_n = sum(totals)
    total_cases = sum(flagged.values())
    best = None
    before_n = before_cases = 0
    for index, week in enumerate(weeks[:-1]):
        before_n += totals[index]
        before_cases += flagged[week]
        after_n = total_n - before_n
        after_cases = total_cases - before_cases
        if before_n < min_segment or after_n < min_segment:
            continue
        difference = abs(before_cases / before_n - after_cases / after_n)
        if best is None or difference > best[0]:
            best = (difference, weeks[index + 1], before_cases / before_n, after_cases / after_n)
    if best is None:
        return None
    return {"estimated_boundary_week": best[1], "before_rate": best[2], "after_rate": best[3],
            "absolute_rate_change": best[0], "label": "descriptive change-point estimate; not causal"}


def analyze_drivers(records: Iterable[dict[str, Any]], affected_record_refs: Iterable[str], *,
                    min_affected: int = 5, min_baseline: int = 5, alpha: float = 0.05,
                    min_effect_size: float = 0.1, min_change_point_segment: int = 5,
                    max_refs: int = 100) -> dict[str, Any]:
    """Compare affected rows with the remaining rows and return ranked hypotheses."""
    if min_affected < 1 or min_baseline < 1 or not 0 < alpha < 1:
        raise ValueError("Support thresholds and alpha are invalid")
    rows = [dict(row) for row in records]
    affected = set(map(str, affected_record_refs))
    identified = {str(row.get("source_record_ref") or row.get("event_id") or "") for row in rows}
    if not affected or not affected.issubset(identified):
        return {"status": "Insufficient evidence", "confident_driver": False, "drivers": [],
                "change_point": None, "limitations": ["Affected source references are missing or not present in the baseline."]}
    findings: list[dict[str, Any]] = []
    for dimension in DIMENSIONS:
        values = [_value(row, dimension) for row in rows]
        categories = sorted({value for value in values if value is not None})
        for category in categories:
            inside = [row for row, value in zip(rows, values) if value == category]
            outside = [row for row, value in zip(rows, values) if value != category]
            inside_cases = [row for row in inside if str(row.get("source_record_ref") or row.get("event_id") or "") in affected]
            outside_cases = [row for row in outside if str(row.get("source_record_ref") or row.get("event_id") or "") in affected]
            inside_base = len(inside) - len(inside_cases)
            outside_base = len(outside) - len(outside_cases)
            if len(inside_cases) < min_affected or inside_base < min_baseline or outside_base < min_baseline:
                continue
            rate_in = len(inside_cases) / len(inside)
            rate_out = len(outside_cases) / len(outside) if outside else 0.0
            table = len(inside_cases), inside_base, len(outside_cases), outside_base
            findings.append({"dimension": dimension, "value": category, "effect_size": rate_in - rate_out,
                "affected_rate": rate_in, "baseline_rate": rate_out,
                "support": {"affected_in_group": len(inside_cases), "baseline_in_group": inside_base,
                            "affected_outside_group": len(outside_cases), "baseline_outside_group": outside_base},
                "p_value": _fisher_two_sided(*table),
                "supporting_record_refs": [str(row.get("source_record_ref") or row.get("event_id")) for row in inside_cases[:max_refs]],
                "contradicting_record_refs": [str(row.get("source_record_ref") or row.get("event_id")) for row in outside_cases[:max_refs]],
                "missing_evidence": ["Independent operational evidence establishing a mechanism.",
                                     "Validation on a later time period or an independent sample."],
                "statement": f"{dimension}={category} is associated with a different affected-record rate."})
    _bh_adjust(findings)
    findings.sort(key=lambda item: (abs(item["effect_size"]), -item["adjusted_p_value"]), reverse=True)
    for rank, item in enumerate(findings, start=1):
        item["rank"] = rank
        item["confident_driver"] = (item["support"]["affected_in_group"] >= min_affected
            and item["support"]["baseline_in_group"] >= min_baseline
            and item["adjusted_p_value"] <= alpha and abs(item["effect_size"]) >= min_effect_size)
        item["interpretation"] = "correlation, not proof"
    confident = any(item["confident_driver"] for item in findings)
    return {"status": "HYPOTHESES_AVAILABLE" if findings else "Insufficient evidence",
        "confident_driver": confident, "drivers": findings,
        "change_point": _change_point(rows, affected, min_change_point_segment),
        "multiple_comparison_correction": "Benjamini-Hochberg false discovery rate",
        "settings": {"min_affected": min_affected, "min_baseline": min_baseline, "alpha": alpha,
                     "min_effect_size": min_effect_size},
        "limitations": ["correlation, not proof", "Unmeasured confounding may explain observed differences.",
                        "A change-point estimate is descriptive and does not establish a cause."]}
