# user_settings.py - بدون Redis

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ذخیره موقت تنظیمات در حافظه
_user_modes = {}  # user_id -> mode

def get_user_default_mode(user_id: int) -> str:
    """دریافت حالت پیشفرض کاربر از حافظه"""
    return _user_modes.get(user_id, "album")

def set_user_default_mode(user_id: int, mode: str) -> bool:
    """تنظیم حالت پیشفرض کاربر در حافظه"""
    if mode not in ["album", "file"]:
        return False
    _user_modes[user_id] = mode
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
