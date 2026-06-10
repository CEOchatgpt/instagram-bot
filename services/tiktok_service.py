import requests
import logging
from config import RAPIDAPI_KEY_TIKTOK, RAPIDAPI_HOST_TIKTOK

logger = logging.getLogger(__name__)

def get_tiktok_media(url: str):
    """
    دانلود ویدیو تیک‌تاک (نسخه کاری که قبلاً داشتی)
    """
    try:
        endpoint = f"https://{RAPIDAPI_HOST_TIKTOK}/api/download/video"
        
        querystring = {"url": url}

        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY_TIKTOK,
            "X-RapidAPI-Host": RAPIDAPI_HOST_TIKTOK
        }

        response = requests.get(endpoint, headers=headers, params=querystring, timeout=35)
        
        logger.info(f"TikTok API Status: {response.status_code}")

        if response.status_code != 200:
            logger.error(f"TikTok API Error {response.status_code}: {response.text[:500]}")
            return None

        data = response.json()

        # ساختار پاسخ API که قبلاً کار می‌کرد
        play_url = data.get("play")                    # لینک بدون واترمارک (اولویت)
        play_watermark = data.get("play_watermark")

        if play_url:
            return {
                "url": play_url,
                "caption": "🎵 TikTok Video",
                "thumbnail": data.get("thumbnail"),
                "watermark_url": play_watermark
            }
        else:
            # fallback
            play_url = data.get("play_url") or data.get("url") or data.get("data", {}).get("play")
            if play_url:
                return {
                    "url": play_url,
                    "caption": "🎵 TikTok Video"
                }

        logger.warning(f"No play URL found. Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not dict'}")
        return None

    except Exception as e:
        logger.error(f"Exception in get_tiktok_media: {e}", exc_info=True)
        return None
