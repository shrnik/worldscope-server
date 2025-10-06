from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from transformers import CLIPTextModelWithProjection, AutoTokenizer
from PIL import Image
import requests
from sqlalchemy.orm import Session
from sqlalchemy import select
from db import engine, Image as DBImage
from utils.get_faa_images import get_faa_images
from image_utils import get_images as get_all_images
from utils.helpers import get_file_path, save_image_to_path, make_url_absolute
from queues import image_processing_queue
import asyncio


text_model = CLIPTextModelWithProjection.from_pretrained("openai/clip-vit-base-patch16")
text_tokenizer = AutoTokenizer.from_pretrained("openai/clip-vit-base-patch16")

router = APIRouter()
BASE_URL = "http://localhost:5001/images"

class TextEmbeddingRequest(BaseModel):
    text: str

class ImageEmbeddingRequest(BaseModel):
    url: str

def get_db():
    try:
        session = Session(engine)
        yield session
    finally:
        session.close()

@router.get("/")
def read_root():
    return {"message": "API - 👋🌎🌍🌏"}

@router.get("/queue_images")
async def queue_all_images():
    images = await get_all_images()
    # await image_processing_queue.obliterate(force=1)
    async def download_and_save_image(img):
        file_path, internal_path = get_file_path(img['cameraId'], img['url'])
        save_image_to_path(img['url'], file_path)
        local_url = make_url_absolute(BASE_URL, internal_path)
        await image_processing_queue.add("imageProcessor", {
            **img,
            "original": img['url'],
            "url": local_url,
        }, {"removeOnComplete": True})
        print(f"Saved image {img['cameraId']} to {file_path}")
    
    async def process_images():
        semaphore = asyncio.Semaphore(20)  # Limit concurrency to 20

        async def bounded_download(img):
            async with semaphore:
                await download_and_save_image(img)
        
        tasks = [bounded_download(img) for img in images[:10]]
        await asyncio.gather(*tasks)
    
    await process_images()
    await image_processing_queue.close()
    return {"message": f"Queued {len(images)} images for processing"}

def get_text_embedding(text: str):
    inputs = text_tokenizer(text, return_tensors="pt", padding=True, truncation=True)
    outputs = text_model(**inputs)
    embeddings = outputs.text_embeds.data.tolist()
    return embeddings[0]    

@router.get("/images")
def get_images(query: str, db: Session = Depends(get_db)):
    if not query:
        raise HTTPException(status_code=400, detail="Invalid query")

    text_embedding = get_text_embedding(query)
    query_vector = text_embedding
    results = db.execute(
        select(DBImage, DBImage.embedding.cosine_distance(query_vector).label('distance'))
        .order_by('distance')
        .limit(100)
    ).all()

    return [
        {
            "id": row[0].id,
            "url": row[0].url,
            "camera_id": row[0].camera_id,
            "distance": 1 - float(row[1]),
        }
        for row in results
    ]


@router.get("/images")
def get_contrail_images(threshold: float , db: Session = Depends(get_db)):
    query_vector = text_embedding
    results = db.execute(
        select(DBImage)
        .order_by(DBImage.contrail_probability)
        .limit(100)
    ).all()
    return results
main = router