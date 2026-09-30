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

No reference index was present during integration. Until one is supplied, uploads return a clear 503 message. No fabricated match is substituted. The confidence is the existing model's similarity-times-agreement score, not a calibrated probability. The globe and travel planner retain their separate demo data.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

API tests cover upload-to-prediction-to-ID-lookup orchestration, invalid/large files, missing reference data, missing landmark records, and database outages. These use a fake predictor and lookup; live database connectivity is verified separately.
