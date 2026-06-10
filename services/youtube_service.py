import requests
import re
import logging
from config import RAPIDAPI_KEY_YOUTUBE, RAPIDAPI_HOST_YOUTUBE

logger = logging.getLogger(__name__)

def extract_video_id(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else None


def get_youtube_media(url: str):
    video_id = extract_video_id(url)
    if not video_id:
        logger.error("Could not extract YouTube ID")
        return None

    try:
        # Endpoint درست این API (video/details)
        endpoint = f"https://{RAPIDAPI_HOST_YOUTUBE}/video/details/"

        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY_YOUTUBE,
            "X-RapidAPI-Host": RAPIDAPI_HOST_YOUTUBE,
            "Content-Type": "application/json"
        }

        payload = {
            "id": video_id,
            "hl": "en",
            "gl": "US"
        }

        response = requests.post(endpoint, json=payload, headers=headers, timeout=40)

        logger.info(f"YouTube API Status: {response.status_code} for {video_id}")

        if response.status_code != 200:
            logger.error(f"YouTube Error: {response.text[:700]}")
            return None

        data = response.json()
        logger.info(f"Response keys: {list(data.keys())}")

        # بعضی نسخه‌ها formats دارن، بعضی adaptiveFormats
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

        # fallback
        if not download_url and formats:
            for fmt in formats:
                if fmt.get("url"):
                    download_url = fmt["url"]
                    break

        if download_url:
            title = data.get("title") or data.get("videoDetails", {}).get("title", "🎥 YouTube Video")
            return {
                "url": download_url,
                "caption": title[:900]
            }
        else:
            logger.warning("No download URL found in response")
            return None

    except Exception as e:
        logger.error(f"Exception in get_youtube_media: {e}", exc_info=True)
        return None
