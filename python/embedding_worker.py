import time
import datetime
import asyncio
from bullmq import Worker
import redis_connection
import signal
from transformers import AutoProcessor, CLIPVisionModelWithProjection
from PIL import Image as PILImage
from queues import results_queue
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
    # Move inputs to the same device as the model
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    outputs = model(**inputs)
    image_embeds = outputs.image_embeds
    pooler_output = outputs.last_hidden_state[:, 0, :]
    pooler_output = model.vision_model.post_layernorm(pooler_output)
    return image_embeds, pooler_output

classifier = ContrailClassifier()

async def image_processor(job, job_id: str) -> None:
    start_time = time.time()
    try:
        images_data = job.data.get('images', [])
        print(f"{job_id} processing batch of {len(images_data)} images")

        # Process each image in the batch
        images = []
        image_index_map = {}  # Maps image index to original images_data index
        async def load_single_image(idx, img_data):
            try:
                image_url = img_data['url']
                image = await asyncio.to_thread(load_image, image_url)
                return (idx, image)
            except Exception as e:
                print(f"Error loading image {img_data.get('url', 'unknown')}: {e}")
                return (idx, None)

        # Load all images concurrently
        load_tasks = [load_single_image(idx, img_data) for idx, img_data in enumerate(images_data)]
        load_results = await asyncio.gather(*load_tasks)

        # Build images list and index map
        for idx, image in load_results:
            if image is not None:
                image_index_map[idx] = len(images)
                images.append(image)

        # Get features and embeddings for all images in the batch
        image_embeds, pooler_output = get_features_and_embeddings(images)
        for idx, img_data in enumerate(images_data):
            try:
                # Get the corresponding features and embeddings
                mapped_idx = image_index_map.get(idx)
                image_feature = pooler_output[mapped_idx].detach().cpu().numpy().tolist()
                image_embedding = image_embeds[mapped_idx].detach().cpu().numpy().tolist()

                # Classify contrail presence
                contrail_present = classifier.predict(image_feature)

                # Store results in the results queue
                await results_queue.add("resultsQueue", {
                    **img_data,
                    "timestamp": datetime.datetime.now(datetime.UTC).timestamp(),
                    "image_features": image_feature,
                    "embedding": image_embedding,
                    "contrail_probability": contrail_present
                }, {"removeOnComplete": True})
            except Exception as e:
                print(f"Error processing image {img_data.get('url', 'unknown')}: {e}")

        print(f"{job_id} batch processed")
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
    finally:
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