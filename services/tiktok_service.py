import requests
import logging
from config import (
    RAPIDAPI_KEY_TIKTOK, 
    RAPIDAPI_HOST_TIKTOK
)

logger = logging.getLogger(__name__)

def get_tiktok_media(url: str):
    """
    دانلود ویدیو از تیک‌تاک
    """
    try:
        endpoint = f"https://{RAPIDAPI_HOST_TIKTOK}/api/v1/tiktok"

        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY_TIKTOK,
            "X-RapidAPI-Host": RAPIDAPI_HOST_TIKTOK,
        }

        params = {"url": url}

        response = requests.get(endpoint, headers=headers, params=params, timeout=30)

        logger.info(f"TikTok API Status: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"TikTok API Error: {response.text[:500]}")
            return None

        data = response.json()

        # استخراج لینک ویدیو
        video_url = None
        if isinstance(data, dict):
            video_url = (
                data.get("data", {}).get("video_url") or
                data.get("video", {}).get("url") or
                data.get("play") or
                data.get("url")
            )

        if video_url:
            return {
                "url": video_url,
                "caption": data.get("title") or data.get("desc") or "🎵 TikTok Video"
            }

        logger.warning("No video URL found in TikTok response")
        return None

    except Exception as e:
        logger.error(f"Exception in get_tiktok_media: {e}", exc_info=True)
        return None
