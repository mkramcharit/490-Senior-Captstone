# backend/main.py

import sys
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image
from io import BytesIO
from pydantic import BaseModel

from database import get_landmark
from landmark_ml import LandmarkPipeline

app = FastAPI(title="Trekmark API")

# ML pipeline
ML_INDEX_PATH = "PATH_TO_INDEX"
ML_MODEL_PATH = "PATH_TO_DINOV2_MODEL"

pipeline = LandmarkPipeline.load(
    ML_INDEX_PATH,
    model_path=ML_MODEL_PATH,
    device="cpu"
)

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

#temp add
@app.get("/landmark/{landmark_id}")
def landmark(landmark_id: int):

    result = get_landmark(landmark_id)

    if not result:
        return {
            "error": "Landmark not found",
            "landmark_id": landmark_id
        }

    return dict(result)
    # temp add

@app.post("/predict")
async def predict(file: UploadFile = File(...)):

    # Check that a file was actually provided
    if not file:
        raise HTTPException(
            status_code=400,
            detail="No file uploaded."
        )

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be an image."
        )

    contents = await file.read()

    # Checks that the file isn't empty
    if not contents:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty."
        )

    # API tries opening the file as an actual image
    try:
        image = Image.open(BytesIO(contents))
        image.verify()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid image."
        )

    
        # Run the actual ML prediction
    try:
        result = pipeline.predict(contents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(e)}"
        )

    landmark_id = result["landmark_id"]
    confidence = result["confidence"]

    # Get landmark information from Neon
    landmark_data = get_landmark(landmark_id)

    if not landmark_data:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in the database."
        )

        # Run the actual ML prediction
    try:
        result = pipeline.predict(contents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(e)}"
        )

    landmark_id = result["landmark_id"]
    confidence = result["confidence"]

    # Get landmark information from Neon
    landmark_data = get_landmark(landmark_id)

    if not landmark_data:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in the database."
        )

    try:
        result = pipeline.predict(contents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(e)}"
        )

    landmark_id = result["landmark_id"]
    confidence = result["confidence"]

    # Get landmark information from Neon
    landmark_data = get_landmark(landmark_id)

    if not landmark_data:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in the database."
        )

    try:
        result = pipeline.predict(contents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(e)}"
        )

    landmark_id = result["landmark_id"]
    confidence = result["confidence"]

    # Get landmark information from Neon
    landmark_data = get_landmark(landmark_id)

    if not landmark_data:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in the database."
        )

        # Run the actual ML prediction
    try:
        result = pipeline.predict(contents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(e)}"
        )

    landmark_id = result["landmark_id"]
    confidence = result["confidence"]

    # Get landmark information from Neon
    landmark_data = get_landmark(landmark_id)

    if not landmark_data:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in the database."
        )

    # Run the actual ML prediction
    try:
        result = pipeline.predict(contents)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"ML prediction failed: {str(e)}"
        )

    landmark_id = result["landmark_id"]
    confidence = result["confidence"]

    # Get landmark information from Neon
    landmark_data = get_landmark(landmark_id)

    if not landmark_data:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in the database."
        )

    try:
        result = pipeline.predict(contents)
    except Exception as e:
        raise HTTPException(
            status_code = 500,
            detail=f"ML prediction failed: {str(e)}"
        )
    landmark_id = result["landmark_id"]
    confidence = result["confidence"]

    landmark_data = get_landmark(landmark_id)

    if not landmark_data:
        raise HTTPException(
            status_code=404,
            detail=f"Landmark {landmark_id} was not found in the database."
        )

    return {
        "landmark": {
            "id": landmark_id,
            "name": landmark_data["name"],
            "city": landmark_data["city"],
            "country": landmark_data["country"],
            "latitude": landmark_data["lat"],
            "longitude": landmark_data["lon"],
            "image": landmark_data["url"]
        },
        "confidence": confidence,
        "nearby_landmarks": [],
        "trip_suggestions": {
            "flights": [],
            "hotels": [],
            "restaurants": [],
            "best_time_to_visit": None
        }
    }