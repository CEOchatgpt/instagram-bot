import requests
import re
import logging
from config import RAPIDAPI_KEY

logger = logging.getLogger(__name__)

def extract_video_id(url: str) -> str:
    """استخراج ID ویدیو از لینک یوتیوب"""
    match = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None


def get_youtube_media(url: str):
    video_id = extract_video_id(url)
    if not video_id:
        logger.error("Could not extract video ID from URL")
        return None

    try:
        endpoint = "https://youtube138.p.rapidapi.com/video/streaming-data/"

        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": "youtube138.p.rapidapi.com",
            "Content-Type": "application/json"
        }

        payload = {
            "id": video_id,
            "hl": "en",
            "gl": "US"
        }

        response = requests.post(endpoint, json=payload, headers=headers, timeout=40)

        if response.status_code != 200:
            logger.error(f"YouTube API Error {response.status_code}: {response.text[:500]}")
            return None

        data = response.json()

        # استخراج لینک دانلود
        formats = data.get("formats", []) or data.get("streamingData", {}).get("formats", [])
        if not formats:
            formats = data.get("streamingData", {}).get("adaptiveFormats", [])

        download_url = None
        best_quality = 0

        for fmt in formats:
            height = fmt.get("height", 0)
            mime = fmt.get("mimeType", "")
            if "video/mp4" in mime and height > best_quality and fmt.get("url"):
                best_quality = height
                download_url = fmt["url"]

        if not download_url and formats:
            download_url = formats[0].get("url")

        if download_url:
            return {
                "url": download_url,
                "caption": data.get("title") or data.get("videoDetails", {}).get("title", "🎥 YouTube Video"),
                "thumbnail": data.get("thumbnail") or data.get("videoDetails", {}).get("thumbnails", [{}])[0].get("url"),
                "quality": f"{best_quality}p"
            }
        
        logger.warning("No download URL found")
        return None

    except Exception as e:
        logger.error(f"Exception in get_youtube_media: {e}")
        return None
