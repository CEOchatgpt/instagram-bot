"""
سرویس دانلود ویدیو از یوتیوب برای ربات تلگرام
سازگار با ساختار bot.py (async / await)
"""

import os
import re
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Tuple, List

import yt_dlp

logger = logging.getLogger(__name__)

# ── تنظیمات ──────────────────────────────────────────────────
DOWNLOAD_PATH = Path("downloads")
DOWNLOAD_PATH.mkdir(exist_ok=True)

# حداکثر مدت مجاز ویدیو (ثانیه) — ۱۵ دقیقه
MAX_DURATION_SECS = 15 * 60

# الگوهای URL یوتیوب
YOUTUBE_URL_PATTERNS = [
    re.compile(r'https?://(?:www\.|m\.)?youtube\.com/watch', re.IGNORECASE),
    re.compile(r'https?://(?:www\.)?youtu\.be/[\w-]+', re.IGNORECASE),
    re.compile(r'https?://(?:www\.|m\.)?youtube\.com/shorts/[\w-]+', re.IGNORECASE),
    re.compile(r'https?://music\.youtube\.com/watch', re.IGNORECASE),
]

# تنظیمات پایه yt-dlp
BASE_OPTS: Dict = {
    'quiet': True,
    'no_warnings': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'user_agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
}


# ── Validation ────────────────────────────────────────────────

def is_youtube_url(url: str) -> bool:
    """بررسی معتبر بودن لینک یوتیوب"""
    return any(p.search(url) for p in YOUTUBE_URL_PATTERNS)


# ── توابع sync (اجرا در thread pool) ─────────────────────────

def _fetch_info(url: str) -> Optional[Dict]:
    """
    اطلاعات ویدیو رو بدون دانلود برمیگردونه (sync).
    شامل: عنوان، مدت، uploader، thumbnail، کیفیت‌های موجود
    """
    try:
        with yt_dlp.YoutubeDL(BASE_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            # کیفیت‌های ویدیویی معتبر
            formats: List[Dict] = []
            for f in info.get('formats', []):
                h = f.get('height')
                if h and h >= 360:
                    size = f.get('filesize') or f.get('filesize_approx') or 0
                    formats.append({
                        'quality': str(h),
                        'ext': f.get('ext', 'mp4'),
                        'filesize_mb': round(size / (1024 * 1024), 1) if size else None,
                    })

            # حذف تکراری‌ها و مرتب‌سازی نزولی
            seen = set()
            unique_formats = []
            for f in sorted(formats, key=lambda x: int(x['quality']), reverse=True):
                if f['quality'] not in seen:
                    seen.add(f['quality'])
                    unique_formats.append(f)

            return {
                'title': info.get('title', 'ویدیوی بدون عنوان'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader') or info.get('channel', 'نامشخص'),
                'thumbnail': info.get('thumbnail', ''),
                'formats': unique_formats,
            }
    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp DownloadError in _fetch_info: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in _fetch_info: {e}")
        return None


def _download_video(url: str, quality: str) -> Tuple[bool, str, str]:
    """
    ویدیو رو دانلود میکنه و مسیر فایل رو برمیگردونه (sync).
    Returns: (موفقیت, پیام, مسیر_فایل)
    """
    timestamp = int(time.time())
    outtmpl = str(DOWNLOAD_PATH / f"yt_{timestamp}_%(title).60s.%(ext)s")

    quality_formats = {
        'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best',
        '1080': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]',
        '720':  'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
        '480':  'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]',
        '360':  'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]',
        'audio': 'bestaudio/best',
    }

    is_audio = (quality == 'audio')
    fmt = quality_formats.get(quality, quality_formats['720'])

    ydl_opts: Dict = {
        **BASE_OPTS,
        'format': fmt,
        'outtmpl': outtmpl,
        'merge_output_format': 'mp3' if is_audio else 'mp4',
    }

    if is_audio:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                return False, "اطلاعات ویدیو دریافت نشد", ""

            # پیدا کردن فایل دانلود‌شده
            filepath = ydl.prepare_filename(info)

            # اگه پسوند عوض شده (merge) چک میکنیم
            if not os.path.exists(filepath):
                for ext in ('.mp4', '.mp3', '.webm', '.mkv', '.m4a'):
                    candidate = Path(filepath).with_suffix(ext)
                    if candidate.exists():
                        filepath = str(candidate)
                        break

            if not os.path.exists(filepath):
                return False, "فایل دانلود‌شده پیدا نشد", ""

            title = info.get('title', 'ویدیو')
            return True, title, filepath

    except yt_dlp.utils.DownloadError as e:
        logger.error(f"yt-dlp DownloadError: {e}")
        return False, str(e), ""
    except Exception as e:
        logger.error(f"Unexpected error in _download_video: {e}")
        return False, str(e), ""


# ── توابع async (استفاده در bot.py) ──────────────────────────

async def get_youtube_info(url: str) -> Optional[Dict]:
    """
    اطلاعات ویدیو رو async برمیگردونه.
    مثال خروجی:
    {
        "title": "...",
        "duration": 245,
        "uploader": "...",
        "thumbnail": "https://...",
        "formats": [{"quality": "1080", "ext": "mp4", "filesize_mb": 85.2}, ...]
    }
    """
    return await asyncio.to_thread(_fetch_info, url)


async def download_youtube_video(url: str, quality: str = '720') -> Tuple[bool, str, str]:
    """
    ویدیو رو async دانلود میکنه.
    
    Args:
        url: لینک یوتیوب
        quality: کیفیت — 'best', '1080', '720', '480', '360', 'audio'
    
    Returns:
        (موفقیت, عنوان_یا_خطا, مسیر_فایل)
    """
    return await asyncio.to_thread(_download_video, url, quality)


def cleanup_file(filepath: str) -> None:
    """فایل رو بعد از ارسال پاک میکنه"""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Cleaned up: {filepath}")
    except Exception as e:
        logger.warning(f"Could not delete file {filepath}: {e}")


def format_duration(seconds: int) -> str:
    """مدت زمان رو به فرمت خوانا تبدیل میکنه"""
    if not seconds:
        return "نامشخص"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
