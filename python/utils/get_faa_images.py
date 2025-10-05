import os
import requests
from dotenv import load_dotenv

load_dotenv()

FAA_API_URL = "https://weathercams.faa.gov/api/redistributable/sites"
FAA_API_KEY = os.getenv("FAA_API_KEY")

def get_faa_images():
    headers = {"Authorization": f"Bearer {FAA_API_KEY}"}
    response = requests.get(FAA_API_URL, headers=headers)
    response.raise_for_status()
    sites = response.json().get("payload", [])
    
    faa_images = []
    for site in sites:
        if not site.get("cameras"):
            continue
        for camera in site["cameras"]:
            faa_images.append({
                "cameraName": f"{site.get('siteName', '')} {camera.get('cameraDirection', '')} {site.get('operatedBy', '')}",
                "url": camera.get("currentImageUri"),
                "source": "faa.gov",
                "lat": site.get("latitude"),
                "long": site.get("longitude"),
                "refreshRate": "10 min",
                "camera_id": camera.get("cameraId"),
                "attribution": site.get("attribution", "FAA")
            })
    faa_images = [img for img in faa_images if img != None]
    faa_images = [img for img in faa_images if "Alert California" not in (img.get("attribution") or "")]
    return faa_images