"""One upload -> ML prediction -> PostgreSQL landmark lookup."""
from functools import lru_cache
from io import BytesIO
import logging
import math
import os
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
app = FastAPI(title="Trekmark")
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
prediction_lock = Lock()


def configured_path(key, default):
    path = Path(os.getenv(key, default))
    return path if path.is_absolute() else ROOT / path


@lru_cache(maxsize=1)
def get_pipeline():
    directory = configured_path("LANDMARK_INDEX_PATH", "artifacts/landmarks")
    if not all((directory / name).is_file() for name in ("images.faiss", "references.json")):
        raise HTTPException(503, "Recognition data unavailable. The landmark reference index must be supplied before images can be identified.")
    from landmark_ml import LandmarkPipeline
    return LandmarkPipeline.load(directory, configured_path("LANDMARK_MODEL_PATH", "dinov2-small"))


def lookup_landmark(landmark_id):
    url = os.getenv("DATABASE_URL")
    if not url:
        raise HTTPException(503, "Database connection is not configured.")
    # Only the predicted ID selects the landmark; user input never becomes SQL.
    with psycopg.connect(url, connect_timeout=10, row_factory=dict_row) as conn:
        conn.execute("SET LOCAL statement_timeout = 10000")
        return conn.execute("""
            SELECT landmark_id, name, category_name, lat, lon, city, state, country
            FROM public.training_data WHERE landmark_id = %s
            ORDER BY (name IS NULL), id LIMIT 1
        """, (landmark_id,)).fetchone()


@app.post("/api/predict")
def predict(image: UploadFile = File(...)):
    try:
        contents = image.file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        image.file.close()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Choose an image smaller than 10 MB.")
    try:
        with Image.open(BytesIO(contents)) as uploaded:
            if uploaded.width * uploaded.height > 25_000_000:
                raise HTTPException(413, "Choose an image with at most 25 million pixels.")
            uploaded.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise HTTPException(422, "The uploaded file is not a readable image.") from None
    try:
        with prediction_lock:
            prediction = get_pipeline().predict(contents)
        raw_id = prediction["landmark_id"]
        if isinstance(raw_id, bool) or not isinstance(raw_id, (int, str)):
            raise ValueError("Invalid landmark ID")
        landmark_id = int(raw_id)
        confidence = float(prediction["confidence"])
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Invalid confidence")
        probability = prediction.get("confidence_probability")
        if probability is not None:
            probability = float(probability)
            if not math.isfinite(probability) or not 0 <= probability <= 1:
                raise ValueError("Invalid calibrated probability")
        landmark = lookup_landmark(landmark_id)
    except HTTPException:
        raise
    except psycopg.Error:
        logger.warning("Landmark database lookup failed")
        raise HTTPException(503, "The landmark database is unavailable. Please try again.") from None
    except Exception:
        logger.warning("Landmark recognition failed")
        raise HTTPException(503, "Recognition could not complete. Check the model and reference index configuration.") from None
    if landmark is None:
        raise HTTPException(404, "The predicted landmark has no matching database record.")
    return {"landmark_id": landmark_id, "confidence": confidence,
            "match_score": confidence, "confidence_probability": probability,
            "confidence_calibrated": probability is not None,
            "probability_description": "Estimated probability of a correct landmark ID for data comparable to the calibration set; requires independent validation." if probability is not None else "No compatible calibrator installed.",
            "confidence_description": "Similarity and reference agreement score; not a calibrated probability.",
            "landmark": landmark}


# A built frontend and API can run from the same server; Vite proxies during development.
if (ROOT / "frontend/dist").is_dir():
    app.mount("/", StaticFiles(directory=ROOT / "frontend/dist", html=True), name="frontend")
