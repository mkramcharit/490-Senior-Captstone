from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import numpy as np
from PIL import Image, ImageOps

ImageInput = str | Path | bytes | BinaryIO | Image.Image
MAX_IMAGE_PIXELS = 25_000_000


def read_image(source: ImageInput) -> Image.Image:
    if isinstance(source, Image.Image):
        if source.width * source.height > MAX_IMAGE_PIXELS:
            raise ValueError('Image exceeds 25 million pixels')
        return ImageOps.exif_transpose(source).convert("RGB")
    if isinstance(source, bytes):
        if len(source) > 10 * 1024 * 1024:
            raise ValueError('Image exceeds 10 MB')
        source = BytesIO(source)
    with Image.open(source) as image:
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise ValueError('Image exceeds 25 million pixels')
        return ImageOps.exif_transpose(image).convert("RGB")


class DinoV2Embedder:
    def __init__(self, model_path: str | Path = "dinov2-small", device: str = "cpu", mixed_precision: bool = False, preprocess_workers: int = 0):
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
        self.mixed_precision = mixed_precision and str(device).startswith("cuda")
        self.preprocess_workers = preprocess_workers
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
        if self.preprocess_workers > 1:
            from concurrent.futures import ThreadPoolExecutor
            def prepare(source):
                with read_image(source) as image:
                    return self.processor(images=[image], return_tensors="pt")["pixel_values"][0]
            with ThreadPoolExecutor(max_workers=self.preprocess_workers) as pool:
                pixels = list(pool.map(prepare, images))
            inputs = {"pixel_values": torch.stack(pixels).to(self.device)}
        else:
            prepared = []
            try:
                for source in images:
                    prepared.append(read_image(source))
                inputs = self.processor(images=prepared, return_tensors="pt").to(self.device)
            finally:
                for image in prepared:
                    image.close()
        with torch.inference_mode(), torch.autocast(device_type="cuda", dtype=torch.float16, enabled=self.mixed_precision):
            vectors = self.model(**inputs).last_hidden_state[:, 0, :]
            vectors = torch.nn.functional.normalize(vectors, p=2, dim=1)
        return np.ascontiguousarray(vectors.float().cpu().numpy(), dtype=np.float32)
