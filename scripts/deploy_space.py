"""Deploy the Gradio search frontend (space/) to a Hugging Face Space.

Uploads the space/ folder to the Space repo (creating it if needed). Auth comes from
the HF_TOKEN environment variable. Override the target with SPACE_REPO_ID.
"""

from __future__ import annotations

import os

from huggingface_hub import create_repo, upload_folder

SPACE_REPO_ID = os.environ.get("SPACE_REPO_ID", "shrnik/worldscope-search")


def main() -> None:
    create_repo(SPACE_REPO_ID, repo_type="space", space_sdk="gradio", exist_ok=True)
    upload_folder(
        repo_id=SPACE_REPO_ID,
        repo_type="space",
        folder_path="space",
        commit_message="Deploy from CI",
    )
    print(f"deployed space/ -> https://huggingface.co/spaces/{SPACE_REPO_ID}")


if __name__ == "__main__":
    main()
