"""Load trained Olist review classifier or its CPU TF-IDF baseline without fabricating outputs."""
from pathlib import Path
from typing import Any

from src.nlp.text import process_review


def predict_reviews(texts: list[str], models_dir: Path | str = "models") -> dict[str, Any]:
    root = Path(models_dir)
    hf_candidates = [root / "bertimbau" / "model", root / "nlp" / "bertimbau" / "model"]
    hf_model_dir = next((path for path in hf_candidates if path.is_dir()), None)
    if hf_model_dir is not None:
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            device = "cuda" if torch.cuda.is_available() else "cpu"
            tokenizer = AutoTokenizer.from_pretrained(hf_model_dir)
            model = AutoModelForSequenceClassification.from_pretrained(hf_model_dir).to(device)
            outputs = []
            for text in texts:
                processed = process_review(text)
                batch = tokenizer(processed["clean_text"], return_tensors="pt", truncation=True, max_length=256)
                batch = {key: value.to(device) for key, value in batch.items()}
                with torch.no_grad():
                    logits = model(**batch).logits[0]
                    probabilities = torch.softmax(logits, dim=0).cpu().tolist()
                label_id = int(torch.argmax(logits).item())
                label = model.config.id2label.get(label_id, str(label_id))
                outputs.append({"label": str(label), "probabilities": probabilities,
                                "language": processed["language"], "dates": processed["dates"],
                                "quantities": processed["quantities"], "text_is_untrusted": True,
                                "action_triggered": False})
            return {"status": "PREDICTED", "model_type": "bertimbau", "model_path": str(hf_model_dir),
                    "predictions": outputs}
        except (ImportError, OSError, RuntimeError) as exc:
            hf_issue = str(exc)
    else:
        hf_issue = None
    candidates = [(root / "olist_review_model.joblib", "fine_tuned"),
                  (root / "nlp" / "olist_review_model.joblib", "fine_tuned"),
                  (root / "nlp" / "olist_tfidf_baseline.joblib", "tfidf_baseline"),
                  (root / "olist_tfidf_baseline.joblib", "tfidf_baseline")]
    artifact = next(((path, kind) for path, kind in candidates if path.is_file()), None)
    if artifact is None:
        return {"status": "MODEL_MISSING", "predictions": [],
                "message": "No trained review model or TF-IDF baseline artifact is available; no results were generated.",
                "model_issue": hf_issue}
    try:
        import joblib
    except ImportError as exc:
        return {"status": "DEPENDENCY_MISSING", "predictions": [], "message": str(exc)}
    path, kind = artifact
    payload = joblib.load(path)
    outputs = []
    for text in texts:
        processed = process_review(text)
        if kind == "tfidf_baseline":
            vector = payload["vectorizer"].transform([processed["clean_text"]])
            prediction = payload["classifier"].predict(vector)[0]
            probabilities = payload["classifier"].predict_proba(vector)[0].tolist()
        else:
            prediction = payload.predict([processed["clean_text"]])[0]
            probabilities = payload.predict_proba([processed["clean_text"]])[0].tolist() if hasattr(payload, "predict_proba") else None
        outputs.append({"label": str(prediction), "probabilities": probabilities,
                        "language": processed["language"], "dates": processed["dates"],
                        "quantities": processed["quantities"], "text_is_untrusted": True,
                        "action_triggered": False})
    return {"status": "PREDICTED", "model_type": kind, "model_path": str(path), "predictions": outputs}
