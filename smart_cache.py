# smart_cache.py - سیستم کش هوشمند چند لایه

import logging
import hashlib
import json
import time
from config import DATABASE_CHANNEL_VIDEOS, DATABASE_CHANNEL_REELS, DATABASE_CHANNEL_PHOTOS, DATABASE_CHANNEL_PROFILES, DATABASE_CHANNEL_STORIES
from database import redis_client

logger = logging.getLogger(__name__)

# زمان‌های انقضا (بر حسب ثانیه)
TTL_REDIS_FAST = 1800      # 30 دقیقه برای محتوای پرتکرار
TTL_REDIS_MEDIUM = 21600   # 6 ساعت برای محتوای معمولی
TTL_REDIS_SLOW = 86400     # 24 ساعت برای محتوای کم تکرار
TTL_CHANNEL = 2592000      # 30 روز برای کانال دیتابیس

# کلیدهای ایندکس در Redis
INDEX_KEY_VIDEOS = "index_videos"
INDEX_KEY_PHOTOS = "index_photos"
INDEX_KEY_PROFILES = "index_profiles"
INDEX_KEY_STORIES = "index_stories"



def get_channel_for_media(media_type: str, media_url: str = None) -> str:
    """تشخیص کانال مناسب بر اساس نوع محتوا"""
    
    if media_type == "video":
        return DATABASE_CHANNEL_VIDEOS
    elif media_type == "reel":
        return DATABASE_CHANNEL_REELS
    elif media_type == "photo":
        return DATABASE_CHANNEL_PHOTOS
    elif media_type == "profile":
        return DATABASE_CHANNEL_PROFILES
    elif media_type == "story":
        return DATABASE_CHANNEL_STORIES
    
    else:
        # تشخیص خودکار از لینک
        if media_url and ("tv" in media_url):
            return DATABASE_CHANNEL_VIDEOS
        elif media_url and("reel" in media_url):
            return DATABASE_CHANNEL_REELS
        elif media_url and ("stories" in media_url):
            return DATABASE_CHANNEL_STORIES
        else:
            return DATABASE_CHANNEL_PHOTOS


def generate_media_key(media_id: str, media_type: str) -> str:
    """تولید کلید یکتا برای هر محتوا"""
    return f"{media_type}:{media_id}"


async def save_file_to_channel(context, file_url: str, media_type: str, caption: str, media_key: str):
    """ذخیره خود فایل در کانال تلگرام (نه لینک)"""
    
    channel_id = get_channel_for_media(media_type, file_url)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای {media_type} تنظیم نشده!")
        return None
    
    try:
        msg = None
        
        if media_type in ["video"]:
            msg = await context.bot.send_video(
                chat_id=channel_id,
                video=file_url,
                caption=f"🎬 {caption[:200]}",
                timeout=60
            )
        elif media_type in ["photo", "profile_pic"]:
            msg = await context.bot.send_photo(
                chat_id=channel_id,
                photo=file_url,
                caption=f"📸 {caption[:200]}"
            )
        elif media_type == "story":
            msg = await context.bot.send_video(
                chat_id=channel_id,
                video=file_url,
                caption=f"📖 {caption[:200]}",
                timeout=60
            )
        else:
            # fallback: send as document
            msg = await context.bot.send_document(
                chat_id=channel_id,
                document=file_url,
                caption=f"📁 {caption[:200]}"
            )
        
        if msg and redis_client:
            # ذخیره ایندکس در Redis
            index_key = f"file_index:{media_key}"
            redis_client.setex(index_key, TTL_CHANNEL, str(msg.message_id))
            logger.info(f"✅ فایل {media_key} در کانال ذخیره شد (message_id: {msg.message_id})")
            
            # ذخیره اطلاعات اضافی
            info_key = f"file_info:{media_key}"
            redis_client.setex(info_key, TTL_CHANNEL, json.dumps({
                "message_id": msg.message_id,
                "channel_id": channel_id,
                "media_type": media_type,
                "created_at": time.time()
            }))
        
        return msg.message_id if msg else None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره فایل در کانال: {e}")
        return None


async def get_file_from_channel(context, media_key: str, target_chat_id: int) -> bool:
    """بازیابی فایل از کانال و ارسال مستقیم به کاربر"""
    
    if not redis_client:
        return False
    
    index_key = f"file_index:{media_key}"
    msg_id = redis_client.get(index_key)
    
    if not msg_id:
        return False
    
    # دریافت اطلاعات کانال
    info_key = f"file_info:{media_key}"
    info = redis_client.get(info_key)
    
    if info:
        info_data = json.loads(info)
        channel_id = info_data.get("channel_id")
    else:
        channel_id = get_channel_for_media("photo")  # fallback
    
    if not channel_id:
        return False
    
    try:
        await context.bot.forward_message(
            chat_id=target_chat_id,
            from_chat_id=channel_id,
            message_id=int(msg_id)
        )
        logger.info(f"📦 فایل {media_key} از کانال به کاربر {target_chat_id} ارسال شد")
        return True
        
    except Exception as e:
        logger.warning(f"⚠️ خطا در فوروارد {media_key}: {e}")
        # ایندکس خراب رو پاک کن
        redis_client.delete(index_key)
        redis_client.delete(info_key)
        return False


async def save_profile_to_channel_smart(context, username: str, profile_data: dict):
    """ذخیره هوشمند پروفایل در کانال"""
    
    channel_id = DATABASE_CHANNEL_PROFILES
    if not channel_id:
        return None
    
    media_key = generate_media_key(username, "profile")
    
    try:
        # ذخیره عکس پروفایل جداگانه
        profile_pic = profile_data.get("profile_pic")
        if profile_pic:
            await save_file_to_channel(context, profile_pic, "profile_pic", f"Profile: {username}", f"{media_key}_pic")
        
        # ذخیره اطلاعات پروفایل به صورت متن
        profile_text = json.dumps(profile_data, ensure_ascii=False)
        
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=f"📦 #PROFILE_{username.upper()}\n{profile_text[:4090]}",
            disable_web_page_preview=True
        )
        
        if msg and redis_client:
            redis_client.setex(f"profile_index:{username}", TTL_CHANNEL, str(msg.message_id))
            logger.info(f"✅ پروفایل {username} در کانال ذخیره شد")
        
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره پروفایل: {e}")
        return None


async def get_profile_from_channel_smart(context, username: str) -> dict:
    """بازیابی پروفایل از کانال"""
    
    if not redis_client:
        return None
    
    msg_id = redis_client.get(f"profile_index:{username}")
    if not msg_id:
        return None
    
    try:
        msg = await context.bot.forward_message(
            chat_id=DATABASE_CHANNEL_PROFILES,
            from_chat_id=DATABASE_CHANNEL_PROFILES,
            message_id=int(msg_id)
        )
        
        if msg.text and "📦" in msg.text:
            start = msg.text.find("{")
            end = msg.text.rfind("}")
            if start != -1 and end != -1:
                json_str = msg.text[start:end+1]
                return json.loads(json_str)
                
    except Exception as e:
        logger.warning(f"خطا در بازیابی پروفایل {username}: {e}")
        redis_client.delete(f"profile_index:{username}")
        return None


async def get_cached_media_smart(media_key: str) -> dict:
    """دریافت از کش Redis"""
    if not redis_client:
        return None
    key = f"cache:media:{hashlib.md5(media_key.encode()).hexdigest()}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None


async def set_cached_media_smart(media_key: str, media_data: dict, ttl: int = TTL_REDIS_MEDIUM):
    """ذخیره در کش Redis"""
    if not redis_client:
        return
    key = f"cache:media:{hashlib.md5(media_key.encode()).hexdigest()}"
    redis_client.setex(key, ttl, json.dumps(media_data))
    logger.info(f"✅ مدیا {media_key} در Redis کش شد (TTL: {ttl}s)")


# # پیش‌بارگذاری خودکار محتوای محبوب
# POPULAR_ACCOUNTS = ["cristiano", "leomessi", "neymarjr", "kylianmbappe"]

# async def preload_popular_content(context):
#     """پیش‌بارگذاری محتوای پیج‌های محبوب (اجرا در استارت ربات)"""
    
#     logger.info("🔄 شروع پیش‌بارگذاری محتوای محبوب...")
    
#     for username in POPULAR_ACCOUNTS:
#         # پروفایل
#         logger.info(f"📥 پیش‌بارگذاری پروفایل {username}")
#         # اینجا باید پروفایل رو از API بگیری و ذخیره کنی
#         # (اجرا فقط یک بار در روز)
    
#     logger.info("✅ پیش‌بارگذاری کامل شد")
