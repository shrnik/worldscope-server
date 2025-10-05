import os
import ssl
import urllib3
import requests
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor

# Disable SSL verification
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
ssl._create_default_https_context = ssl._create_unverified_context

SHEET_URL = "https://sheets.googleapis.com/v4/spreadsheets/1_tbi4WTx9qGErN-2cvYvEd3qeJxgzd_9N9HJWWPD7SA/values/Main?alt=json&key=AIzaSyA6pmS1gW0a3dWzxdYOfo-sE5hmmvGrW8M"

VALID_EXTENSIONS = ["jpg", "jpeg", "png", "gif"]


def is_valid_ext(ext: Optional[str]) -> bool:
    return ext is not None and ext.lower() in VALID_EXTENSIONS


async def download_image(session: aiohttp.ClientSession, url: str, meta: Dict, path_name: str, timestamp: int) -> Optional[Dict]:
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(url, timeout=timeout, ssl=False) as response:
            # Create images directory if it doesn't exist
            images_dir = Path(path_name) / "images"
            images_dir.mkdir(parents=True, exist_ok=True)

            # Determine file extension
            temp_ext = url.split(".")[-1] if "." in url else None
            ext = temp_ext if is_valid_ext(temp_ext) else "jpg"

            # Create file path
            file_path = images_dir / f"{timestamp}-{meta['cameraId']}.{ext}"

            # Download and save the file
            with open(file_path, "wb") as f:
                f.write(await response.read())

            print("download complete")
            return {
                **meta,
                "path": str(file_path)
            }

    except asyncio.TimeoutError:
        print("download timeout")
        return None
    except Exception as e:
        print(f"download error: {e}")
        return None


async def download_all(path_name: str) -> List[Dict]:
    # Fetch spreadsheet data
    response = requests.get(SHEET_URL, verify=False)
    values = response.json()["values"]

    header, *data = values
    timestamp = int(datetime.now().timestamp() * 1000)

    # Create image metadata
    image_metas = [
        {
            "url": row[1],
            "cameraId": index,
            "cameraName": row[0],
            "timeStamp": timestamp
        }
        for index, row in enumerate(data)
    ]

    # Download images with concurrency limit of 25
    connector = aiohttp.TCPConnector(limit=25, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            download_image(session, meta.pop("url"), meta, path_name, timestamp)
            for meta in image_metas
        ]
        results = await asyncio.gather(*tasks)

    # Filter out None results
    return [r for r in results if r is not None]


def main(path_name: str = "."):
    return asyncio.run(download_all(path_name))


if __name__ == "__main__":
    result = main()
    print(f"Downloaded {len(result)} images")
