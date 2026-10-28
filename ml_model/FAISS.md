# FAISS setup and image recognition

Start by installing the ML package from the repo root:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

Set `DATABASE_URL` in the root `.env` file or your environment. The builder only reads `public.training_data`, so it won't change the schema or any rows.

## Build from Neon

To try a small build first, run this from the repo root:

```powershell
.\.venv\Scripts\python.exe scripts/index_neon.py artifacts/neon-pilot --limit 1000 --fetch-size 256 --batch-size 16 --workers 4
```

Remove `--limit 1000` when you're ready to process all eligible rows. To build for specific landmarks, add `--landmark-ids 104169 25719 73107`. The builder uses the CPU by default; add `--device cuda` to use a GPU if your PyTorch installation supports CUDA. Keep `DATABASE_URL` in your environment or `.env` file, rather than passing it on the command line.

The builder reads rows in `training_data.id` order, picking up after the last ID each time (keyset pagination). It handles one fetch batch and one image embedding batch at a time. IDs need to be unique and stable, and you should leave the source table unchanged while a build runs. If several images share a `landmark_id`, it keeps all of them.

DINOv2-small supplies its own embedding size: 384 dimensions. FAISS uses normalized inner-product search to keep the existing cosine-similarity behavior. The starter file's hardcoded 768 dimensions and L2 scoring aren't used.

After each successful embedding batch, the builder saves an ordered shard in `<output>.work`. Checkpoints track the last source row ID, counts, source URLs, and failures. Temporary network errors get up to three retries. Images that can't be read, are too large, or aren't available get logged and skipped, with the landmark mappings kept in sync. Downloads stay within bounded memory and aren't saved to disk.

You can trace rows through `sources.json`; references use IDs like `neon:<row-id>`. The existing calibration scripts need local reference photos and can't directly check those IDs. Keep those photos, or collect them again, before calibrating a new full index.

If the build stops partway through, run the same command again with `--resume`. Use the same database, model, and landmark selection. Rows already saved in checkpoints won't be downloaded again, and existing output directories won't be overwritten. Failed rows count as processed, so check the failure log and retry those separately. Resume ignores any pending directories left behind by the interruption.

When the build finishes, you'll get:

- `landmarks.index` and `landmark_ids.pkl`, as requested in `FAISS_Next_Steps.txt`
- `images.faiss` and `references.json` for the existing `LandmarkPipeline` loader
- `build.json` with counts, embedding dimension, and model signature

Both FAISS files hold the same vectors in the same order. Vector position `i` matches `landmark_ids.pkl[i]` and `references.json`'s `references[i]`. The pickle file is there for the handoff; the ML loader uses the JSON mapping. Only load pickle files made by this project that came from a trusted source.

The flat index keeps every embedding in RAM. A million 384-dimensional float32 vectors take about 1.54 GB by themselves. You'll also need memory for model weights, mappings, and export, plus disk space for checkpoint shards and both exported index files. The million-row build hasn't been completed or benchmarked as part of this work.

## Recognize an uploaded image

```python
from landmark_ml import recognize_image

landmark_id, confidence = recognize_image(uploaded_bytes)
```

You can pass image bytes, a PIL image, a binary file object, or a local image path. Set `LANDMARK_INDEX_PATH` and `LANDMARK_MODEL_PATH` to choose the bundle directory and local DINOv2 weights. Relative defaults start from the repo root. You can also pass `index_path`, `model_path`, `device`, and `top_k` directly. Once loaded, the pipeline is cached.

```python
landmark_id, confidence = recognize_image(
    uploaded_bytes,
    index_path="artifacts/neon-pilot",
    model_path="dinov2-small",
)
```

If you're using `LandmarkPipeline.predict()`, the response still includes `match_score`, `confidence_probability`, `confidence_calibrated`, `similarity`, `agreement`, and `top_matches`. The `confidence` field uses `confidence_probability` when compatible calibration is available; otherwise, it uses `match_score`. `recognize_image()` returns that same value.

Without calibration, confidence is just a matching score, not a validated probability. If your code needs to tell the difference, call `predict()` and check `confidence_calibrated`.

A new index starts out uncalibrated. Don't copy over the old 15-image calibrator: it only works with the exact index, labels, model, and `top_k` it was built for. You'll need fresh calibration and an independent evaluation. Also, the matcher always picks a landmark from the index, even if the uploaded image shows an unknown landmark.

## What's been built and checked

`artifacts/faiss-handoff-v1` contains the existing 15-reference demo index. It isn't the million-row production index. There's also a separate live Neon test in `artifacts/neon-smoke-1017`: eight rows processed, two successful embeddings, and six logged failures.

Git ignores these local artifacts, so you'll need to access them separately. The checkpoints include the source records and failure categories. Both mappings passed round-trip tests.