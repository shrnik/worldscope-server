# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "pandas",
#   "pyarrow",
# ]
# ///
"""HF Job (CPU): prune bucket images not referenced by the current embeddings.

Runs after the embed job. Reads /bucket/<EMBEDDINGS_PATH>, collects the image paths
it references, and deletes any file under /bucket/images that isn't in that set
(snapshots from previous runs). Because it prunes against the finalized embeddings,
nothing currently served is removed.

The storage bucket is mounted read+write at /bucket. Only the images/ tree is touched
(embeddings.parquet, manifest.parquet and scripts/ are left alone).
"""

from __future__ import annotations

import os

import pandas as pd

BUCKET = os.environ.get("BUCKET_DIR", "/bucket")
IMAGES_DIR = os.path.join(BUCKET, "images")
EMBEDDINGS_PATH = os.path.join(BUCKET, os.environ.get("EMBEDDINGS_PATH", "embeddings.parquet"))


def referenced_paths() -> set[str]:
    """Relative image paths (e.g. 'images/3/<ts>.jpg') referenced by the embeddings."""
    df = pd.read_parquet(EMBEDDINGS_PATH)
    paths: set[str] = set()
    for url in df["url"].tolist():
        if isinstance(url, str) and "/resolve/" in url:
            paths.add(url.split("/resolve/", 1)[1])
    return paths


def main() -> None:
    if not os.path.exists(EMBEDDINGS_PATH):
        print(f"{EMBEDDINGS_PATH} not found; nothing to clean")
        return

    keep = referenced_paths()
    if not keep:
        print("embeddings reference no images; skipping cleanup to avoid wiping bucket")
        return
    print(f"{len(keep)} images referenced by embeddings")

    removed = 0
    for root, _dirs, files in os.walk(IMAGES_DIR, topdown=False):
        for name in files:
            abs_path = os.path.join(root, name)
            rel_path = os.path.relpath(abs_path, BUCKET)  # images/<camera_id>/<ts>.jpg
            if rel_path not in keep:
                try:
                    os.remove(abs_path)
                    removed += 1
                except OSError as exc:
                    print(f"failed to delete {abs_path}: {exc}")
        # Drop now-empty camera directories.
        if root != IMAGES_DIR and os.path.isdir(root) and not os.listdir(root):
            try:
                os.rmdir(root)
            except OSError:
                pass

    print(f"cleaned up {removed} unreferenced images")


if __name__ == "__main__":
    main()
