import yt_dlp
import logging
import asyncio
import aiohttp
from io import BytesIO

logger = logging.getLogger(__name__)

async def get_tiktok_media_yt_dlp(url: str):
    """دانلود اطلاعات تیک‌تاک با کیفیت مناسب برای تلگرام"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best[height<=720][filesize<45M]/best[height<=480]/best',  # مهم: زیر ۵۰ مگ
            'extract_flat': False,
        }

        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None, 
            lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
        )

        if not info:
            logger.error("yt-dlp: No info extracted")
            return None

        video_url = info.get('url')
        if not video_url and info.get('formats'):
            # انتخاب بهترین فرمت زیر ۵۰ مگ
            formats = [f for f in info['formats'] if f.get('filesize') or f.get('filesize_approx', 0) < 45_000_000]
            if formats:
                best = max(formats, key=lambda f: f.get('height', 0))
                video_url = best.get('url')
            else:
                best = max(info['formats'], key=lambda f: f.get('height', 0))
                video_url = best.get('url')

        if video_url:
            title = info.get('title') or info.get('description') or info.get('id', 'TikTok Video')
            return {
                "type": "video",
                "url": video_url,
                "caption": f"🎵 {title[:200]}",
                "title": title,
                "height": info.get('height')
            }

        logger.warning("No suitable video URL found")
        return None

    except Exception as e:
        logger.error(f"yt-dlp TikTok Error: {e}")
        return None


async def download_video_for_telegram(video_url: str, filename="tiktok_video.mp4"):
    """دانلود ویدیو به حافظه"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=90)) as resp:
                if resp.status != 200:
                    logger.error(f"Download failed with status: {resp.status}")
                    return None
                
                data = await resp.read()
                logger.info(f"Downloaded video size: {len(data) / (1024*1024):.2f} MB")
                
                file_obj = BytesIO(data)
                file_obj.name = filename
                return file_obj
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None
