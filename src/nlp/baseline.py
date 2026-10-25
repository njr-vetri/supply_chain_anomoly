"""CPU TF-IDF + Logistic Regression baseline for Olist review-score bands."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
import zipfile

import pandas as pd

from src.nlp.text import process_review


LABEL_MAP = {1: "complaint", 2: "complaint", 3: "neutral", 4: "positive", 5: "positive"}
REVIEW_LABELS = ["complaint", "neutral", "positive"]


def classification_summary(y_true: Any, predicted: Any) -> dict[str, Any]:
    """Metrics over each unique documented review-score band exactly once."""
    from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, predicted, labels=REVIEW_LABELS, zero_division=0)
    return {"macro_precision": float(precision.mean()), "macro_recall": float(recall.mean()),
            "macro_f1": float(f1.mean()), "accuracy": float(accuracy_score(y_true, predicted)),
            "per_class": {label: {"precision": float(p), "recall": float(r), "f1": float(f),
                                   "support": int(s)}
                          for label, p, r, f, s in zip(REVIEW_LABELS, precision, recall, f1, support)},
            "confusion_matrix": confusion_matrix(y_true, predicted, labels=REVIEW_LABELS).tolist()}


def build_review_frame(archive_path: Path | str) -> pd.DataFrame:
    """Read an Olist review CSV directly from a ZIP or a supplied CSV file."""
    source = Path(archive_path)
    if source.suffix.lower() == ".csv":
        frame = pd.read_csv(source)
    else:
        with zipfile.ZipFile(source) as archive:
            names = [name for name in archive.namelist() if Path(name).name == "olist_order_reviews_dataset.csv"]
            if len(names) != 1:
                raise FileNotFoundError("Expected one Olist review CSV in archive")
            with archive.open(names[0]) as stream:
                frame = pd.read_csv(stream)
    frame["text"] = (frame["review_comment_title"].fillna("").astype(str) + " " +
                     frame["review_comment_message"].fillna("").astype(str)).map(
                         lambda text: process_review(text)["clean_text"])
    frame["label"] = pd.to_numeric(frame["review_score"], errors="coerce").map(LABEL_MAP)
    frame["timestamp"] = pd.to_datetime(frame["review_creation_date"], errors="coerce", utc=True)
    return frame.loc[frame["label"].notna() & frame["timestamp"].notna() & frame["text"].str.strip().ne("")].copy()


def chronological_split(frame: pd.DataFrame, train_fraction: float = 0.6, validation_fraction: float = 0.2):
    frame = frame.sort_values("timestamp", kind="stable")
    train_end = int(len(frame) * train_fraction)
    val_end = train_end + int(len(frame) * validation_fraction)
    return frame.iloc[:train_end], frame.iloc[train_end:val_end], frame.iloc[val_end:]


def run(archive_path: Path | str, output_dir: Path | str, seed: int = 42) -> dict[str, Any]:
    """Train baseline, compare to majority class, and save only computed metrics."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    archive_path = Path(archive_path)
    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    config = {"dataset": "Olist reviews only", "seed": seed, "label_map": LABEL_MAP,
              "split": "chronological 60/20/20 by review_creation_date", "model": "TF-IDF word 1-2 grams + LogisticRegression"}
    frame = build_review_frame(archive_path)
    try:
        from sklearn.dummy import DummyClassifier
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import f1_score
        import joblib
    except ImportError as exc:
        result = {"status": f"NOT COMPUTED: dependency unavailable: {exc}", "dataset": "Olist reviews",
                  "metrics": None, "rows_loaded": len(frame),
                  "label_counts": {str(key): int(value) for key, value in frame["label"].value_counts().items()},
                  "data_sha256": archive_hash}
        (output / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        (output / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        return result
    train, validation, test = chronological_split(frame)
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=50000, min_df=2, sublinear_tf=True)
    x_train = vectorizer.fit_transform(train["text"])
    x_val, x_test = vectorizer.transform(validation["text"]), vectorizer.transform(test["text"])
    y_train, y_val, y_test = train["label"], validation["label"], test["label"]
    classifier = LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced")
    classifier.fit(x_train, y_train)
    majority = DummyClassifier(strategy="most_frequent").fit(x_train, y_train)
    metrics = {}
    for name, model in (("majority_baseline", majority), ("tfidf_logistic_regression", classifier)):
        predicted = model.predict(x_test)
        metrics[name] = classification_summary(y_test, predicted)
    result = {"status": "COMPUTED", "dataset": "Olist reviews only", "data_sha256": archive_hash,
              "rows": {"train": len(train), "validation": len(validation), "test": len(test)},
              "metrics": metrics, "validation_macro_f1": float(f1_score(y_val, classifier.predict(x_val), average="macro")),
              "limitations": ["Labels are review-score bands, not human-verified complaint causes or sentiment annotation.",
                              "Chronological holdout is an evaluation, not a guarantee of future performance."]}
    joblib.dump({"vectorizer": vectorizer, "classifier": classifier, "labels": LABEL_MAP}, output / "olist_tfidf_baseline.joblib")
    (output / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (output / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("models/nlp"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    result = run(args.archive, args.output, args.seed)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
