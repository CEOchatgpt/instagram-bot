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
        return DATABASE_CHANNEL_REELS or DATABASE_CHANNEL_VIDEOS
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
    if not url or not url.startswith(('http://', 'https://')):
        logger.error(f"❌ لینک نامعتبر: {url}")
        return None
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as response:
                if response.status == 200:
                    data = await response.read()
                    logger.info(f"✅ دانلود شد: {len(data)} بایت از {url[:80]}...")
                    return data
                else:
                    logger.error(f"❌ خطا در دانلود: وضعیت {response.status} - {url[:80]}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"❌ تایم اوت در دانلود: {url[:80]}")
        return None
    except Exception as e:
        logger.error(f"❌ خطا در دانلود فایل: {e}")
        return None


async def save_file_to_channel(context, instagram_url: str, direct_download_url: str, media_type: str, caption: str = "") -> str:
    """
    ذخیره فایل در کانال تلگرام
    - دانلود فایل از لینک مستقیم
    - آپلود در کانال مناسب
    - ذخیره file_id در Redis
    """
    if not direct_download_url:
        logger.error(f"❌ لینک دانلود مستقیم وجود ندارد برای: {instagram_url}")
        return None
    
    if not direct_download_url.startswith(('http://', 'https://')):
        logger.error(f"❌ لینک دانلود نامعتبر: {direct_download_url}")
        return None
    
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
            logger.info(f"📦 فایل قبلاً در کش وجود دارد: {instagram_url[:50]}...")
            return existing_file_id
    
    logger.info(f"📥 دانلود فایل جدید: {instagram_url[:50]}...")
    logger.info(f"🔗 لینک دانلود: {direct_download_url[:100]}...")
    
    # دانلود فایل
    file_data = await download_file(direct_download_url)
    if not file_data:
        logger.error(f"❌ دانلود فایل ناموفق: {instagram_url[:50]}")
        return None
    
    logger.info(f"✅ دانلود کامل شد: {len(file_data)} بایت")
    
    # آپلود در کانال
    try:
        msg = None
        file_caption = f"📦 #{media_type.upper()}\n🔗 {instagram_url[:150]}"
        
        if media_type in ["video", "reel"]:
            msg = await context.bot.send_video(
                chat_id=channel_id,
                video=file_data,
                caption=file_caption[:200],
                timeout=120
            )
            if msg:
                file_id = msg.video.file_id
                logger.info(f"✅ ویدیو در کانال آپلود شد: {file_id[:30]}...")
            
        elif media_type in ["photo", "profile_pic"]:
            msg = await context.bot.send_photo(
                chat_id=channel_id,
                photo=file_data,
                caption=file_caption[:200],
                timeout=60
            )
            if msg:
                file_id = msg.photo[-1].file_id
                logger.info(f"✅ عکس در کانال آپلود شد: {file_id[:30]}...")
            
        elif media_type == "story":
            msg = await context.bot.send_video(
                chat_id=channel_id,
                video=file_data,
                caption=file_caption[:200],
                timeout=120
            )
            if msg:
                file_id = msg.video.file_id
                logger.info(f"✅ استوری در کانال آپلود شد: {file_id[:30]}...")
            
        else:
            msg = await context.bot.send_document(
                chat_id=channel_id,
                document=file_data,
                caption=file_caption[:200],
                timeout=120
            )
            if msg:
                file_id = msg.document.file_id
                logger.info(f"✅ فایل در کانال آپلود شد: {file_id[:30]}...")
        
        # ذخیره file_id در Redis
        if msg and redis_client:
            redis_client.setex(f"file_cache:{url_hash}", TTL_INDEX, file_id)
            # ذخیره متادیتا برای دیباگ
            redis_client.setex(f"file_meta:{url_hash}", TTL_INDEX, json.dumps({
                "instagram_url": instagram_url,
                "media_type": media_type,
                "created_at": time.time()
            }))
            logger.info(f"✅ فایل در Redis کش شد: {instagram_url[:50]}...")
            return file_id
            
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در آپلود به کانال: {e}")
        return None


async def send_cached_media(context, chat_id: int, instagram_url: str, media_type: str, caption: str = "") -> bool:
    """
    ارسال فایل از کش به کاربر
    اگر فایل در کش باشد، مستقیم با file_id ارسال میشود
    """
    if not redis_client:
        return False
    
    url_hash = hashlib.md5(instagram_url.encode()).hexdigest()
    file_id = redis_client.get(f"file_cache:{url_hash}")
    
    if not file_id:
        return False
    
    file_id = file_id.decode() if isinstance(file_id, bytes) else file_id
    
    try:
        if media_type in ["video", "reel"]:
            await context.bot.send_video(
                chat_id=chat_id, 
                video=file_id, 
                caption=caption or "📦 ارسال شده از آرشیو ربات (بدون مصرف API)"
            )
        elif media_type in ["photo", "profile_pic"]:
            await context.bot.send_photo(
                chat_id=chat_id, 
                photo=file_id, 
                caption=caption or "📸 ارسال شده از آرشیو ربات (بدون مصرف API)"
            )
        elif media_type == "story":
            await context.bot.send_video(
                chat_id=chat_id, 
                video=file_id, 
                caption=caption or "📖 ارسال شده از آرشیو ربات (بدون مصرف API)"
            )
        else:
            await context.bot.send_document(
                chat_id=chat_id, 
                document=file_id, 
                caption=caption or "📁 ارسال شده از آرشیو ربات (بدون مصرف API)"
            )
        
        logger.info(f"🚀 فایل از کش به کاربر {chat_id} ارسال شد: {instagram_url[:50]}...")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ خطا در ارسال فایل کش شده: {e}")
        # اگر file_id منقضی شده، کش را پاک کن
        redis_client.delete(f"file_cache:{url_hash}")
        redis_client.delete(f"file_meta:{url_hash}")
        return False


# توابع سازگاری با کدهای قدیمی
async def save_media_to_channel(context, media_url: str, media_data: dict, media_type: str = "media"):
    """نسخه سازگار با کدهای قدیمی"""
    return await save_file_to_channel(context, media_url, media_url, media_type, "")


async def get_media_from_channel(context, media_url: str, media_type: str = "media"):
    """نسخه سازگار با کدهای قدیمی"""
    return await send_cached_media(context, 0, media_url, media_type, "")
