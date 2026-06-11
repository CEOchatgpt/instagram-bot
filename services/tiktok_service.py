import requests
import logging
from config import TIKTOK_RAPIDAPI_KEY, RAPIDAPI_HOST_TIKTOK

logger = logging.getLogger(__name__)

def get_tiktok_media(url: str):
    """
    دانلود اطلاعات ویدیو تیک‌تاک با Tikfly API
    """
    try:
        endpoint = f"https://{RAPIDAPI_HOST_TIKTOK}/api/download/video"
        
        querystring = {"url": url}

        headers = {
            "X-RapidAPI-Key": TIKTOK_RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST_TIKTOK
        }

        response = requests.get(endpoint, headers=headers, params=querystring, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"TikTok API Error {response.status_code}: {response.text[:400]}")
            return None

        data = response.json()

        # ساختار پاسخ API (طبق داکیومنت)
        play_url = data.get("play")          # بدون واترمارک (پیشنهادی)
        play_watermark = data.get("play_watermark")

        if play_url:
            return {
                "type": "video",
                "url": play_url,                    # لینک بدون واترمارک
                "caption": "TikTok Video",          # فعلاً ثابت (این endpoint عنوان نداره)
                "thumbnail": None,
                "watermark_url": play_watermark
            }
        else:
            logger.warning("No play URL found in TikTok response")
            return None

    except Exception as e:
        logger.error(f"Exception in get_tiktok_media: {e}")
        return None
