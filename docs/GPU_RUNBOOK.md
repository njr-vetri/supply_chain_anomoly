# Optional GPU runbook

The reproducible CPU baseline is TF-IDF plus Logistic Regression. GPU work is optional; use the CPU path if a GPU is unavailable. Never report metrics for a run that did not complete.

## Inputs and outputs

- Input: the original Olist ZIP containing `olist_order_reviews_dataset.csv`, or a prepared Olist review CSV with the original review columns (`review_id`, `review_score`, `review_creation_date`, `review_comment_title`, `review_comment_message`). The scripts read the ZIP member in memory and do not extract or alter the archive.
- Outputs: a `model/` directory for BERTimbau or chunked `embeddings_*.npz` plus `records_*.json` for embeddings; both runs also write `config.json` and `metrics.json` to the chosen output folder.
- Default model: `neuralmind/bert-base-portuguese-cased`. GPU embeddings use multilingual MiniLM. Default batch size is 8 and seed is 42. The scripts detect CUDA, use fp16 only on CUDA, and otherwise run on CPU.

## Google Colab T4

1. In Colab, select **Runtime → Change runtime type → T4 GPU**. Mount Drive and copy/clone this project into the runtime:

   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   %cd /content
   !git clone <YOUR_PROJECT_REPOSITORY_URL> supply-chain-risk-system
   %cd /content/supply-chain-risk-system
   !pip install -r requirements.txt -r requirements-gpu.txt
   ```

2. Put the authorized Olist ZIP in Drive, then train with output on Drive so checkpoints survive a session reset:

   ```bash
   python scripts/gpu/train_bertimbau.py \
     --data-path "/content/drive/MyDrive/datasets/archive (1).zip" \
     --output-path "/content/drive/MyDrive/supply-chain-risk/bertimbau" \
     --batch-size 8 --save-steps 100 --seed 42
   ```

3. Generate sentence embeddings in resumable chunks:

   ```bash
   python scripts/gpu/embed_reviews.py \
     --data-path "/content/drive/MyDrive/datasets/archive (1).zip" \
     --output-path "/content/drive/MyDrive/supply-chain-risk/olist-embeddings" \
     --batch-size 8 --chunk-size 1000 --seed 42
   ```

## Kaggle

1. Attach the Olist dataset as a notebook input. Enable **Settings → Accelerator → GPU T4** (or run on CPU if unavailable). Add the project files to the notebook or clone the authorized repository:

   ```bash
   %cd /kaggle/working
   !git clone <YOUR_PROJECT_REPOSITORY_URL> supply-chain-risk-system
   %cd /kaggle/working/supply-chain-risk-system
   !pip install -r requirements.txt -r requirements-gpu.txt
   ```

2. Replace the input path below with the exact ZIP path shown under `/kaggle/input/`:

   ```bash
   python scripts/gpu/train_bertimbau.py \
     --data-path "/kaggle/input/<dataset-folder>/archive (1).zip" \
     --output-path "/kaggle/working/bertimbau" --batch-size 8 --save-steps 100 --seed 42
   python scripts/gpu/embed_reviews.py \
     --data-path "/kaggle/input/<dataset-folder>/archive (1).zip" \
     --output-path "/kaggle/working/olist-embeddings" --batch-size 8 --chunk-size 1000 --seed 42
   ```

3. Download output folders from `/kaggle/working` before the notebook session expires. In Colab, Drive outputs are already persistent.

## Files to copy back

- For inference: copy the complete BERT output folder to `models/nlp/bertimbau/` so the model is at `models/nlp/bertimbau/model/`. Include the adjacent `config.json` and `metrics.json` for provenance. Keep checkpoints if training may need to resume.
- For retrieval/embedding experiments: copy all `embeddings_*.npz`, matching `records_*.json`, `config.json`, and `metrics.json` into a dedicated folder under `models/nlp/`. Do not treat review embeddings as incident evidence; retrieval results require explicit source record citations and are context, not proof.
- Model artifacts and outputs are local, ignored by Git, and must not be committed. Preserve the original dataset ZIP unchanged.
