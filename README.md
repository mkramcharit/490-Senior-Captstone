# Trekmark image recognition

Selecting an image automatically posts it to `/api/predict`. The backend runs the existing DINOv2/FAISS pipeline, queries `public.training_data` using the predicted `landmark_id`, and returns landmark details plus the model confidence. React displays a table without requiring an ID, confidence entry, or a second submit action.

## Setup

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
cd frontend
npm install
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. The backend serves the built frontend. During frontend development, run `npm run dev` in `frontend` alongside the backend; Vite proxies `/api` requests to port 8000.

The root `.env` contains the private `DATABASE_URL` and is ignored by Git. `.env.example` documents configuration. Never put the database URL in frontend environment variables.

## Required recognition data

The DINOv2 weights alone cannot map images to landmark IDs. Supply the reference index from the ML/data component: `images.faiss` and `references.json` in `artifacts/landmarks`, or set `LANDMARK_INDEX_PATH` in `.env`. It must use this pipeline's format and matching model signature. Its IDs must correspond to `training_data.landmark_id`. The backend loads and caches it automatically on the first upload; restart after replacing it.

Alternatively, build it once from labeled reference images using a JSON array such as `[{"landmark_id": 42, "image_path": "photos/reference.jpg"}]`, with paths relative to the manifest:

```powershell
.\.venv\Scripts\python.exe -m landmark_ml build references.json artifacts/landmarks --model dinov2-small
```

The initial integration had no reference index. On October 1, 2026, a first real index was built locally from 15 Neon-labeled Wikimedia photos covering three landmarks. Missing index files still cause uploads to return a clear 503 message. The confidence is the existing model's similarity-times-agreement score, not a calibrated probability. The globe and travel planner retain their separate demo data.

## Collect and verify real reference data

Neon's `public.training_data` contains `id`, `url`, `landmark_id`, and landmark metadata. The collection tool reads these rows directly, preserves the real IDs and source URLs, validates downloaded image files, records SHA-256 hashes, and separates reference photos from held-out photos. It currently supports Wikimedia image URLs. Database labels can include interiors or nearby objects; review the photos before treating their labels as reliable.

Example for Stirling Castle (104169), Monza Cathedral (25719), and Mount Vernon (73107):

```powershell
.\.venv\Scripts\python.exe scripts/collect_images.py artifacts/reference-data-v3 --landmark-ids 104169 25719 73107
.\.venv\Scripts\python.exe -m landmark_ml build artifacts/reference-data-v3/manifest.json artifacts/landmarks-v3 --model dinov2-small
$env:LANDMARK_INDEX_PATH = 'artifacts/landmarks-v3'
.\.venv\Scripts\python.exe scripts/verify_recognition.py artifacts/reference-data-v3/holdouts.json artifacts/recognition-report-v3.json
```

The first command requires network access to Neon and Wikimedia. It downloads standard 960-pixel thumbnails, pauses on rate limits, and requests five reference photos and two held-out photos per landmark; unavailable URLs are recorded in `download_failures.json`. Partial collections are saved and reported as incomplete. Both collection and index commands require a new output directory. The verification command uses the real API endpoint, model, index, and database lookup, rejects exact reference-image overlap, writes each response and expected ID to the report, and exits unsuccessfully if any held-out prediction fails. It verifies API behavior; browser upload/rendering still needs a separate check.

The completed local collection is `artifacts/reference-data-v2`: five references per landmark and five held-out photos total (two Stirling Castle, one Monza Cathedral, two Mount Vernon). The working index is `artifacts/landmarks/images.faiss` plus `references.json`. Evaluation through the real API and Neon returned HTTP 200 for all five uploads and the correct ID for three of five: both Stirling Castle photos and one Mount Vernon photo. The Monza garden photo and Mount Vernon detail photo were misidentified. These broad category labels include grounds and objects; this is an initial working index, not production-quality recognition or coverage of every landmark.

Tracked provenance manifests, download failures, and the full evaluation report are in `docs/reference-data/`. Local `artifacts/trekmark-reference-index-v1.zip` contains the index, photos, manifests, contact sheet, and report for sharing with teammates. Extract it into `artifacts/` to restore the default index location. The DINOv2 weights must match the saved index signature. Restart the backend after installing or replacing the index.

`artifacts/` is ignored by Git. Share the collection and built index separately, or provide a download location, so teammates can reproduce the same result. The index metadata currently stores absolute reference paths, so preserve the collection locally when rerunning the overlap verification.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

API tests cover upload-to-prediction-to-ID-lookup orchestration, invalid/large files, missing reference data, missing landmark records, and database outages. These use a fake predictor and lookup; live database connectivity is verified separately.
