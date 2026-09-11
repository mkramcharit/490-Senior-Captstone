# backend/main.py

from fastapi import FastAPI, UploadFile, File

app = FastAPI(title="Trekmark API")

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "prediction": "placeholder"
    }


