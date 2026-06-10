import yt_dlp
import logging
import asyncio
import aiohttp
from io import BytesIO

logger = logging.getLogger(__name__)

async def get_tiktok_media_yt_dlp(url: str):
    """دانلود تیک‌تاک با yt-dlp + آماده‌سازی برای ارسال"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best[height<=1080]/best',
        }

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
        )

        if not info:
            return None

        video_url = info.get('url')
        if not video_url and info.get('formats'):
            best_format = max(info['formats'], key=lambda f: f.get('height', 0) or 0)
            video_url = best_format.get('url')

        if not video_url:
            return None

        title = info.get('title') or info.get('description') or "TikTok Video"

        return {
            "type": "video",
            "url": video_url,           # لینک مستقیم
            "caption": f"🎵 {title}",
            "title": title,
            "thumbnail": info.get('thumbnail')
        }

    except Exception as e:
        logger.error(f"yt-dlp Error: {e}")
        return None


async def download_video_for_telegram(video_url: str, filename="tiktok_video.mp4"):
    """دانلود ویدیو به حافظه و آماده کردن برای ارسال"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=60) as resp:
                if resp.status != 200:
                    logger.error(f"Download failed: {resp.status}")
                    return None
                data = await resp.read()
                file_obj = BytesIO(data)
                file_obj.name = filename
                return file_obj
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None
