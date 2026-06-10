import yt_dlp
import logging
from io import BytesIO
import asyncio

logger = logging.getLogger(__name__)

async def get_tiktok_media_yt_dlp(url: str):
    """
    دانلود اطلاعات تیک‌تاک با yt-dlp (بدون واترمارک در بیشتر موارد)
    """
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'format': 'best[height<=1080]',  # کیفیت خوب (تا 1080p)
            # 'format': 'best',               # بهترین کیفیت موجود
        }

        # چون yt-dlp بلاک‌کننده است، در ترد جدا اجرا می‌کنیم
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False))

        if not info:
            return None

        # استخراج بهترین لینک ویدیو
        video_url = info.get('url') or info.get('original_url')
        
        if not video_url and info.get('formats'):
            # اگر url مستقیم نبود، بهترین فرمت رو انتخاب کن
            best_format = max(info['formats'], key=lambda f: f.get('height', 0) or 0)
            video_url = best_format.get('url')

        if video_url:
            return {
                "type": "video",
                "url": video_url,
                "caption": info.get('title') or info.get('description') or "🎵 TikTok Video",
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration')
            }
        
        logger.warning("No video URL found with yt-dlp")
        return None

    except Exception as e:
        logger.error(f"yt-dlp TikTok Error: {e}")
        return None
