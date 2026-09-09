# backend/main.py

from fastapi import FastAPI

app = FastAPI(title="Trekmark API")

@app.get("/health")
def health_check():
    return {"status": "ok"}
