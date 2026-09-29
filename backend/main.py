# backend/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image
from io import BytesIO
from pydantic import BaseModel

# temp add
from fastapi import Depends
from sqlalchemy.orm import Session

from database import get_db
from models import TrainingData
# temp add

app = FastAPI(title="Trekmark API")

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

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

    #temp add
@app.get("/landmark/{landmark_id}")
def get_landmark(landmark_id: int, db: Session = Depends(get_db)):
    landmark = (
        db.query(TrainingData)
        .filter(TrainingData.landmark_id == landmark_id)
        .first()
    )

    if not landmark:
        return {
            "error": "Landmark not found",
            "landmark_id": landmark_id
        }

    return {
        "id": landmark.id,
        "url": landmark.url,
        "landmark_id": landmark.landmark_id,
        "category_name": landmark.category_name,
        "name": landmark.name,
        "lat": landmark.lat,
        "lon": landmark.lon,
        "city": landmark.city,
        "state": landmark.state,
        "country": landmark.country
    }
    # temp add

    return {
        "landmark": {
            "id": 417,
            "name": "Eiffel Tower",
            "city": "Paris",
            "country": "France",
            "latitude": 48.8584,
            "longitude": 2.2945,
            "image": "https://..."
        },
        "confidence": 0.96,
        "nearby_landmarks": [],
        "trip_suggestions": {
            "flights": [],
            "hotels": [],
            "restaurants": [],
            "best_time_to_visit": None
        }
    }



