# user_settings.py - نسخه جدید با SQLite
from database import get_user_mode, set_user_mode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_user_default_mode(user_id: int) -> str:
    """دریافت حالت پیشفرض کاربر"""
    return get_user_mode(user_id)

def set_user_default_mode(user_id: int, mode: str) -> bool:
    """تنظیم حالت پیشفرض کاربر"""
    if mode not in ["album", "file"]:
        return False
    set_user_mode(user_id, mode)
    return True

def get_user_settings_keyboard(user_id: int):
    """دریافت کیبورد تنظیمات"""
    current_mode = get_user_default_mode(user_id)
    
    if current_mode == "album":
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

def debug_user_settings(user_id: int):
    """نمایش تنظیمات کاربر برای دیباگ"""
    mode = get_user_default_mode(user_id)
    print(f"📊 کاربر {user_id} حالت: {mode}")
