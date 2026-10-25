"""Generic incident assembly from stored anomaly and prediction findings."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.core.schemas import Evidence, Hypothesis, Incident, HypothesisStatus


def assemble_incident(*, source: str, anomalies: list[dict[str, Any]],
                      predictions: list[dict[str, Any]], title: str | None = None) -> dict[str, Any]:
    """Create a fact/prediction ledger and unverified hypotheses with record provenance."""
    findings = [("anomaly", item) for item in anomalies] + [("prediction", item) for item in predictions]
    def refs_for(item: dict[str, Any]) -> list[str]:
        refs = item.get("record_refs")
        if refs is None:
            refs = item.get("record_ref")
        if isinstance(refs, str):
            refs = [refs]
        return [str(ref) for ref in (refs or []) if ref]

    record_refs = list(dict.fromkeys(ref for _, item in findings for ref in refs_for(item)))
    evidence: list[Evidence] = []
    hypotheses: list[Hypothesis] = []
    for kind, item in findings:
        refs = refs_for(item)
        timestamp = item.get("predicted_at") or item.get("observed_at") or item.get("created_at")
        if isinstance(timestamp, str):
            try:
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except ValueError:
                timestamp = None
        timestamp = timestamp or datetime.now(timezone.utc)
        if kind == "anomaly":
            fact = {key: item.get(key) for key in ("feature", "observed_value", "baseline", "detector")}
            ev = Evidence(evidence_type="observed_anomaly", source=source, record_refs=refs,
                          observed_at=timestamp, facts={key: value for key, value in fact.items() if value is not None})
            evidence.append(ev)
            if refs:
                hypotheses.append(Hypothesis(statement=f"Recorded anomaly in {fact.get('feature') or 'a measured feature'} warrants investigation.",
                    status=HypothesisStatus.UNVERIFIED, evidence_refs=[ev.id], source=source, record_refs=refs))
        else:
            prediction = {key: item.get(key) for key in ("target", "value", "model_version_id", "confidence")}
            ev = Evidence(evidence_type="prediction_output", source=source, record_refs=refs,
                          observed_at=timestamp, facts={key: value for key, value in prediction.items() if value is not None})
            evidence.append(ev)
            if refs:
                hypotheses.append(Hypothesis(statement=f"Prediction for {prediction.get('target') or 'an outcome'} warrants review; prediction is not an observed cause.",
                    status=HypothesisStatus.UNVERIFIED, evidence_refs=[ev.id], source=source, record_refs=refs))
    if not evidence:
        raise ValueError("At least one anomaly or prediction is required")
    times = [item.observed_at for item in evidence]
    incident = Incident(title=title or "Supply-chain risk finding", description="Incident assembled from stored anomaly and prediction outputs; neither establishes a cause.",
        source=source, record_refs=record_refs, occurred_at=min(times),
        evidence_refs=[item.id for item in evidence], hypothesis_refs=[item.id for item in hypotheses])
    return {"incident": incident, "evidence": evidence, "hypotheses": hypotheses,
            "limitations": ["Predictions and anomalies are distinct from observed facts.",
                            "Any proposed explanation remains UNVERIFIED until reviewed."]}
