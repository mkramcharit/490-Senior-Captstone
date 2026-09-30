from io import BytesIO
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import psycopg
from backend import app as api

@pytest.fixture
def client():
    return TestClient(api.app)

@pytest.fixture
def photo():
    output = BytesIO()
    Image.new("RGB", (16, 16), "red").save(output, format="PNG")
    return output.getvalue()

def test_upload_predicts_then_looks_up_same_id(client, photo, monkeypatch):
    seen = []
    def predict(data):
        assert data == photo
        seen.append("predict")
        return {"landmark_id": "42", "confidence": .87}
    def lookup(key):
        seen.append(key)
        return {"landmark_id": key, "name": "Test landmark", "lat": 0}
    monkeypatch.setattr(api, "get_pipeline", lambda: SimpleNamespace(predict=predict))
    monkeypatch.setattr(api, "lookup_landmark", lookup)
    response = client.post("/api/predict", files={"image": ("image.png", photo, "image/png")})
    assert response.status_code == 200
    assert response.json()["confidence"] == .87
    assert response.json()["landmark"]["name"] == "Test landmark"
    assert seen == ["predict", 42]

def test_invalid_image(client):
    assert client.post("/api/predict", files={"image": ("x.png", b"bad")}).status_code == 422

def test_large_upload(client, photo, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 1)
    assert client.post("/api/predict", files={"image": ("x.png", photo)}).status_code == 413

def test_missing_index(client, photo, monkeypatch, tmp_path):
    api.get_pipeline.cache_clear()
    monkeypatch.setenv("LANDMARK_INDEX_PATH", str(tmp_path))
    response = client.post("/api/predict", files={"image": ("x.png", photo)})
    assert response.status_code == 503
    assert "Recognition data unavailable" in response.json()["detail"]

@pytest.mark.parametrize("failure,expected", [(None, 404), ("database", 503)])
def test_lookup_errors(client, photo, monkeypatch, failure, expected):
    monkeypatch.setattr(api, "get_pipeline", lambda: SimpleNamespace(predict=lambda _: {"landmark_id": 42, "confidence": .8}))
    def lookup(_):
        if failure:
            raise psycopg.OperationalError("private connection details")
        return None
    monkeypatch.setattr(api, "lookup_landmark", lookup)
    response = client.post("/api/predict", files={"image": ("x.png", photo)})
    assert response.status_code == expected
    assert "private" not in response.text
