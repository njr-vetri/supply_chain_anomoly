"""Optional chunked sentence embedding generator with resumable chunk files."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from src.nlp.baseline import build_review_frame


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-path", type=Path, required=True, help="Olist ZIP archive or review CSV")
    parser.add_argument("--output-path", type=Path, required=True, help="Local, Drive, or Kaggle output folder")
    parser.add_argument("--model-name", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--chunk-size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    args.output_path.mkdir(parents=True, exist_ok=True)
    frame = build_review_frame(args.data_path).reset_index(drop=True)
    model = SentenceTransformer(args.model_name, device=device)
    if device == "cuda":
        model.half()
    saved_rows = 0
    chunk_count = 0
    for start in range(0, len(frame), args.chunk_size):
        end = min(start + args.chunk_size, len(frame))
        chunk_path = args.output_path / f"embeddings_{start:09d}_{end:09d}.npz"
        ids_path = args.output_path / f"records_{start:09d}_{end:09d}.json"
        if chunk_path.exists() and ids_path.exists():
            saved_rows += end - start
            chunk_count += 1
            continue
        vectors = model.encode(frame.loc[start:end - 1, "text"].tolist(), batch_size=args.batch_size,
                               convert_to_numpy=True, show_progress_bar=False)
        np.savez_compressed(chunk_path, embeddings=vectors.astype(np.float32))
        ids_path.write_text(json.dumps(frame.loc[start:end - 1, "review_id"].astype(str).tolist()), encoding="utf-8")
        saved_rows += end - start
        chunk_count += 1
    config = {"model_name": args.model_name, "device": device, "fp16": device == "cuda",
              "batch_size": args.batch_size, "chunk_size": args.chunk_size, "seed": args.seed,
              "input_path": str(args.data_path), "input_sha256": hashlib.sha256(args.data_path.read_bytes()).hexdigest(),
              "output_path": str(args.output_path),
              "resume": "existing complete chunk files are skipped"}
    result = {"rows_embedded_or_resumed": saved_rows, "chunks": chunk_count,
              "note": "Embedding counts are processing metadata, not model quality metrics."}
    (args.output_path / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    (args.output_path / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
