# channel_cache.py - ذخیره دائمی در کانال‌های تخصصی تلگرام

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
    if media_type == "video":
        return DATABASE_CHANNEL_VIDEOS
    elif media_type == "reel":
        return DATABASE_CHANNEL_REELS
    elif media_type == "photo" or media_type == "profile_pic":
        return DATABASE_CHANNEL_PHOTOS
    elif media_type == "profile":
        return DATABASE_CHANNEL_PROFILES
    elif media_type == "story":
        return DATABASE_CHANNEL_STORIES
    else:
        return DATABASE_CHANNEL_PHOTOS  # fallback


async def save_media_to_channel(context: ContextTypes.DEFAULT_TYPE, media_url: str, media_data: dict, media_type: str = "media"):
    """ذخیره محتوای مدیا در کانال تلگرام و ایندکس در Redis"""
    
    channel_id = get_channel_for_type(media_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای {media_type} تنظیم نشده!")
        return None
    
    try:
        # تولید کلید یکتا برای این محتوا
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        
        # چک کن قبلاً ذخیره شده؟
        if redis_client and redis_client.exists(f"channel_media:{url_hash}"):
            logger.info(f"📦 مدیا قبلاً در کانال ذخیره شده، اسکیپ")
            return None
        
        # ایجاد متن پیام برای ذخیره در کانال
        message_data = {
            "type": media_type,
            "url": media_url,
            "data": media_data,
            "hash": url_hash,
            "created_at": time.time()
        }
        
        message_text = json.dumps(message_data, ensure_ascii=False)
        
        # ذخیره در کانال
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=f"📦 #{media_type.upper()}\n{message_text[:3800]}",
            disable_web_page_preview=True
        )
        
        # ذخیره ایندکس در Redis
        if redis_client:
            redis_client.setex(f"channel_media:{url_hash}", 2592000, str(msg.message_id))
            redis_client.sadd(f"channel:{media_type}_index", url_hash)
            logger.info(f"✅ مدیا در Redis ایندکس شد (message_id: {msg.message_id})")
        
        logger.info(f"✅ محتوا در کانال {channel_id} ذخیره شد")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره به کانال: {e}")
        return None


async def get_media_from_channel(context: ContextTypes.DEFAULT_TYPE, media_url: str, media_type: str = "media"):
    """بازیابی محتوا از کانال با استفاده از ایندکس Redis"""
    
    channel_id = get_channel_for_type(media_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای {media_type} تنظیم نشده!")
        return None
    
    if not redis_client:
        logger.warning("⚠️ redis_client در دسترس نیست!")
        return None
    
    try:
        # پیدا کردن message_id از ایندکس
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        message_id = redis_client.get(f"channel_media:{url_hash}")
        
        if not message_id:
            return None
        
        message_id = int(message_id)
        
        # گرفتن پیام از کانال
        try:
            msg = await context.bot.forward_message(
                chat_id=channel_id,
                from_chat_id=channel_id,
                message_id=message_id
            )
            
            # استخراج دیتا از متن پیام
            if msg.text and "📦" in msg.text:
                start = msg.text.find("{")
                end = msg.text.rfind("}")
                if start != -1 and end != -1:
                    json_str = msg.text[start:end+1]
                    data = json.loads(json_str)
                    return data.get("data")
                    
        except Exception as e:
            logger.warning(f"پیام {message_id} در کانال یافت نشد: {e}")
            if redis_client:
                redis_client.delete(f"channel_media:{url_hash}")
            return None
            
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی از کانال: {e}")
        return None


async def save_profile_to_channel(context, username: str, profile_data: dict):
    """ذخیره پروفایل در کانال تلگرام"""
    
    channel_id = DATABASE_CHANNEL_PROFILES
    if not channel_id:
        logger.warning("⚠️ DATABASE_CHANNEL_PROFILES تنظیم نشده!")
        return None
    
    if not redis_client:
        logger.warning("⚠️ redis_client در دسترس نیست!")
        return None
    
    try:
        data_hash = hashlib.md5(json.dumps(profile_data, sort_keys=True).encode()).hexdigest()
        
        existing = redis_client.get(f"channel_profile_hash:{username}")
        if existing and existing.decode() == data_hash:
            logger.info(f"📦 پروفایل {username} قبلاً در کانال ذخیره شده، اسکیپ")
            return None
        
        message_data = {
            "type": "profile",
            "username": username,
            "data": profile_data,
            "created_at": time.time()
        }
        
        message_text = json.dumps(message_data, ensure_ascii=False)
        
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=f"📦 #PROFILE_{username.upper()}\n{message_text[:4090]}",
            disable_web_page_preview=True
        )
        
        redis_client.setex(f"channel_profile:{username}", 2592000, str(msg.message_id))
        redis_client.setex(f"channel_profile_hash:{username}", 2592000, data_hash)
        
        logger.info(f"✅ پروفایل {username} در کانال دیتابیس ذخیره شد")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره پروفایل {username}: {e}")
        return None


async def get_profile_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str):
    """بازیابی پروفایل از کانال تلگرام"""
    
    channel_id = DATABASE_CHANNEL_PROFILES
    if not channel_id:
        logger.warning("⚠️ DATABASE_CHANNEL_PROFILES تنظیم نشده!")
        return None
    
    if not redis_client:
        logger.warning("⚠️ redis_client در دسترس نیست!")
        return None
    
    try:
        message_id = redis_client.get(f"channel_profile:{username}")
        if not message_id:
            return None
        
        message_id = int(message_id)
        
        try:
            msg = await context.bot.forward_message(
                chat_id=channel_id,
                from_chat_id=channel_id,
                message_id=message_id
            )
            
            if msg.text and "📦" in msg.text:
                start = msg.text.find("{")
                end = msg.text.rfind("}")
                if start != -1 and end != -1:
                    json_str = msg.text[start:end+1]
                    data = json.loads(json_str)
                    return data.get("data")
                    
        except Exception as e:
            logger.warning(f"پیام {message_id} برای پروفایل {username} یافت نشد: {e}")
            redis_client.delete(f"channel_profile:{username}")
            redis_client.delete(f"channel_profile_hash:{username}")
            return None
            
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی پروفایل {username}: {e}")
        return None
