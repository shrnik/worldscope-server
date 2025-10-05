from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from api import main as api_router
from pathlib import Path


app = FastAPI()

# CORS Middleware
origins = [
    "http://localhost:3000",
    "https://shrnik.github.io",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
# make sure the "images" directory exists in your project root
directory = "./images"
images_dir = Path(directory)
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=images_dir), name="images")

@app.get("/")
def read_root():
    return {"message": "🦄🌈✨👋🌎🌍🌏✨🌈🦄"}

# Include API routes
app.include_router(api_router, prefix="/api/v1")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)
