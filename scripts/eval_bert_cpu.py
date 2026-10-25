"""Evaluate the saved BERT review classifier on the baseline's chronological holdout."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
import zipfile

# Make direct `python scripts/eval_bert_cpu.py` execution resolve project modules.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.loaders import find_archive
from src.nlp.baseline import build_review_frame, chronological_split


LABELS = ["complaint", "neutral", "positive"]


def review_input_sha256(source: Path) -> str:
    """Hash raw review CSV bytes, streaming the review member when source is a ZIP."""
    if source.suffix.lower() != ".zip":
        return hashlib.sha256(source.read_bytes()).hexdigest()
    with zipfile.ZipFile(source) as archive:
        matches = [name for name in archive.namelist() if Path(name).name == "olist_order_reviews_dataset.csv"]
        if len(matches) != 1:
            raise FileNotFoundError("Expected one Olist review CSV member in ZIP")
        digest = hashlib.sha256()
        with archive.open(matches[0]) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def classification_metrics(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    """Return exact per-class, macro-F1 and confusion counts for the fixed label order."""
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, y_pred, labels=LABELS, zero_division=0)
    return {
        "per_class": {
            label: {"precision": float(p), "recall": float(r), "f1": float(f), "support": int(n)}
            for label, p, r, f, n in zip(LABELS, precision, recall, f1, support)
        },
        "macro_precision": float(precision.mean()),
        "macro_recall": float(recall.mean()),
        "macro_f1": float(f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "confusion_matrix_labels_complaint_neutral_positive": confusion_matrix(
            y_true, y_pred, labels=LABELS).tolist(),
    }


def evaluate(archive: Path, model_dir: Path, output: Path, *, batch_size: int = 16,
             max_length: int = 256, reference_metrics_path: Path | None = None,
             reference_config_path: Path | None = None) -> dict[str, Any]:
    """Run CPU-only batched inference on the final 20% chronological holdout."""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    frame = build_review_frame(archive)
    train, validation, test = chronological_split(frame)
    split_rows = {"train": len(train), "validation": len(validation), "test": len(test)}
    reference = None
    if reference_metrics_path and reference_metrics_path.is_file():
        reference = json.loads(reference_metrics_path.read_text(encoding="utf-8"))
        expected_rows = reference.get("rows", {})
        if expected_rows != split_rows:
            result = {"status": "SPLIT_MISMATCH", "reproduced_rows": split_rows,
                      "reference_rows": expected_rows,
                      "message": "BERT evaluation was not run because chronological split row counts differ."}
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result
    if reference_config_path and reference_config_path.is_file():
        config = json.loads(reference_config_path.read_text(encoding="utf-8"))
        expected_hash = config.get("input_sha256")
        if expected_hash and expected_hash != review_input_sha256(archive):
            result = {"status": "INPUT_HASH_MISMATCH", "reproduced_rows": split_rows,
                      "reference_rows": reference.get("rows", {}) if reference else {},
                      "message": "BERT evaluation was not run because the Olist review CSV hash differs."}
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result
    # Explicitly retain the split counts while passing only test text to the model.
    model_config_path = model_dir / "config.json"
    if not model_config_path.is_file():
        raise FileNotFoundError(f"Model config missing: {model_config_path}")
    saved_config = json.loads(model_config_path.read_text(encoding="utf-8"))
    label2id = {str(key): int(value) for key, value in saved_config.get("label2id", {}).items()}
    if set(label2id) != set(LABELS):
        raise ValueError(f"Model labels {sorted(label2id)} do not match docs/LABELS.md bands {LABELS}")
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True).to("cpu")
    model.eval()
    id2label = {int(key): str(value) for key, value in model.config.id2label.items()}

    predicted: list[str] = []
    texts = test["text"].astype(str).tolist()
    torch.set_grad_enabled(False)
    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start:start + batch_size]
        tokens = tokenizer(batch_texts, return_tensors="pt", padding=True,
                           truncation=True, max_length=max_length)
        with torch.inference_mode():
            logits = model(**tokens).logits
        predicted.extend(id2label[int(index)] for index in logits.argmax(dim=1).tolist())

    result = {
        "status": "COMPUTED",
        "dataset": "Olist reviews",
        "label_definition": "review_score 1-2 complaint, 3 neutral, 4-5 positive (docs/LABELS.md)",
        "split": "same stable chronological 60/20/20 split as src.nlp.baseline",
        "rows": {"train": len(train), "validation": len(validation), "test": len(test), "holdout_evaluated": len(test)},
        "holdout_role": "final chronological test partition; training and validation rows were not evaluated",
        "sequence_length_used": max_length,
        "sequence_length_training_match": "256 is set in scripts/gpu/train_bertimbau.py",
        "inference_device": "cpu",
        "inference_batch_size": batch_size,
        "review_csv_sha256": review_input_sha256(archive),
        "label_order": LABELS,
        "metrics": classification_metrics(test["label"].astype(str).tolist(), predicted),
    }
    if reference:
        reference_test = reference.get("test_metrics", {})
        compared = {"accuracy": reference_test.get("test_accuracy"),
                    "macro_precision": reference_test.get("test_macro_precision"),
                    "macro_recall": reference_test.get("test_macro_recall"),
                    "macro_f1": reference_test.get("test_macro_f1")}
        actual = {"accuracy": result["metrics"]["accuracy"],
                  "macro_precision": result["metrics"]["macro_precision"],
                  "macro_recall": result["metrics"]["macro_recall"],
                  "macro_f1": result["metrics"]["macro_f1"]}
        result["colab_reference_metrics"] = compared
        result["difference_cpu_minus_colab"] = {
            key: actual[key] - value if value is not None else None for key, value in compared.items()
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-length", type=int, default=256)
    args = parser.parse_args()
    root = args.root
    archive = args.archive or find_archive("olist", root)
    model_dir = args.model_dir or root / "models" / "bertimbau" / "model"
    output = args.output or root / "models" / "bertimbau" / "eval_metrics.json"
    reference_path = root / "models" / "bertimbau" / "metrics.json"
    config_path = root / "models" / "bertimbau" / "config.json"
    result = evaluate(archive, model_dir, output, batch_size=args.batch_size,
                      max_length=args.max_length, reference_metrics_path=reference_path,
                      reference_config_path=config_path)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
