# channel_cache.py - ذخیره دائمی خود فایل‌ها در کانال‌های تخصصی تلگرام

import logging
import hashlib
import json
import time
import aiohttp
import asyncio
from telegram.ext import ContextTypes
from config import (
    DATABASE_CHANNEL_VIDEOS, 
    DATABASE_CHANNEL_REELS, 
    DATABASE_CHANNEL_PHOTOS, 
    DATABASE_CHANNEL_PROFILES, 
    DATABASE_CHANNEL_STORIES
)
from database import redis_client

logger = logging.getLogger(__name__)

# زمان ذخیره ایندکس در Redis (30 روز)
TTL_INDEX = 2592000


def get_channel_for_type(media_type: str) -> str:
    """دریافت کانال مناسب بر اساس نوع محتوا"""
    if media_type in ["video", "reel"]:
        return DATABASE_CHANNEL_VIDEOS
    elif media_type in ["photo", "profile_pic"]:
        return DATABASE_CHANNEL_PHOTOS
    elif media_type == "profile":
        return DATABASE_CHANNEL_PROFILES
    elif media_type == "story":
        return DATABASE_CHANNEL_STORIES
    else:
        return DATABASE_CHANNEL_PHOTOS


async def download_file(url: str) -> bytes:
    """دانلود فایل از لینک مستقیم"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    logger.error(f"خطا در دانلود: وضعیت {response.status}")
                    return None
    except Exception as e:
        logger.error(f"خطا در دانلود فایل: {e}")
        return None


async def save_file_to_channel(context, file_url: str, media_type: str, caption: str, instagram_url: str) -> str:
    """
    دانلود فایل و آپلود در کانال تلگرام
    برگرداندن file_id برای استفاده بعدی
    """
    channel_id = get_channel_for_type(media_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای {media_type} تنظیم نشده!")
        return None
    
    # کلید یکتا بر اساس لینک اینستاگرام
    url_hash = hashlib.md5(instagram_url.encode()).hexdigest()
    
    # چک کن قبلاً ذخیره شده؟
    if redis_client:
        existing_file_id = redis_client.get(f"file_cache:{url_hash}")
        if existing_file_id:
            existing_file_id = existing_file_id.decode() if isinstance(existing_file_id, bytes) else existing_file_id
            logger.info(f"📦 فایل قبلاً در کش وجود دارد: {existing_file_id[:20]}...")
            return existing_file_id
    
    # دانلود فایل
    logger.info(f"📥 در حال دانلود فایل از: {file_url[:100]}...")
    file_data = await download_file(file_url)
    if not file_data:
        logger.error(f"❌ دانلود فایل ناموفق بود")
        return None
    
    logger.info(f"✅ دانلود کامل شد: {len(file_data)} بایت")
    
    # آپلود در کانال
    try:
        msg = None
        file_caption = f"📦 #{media_type.upper()}\n🔗 {instagram_url[:100]}"
        
        if media_type in ["video", "reel", "story"]:
            msg = await context.bot.send_video(
                chat_id=channel_id,
                video=file_data,
                caption=file_caption[:200],
                timeout=120
            )
            file_id = msg.video.file_id
            
        elif media_type in ["photo", "profile_pic"]:
            msg = await context.bot.send_photo(
                chat_id=channel_id,
                photo=file_data,
                caption=file_caption[:200],
                timeout=60
            )
            file_id = msg.photo[-1].file_id
            
        else:
            msg = await context.bot.send_document(
                chat_id=channel_id,
                document=file_data,
                caption=file_caption[:200],
                timeout=120
            )
            file_id = msg.document.file_id
        
        # ذخیره file_id در Redis
        if msg and redis_client:
            redis_client.setex(f"file_cache:{url_hash}", TTL_INDEX, file_id)
            redis_client.setex(f"file_meta:{url_hash}", TTL_INDEX, json.dumps({
                "media_type": media_type,
                "instagram_url": instagram_url,
                "created_at": time.time()
            }))
            logger.info(f"✅ فایل در کانال ذخیره شد. File ID: {file_id[:30]}...")
            return file_id
            
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در آپلود به کانال: {e}")
        return None


async def get_file_from_cache(context, instagram_url: str, media_type: str, target_chat_id: int, caption: str = "") -> bool:
    """
    بازیابی فایل از کش و ارسال مستقیم به کاربر
    برگرداندن True اگر موفق بود
    """
    if not redis_client:
        return False
    
    url_hash = hashlib.md5(instagram_url.encode()).hexdigest()
    file_id = redis_client.get(f"file_cache:{url_hash}")
    
    if not file_id:
        return False
    
    file_id = file_id.decode() if isinstance(file_id, bytes) else file_id
    
    try:
        # ارسال مستقیم با file_id (فوق‌العاده سریع)
        if media_type in ["video", "reel", "story"]:
            await context.bot.send_video(
                chat_id=target_chat_id, 
                video=file_id, 
                caption=caption or "📦 ارسال شده از آرشیو ربات"
            )
        elif media_type in ["photo", "profile_pic"]:
            await context.bot.send_photo(
                chat_id=target_chat_id, 
                photo=file_id, 
                caption=caption or "📸 ارسال شده از آرشیو ربات"
            )
        else:
            await context.bot.send_document(
                chat_id=target_chat_id, 
                document=file_id, 
                caption=caption or "📁 ارسال شده از آرشیو ربات"
            )
        
        logger.info(f"🚀 فایل از کش به کاربر {target_chat_id} ارسال شد")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ خطا در ارسال فایل کش شده: {e}")
        # ایندکس خراب رو پاک کن
        redis_client.delete(f"file_cache:{url_hash}")
        return False


# برای سازگاری با کدهای قبلی
async def save_media_to_channel(context, media_url: str, media_data: dict, media_type: str = "media"):
    """نسخه سازگار با کدهای قدیمی"""
    return await save_file_to_channel(context, media_url, media_type, "", media_url)


async def send_cached_media(context, chat_id: int, instagram_url: str, media_type: str, caption: str = "") -> bool:
    """نسخه سازگار با کدهای قدیمی"""
    return await get_file_from_cache(context, instagram_url, media_type, chat_id, caption)
