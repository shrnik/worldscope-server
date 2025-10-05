import os
from pathlib import Path
from typing import Optional, Union, Dict
from datetime import datetime
from PIL import Image as PILImage
import requests

VALID_EXTENSIONS = ["jpg", "jpeg", "png"]


def is_valid_ext(ext: Optional[str]) -> bool:
    """Check if the file extension is valid."""
    return ext is not None and ext.lower() in VALID_EXTENSIONS


def get_file_path(camera_id: Union[int, str], url: str) -> Dict[str, str]:
    """
    Generate file path for camera image.

    Args:
        camera_id: Camera identifier
        url: Image URL

    Returns:
        Dictionary containing filePath and internalPath
    """
    timestamp = datetime.now().isoformat()

    # Extract extension from URL
    temp_ext = url.split(".")[-1] if "." in url else None
    ext = temp_ext if is_valid_ext(temp_ext) else "jpg"

    # Create internal path based on camera ID
    internal_path = os.path.join(str(camera_id), f"default.{ext}")

    # Get the directory where this script is located
    current_dir = Path(__file__).parent

    # Create folder path (go up 2 levels to root, then into images)
    folder_path = current_dir.parent.parent / "images" / str(camera_id)
    folder_path.mkdir(parents=True, exist_ok=True)

    # Create full file path
    file_path = str(current_dir.parent.parent / "images" / internal_path)

    return file_path, internal_path

def save_image_to_path(url: str, file_path: str) -> bool:
    try:
        img = PILImage.open(requests.get(url, stream=True).raw)
        img.save(file_path)
        print(f"Image saved to {file_path}")
        return True
    except Exception as e:
        print(f"Error saving image to {file_path}: {e}")
        return False
    
def make_url_absolute(base_url: str, relative_url: str) -> str:
    if relative_url.startswith("http://") or relative_url.startswith("https://"):
        return relative_url
    return base_url.rstrip("/") + "/" + relative_url.lstrip("/")