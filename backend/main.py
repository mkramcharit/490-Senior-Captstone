# backend/main.py

from fastapi import FastAPI, UploadFile, File, HTTPException
from PIL import Image
from io import BytesIO

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

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "prediction": "placeholder"
    }


