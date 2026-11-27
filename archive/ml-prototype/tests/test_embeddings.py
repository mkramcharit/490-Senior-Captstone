from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from landmark_ml import LandmarkPipeline, Reference
from landmark_ml.embeddings import read_image

def test_image_preprocessing():
    image = Image.new("L", (20, 10), 128)
    exif = image.getexif()
    exif[274] = 6
    stream = BytesIO()
    image.save(stream, format="JPEG", exif=exif)
    converted = read_image(stream.getvalue())
    assert converted.mode == "RGB"
    assert converted.size == (10, 20)
    assert read_image(Image.new("RGBA", (4, 4))).mode == "RGB"
    with pytest.raises(OSError):
        read_image(b"not an image")

@pytest.mark.integration
def test_full_pipeline(tmp_path):
    model = Path(__file__).resolve().parents[1] / "dinov2-small"
    if not (model / "model.safetensors").is_file():
        pytest.skip("Local DINOv2 weights are not installed")
    rng = np.random.default_rng(42)
    image = Image.fromarray(rng.integers(0, 256, (224, 224, 3), dtype=np.uint8))
    reference = tmp_path / "reference.png"
    image.save(reference)
    pipeline = LandmarkPipeline.build([Reference(417, str(reference))], model)
    embeddings = pipeline.embedder.embed([reference, reference.read_bytes()])
    assert embeddings.shape == (2, 384)
    np.testing.assert_allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-6)
    np.testing.assert_allclose(embeddings[0], embeddings[1], atol=1e-6)
    pipeline.save(tmp_path / "index")
    loaded = LandmarkPipeline.load(tmp_path / "index", model)
    prediction = loaded.predict(reference.read_bytes())
    assert prediction["landmark_id"] == 417
    assert prediction["similarity"] == pytest.approx(1, abs=1e-5)
