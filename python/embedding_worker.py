import os
import ssl
import time
import datetime
from typing import Dict, Any
import asyncio
from bullmq import Worker, Job
from sqlalchemy.orm import Session
import db, redis_connection
import signal
from transformers import AutoProcessor, CLIPVisionModelWithProjection
from PIL import Image as PILImage
from queues import results_queue
import requests
from transformers.image_utils import load_image
# Import dependencies (you'll need to convert/install these)
# from bullmq import Worker, Job  # Python equivalent: arq, rq, or celery
# import pgvector  # Python pgvector library
# from db import db
# from redis_connection import connection

print("Worker loaded")
model = CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-base-patch32")
processor = AutoProcessor.from_pretrained("openai/clip-vit-base-patch32")

async def image_processor(job, job_id: str) -> None:
    start_time = time.time()
    try:
        print(f"{job_id} processing {job.data}")
        image_url = job.data['url']
        image = load_image(image_url)
        inputs = processor(images=image, return_tensors="pt")
        outputs = model(**inputs)
        embeddings = outputs.image_embeds.data.tolist()
        #  add to results queue
        await results_queue.add("resultsProcessor", {
            # spread the job data
            **job.data,
            "embedding": embeddings,
            "timestamp": datetime.datetime.now(datetime.UTC).isoformat(),
        }, {"removeOnComplete": True, "removeOnFail": True})
        # Store in database
        print(f"{job_id} processed")
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
    finally:
        # await results_queue.close()
        elapsed_time = (time.time() - start_time) * 1000  # Convert to ms
        print(f"{job_id}: {elapsed_time:.2f}ms")
        


def on_completed(job_id: str, result: Any) -> None:
    """Callback when worker completes a job."""
    print("worker completed")
    print(f"Result: {result}")

def on_error(error: Exception, job_id: str) -> None:
    """Callback when worker encounters an error."""
    print(f"Worker error: {error}")



async def main():

    # Create an event that will be triggered for shutdown
    shutdown_event = asyncio.Event()

    def signal_handler(signal, frame):
        print("Signal received, shutting down.")
        shutdown_event.set()

    # Assign signal handlers to SIGTERM and SIGINT
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Create worker
    worker = Worker(
        name="imageProcessingQueue",
        processor=image_processor,
        opts={
            "connection": redis_connection.redis_connection_options,
            "concurrency": 2,
            "autorun": True,
        }
    )

    worker.on("completed", on_completed)
    worker.on("error", on_error)

    # Wait until the shutdown event is set
    await shutdown_event.wait()

    # close the worker
    print("Cleaning up worker...")
    await worker.close()
    print("Worker shut down successfully.")

if __name__ == "__main__":
    asyncio.run(main())