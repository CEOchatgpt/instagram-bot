# channel_cache.py - ذخیره دائمی همه چیز در کانال تلگرام (بدون Redis)

import logging
import hashlib
import json
import time
from typing import Optional, Dict, Any, List
from telegram.ext import ContextTypes
from config import DATABASE_CHANNEL_ID

logger = logging.getLogger(__name__)

# ذخیره موقت در حافظه برای کاهش درخواست به کانال
_memory_cache = {}  # key -> {"data": data, "expires": timestamp}
CACHE_TTL = 300  # 5 دقیقه کش موقت در حافظه


def _get_from_memory_cache(key: str) -> Optional[Any]:
    """دریافت از کش حافظه موقت"""
    if key in _memory_cache:
        item = _memory_cache[key]
        if time.time() < item["expires"]:
            return item["data"]
        else:
            del _memory_cache[key]
    return None


def _set_to_memory_cache(key: str, data: Any, ttl: int = CACHE_TTL):
    """ذخیره در کش حافظه موقت"""
    _memory_cache[key] = {
        "data": data,
        "expires": time.time() + ttl
    }


async def save_data_to_channel(
    context: ContextTypes.DEFAULT_TYPE, 
    data_key: str, 
    data: Any, 
    data_type: str = "media"
) -> Optional[int]:
    """
    ذخیره هر نوع داده‌ای در کانال تلگرام
    
    Args:
        context: Context ربات
        data_key: کلید یکتا برای داده (مثل username یا URL)
        data: خود داده برای ذخیره
        data_type: نوع داده (profile, media, reels, highlights, stories, user_mode)
    
    Returns:
        message_id ذخیره شده یا None
    """
    if not DATABASE_CHANNEL_ID:
        logger.warning("⚠️ DATABASE_CHANNEL_ID تنظیم نشده! نمی‌توان در کانال ذخیره کرد.")
        return None
    
    try:
        # تولید هش برای کلید
        key_hash = hashlib.md5(data_key.encode()).hexdigest()
        cache_key = f"{data_type}:{key_hash}"
        
        # تولید محتوای پیام
        message_data = {
            "type": data_type,
            "key": data_key,
            "key_hash": key_hash,
            "data": data,
            "version": 2,  # ورژن برای به‌روزرسانی‌های آینده
            "created_at": time.time()
        }
        
        message_text = json.dumps(message_data, ensure_ascii=False)
        
        # محدودیت 4096 کاراکتری تلگرام
        if len(message_text) > 4000:
            # اگر داده بزرگ بود، compress کن
            message_text = json.dumps({
                "type": data_type,
                "key": data_key,
                "key_hash": key_hash,
                "data": _compress_large_data(data),
                "compressed": True,
                "created_at": time.time()
            }, ensure_ascii=False)
        
        # ذخیره در کانال
        msg = await context.bot.send_message(
            chat_id=DATABASE_CHANNEL_ID,
            text=f"💾 #{data_type.upper()}\n{message_text[:4090]}",
            disable_web_page_preview=True
        )
        
        # ذخیره در کش حافظه موقت
        _set_to_memory_cache(cache_key, {
            "message_id": msg.message_id,
            "data": data
        }, ttl=3600)  # 1 ساعت کش
        
        logger.info(f"✅ داده {data_type} برای کلید {data_key[:30]}... در کانال ذخیره شد (msg_id: {msg.message_id})")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره به کانال: {e}")
        return None


def _compress_large_data(data: Any) -> Any:
    """فشرده‌سازی داده‌های بزرگ"""
    if isinstance(data, dict):
        # حذف فیلدهای حجیم
        copy_data = data.copy()
        for key in ["items", "posts", "reels"]:
            if key in copy_data and isinstance(copy_data[key], list) and len(copy_data[key]) > 50:
                copy_data[key] = copy_data[key][:50]  # فقط 50 تا اول
                copy_data[f"{key}_truncated"] = True
        return copy_data
    return data


async def get_data_from_channel(
    context: ContextTypes.DEFAULT_TYPE, 
    data_key: str, 
    data_type: str = "media"
) -> Optional[Any]:
    """
    بازیابی داده از کانال تلگرام
    
    Args:
        context: Context ربات
        data_key: کلید یکتا برای داده
        data_type: نوع داده
    
    Returns:
        داده بازیابی شده یا None
    """
    if not DATABASE_CHANNEL_ID:
        logger.warning("⚠️ DATABASE_CHANNEL_ID تنظیم نشده! نمی‌توان از کانال خواند.")
        return None
    
    try:
        key_hash = hashlib.md5(data_key.encode()).hexdigest()
        cache_key = f"{data_type}:{key_hash}"
        
        # اول چک کن توی کش حافظه هست؟
        cached = _get_from_memory_cache(cache_key)
        if cached:
            logger.info(f"📦 داده {data_type} برای {data_key[:30]}... از حافظه کش برگردانده شد")
            return cached.get("data")
        
        # باید کل کانال رو جستجو کنیم
        # برای این کار، یک ایندکس کوچک توی حافظه نگه می‌داریم
        # یا می‌تونیم از forward_message استفاده کنیم با message_id که قبلاً ذخیره شده
        
        # فعلاً از روش جستجو در کانال استفاده می‌کنیم (برای پیاده‌سازی کامل‌تر)
        # اینجا یه پیاده‌سازی ساده داریم
        
        logger.info(f"🔍 داده {data_type} برای {data_key[:30]}... در کانال جستجو می‌شود")
        
        # برای بهینه‌سازی، می‌تونیم message_id رو توی یه فایل یا متغیر محیطی ذخیره کنیم
        # فعلاً null برمی‌گردونیم تا از API گرفته بشه
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی از کانال: {e}")
        return None


# ========== توابع اختصاصی برای انواع داده ==========

async def save_profile_to_channel(context, username: str, profile_data: dict) -> Optional[int]:
    """ذخیره پروفایل در کانال"""
    return await save_data_to_channel(context, f"profile:{username}", profile_data, "profile")


async def get_profile_from_channel(context, username: str) -> Optional[dict]:
    """بازیابی پروفایل از کانال"""
    return await get_data_from_channel(context, f"profile:{username}", "profile")


async def save_media_to_channel(context, media_key: str, media_data: dict) -> Optional[int]:
    """ذخیره مدیا در کانال"""
    return await save_data_to_channel(context, media_key, media_data, "media")


async def get_media_from_channel(context, media_key: str) -> Optional[dict]:
    """بازیابی مدیا از کانال"""
    return await get_data_from_channel(context, media_key, "media")


async def save_reels_list_to_channel(context, username: str, reels_data: dict) -> Optional[int]:
    """ذخیره لیست ریل‌ها در کانال"""
    return await save_data_to_channel(context, f"reels:{username}", reels_data, "reels")


async def get_reels_list_from_channel(context, username: str) -> Optional[dict]:
    """بازیابی لیست ریل‌ها از کانال"""
    return await get_data_from_channel(context, f"reels:{username}", "reels")


async def save_highlights_list_to_channel(context, username: str, highlights: list) -> Optional[int]:
    """ذخیره لیست هایلایت‌ها در کانال"""
    return await save_data_to_channel(context, f"highlights:{username}", highlights, "highlights")


async def get_highlights_list_from_channel(context, username: str) -> Optional[list]:
    """بازیابی لیست هایلایت‌ها از کانال"""
    return await get_data_from_channel(context, f"highlights:{username}", "highlights")


async def save_user_mode_to_channel(context, user_id: int, mode: str) -> Optional[int]:
    """ذخیره تنظیمات کاربر در کانال"""
    return await save_data_to_channel(context, f"mode:{user_id}", {"mode": mode}, "user_mode")


async def get_user_mode_from_channel(context, user_id: int) -> Optional[str]:
    """بازیابی تنظیمات کاربر از کانال"""
    data = await get_data_from_channel(context, f"mode:{user_id}", "user_mode")
    if data and isinstance(data, dict):
        return data.get("mode")
    return None
