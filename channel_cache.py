# channel_cache.py - ذخیره دائمی خود فایل‌ها در کانال‌های تخصصی تلگرام

import logging
import hashlib
import json
import time
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


def get_channel_for_type(media_type: str) -> str:
    """دریافت کانال مناسب بر اساس نوع محتوا"""
    if media_type in ["video", "reel"]:
        return DATABASE_CHANNEL_VIDEOS  # می‌توانی ریلز و ویدیو را تفکیک کنی یا در یک کانال بریزی
    elif media_type in ["photo", "profile_pic"]:
        return DATABASE_CHANNEL_PHOTOS
    elif media_type == "profile":
        return DATABASE_CHANNEL_PROFILES
    elif media_type == "story":
        return DATABASE_CHANNEL_STORIES
    else:
        return DATABASE_CHANNEL_PHOTOS  # fallback


async def save_media_to_channel(context: ContextTypes.DEFAULT_TYPE, media_url: str, media_data: dict, media_type: str = "media"):
    """ذخیره خود فایل (عکس/ویدیو) در کانال تلگرام و ایندکس کردن file_id در Redis"""
    
    channel_id = get_channel_for_type(media_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای {media_type} تنظیم نشده!")
        return None
    
    try:
        # تولید کلید یکتا بر اساس URL اصلی یا ID پست اینستاگرام
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        
        # بررسی اینکه آیا قبلاً کش شده یا خیر
        if redis_client:
            existing_file_id = redis_client.get(f"file_cache:{url_hash}")
            if existing_file_id:
                logger.info(f"📦 فایل قبلاً در کانال ذخیره و در Redis موجود است.")
                return existing_file_id.decode() if isinstance(existing_file_id, bytes) else existing_file_id
        
        msg = None
        caption = f"📦 #{media_type.upper()}\n🔗 Original URL Hash: {url_hash}"
        
        # ارسال خود فایل به کانال بر اساس نوع محتوا
        if media_type in ["video", "reel", "story"]:
            msg = await context.bot.send_video(
                chat_id=channel_id,
                video=media_url,  # تلگرام خودش فایل را از این لینک دانلود و آپلود میکند
                caption=caption,
                timeout=90
            )
            file_id = msg.video.file_id
            
        elif media_type in ["photo", "profile_pic"]:
            msg = await context.bot.send_photo(
                chat_id=channel_id,
                photo=media_url,
                caption=caption,
                timeout=60
            )
            file_id = msg.photo[-1].file_id  # گرفتن باکیفیت‌ترین نسخه عکس
            
        else:
            # Fallback به صورت سند
            msg = await context.bot.send_document(
                chat_id=channel_id,
                document=media_url,
                caption=caption,
                timeout=90
            )
            file_id = msg.document.file_id

        # ذخیره ایندکس و file_id در Redis (با TTL طولانی مثلاً ۳۰ روز)
        if msg and redis_client:
            # ذخیره file_id برای ارسال‌های بعدی
            redis_client.setex(f"file_cache:{url_hash}", 2592000, str(file_id))
            # ذخیره ساختار قدیمی برای اینکه بقیه کدهات نشکنه (اختیاری)
            redis_client.setex(f"channel_media:{url_hash}", 2592000, str(msg.message_id))
            
            logger.info(f"✅ فایل با موفقیت آپلود و در Redis کش شد. File ID: {file_id[:15]}...")
            return file_id
            
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در آپلود و ذخیره فایل در کانال: {e}")
        return None


async def send_cached_media(context: ContextTypes.DEFAULT_TYPE, chat_id: int, media_url: str, media_type: str, caption: str = "") -> bool:
    """ارسال مستقیم فایل کش شده به کاربر با استفاده از file_id بدون مصرف آپلود سرور"""
    if not redis_client:
        return False
        
    try:
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        file_id = redis_client.get(f"file_cache:{url_hash}")
        
        if not file_id:
            return False  # کش موجود نیست، باید از API اینستاگرام گرفته شود
            
        file_id = file_id.decode() if isinstance(file_id, bytes) else file_id
        
        # ارسال بسیار سریع به کاربر با استفاده از file_id نیتیو تلگرام
        if media_type in ["video", "reel", "story"]:
            await context.bot.send_video(chat_id=chat_id, video=file_id, caption=caption)
        elif media_type in ["photo", "profile_pic"]:
            await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
        else:
            await context.bot.send_document(chat_id=chat_id, document=file_id, caption=caption)
            
        logger.info(f"🚀 فایل کش شده با موفقیت به کاربر {chat_id} ارسال شد (از طریق file_id)")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ خطا در ارسال فایل کش شده (احتمالاً file_id منقضی یا نامعتبر شده): {e}")
        # پاک کردن کش خراب از ردیس تا در ریکوئست بعدی دوباره دانلود شود
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        redis_client.delete(f"file_cache:{url_hash}")
        return False
