"""Synthetic-only unit tests; these fixtures do not represent real dataset results."""
import json
import zipfile

import numpy as np
import pandas as pd

from src.nlp.baseline import LABEL_MAP, REVIEW_LABELS, build_review_frame, classification_summary
from src.nlp.inference import predict_reviews
from src.nlp.text import process_review
from src.risk.retrieval import search_incidents
from scripts.eval_bert_cpu import classification_metrics


def test_synthetic_review_text_cleaning_and_extraction():
    result = process_review("Entrega boa em 2024-05-01, 2 unidades. contato a@b.com +1 555 123 4567")
    assert "a@b.com" not in result["clean_text"]
    assert "[REDACTED_EMAIL]" in result["clean_text"]
    assert "2024-05-01" in result["dates"]
    assert "2 unidades" in result["quantities"]
    assert result["language"] == "pt"
    assert result["text_is_untrusted"] is True
    assert result["action_triggered"] is False


def test_review_score_bands_are_data_derived():
    assert LABEL_MAP == {1: "complaint", 2: "complaint", 3: "neutral", 4: "positive", 5: "positive"}
    assert REVIEW_LABELS == ["complaint", "neutral", "positive"]


def test_synthetic_review_metrics_average_each_label_band_once():
    result = classification_summary(
        ["complaint", "neutral", "positive"], ["complaint", "complaint", "positive"])
    assert result["per_class"]["neutral"]["support"] == 1
    assert len(result["confusion_matrix"]) == 3
    assert abs(result["macro_f1"] - (5 / 9)) < 1e-12


def test_synthetic_zip_loader_preserves_review_id(tmp_path):
    archive_path = tmp_path / "synthetic_olist.zip"
    frame = pd.DataFrame([{
        "review_id": "synthetic-review-1", "review_score": 1,
        "review_creation_date": "2018-01-01 00:00:00", "review_comment_title": "Atraso",
        "review_comment_message": "Pedido atrasado", "order_id": "synthetic-order-1",
    }])
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("olist_order_reviews_dataset.csv", frame.to_csv(index=False))
    loaded = build_review_frame(archive_path)
    assert loaded.iloc[0]["review_id"] == "synthetic-review-1"
    assert loaded.iloc[0]["label"] == "complaint"


def test_missing_models_do_not_fabricate_predictions(tmp_path):
    result = predict_reviews(["synthetic review text"], tmp_path)
    assert result["status"] == "MODEL_MISSING"
    assert result["predictions"] == []


def test_synthetic_retrieval_returns_citations_and_context_note(tmp_path):
    records = tmp_path / "records.jsonl"
    embeddings = tmp_path / "embeddings.npy"
    records.write_text(json.dumps({"text": "synthetic evidence", "source_record_ids": ["synthetic-record-1"]}) + "\n")
    np.save(embeddings, np.asarray([[1.0, 0.0]], dtype=np.float32))
    result = search_incidents([1.0, 0.0], records_path=records, embeddings_path=embeddings)
    assert result["note"] == "Retrieved text is context, not proof."
    assert result["results"][0]["source_record_ids"] == ["synthetic-record-1"]


def test_missing_retrieval_artifacts_are_insufficient_evidence(tmp_path):
    result = search_incidents([1.0], records_path=tmp_path / "absent.jsonl", embeddings_path=tmp_path / "absent.npy")
    assert result["status"] == "Insufficient evidence"
    assert result["results"] == []


def test_synthetic_chunked_review_index_loads_ids_without_fabricating_text(tmp_path):
    np.savez_compressed(tmp_path / "embeddings_000000000_000000001.npz",
                        embeddings=np.asarray([[1.0, 0.0]], dtype=np.float32))
    (tmp_path / "records_000000000_000000001.json").write_text(
        json.dumps(["synthetic-review-7"]), encoding="utf-8")
    result = search_incidents([1.0, 0.0], records_path=tmp_path)
    assert result["status"] == "RETRIEVED"
    assert result["results"][0]["source_record_ids"] == ["synthetic-review-7"]
    assert result["results"][0]["text"] is None
    assert "IDs but not source text" in result["note"]


def test_synthetic_bert_metric_summary_uses_fixed_label_order():
    truth = ["complaint", "neutral", "positive"]
    result = classification_metrics(truth, truth)
    assert result["macro_f1"] == 1.0
    assert result["per_class"]["neutral"]["support"] == 1
    assert result["confusion_matrix_labels_complaint_neutral_positive"] == [
        [1, 0, 0], [0, 1, 0], [0, 0, 1]
    ]
