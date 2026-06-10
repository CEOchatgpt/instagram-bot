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
        # Endpoint اصلی که در فایل‌هات بود (video/details)
        endpoint = f"https://{RAPIDAPI_HOST_YOUTUBE}/video/details/"

        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY_YOUTUBE,
            "X-RapidAPI-Host": RAPIDAPI_HOST_YOUTUBE,
            "Content-Type": "application/json"
        }

        # بعضی endpointها GET، بعضی POST کار می‌کنن. اول GET امتحان می‌کنیم
        params = {
            "id": video_id,
            "hl": "en",
            "gl": "US"
        }

        response = requests.get(endpoint, headers=headers, params=params, timeout=40)

        logger.info(f"YouTube API Status: {response.status_code} for {video_id}")

        if response.status_code != 200:
            logger.error(f"YouTube Error: {response.text[:800]}")
            return None

        data = response.json()
        logger.info(f"Response keys: {list(data.keys())}")

        # جستجو برای لینک دانلود
        download_url = None

        # مسیرهای مختلف ممکن
        if isinstance(data, dict):
            # مسیر 1: formats مستقیم
            formats = data.get("formats") or data.get("streamingData", {}).get("formats", [])
            if not formats:
                formats = data.get("streamingData", {}).get("adaptiveFormats", [])

            for fmt in formats:
                if fmt.get("url") and "video/mp4" in fmt.get("mimeType", ""):
                    download_url = fmt["url"]
                    break

            # fallback
            if not download_url:
                for key in ["url", "play", "download_url", "video_url"]:
                    if data.get(key):
                        download_url = data.get(key)
                        break

        if download_url:
            title = data.get("title") or data.get("videoDetails", {}).get("title", "🎥 YouTube Video")
            return {
                "url": download_url,
                "caption": title[:900]
            }
        else:
            logger.warning("No download URL found in the response")
            return None

    except Exception as e:
        logger.error(f"Exception in get_youtube_media: {e}", exc_info=True)
        return None
