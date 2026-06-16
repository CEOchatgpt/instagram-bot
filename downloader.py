# downloader.py - تابع دانلود فایل

import aiohttp
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# هدرهای دانلود برای شبیه‌سازی مرورگر
DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.instagram.com/",
}


async def download_media(url: str, timeout: int = 20) -> Optional[bytes]:
    """
    دانلود فایل از URL با هدرهای مناسب و بازگشت بایت‌ها
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=DOWNLOAD_HEADERS, timeout=timeout) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get('Content-Type', '')
                    # اگر محتوا HTML باشد، احتمالاً لینک اشتباه است
                    if 'text/html' in content_type:
                        logger.warning(f"URL returned HTML instead of media: {url[:100]}")
                        return None
                    return await resp.read()
                else:
                    logger.warning(f"Download failed with status {resp.status}: {url[:100]}")
                    return None
    except asyncio.TimeoutError:
        logger.warning(f"Download timeout: {url[:100]}")
        return None
    except Exception as e:
        logger.error(f"Download error: {e} for {url[:100]}")
        return None
