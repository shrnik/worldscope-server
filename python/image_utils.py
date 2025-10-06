import os
import asyncio
import requests
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv
from pathlib import Path

# Import the function from the module
from utils.get_faa_images import get_faa_images

# Import other modules (you'll need to convert these as well)
# from constants import SHEET_URL
# from download_image import download_image
# from queue import image_queue
# from db import db

load_dotenv()

# Placeholder for constants - replace with actual import
SHEET_URL = "https://sheets.googleapis.com/v4/spreadsheets/1_tbi4WTx9qGErN-2cvYvEd3qeJxgzd_9N9HJWWPD7SA/values/Main?alt=json&key=AIzaSyA6pmS1gW0a3dWzxdYOfo-sE5hmmvGrW8M"


class CamDataType(TypedDict):
    url: str
    cameraId: int
    cameraName: str
    source: str
    lat: str
    lon: str
    refreshRate: str


async def get_images() -> List[CamDataType]:
    res = requests.get(SHEET_URL)
    values = res.json()["values"]
    header, *data = values

    image_metas: List[CamDataType] = []
    
    for index, row in enumerate(data):
        if len(row) >= 1:  # Check if row has all required indexes (0-5)
            image_metas.append({
                "url": row[1],
                "cameraId": index,
                "cameraName": row[0],
                "source": row[2],
                "lat": row[3],
                "lon": row[4],
                "refreshRate": row[5],
            })
        else:
            print(f"Skipping row {index} due to missing data: {row}")

    non_faa_images = [image for image in image_metas if image["source"] != "faa.gov"]
    faa_images = get_faa_images()

    all_images = [*non_faa_images, *faa_images]
    # camera_id is index
    for i, img in enumerate(all_images):
        img["cameraId"] = i
    return all_images
