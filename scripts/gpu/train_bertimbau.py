"""Optional GPU fine-tuning script; CPU fallback remains available through src.nlp.baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import numpy as np

from src.nlp.baseline import build_review_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-path", type=Path, required=True, help="Olist ZIP archive or review CSV")
    parser.add_argument("--output-path", type=Path, required=True, help="Local, Drive, or Kaggle output folder")
    parser.add_argument("--model-name", default="neuralmind/bert-base-portuguese-cased")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import torch
    from datasets import Dataset
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer, Trainer,
                              TrainingArguments, set_seed)
    from sklearn.metrics import accuracy_score, precision_recall_fscore_support
    from transformers.trainer_utils import get_last_checkpoint

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    set_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    args.output_path.mkdir(parents=True, exist_ok=True)
    frame = build_review_frame(args.data_path)
    frame = frame.sort_values("timestamp", kind="stable")
    labels = {"complaint": 0, "neutral": 1, "positive": 2}
    frame["label_id"] = frame["label"].map(labels)
    train_end, val_end = int(len(frame) * 0.6), int(len(frame) * 0.8)
    parts = {"train": frame.iloc[:train_end], "validation": frame.iloc[train_end:val_end], "test": frame.iloc[val_end:]}
    tokenizer = AutoTokenizer.from_pretrained(args.model_name)

    def to_dataset(part):
        dataset = Dataset.from_pandas(part[["text", "label_id"]].rename(columns={"label_id": "labels"}), preserve_index=False)
        return dataset.map(lambda batch: tokenizer(batch["text"], truncation=True, max_length=256), batched=True)

    datasets = {name: to_dataset(part) for name, part in parts.items()}
    model = AutoModelForSequenceClassification.from_pretrained(args.model_name, num_labels=len(labels),
                                                                id2label={v: k for k, v in labels.items()}, label2id=labels)

    def metrics(prediction):
        logits, truth = prediction
        predicted = np.argmax(logits, axis=1)
        p, r, f, _ = precision_recall_fscore_support(truth, predicted, average="macro", zero_division=0)
        return {"accuracy": float(accuracy_score(truth, predicted)), "macro_precision": float(p),
                "macro_recall": float(r), "macro_f1": float(f)}

    training_args = TrainingArguments(output_dir=str(args.output_path / "checkpoints"),
        per_device_train_batch_size=args.batch_size, per_device_eval_batch_size=args.batch_size,
        num_train_epochs=args.epochs, seed=args.seed, data_seed=args.seed,
        eval_strategy="steps", save_strategy="steps", save_steps=args.save_steps,
        eval_steps=args.save_steps, save_total_limit=2, logging_steps=args.save_steps,
        fp16=(device == "cuda"), report_to=[], load_best_model_at_end=False)
    trainer = Trainer(model=model, args=training_args, train_dataset=datasets["train"],
                      eval_dataset=datasets["validation"], processing_class=tokenizer,
                      compute_metrics=metrics)
    checkpoint = get_last_checkpoint(str(args.output_path / "checkpoints"))
    train_result = trainer.train(resume_from_checkpoint=checkpoint)
    test_metrics = trainer.evaluate(datasets["test"], metric_key_prefix="test")
    model_dir = args.output_path / "model"
    trainer.save_model(str(model_dir))
    tokenizer.save_pretrained(str(model_dir))
    config = {"model_name": args.model_name, "device": device, "fp16": device == "cuda",
              "batch_size": args.batch_size, "epochs": args.epochs, "save_steps": args.save_steps,
              "seed": args.seed, "resume_checkpoint": checkpoint, "label_map": labels,
              "input_path": str(args.data_path), "input_sha256": hashlib.sha256(args.data_path.read_bytes()).hexdigest(),
              "output_path": str(args.output_path)}
    (args.output_path / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    metrics_result = {"train_metrics": train_result.metrics, "test_metrics": test_metrics,
                      "rows": {key: len(value) for key, value in parts.items()}, "model_path": str(model_dir)}
    (args.output_path / "metrics.json").write_text(json.dumps(metrics_result, indent=2, default=float), encoding="utf-8")
    print(json.dumps(metrics_result, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
