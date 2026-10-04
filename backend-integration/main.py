# backend-integration/main.py

"""
TREKMARK BACKEND - main.py

This is the FastAPI implementation for Trekmark.

The entire system chain for the 60% checkpoint is as follows:

Frontend image upload
        ↓
FastAPI /api/predict
        ↓
Simulated ML prediction
        ↓
Real landmark_id
        ↓
Real lookup in Neon database
        ↓
Real landmark information
        ↓
JSON response
        ↓
React updates

The only simulated piece is the ML identification of the image.

When the production DINOv2 + FAISS implementation is available
this simulated piece can be swapped out without affecting the
database or the frontend.
"""

import os
from io import BytesIO

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from database import check_database_connection, get_landmark


# ENVIRONMENT CONFIGURATION


load_dotenv()

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

DEMO_LANDMARK_ID = int(
    os.getenv("DEMO_LANDMARK_ID", "104169")
)

DEMO_CONFIDENCE = float(
    os.getenv("DEMO_CONFIDENCE", "0.94")
)


# FASTAPI APPLICATION


app = FastAPI(
    title="Trekmark API",
    description="Backend API for Trekmark landmark recognition and trip planning.",
    version="0.6.0",
)


# CORS

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ROOT

@app.get("/")
def root():
    return {
        "application": "Trekmark API",
        "status": "running",
        "demo_mode": DEMO_MODE,
    }


# HEALTH CHECK


@app.get("/api/health")
def health_check():
    try:
        check_database_connection()

        return {
            "api": "ok",
            "database": "ok",
            "demo_mode": DEMO_MODE,
        }

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Database connection failed: {error}",
        )


# DIRECT LANDMARK LOOKUP


@app.get("/api/landmark/{landmark_id}")
def landmark_lookup(landmark_id: int):
    landmark = get_landmark(landmark_id)

    if landmark is None:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in Neon.",
        )

    return dict(landmark)


# PREDICTION ENDPOINT

@app.post("/api/predict")
async def predict_landmark(
    file: UploadFile = File(...)
):
    # Validate uploaded image as an image
    if (
        not file.content_type
        or not file.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be an image.",
        )

    # Read uploaded image
    contents = await file.read()

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty.",
        )

    # Check image bytes
    try:
        image = Image.open(BytesIO(contents))
        image.verify()

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid image.",
        )

    # 60% checkpoint - temporary ML prediction
    if DEMO_MODE:
        landmark_id = DEMO_LANDMARK_ID
        confidence = DEMO_CONFIDENCE
        recognition_mode = "demo"

    else:
        raise HTTPException(
            status_code=503,
            detail="Production landmark recognition is not available yet.",
        )

    # Real lookup in Neon
    landmark = get_landmark(landmark_id)

    if landmark is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Prediction returned landmark_id {landmark_id}, "
                "but that landmark does not exist in Neon."
            ),
        )

    display_name = (
        landmark["name"]
        or landmark["category_name"]
        or f"Landmark {landmark_id}"
    )

    return {
        "landmark": {
            "id": landmark_id,
            "name": display_name,
            "category_name": landmark["category_name"],
            "city": landmark["city"],
            "state": landmark["state"],
            "country": landmark["country"],
            "latitude": landmark["lat"],
            "longitude": landmark["lon"],
            "image": landmark["url"],
        },

        "confidence": confidence,

        "recognition_mode": recognition_mode,

        "nearby_landmarks": [],

        "trip_suggestions": {
            "flights": [],
            "hotels": [],
            "restaurants": [],
            "best_time_to_visit": None,
        },
    }