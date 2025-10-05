import os
import asyncio
from pathlib import Path
from typing import Any, Dict
from bullmq import Queue
from dotenv import load_dotenv

# Import dependencies (you'll need to convert these modules)
# from download_all_images import get_images
# from utils.helpers import get_file_path
# from download_image import save_image
# from queue import image_queue
# from db import db

load_dotenv()

TABLE_NAME = "images"


async def queue_images(get_images_func, get_file_path_func, save_image_func, image_queue: Queue, db) -> None:
    """
    Queue images for processing with embeddings.

    Args:
        get_images_func: Function to get images from source
        get_file_path_func: Function to generate file paths
        save_image_func: Function to save images
        image_queue: Queue instance for processing images
        db: Database connection
    """
    images = await get_images_func()

    # Filter out images without URLs
    valid_images = [image for image in images if image.get("url")]

    # Process with concurrency limit of 10
    semaphore = asyncio.Semaphore(10)

    async def process_image(image_data: Dict[str, Any], camera_id: int) -> None:
        async with semaphore:
            url = image_data.pop("url")
            extra = image_data  # Remaining metadata

            file_paths = get_file_path_func(camera_id, url)
            file_path = file_paths["filePath"]
            internal_path = file_paths["internalPath"]

            try:
                # Save the image
                await save_image_func(url, file_path)

                # Construct new URL
                images_base_url = os.getenv("IMAGES_BASE_URL", "")
                new_url = f"{images_base_url}/{internal_path}"

                print(f"queued image {camera_id}")

                # Add to queue with retry configuration
                await image_queue.add(
                    "imageProcessor",
                    {
                        "url": new_url,
                        "cameraId": camera_id,
                        "metadata": extra
                    },
                    {
                        "removeOnComplete": True,
                        "deduplication": {"id": str(camera_id)},
                        "attempts": 3,
                        "backoff": {
                            "type": "exponential",
                            "delay": 10000,
                        },
                    }
                )

            except Exception as e:
                # Remove file if it exists to avoid stale data
                if Path(file_path).exists():
                    try:
                        Path(file_path).unlink()
                        print("File deleted successfully")
                    except Exception as err:
                        print(f"Error deleting file: {err}")

                # Remove entry from database
                try:
                    await db(TABLE_NAME).where("url", url).delete()
                except Exception as db_err:
                    print(f"Error deleting from database: {db_err}")

                print(f"Error processing image: {e}")

    # Create tasks for all valid images
    tasks = [
        process_image(image.copy(), camera_id)
        for camera_id, image in enumerate(valid_images)
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    # Example usage - you'll need to provide the dependencies
    # asyncio.run(queue_images(get_images, get_file_path, save_image, image_queue, db))
    pass
