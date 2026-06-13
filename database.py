# database.py - با پشتیبانی از ذخیره تنظیمات در کانال تلگرام

import os
import json
import hashlib
import logging
import time
from typing import Optional, Dict, Any
from config import DATABASE_CHANNEL_ID
from index_manager import save_to_index, get_from_index, generate_storage_key

logger = logging.getLogger(__name__)

# کش حافظه برای تنظیمات کاربر (برای سرعت)
_user_settings_cache = {}  # user_id -> {"mode": mode, "expires": timestamp}
CACHE_TTL = 3600  # 1 ساعت


def _get_cache(user_id: int) -> Optional[str]:
    """دریافت از کش حافظه"""
    if user_id in _user_settings_cache:
        item = _user_settings_cache[user_id]
        if time.time() < item["expires"]:
            return item["mode"]
        else:
            del _user_settings_cache[user_id]
    return None


def _set_cache(user_id: int, mode: str):
    """ذخیره در کش حافظه"""
    _user_settings_cache[user_id] = {
        "mode": mode,
        "expires": time.time() + CACHE_TTL
    }


async def get_user_mode(user_id: int, context=None) -> str:
    """
    دریافت حالت کاربر از کش یا کانال تلگرام
    
    Returns:
        'album' یا 'file'
    """
    
    # 1️⃣ چک کش حافظه
    cached = _get_cache(user_id)
    if cached:
        logger.debug(f"📦 حالت کاربر {user_id} از کش: {cached}")
        return cached
    
    # 2️⃣ چک کانال تلگرام (اگه context داریم)
    if context and DATABASE_CHANNEL_ID:
        try:
            storage_key = generate_storage_key("user_setting", str(user_id))
            index_data = get_from_index(storage_key)
            
            if index_data:
                message_id = index_data.get("message_id")
                if message_id:
                    # فوروارد پیام برای خوندن محتوا
                    msg = await context.bot.forward_message(
                        chat_id=DATABASE_CHANNEL_ID,
                        from_chat_id=DATABASE_CHANNEL_ID,
                        message_id=message_id
                    )
                    
                    # استخراج حالت از کپشن
                    if msg.caption or msg.text:
                        text = msg.caption or msg.text
                        if "حالت: album" in text:
                            mode = "album"
                        elif "حالت: file" in text:
                            mode = "file"
                        else:
                            mode = "album"
                        
                        _set_cache(user_id, mode)
                        logger.info(f"🏦 حالت کاربر {user_id} از کانال: {mode}")
                        return mode
        except Exception as e:
            logger.warning(f"خطا در خواندن تنظیمات کاربر از کانال: {e}")
    
    # 3️⃣ پیش‌فرض
    logger.info(f"🆕 حالت پیش‌فرض album برای کاربر {user_id}")
    return "album"


async def set_user_mode(user_id: int, mode: str, context=None) -> bool:
    """
    ذخیره حالت کاربر در کش و کانال تلگرام
    
    Args:
        user_id: آیدی کاربر
        mode: 'album' یا 'file'
        context: Context از telegram.ext (برای دسترسی به بات)
    
    Returns:
        True اگر موفق بود، False اگر ناموفق
    """
    
    if mode not in ["album", "file"]:
        logger.warning(f"❌ حالت نامعتبر: {mode}")
        return False
    
    # 1️⃣ ذخیره در کش حافظه
    _set_cache(user_id, mode)
    logger.info(f"💾 حالت کاربر {user_id} در کش ذخیره شد: {mode}")
    
    # 2️⃣ ذخیره در کانال تلگرام (اگه context داریم)
    if context and DATABASE_CHANNEL_ID:
        try:
            storage_key = generate_storage_key("user_setting", str(user_id))
            
            # متن پیام برای ذخیره در کانال
            mode_text = "🎬 آلبوم ترکیبی" if mode == "album" else "📁 فایل جداگانه"
            
            message_text = f"""⚙️ <b>تنظیمات کاربر</b>
━━━━━━━━━━━━━━━━
👤 کاربر: {user_id}
🎯 حالت: {mode}
📝 توضیح: {mode_text}

🔑 کلید: {storage_key}
💾 ذخیره: {time.strftime('%Y/%m/%d %H:%M:%S')}"""
            
            # حذف پیام قبلی (اگه وجود داشته باشه)
            existing = get_from_index(storage_key)
            if existing:
                try:
                    await context.bot.delete_message(
                        chat_id=DATABASE_CHANNEL_ID,
                        message_id=existing["message_id"]
                    )
                    logger.info(f"🗑️ پیام قبلی تنظیمات کاربر {user_id} حذف شد")
                except Exception as e:
                    logger.warning(f"خطا در حذف پیام قبلی: {e}")
            
            # ارسال پیام جدید
            msg = await context.bot.send_message(
                chat_id=DATABASE_CHANNEL_ID,
                text=message_text,
                parse_mode='HTML'
            )
            
            # ذخیره در ایندکس
            save_to_index(storage_key, msg.message_id, "user_setting", {
                "user_id": user_id,
                "mode": mode
            })
            
            logger.info(f"✅ تنظیمات کاربر {user_id} در کانال ذخیره شد (mode: {mode})")
            return True
            
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره تنظیمات کاربر در کانال: {e}")
            return False
    
    # اگه context نداشتیم، فقط در کش ذخیره شد
    return True


# ========== توابع کمکی برای سازگاری با کد قبلی ==========

def get_user_mode_from_memory(user_id: int) -> str:
    """
    دریافت حالت از حافظه موقت (برای سازگاری با کد قبلی)
    این تابع فقط از کش میخونه، نه از کانال
    """
    cached = _get_cache(user_id)
    return cached if cached in ["album", "file"] else "album"


def init_db():
    """آماده‌سازی - فقط لاگ میندازه"""
    logger.info("✅ دیتابیس با پشتیبانی از ذخیره تنظیمات در کانال راه‌اندازی شد")
