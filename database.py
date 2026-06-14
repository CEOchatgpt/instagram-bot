# database.py - نسخه یکپارچه با پشتیبانی از کش حافظه و کانال

import logging
import time
from typing import Optional
from config import USER_SETTING_CHANNEL_ID
from index_manager import save_to_index, get_from_index, generate_storage_key
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# کش حافظه برای سرعت
_user_cache = {}  # user_id -> {"mode": mode, "expires": timestamp}
CACHE_TTL = 3600  # 1 ساعت


def _get_cache(user_id: int) -> Optional[str]:
    """دریافت از کش حافظه"""
    if user_id in _user_cache:
        item = _user_cache[user_id]
        if time.time() < item["expires"]:
            return item["mode"]
        else:
            del _user_cache[user_id]
    return None


def _set_cache(user_id: int, mode: str):
    """ذخیره در کش حافظه"""
    _user_cache[user_id] = {
        "mode": mode,
        "expires": time.time() + CACHE_TTL
    }


async def get_user_mode(user_id: int, context=None) -> str:
    """
    دریافت حالت کاربر از کش یا کانال
    
    اولویت: کش حافظه > کانال تلگرام > پیش‌فرض (album)
    """
    
    # 1️⃣ کش حافظه (سریع)
    cached = _get_cache(user_id)
    if cached:
        logger.debug(f"📦 حالت کاربر {user_id} از کش: {cached}")
        return cached
    
    # 2️⃣ کانال تلگرام (دائمی)
    if context and USER_SETTING_CHANNEL_ID:
        try:
            storage_key = generate_storage_key("user_setting", str(user_id))
            index_data = await get_from_index(storage_key)
            
            if index_data:
                message_id = index_data.get("message_id")
                if message_id:
                    msg = await context.bot.forward_message(
                        chat_id=USER_SETTING_CHANNEL_ID,
                        from_chat_id=USER_SETTING_CHANNEL_ID,
                        message_id=message_id
                    )
                    
                    text = msg.caption or msg.text or ""
                    if "حالت: file" in text or "mode: file" in text:
                        mode = "file"
                    else:
                        mode = "album"
                    
                    _set_cache(user_id, mode)
                    logger.info(f"🏦 حالت کاربر {user_id} از کانال: {mode}")
                    return mode
        except Exception as e:
            logger.warning(f"خطا در خواندن تنظیمات از کانال: {e}")
    
    # 3️⃣ پیش‌فرض
    logger.info(f"🆕 حالت پیش‌فرض album برای کاربر {user_id}")
    return "album"


async def set_user_mode(user_id: int, mode: str, context=None) -> bool:
    """
    ذخیره حالت کاربر در کش و کانال
    """
    
    if mode not in ["album", "file"]:
        logger.warning(f"❌ حالت نامعتبر: {mode}")
        return False
    
    # 1️⃣ ذخیره در کش
    _set_cache(user_id, mode)
    logger.info(f"💾 حالت کاربر {user_id} در کش: {mode}")
    
    # 2️⃣ ذخیره در کانال
    if context and USER_SETTING_CHANNEL_ID:
        try:
            storage_key = generate_storage_key("user_setting", str(user_id))
            
            mode_text = "🎬 آلبوم ترکیبی" if mode == "album" else "📁 فایل جداگانه"
            mode_en = "album" if mode == "album" else "file"
            
            message_text = f"""⚙️ <b>تنظیمات کاربر</b>
━━━━━━━━━━━━━━━━
👤 کاربر: {user_id}
🎯 حالت: {mode_en}
📝 توضیح: {mode_text}

🔑 کلید: {storage_key}
💾 ذخیره: {time.strftime('%Y/%m/%d %H:%M:%S')}"""
            
            # حذف پیام قبلی
            existing = await get_from_index(storage_key)
            if existing:
                try:
                    await context.bot.delete_message(
                        chat_id=USER_SETTING_CHANNEL_ID,
                        message_id=existing["message_id"]
                    )
                except:
                    pass
            
            # ارسال پیام جدید
            msg = await context.bot.send_message(
                chat_id=USER_SETTING_CHANNEL_ID,
                text=message_text,
                parse_mode='HTML'
            )
            
            await save_to_index(storage_key, msg.message_id, "user_setting", {
                "user_id": user_id,
                "mode": mode
            })
            
            logger.info(f"✅ تنظیمات کاربر {user_id} در کانال ذخیره شد: {mode}")
            return True
            
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره در کانال: {e}")
            return False
    
    return True


def get_user_settings_keyboard(user_id: int):
    """دریافت کیبورد تنظیمات (برای استفاده در bot.py)"""
    
    # اینجا باید از get_user_mode استفاده کنی ولی نمی‌تونی async باشه
    # برای حل این مشکل، mode رو از کش میخونیم یا از پارامتر میگیریم
    
    # به صورت همزمان (synchronous) از کش میخونیم
    mode = _get_cache(user_id)
    if not mode:
        mode = "album"  # پیش‌فرض موقت
    
    if mode == "album":
        album_text = "✅ آلبوم ترکیبی (فعال)"
        file_text = "📁 فایل"
    else:
        album_text = "🎬 آلبوم ترکیبی"
        file_text = "✅ فایل (فعال)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(album_text, callback_data="set_mode_album")],
        [InlineKeyboardButton(file_text, callback_data="set_mode_file")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])
    return keyboard


# ========== برای سازگاری با کد قدیمی ==========

def get_user_mode_from_memory(user_id: int) -> str:
    """فقط برای سازگاری - از کش میخونه"""
    cached = _get_cache(user_id)
    return cached if cached in ["album", "file"] else "album"


def init_db():
    logger.info("✅ دیتابیس یکپارچه راه‌اندازی شد")
