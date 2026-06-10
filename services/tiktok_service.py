import aiohttp
import logging
import asyncio
from config import TIKTOK_RAPIDAPI_KEY, RAPIDAPI_HOST_TIKTOK

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1


async def get_tiktok_media(url: str) -> dict | None:
    """
    دانلود اطلاعات ویدیو تیک‌تاک به صورت ASYNC
    
    Args:
        url: لینک تیک‌تاک
        
    Returns:
        dict با ساختار: {"type": "video", "url": "...", "caption": "...", "watermark_url": "..."}
        یا None اگه خطا یا ناموفق
    """
    
    if not TIKTOK_RAPIDAPI_KEY:
        logger.error("TIKTOK_RAPIDAPI_KEY is not configured!")
        return None
    
    headers = {
        "X-RapidAPI-Key": TIKTOK_RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST_TIKTOK
    }
    
    params = {"url": url}
    endpoint = f"https://{RAPIDAPI_HOST_TIKTOK}/api/download/video"
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    endpoint,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    
                    if response.status != 200:
                        logger.error(f"TikTok API Error {response.status} — تلاش {attempt}/{MAX_RETRIES}")
                        
                        # اگه 4xx هست، retry فایده نداره
                        if response.status < 500:
                            return None
                    else:
                        data = await response.json()
                        
                        play_url = data.get("play")
                        play_watermark = data.get("play_watermark")
                        
                        if play_url:
                            logger.info(f"TikTok media downloaded successfully: {url}")
                            return {
                                "type": "video",
                                "url": play_url,
                                "caption": "🎵 TikTok Video",
                                "thumbnail": None,
                                "watermark_url": play_watermark
                            }
                        else:
                            logger.warning("No play URL found in TikTok response")
                            return None
        
        except asyncio.TimeoutError:
            logger.warning(f"TikTok API Timeout — تلاش {attempt}/{MAX_RETRIES}")
        
        except aiohttp.ClientError as e:
            logger.error(f"TikTok API Connection Error: {e} — تلاش {attempt}/{MAX_RETRIES}")
        
        except Exception as e:
            logger.error(f"Unexpected error in get_tiktok_media: {e}")
            return None
        
        # انتظار قبل از retry
        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** (attempt - 1))
            logger.info(f"🔁 {delay} ثانیه صبر میکنیم...")
            await asyncio.sleep(delay)
    
    logger.error("TikTok: همه تلاش‌ها ناموفق بود")
    return None
