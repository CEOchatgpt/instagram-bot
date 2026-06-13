# smart_cache.py - سیستم کش هوشمند چند لایه

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
from channel_cache import save_file_to_channel as channel_save_file, send_cached_media

logger = logging.getLogger(__name__)

TTL_CHANNEL = 2592000  # 30 روز


def get_channel_for_media(media_type: str) -> str:
    """تشخیص کانال مناسب بر اساس نوع محتوا"""
    if media_type in ["video", "reel"]:
        return DATABASE_CHANNEL_REELS or DATABASE_CHANNEL_VIDEOS
    elif media_type in ["photo", "profile_pic"]:
        return DATABASE_CHANNEL_PHOTOS
    elif media_type == "profile":
        return DATABASE_CHANNEL_PROFILES
    elif media_type == "story":
        return DATABASE_CHANNEL_STORIES
    return DATABASE_CHANNEL_PHOTOS


async def save_file_to_channel(context, instagram_url: str, direct_download_url: str, media_type: str, caption: str = ""):
    """ذخیره فایل در کانال - واسط برای channel_cache"""
    if not direct_download_url:
        logger.error(f"❌ save_file_to_channel: لینک دانلود وجود ندارد برای {instagram_url[:50]}")
        return None
    
    logger.info(f"💾 ذخیره فایل در کانال: {instagram_url[:50]}... (نوع: {media_type})")
    logger.info(f"🔗 لینک دانلود: {direct_download_url[:100]}...")
    
    return await channel_save_file(
        context=context,
        instagram_url=instagram_url,
        direct_download_url=direct_download_url,
        media_type=media_type,
        caption=caption
    )


async def send_cached_media(context, chat_id: int, instagram_url: str, media_type: str, caption: str = "") -> bool:
    """ارسال فایل از کش - واسط برای channel_cache"""
    logger.info(f"🔍 بررسی کش برای: {instagram_url[:50]}...")
    return await send_cached_media(context, chat_id, instagram_url, media_type, caption)


async def get_cached_media_smart(media_key: str) -> dict:
    """دریافت از کش Redis (برای داده‌های کوچک مثل لیست ریلز)"""
    if not redis_client:
        return None
    key = f"cache:media:{hashlib.md5(media_key.encode()).hexdigest()}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None


async def set_cached_media_smart(media_key: str, media_data: dict, ttl: int = 3600):
    """ذخیره در کش Redis (برای داده‌های کوچک مثل لیست ریلز)"""
    if not redis_client:
        return
    key = f"cache:media:{hashlib.md5(media_key.encode()).hexdigest()}"
    redis_client.setex(key, ttl, json.dumps(media_data))
    logger.info(f"✅ داده در Redis کش شد: {media_key[:50]}... (TTL: {ttl}s)")


def generate_media_key(media_id: str, media_type: str) -> str:
    """تولید کلید یکتا برای هر محتوا"""
    return f"{media_type}:{media_id}"
