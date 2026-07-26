# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "torch",
#   "torchvision",
#   "transformers",
#   "sentencepiece==0.2.0",
#   "pillow",
#   "pandas",
#   "pyarrow",
#   "numpy",
# ]
# ///
"""HF Job (GPU): compute image embeddings from the manifest produced by the
download job (jobs/download_job.py).

The storage bucket is mounted read+write at /bucket. Images and the manifest are
already there, so this job is pure GPU work:
  1. Read /bucket/<MANIFEST_PATH>.
  2. Stream images through a DataLoader (CPU workers preprocess + prefetch while the
     GPU computes), embed with google/tipsv2-b14 under fp16 autocast.
  3. Write /bucket/<EMBEDDINGS_PATH> (manifest columns + the embedding) atomically.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
from transformers import AutoModel

# /bucket on HF (volume mount); override BUCKET_DIR to run the job locally.
BUCKET = os.environ.get("BUCKET_DIR", "/bucket")
MANIFEST_PATH = os.path.join(BUCKET, os.environ.get("MANIFEST_PATH", "manifest.parquet"))
EMBEDDINGS_PATH = os.path.join(BUCKET, os.environ.get("EMBEDDINGS_PATH", "embeddings.parquet"))
EMBED_MODEL = os.environ.get("EMBED_MODEL", "google/tipsv2-b14")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
# 448x448 means 1024 patches per image for the /14 ViT, so batches are heavier
# than they were at CLIP's 224x224.
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "64"))
NUM_WORKERS = int(os.environ.get("NUM_WORKERS", str(min(8, os.cpu_count() or 4))))

# TIPS expects [0, 1] pixel values at 448x448 — no ImageNet normalization.
PREPROCESS = transforms.Compose([transforms.Resize((448, 448)), transforms.ToTensor()])


class ImageDataset(Dataset):
    """Reads + preprocesses one image per row of the manifest.

    Returns (row_index, pixel_values) or None when an image can't be read, so the
    GPU embeds only what loaded successfully (the index stays aligned via row_index).
    """

    def __init__(self, image_paths: list[str]):
        self.image_paths = image_paths

    def __len__(self) -> int:
        return len(self.image_paths)

    def __getitem__(self, idx: int):
        rel_path = self.image_paths[idx]
        abs_path = os.path.join(BUCKET, rel_path)
        try:
            image = Image.open(abs_path).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            print(f"failed to read {abs_path}: {exc}")
            return None
        pixel_values = PREPROCESS(image)
        # Carry the path so the embed loop can verify alignment with the manifest.
        return idx, rel_path, pixel_values


def _collate(batch):
    batch = [b for b in batch if b is not None]
    if not batch:
        return [], [], None
    idxs = [b[0] for b in batch]
    paths = [b[1] for b in batch]
    pixel_values = torch.stack([b[2] for b in batch])
    return idxs, paths, pixel_values


def main() -> None:
    print(f"Device: {DEVICE}")
    if DEVICE == "cuda":
        print(f"GPU: {torch.cuda.get_device_name()}")

    manifest = pd.read_parquet(MANIFEST_PATH)
    print(f"{len(manifest)} images in manifest")
    if manifest.empty:
        print("empty manifest; exiting")
        return

    model = AutoModel.from_pretrained(EMBED_MODEL, trust_remote_code=True).eval()
    # Probe the embedding width before moving to the GPU (encode_text runs fine on CPU).
    with torch.inference_mode():
        dim = int(model.encode_text(["probe"]).shape[-1])
    model = model.to(DEVICE)

    dataset = ImageDataset(manifest["image_path"].tolist())
    loader = DataLoader(
        dataset,
        batch_size=BATCH_SIZE,
        num_workers=NUM_WORKERS,
        collate_fn=_collate,
        pin_memory=(DEVICE == "cuda"),
        persistent_workers=(NUM_WORKERS > 0),
    )

    embeddings = np.zeros((len(manifest), dim), dtype=np.float32)
    done = np.zeros(len(manifest), dtype=bool)
    autocast = (
        torch.autocast(device_type="cuda", dtype=torch.float16)
        if DEVICE == "cuda"
        else torch.autocast(device_type="cpu", enabled=False)
    )

    manifest_paths = manifest["image_path"].tolist()
    processed = 0
    with torch.inference_mode():
        for idxs, paths, pixel_values in loader:
            if pixel_values is None:
                continue
            # Alignment guard: each carried path must match the manifest row it maps to,
            # otherwise an embedding would be written against the wrong image.
            for i, path in zip(idxs, paths):
                if manifest_paths[i] != path:
                    raise RuntimeError(
                        f"image/index misalignment at row {i}: "
                        f"manifest={manifest_paths[i]!r} batch={path!r}"
                    )
            pixel_values = pixel_values.to(DEVICE, non_blocking=True)
            with autocast:
                out = model.encode_image(pixel_values)
            # cls_token is the global image embedding, shape (batch, 1, dim).
            feats = out.cls_token[:, 0, :].float().cpu().numpy()
            norms = np.linalg.norm(feats, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            embeddings[idxs] = feats / norms
            done[idxs] = True
            processed += len(idxs)
            print(f"embedded {processed}/{len(manifest)}")

    # Sanity: every embedded row must carry a non-zero vector.
    if np.any(done & ~np.any(embeddings != 0, axis=1)):
        raise RuntimeError("found embedded rows with all-zero embeddings")
    if int(done.sum()) != processed:
        raise RuntimeError(
            f"embedded-row count {int(done.sum())} != processed {processed}"
        )

    out = manifest.loc[done].copy()
    out["embedding"] = list(embeddings[done])
    out = out.drop(columns=["image_path"])

    tmp_path = EMBEDDINGS_PATH + ".tmp"
    out.to_parquet(tmp_path, index=False)
    os.replace(tmp_path, EMBEDDINGS_PATH)
    print(f"wrote {len(out)} embeddings to {EMBEDDINGS_PATH}")


if __name__ == "__main__":
    main()
