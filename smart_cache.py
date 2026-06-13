# smart_cache.py - سیستم کش هوشمند چند لایه و ذخیره فایل

import logging
import hashlib
import json
import time
from config import (
    DATABASE_CHANNEL_VIDEOS, 
    DATABASE_CHANNEL_REELS, 
    DATABASE_CHANNEL_PHOTOS, 
    DATABASE_CHANNEL_PROFILES, 
    DATABASE_CHANNEL_STORIES
)
from database import redis_client

logger = logging.getLogger(__name__)

TTL_CHANNEL = 2592000      # ۳۰ روز برای ماندگاری در ردیس

def get_channel_for_media(media_type: str) -> str:
    """تشخیص کانال مناسب بر اساس نوع محتوا"""
    if media_type in ["video", "reel"]:
        return DATABASE_CHANNEL_VIDEOS
    elif media_type in ["photo", "profile_pic"]:
        return DATABASE_CHANNEL_PHOTOS
    elif media_type == "profile":
        return DATABASE_CHANNEL_PROFILES
    elif media_type == "story":
        return DATABASE_CHANNEL_STORIES
    return DATABASE_CHANNEL_PHOTOS


async def send_cached_media(context, chat_id: int, instagram_url: str, media_type: str) -> bool:
    """
    بررسی می‌کند آیا این لینک قبلاً دانلود و در کانال آپلود شده یا نه.
    اگر بود، خود فایل را مستقیماً برای کاربر می‌فرستد و True برمی‌گرداند.
    """
    if not redis_client:
        return False
        
    try:
        # تولید یک کلید یکتا بر اساس لینک پست اینستاگرام
        url_hash = hashlib.md5(instagram_url.encode()).hexdigest()
        file_id = redis_client.get(f"file_cache:{url_hash}")
        
        if not file_id:
            return False  # فایل در کش پیدا نشد
            
        file_id = file_id.decode() if isinstance(file_id, bytes) else file_id
        
        # ارسال مستقیم و آنی فایل به کاربر با استفاده از file_id تلگرام
        if media_type in ["video", "reel", "story"]:
            await context.bot.send_video(chat_id=chat_id, video=file_id, caption="🎬 ارسال شده از آرشیو ربات (بدون مصرف اپی‌آی)")
        elif media_type in ["photo", "profile_pic"]:
            await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption="📸 ارسال شده از آرشیو ربات (بدون مصرف اپی‌آی)")
        else:
            await context.bot.send_document(chat_id=chat_id, document=file_id, caption="📁 ارسال شده از آرشیو ربات")
            
        logger.info(f"🚀 فایل از طریق file_id به کاربر {chat_id} ارسال شد.")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ خطا در ارسال فایل کش شده: {e}")
        return False


async def save_file_to_channel(context, instagram_url: str, direct_download_url: str, media_type: str):
    """
    خود فایل را از لینک دانلود مستقیم می‌گیرد، در کانال آپلود می‌کند و file_id را در ردیس ذخیره می‌کند.
    """
    channel_id = get_channel_for_media(media_type)
    if not channel_id:
        return None
    
    try:
        url_hash = hashlib.md5(instagram_url.encode()).hexdigest()
        msg = None
        caption = f"📦 #{media_type.upper()}\n🔗 Hash: {url_hash}"
        
        # آپلود فایل در کانال تلگرام
        if media_type in ["video", "reel", "story"]:
            msg = await context.bot.send_video(chat_id=channel_id, video=direct_download_url, caption=caption, timeout=90)
            file_id = msg.video.file_id
        elif media_type in ["photo", "profile_pic"]:
            msg = await context.bot.send_photo(chat_id=channel_id, photo=direct_download_url, caption=caption, timeout=60)
            file_id = msg.photo[-1].file_id
        else:
            msg = await context.bot.send_document(chat_id=channel_id, document=direct_download_url, caption=caption, timeout=90)
            file_id = msg.document.file_id
        
        # ذخیره شناسه فایل در ردیس برای دفعات بعدی
        if msg and redis_client:
            redis_client.setex(f"file_cache:{url_hash}", TTL_CHANNEL, str(file_id))
            logger.info(f"✅ فایل در کانال ذخیره و در ردیس با موفقیت کش شد.")
            return file_id
            
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره فایل در کانال: {e}")
        return None
