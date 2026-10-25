"""Historical incident retrieval; similar text is context, never proof."""
from pathlib import Path
from typing import Any
import json

import numpy as np


def _read_record_file(path: Path) -> list[dict[str, Any]]:
    """Read JSONL records or the review-ID arrays emitted by the embedding job."""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []
    if path.suffix.lower() == ".json":
        values = json.loads(content)
        if not isinstance(values, list):
            raise ValueError(f"Expected a JSON list in {path}")
        records = []
        for value in values:
            if isinstance(value, dict):
                records.append(value)
            else:
                # Colab output stores review IDs, not source text. Do not invent text.
                records.append({"text": None, "source_record_ids": [str(value)], "text_available": False})
        return records
    return [json.loads(line) for line in content.splitlines() if line.strip()]


def _load_embedding_directory(directory: Path) -> tuple[list[dict[str, Any]], np.ndarray] | None:
    """Load matching chunk/record pairs from models/embeddings."""
    chunks = sorted(directory.glob("embeddings_*.npz"))
    if not chunks:
        return None
    records: list[dict[str, Any]] = []
    matrices: list[np.ndarray] = []
    for chunk_path in chunks:
        record_path = directory / chunk_path.name.replace("embeddings_", "records_").replace(".npz", ".json")
        if not record_path.is_file():
            return None
        chunk_records = _read_record_file(record_path)
        with np.load(chunk_path, allow_pickle=False) as chunk:
            matrix = chunk["embeddings"]
        if matrix.ndim != 2 or matrix.shape[0] != len(chunk_records):
            raise ValueError(f"Embedding and source record dimensions do not match for {chunk_path.name}")
        records.extend(chunk_records)
        matrices.append(matrix)
    return records, np.concatenate(matrices, axis=0)


def search_incidents(query_embedding: list[float], *, records_path: Path | str = "models/embeddings",
                     embeddings_path: Path | str | None = None, top_k: int = 5) -> dict[str, Any]:
    """Cosine-search stored embeddings and return citations to source record IDs.

    With defaults, loads chunked embedding artifacts from ``models/embeddings``.
    Similarity is retrieval context and does not establish evidence or causation.
    """
    records_file = Path(records_path)
    if embeddings_path is None and records_file.is_dir():
        loaded = _load_embedding_directory(records_file)
        if loaded is None:
            return {"status": "Insufficient evidence", "results": [],
                    "reason": "Stored embedding chunks or matching records are missing."}
        records, matrix = loaded
    else:
        embedding_file = Path(embeddings_path) if embeddings_path is not None else Path()
        if not records_file.is_file() or not embedding_file.is_file():
            return {"status": "Insufficient evidence", "results": [],
                    "reason": "Stored incident text or embeddings are missing; no retrieval results were generated."}
        records = _read_record_file(records_file)
        matrix = np.load(embedding_file, allow_pickle=False)
    query = np.asarray(query_embedding, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != len(records) or matrix.shape[1] != query.size:
        raise ValueError("Embedding matrix and source record dimensions do not match")
    denominator = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query)
    similarities = np.divide(matrix @ query, denominator, out=np.zeros(len(records)), where=denominator != 0)
    indices = np.argsort(similarities)[::-1][:max(0, top_k)]
    text_available = all(records[index].get("text") is not None for index in indices)
    note = "Retrieved text is context, not proof."
    if not text_available:
        note += " The stored embedding records include IDs but not source text."
    return {"status": "RETRIEVED", "note": note,
            "results": [{"similarity": float(similarities[index]),
                         "text": records[index].get("text"),
                         "source_record_ids": records[index].get("source_record_ids", [])} for index in indices]}
