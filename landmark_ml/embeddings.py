from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image, ImageOps

ImageInput = str | Path | bytes | BinaryIO | Image.Image


def read_image(source: ImageInput) -> Image.Image:
    """Accept a local image, uploaded bytes/files, or a PIL image."""
    if isinstance(source, Image.Image):
        return ImageOps.exif_transpose(source).convert("RGB")
    if isinstance(source, bytes):
        source = BytesIO(source)
    with Image.open(source) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


class DinoV2Embedder:
    def __init__(self, model_path: str | Path = "dinov2-small", device: str = "cpu"):
        import torch
        from transformers import AutoImageProcessor, AutoModel

        self.model_path = Path(model_path).resolve()
        self.processor = AutoImageProcessor.from_pretrained(
            str(self.model_path), local_files_only=True, use_fast=False
        )
        self.model = (
            AutoModel.from_pretrained(
                str(self.model_path), local_files_only=True, use_safetensors=True
            )
            .to(device)
            .eval()
        )
        if self.model.config.model_type != "dinov2":
            raise ValueError("Expected a DINOv2 model")
        self.device = device
        self.dimension = self.model.config.hidden_size

        import hashlib

        digest = hashlib.sha256()
        for name in ("config.json", "preprocessor_config.json", "model.safetensors"):
            with (self.model_path / name).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        self.signature = "dinov2-cls-rgb-exif-l2-v1:" + digest.hexdigest()


    def embed(self, images: list[ImageInput]) -> np.ndarray:
        import torch

        if not images:
            raise ValueError("At least one image is required")
        prepared = [read_image(source) for source in images]
        try:
            inputs = self.processor(images=prepared, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                vectors = self.model(**inputs).last_hidden_state[:, 0, :]
                vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
            return np.ascontiguousarray(vectors.cpu().numpy(), dtype=np.float32)
        finally:
            for image in prepared:
                image.close()
