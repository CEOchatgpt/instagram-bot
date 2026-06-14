# database.py - نسخه بدون کش حافظه (فقط کانال تلگرام)

import logging
import time
from typing import Optional
from config import USER_SETTING_CHANNEL_ID
from index_manager import save_to_index, get_from_index, generate_storage_key
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def get_user_mode(user_id: int, context=None) -> str:
    """
    دریافت حالت کاربر از کانال تلگرام
    
    اولویت: کانال تلگرام > پیش‌فرض (album)
    """
    
    # کانال تلگرام (دائمی)
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
                    
                    logger.info(f"🏦 حالت کاربر {user_id} از کانال: {mode}")
                    return mode
        except Exception as e:
            logger.warning(f"خطا در خواندن تنظیمات از کانال: {e}")
    
    # پیش‌فرض
    logger.info(f"🆕 حالت پیش‌فرض album برای کاربر {user_id}")
    return "album"


async def set_user_mode(user_id: int, mode: str, context=None) -> bool:
    """
    ذخیره حالت کاربر در کانال تلگرام
    """
    
    if mode not in ["album", "file"]:
        logger.warning(f"❌ حالت نامعتبر: {mode}")
        return False
    
    # ذخیره در کانال
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
    
    return False


def get_user_settings_keyboard(user_id: int):
    """
    دریافت کیبورد تنظیمات
    توجه: این تابع sync است و mode رو از حافظه نمی‌خونه
    برای نمایش حالت فعلی، باید از طریق کش در bot.py مدیریت بشه
    """
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 آلبوم ترکیبی", callback_data="set_mode_album")],
        [InlineKeyboardButton("📁 فایل جداگانه", callback_data="set_mode_file")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])
    return keyboard


def get_user_settings_keyboard_with_mode(mode: str):
    """
    دریافت کیبورد تنظیمات با نمایش حالت فعال
    mode: 'album' یا 'file'
    """
    if mode == "album":
        album_text = "✅ آلبوم ترکیبی (فعال)"
        file_text = "📁 فایل جداگانه"
    else:
        album_text = "🎬 آلبوم ترکیبی"
        file_text = "✅ فایل جداگانه (فعال)"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(album_text, callback_data="set_mode_album")],
        [InlineKeyboardButton(file_text, callback_data="set_mode_file")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")]
    ])
    return keyboard


def init_db():
    logger.info("✅ دیتابیس یکپارچه راه‌اندازی شد")
