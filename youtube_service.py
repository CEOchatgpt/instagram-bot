"""
سرویس دانلود ویدیو از یوتیوب با RapidAPI
(جایگزین yt-dlp که روی سرور بلاک میشه)
"""

import re
import aiohttp
import asyncio
import logging
from typing import Optional, Dict, Tuple

from config import YOUTUBE_RAPIDAPI_KEY

logger = logging.getLogger(__name__)

MAX_DURATION_SECS = 15 * 60  # ۱۵ دقیقه
MAX_RETRIES = 3
RETRY_DELAY = 1

RAPIDAPI_HOST_YOUTUBE = "youtube-video-fast-downloader.p.rapidapi.com"

YOUTUBE_URL_PATTERNS = [
    re.compile(r'https?://(?:www\.|m\.)?youtube\.com/watch', re.IGNORECASE),
    re.compile(r'https?://(?:www\.)?youtu\.be/[\w-]+', re.IGNORECASE),
    re.compile(r'https?://(?:www\.|m\.)?youtube\.com/shorts/[\w-]+', re.IGNORECASE),
]


def is_youtube_url(url: str) -> bool:
    return any(p.search(url) for p in YOUTUBE_URL_PATTERNS)


def format_duration(seconds: int) -> str:
    if not seconds:
        return "نامشخص"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _extract_video_id(url: str) -> Optional[str]:
    patterns = [
        r'(?:v=|youtu\.be/|shorts/)([\w-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


async def get_youtube_info(url: str) -> Optional[Dict]:
    """
    اطلاعات ویدیو رو از RapidAPI میگیره.
    خروجی: {"title", "duration", "uploader", "thumbnail", "formats", "video_id"}
    """
    video_id = _extract_video_id(url)
    if not video_id:
        logger.error(f"Could not extract video ID from: {url}")
        return None

    if not YOUTUBE_RAPIDAPI_KEY:
        logger.error("YOUTUBE_RAPIDAPI_KEY is not set!")
        return None

    headers = {
        "X-RapidAPI-Key": YOUTUBE_RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST_YOUTUBE,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://{RAPIDAPI_HOST_YOUTUBE}/",
                    headers=headers,
                    params={"id": video_id},
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 404:
                        logger.warning("YouTube video not found")
                        return None
                    if resp.status != 200:
                        logger.warning(f"YouTube API {resp.status} — attempt {attempt}")
                        if resp.status < 500:
                            return None
                    else:
                        data = await resp.json()
                        return _parse_info(data, video_id)
        except asyncio.TimeoutError:
            logger.warning(f"YouTube API timeout — attempt {attempt}")
        except Exception as e:
            logger.error(f"YouTube API error: {e}")
            return None

        if attempt < MAX_RETRIES:
            await asyncio.sleep(RETRY_DELAY * (2 ** (attempt - 1)))

    return None


def _parse_info(data: dict, video_id: str) -> Optional[Dict]:
    if not data:
        return None

    formats = []
    seen = set()

    # ساختار پاسخ این API: لیستی از لینک‌ها با quality
    for item in data.get("links", []):
        quality = str(item.get("quality", "")).replace("p", "")
        url = item.get("url", "")
        ext = item.get("extension", "mp4")

        # فقط فرمت‌های ویدیویی
        if quality.isdigit() and url and quality not in seen:
            seen.add(quality)
            formats.append({
                "quality": quality,
                "url": url,
                "ext": ext,
            })

    formats.sort(key=lambda x: int(x["quality"]), reverse=True)

    # اطلاعات اصلی
    duration = data.get("duration", 0)
    # بعضی API‌ها duration رو به صورت "MM:SS" میدن
    if isinstance(duration, str) and ":" in duration:
        parts = duration.split(":")
        if len(parts) == 2:
            duration = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            duration = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    duration = int(duration) if duration else 0

    return {
        "title": data.get("title", "ویدیوی یوتیوب"),
        "duration": duration,
        "uploader": data.get("channel", data.get("author", "نامشخص")),
        "thumbnail": data.get("thumb", data.get("thumbnail", "")),
        "formats": formats,
        "video_id": video_id,
    }


async def get_youtube_direct_url(url: str, quality: str = "720") -> Tuple[bool, str, str]:
    """
    لینک مستقیم دانلود رو برمیگردونه — بدون دانلود روی سرور.
    Returns: (موفقیت, عنوان_یا_خطا, direct_url)
    """
    info = await get_youtube_info(url)
    if not info:
        return False, "اطلاعات ویدیو دریافت نشد", ""

    formats = info.get("formats", [])
    if not formats:
        return False, "هیچ فرمتی پیدا نشد", ""

    # انتخاب بهترین کیفیت مطابق درخواست
    chosen = None
    if quality == "best":
        chosen = formats[0]
    else:
        target = int(quality)
        for f in formats:
            if int(f["quality"]) <= target:
                chosen = f
                break
        if not chosen:
            chosen = formats[-1]  # پایین‌ترین کیفیت موجود

    return True, info["title"], chosen["url"]


# برای سازگاری با bot.py — ارسال مستقیم URL به تلگرام (بدون دانلود روی سرور)
async def download_youtube_video(url: str, quality: str = "720") -> Tuple[bool, str, str]:
    """
    سازگار با bot.py — لینک مستقیم رو برمیگردونه.
    Returns: (موفقیت, عنوان, direct_url)
    """
    return await get_youtube_direct_url(url, quality)


def cleanup_file(filepath: str) -> None:
    """در این نسخه فایلی دانلود نمیشه — تابع خالی برای سازگاری"""
    pass
