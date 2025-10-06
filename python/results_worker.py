import os
import ssl
import time
from datetime import datetime
from typing import Dict, Any
import asyncio
from bullmq import Worker, Job
from sqlalchemy.orm import Session
import db, redis_connection
import signal

async def processor(job, job_id: str) -> None:
    """
    Process job to store image embeddings in database.

    Args:
        job: Job data dictionary
        job_id: Job identifier
        db: Database connection
        pgvector_to_sql: Function to convert embedding to SQL format
    """
    start_time = time.time()

    try:
        url = job.data.get("url")
        camera_id = job.data.get("cameraId")
        embedding = job.data.get("embedding")
        timestamp = job.data.get("timestamp")
        image_features = job.data.get("image_features")
        # image_id = job.data.get("imageId")
        # metadata = job.get("metadata")
        camera_data = {
            "cameraName": job.data.get("cameraName"),
            "source": job.data.get("source"),
            "lat": job.data.get("lat"),
            "long": job.data.get("long"),
            "refreshRate": job.data.get("refreshRate"),
            "attribution": job.data.get("attribution"),
        }

        # Convert embedding to SQL format

        print(f"{job_id} embedding created")
        # Process regular image
        # Use regular transaction pattern instead of async context manager
        session = Session(db.engine)
        try:
            # Check if existing record exists using the ORM
            existing_record = session.query(db.Image).filter_by(camera_id=str(camera_id)).first()
            updated_at = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
            # Only update if no existing record or new timestamp is more recent
            if not existing_record or updated_at > existing_record.updated_at:
                if existing_record:
                    # Update existing record
                    existing_record.url = url
                    existing_record.embedding = embedding
                    existing_record.updated_at = updated_at 
                    existing_record.camera_data = camera_data
                else:
                    # Create new record
                    new_image = db.Image(
                        url=url,
                        embedding=embedding,
                        image_features=image_features,
                        camera_id=str(camera_id),
                        created_at=datetime.now(),
                        updated_at=updated_at,
                        camera_data=camera_data,
                        contrail_probability=job.data.get("contrail_probability", 0)
                    )
                    session.add(new_image)
                
                print(f"{job_id} inserted into db")
            else:
                print(f"{job_id} skipped insert due to timestamp")
            
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    except Exception as e:
        print(f"Error processing job {job_id}: {e}")
    finally:
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
        name="resultsQueue",
        processor=processor,
        opts = {
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