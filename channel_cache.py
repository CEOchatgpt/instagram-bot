# channel_cache.py - ذخیره دائمی در کانال تلگرام

import logging
import hashlib
import json
from telegram.ext import ContextTypes
from config import DATABASE_CHANNEL_ID

logger = logging.getLogger(__name__)

# کلیدهای ذخیره‌سازی در Redis (برای ایندکس)
INDEX_KEY = "channel_index"
PROFILE_INDEX_KEY = "channel_profile_index"

async def save_media_to_channel(context: ContextTypes.DEFAULT_TYPE, media_url: str, media_data: dict, media_type: str = "media"):
    """ذخیره محتوای مدیا در کانال تلگرام و ایندکس در Redis"""
    
    if not DATABASE_CHANNEL_ID:
        return None
    
    try:
        # تولید کلید یکتا برای این محتوا
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        
        # ایجاد متن پیام برای ذخیره در کانال
        message_text = json.dumps({
            "type": media_type,
            "url": media_url,
            "data": media_data,
            "hash": url_hash,
            "created_at": time.time()
        }, ensure_ascii=False)
        
        # ذخیره در کانال
        msg = await context.bot.send_message(
            chat_id=DATABASE_CHANNEL_ID,
            text=f"📦 #{media_type.upper()}\n{message_text[:3800]}",  # محدودیت 4096 کاراکتر
            disable_web_page_preview=True
        )
        
        # ذخیره ایندکس در Redis
        from database import redis_client
        if redis_client:
            # ایندکس اصلی
            redis_client.hset(INDEX_KEY, url_hash, str(msg.message_id))
            # ایندکس بر اساس نوع
            redis_client.sadd(f"channel:{media_type}_index", url_hash)
            # زمان انقضا برای ایندکس (۳۰ روز)
            redis_client.expire(INDEX_KEY, 2592000)
        
        logger.info(f"✅ محتوا در کانال ذخیره شد (message_id: {msg.message_id})")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره به کانال: {e}")
        return None

async def get_media_from_channel(context: ContextTypes.DEFAULT_TYPE, media_url: str):
    """بازیابی محتوا از کانال با استفاده از ایندکس Redis"""
    
    if not DATABASE_CHANNEL_ID:
        return None
    
    try:
        from database import redis_client
        
        if not redis_client:
            return None
        
        # پیدا کردن message_id از ایندکس
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        message_id = redis_client.hget(INDEX_KEY, url_hash)
        
        if not message_id:
            return None
        
        # تبدیل به int
        message_id = int(message_id)
        
        # گرفتن پیام از کانال
        try:
            msg = await context.bot.forward_message(
                chat_id=DATABASE_CHANNEL_ID,  # از خود کانال
                from_chat_id=DATABASE_CHANNEL_ID,
                message_id=message_id
            )
            
            # استخراج دیتا از متن پیام
            if msg.text and msg.text.startswith("📦"):
                json_part = msg.text.split("\n", 1)[1]
                data = json.loads(json_part)
                return data.get("data")
                
        except Exception as e:
            logger.warning(f"پیام {message_id} در کانال یافت نشد: {e}")
            # ایندکس خراب رو پاک کن
            redis_client.hdel(INDEX_KEY, url_hash)
            return None
            
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی از کانال: {e}")
        return None

async def save_profile_to_channel(context, username: str, profile_data: dict):
    """ذخیره پروفایل در کانال تلگرام"""
    from config import DATABASE_CHANNEL_ID
    
    if not DATABASE_CHANNEL_ID:
        return None
    
    try:
        # تولید یک کلید یکتا برای این پروفایل
        import time
        import hashlib
        
        # ایجاد محتوای پیام با ساختار بهتر
        message_data = {
            "type": "profile",
            "username": username,
            "data": profile_data,
            "created_at": time.time()
        }
        
        # هش برای بررسی یکتا بودن
        data_hash = hashlib.md5(json.dumps(profile_data, sort_keys=True).encode()).hexdigest()
        
        # چک کن قبلاً این پروفایل ذخیره شده؟
        if redis_client:
            existing = redis_client.get(f"channel_profile_hash:{username}")
            if existing and existing.decode() == data_hash:
                logger.info(f"📦 پروفایل {username} قبلاً در کانال ذخیره شده، اسکیپ")
                return None
        
        # ارسال پیام به کانال
        message_text = f"📦 #PROFILE_{username.upper()}\n{json.dumps(message_data, ensure_ascii=False)}"
        
        msg = await context.bot.send_message(
            chat_id=DATABASE_CHANNEL_ID,
            text=message_text[:4090],
            disable_web_page_preview=True
        )
        
        # ذخیره ایندکس در Redis
        if redis_client:
            redis_client.setex(f"channel_profile:{username}", 2592000, str(msg.message_id))
            redis_client.setex(f"channel_profile_hash:{username}", 2592000, data_hash)
        
        logger.info(f"✅ پروفایل {username} در کانال دیتابیس ذخیره شد (message_id: {msg.message_id})")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره پروفایل {username} در کانال: {e}")
        return None


async def get_profile_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str):
    """بازیابی پروفایل از کانال"""
    result = await get_media_from_channel(context, f"profile:{username}")
    return result

# نیاز به import time
import time
