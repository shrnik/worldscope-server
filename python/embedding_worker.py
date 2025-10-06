import time
import datetime
import asyncio
from bullmq import Worker
import redis_connection
import signal
from transformers import AutoProcessor, CLIPVisionModelWithProjection
from PIL import Image as PILImage
from queues import results_queue
import requests
from transformers.image_utils import load_image
from contrail_classifier import ContrailClassifier
# Import dependencies (you'll need to convert/install these)
# from bullmq import Worker, Job  # Python equivalent: arq, rq, or celery
# import pgvector  # Python pgvector library
# from db import db
# from redis_connection import connection

print("Worker loaded")
model = CLIPVisionModelWithProjection.from_pretrained("openai/clip-vit-base-patch16", device_map="auto")
processor = AutoProcessor.from_pretrained("openai/clip-vit-base-patch16")

def get_features_and_embeddings(images: PILImage.Image):
    inputs = processor(images=images, return_tensors="pt")
    outputs = model(**inputs)
    image_embeds = outputs.image_embeds
    pooler_output = outputs.last_hidden_state[:, 0, :]
    pooler_output = model.vision_model.post_layernorm(pooler_output)
    return image_embeds, pooler_output

classifier = ContrailClassifier()

async def image_processor(job, job_id: str) -> None:
    start_time = time.time()
    try:
        print(f"{job_id} processing {job.data}")
        image_url = job.data['url']
        image = load_image(image_url)
        image_embeds, pooler_output = get_features_and_embeddings(image)
        #  add to results queue
        image_features = pooler_output.tolist()[0]
        contrail_prob = classifier.predict(image_features)
        embedding = image_embeds.data.tolist()[0]
        await results_queue.add("resultsProcessor", {
            # spread the job data
            **job.data,
            "embedding": embedding,
            "image_features": image_features,
            "timestamp": datetime.datetime.now(datetime.UTC).timestamp(),
            "contrail_probability": contrail_prob,
        }, {"removeOnComplete": True, "removeOnFail": True})
        # Store in database
        print(f"{job_id} processed")
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
    finally:
        # await results_queue.close()
        elapsed_time = (time.time() - start_time) * 1000  # Convert to ms
        print(f"{job_id}: {elapsed_time:.2f}ms")
        


def on_completed(job_id: str, result) -> None:
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