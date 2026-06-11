# user_settings.py - مدیریت تنظیمات کاربران

import json
import os
from typing import Dict, Any

SETTINGS_FILE = "user_settings.json"

def load_settings() -> Dict[str, Any]:
    """بارگذاری تنظیمات کاربران از فایل"""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_settings(settings: Dict[str, Any]):
    """ذخیره تنظیمات کاربران در فایل"""
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

def get_user_default_mode(user_id: int) -> str:
    """
    دریافت حالت پیشفرض کاربر
    مقادیر ممکن: "album" (آلبوم ترکیبی) یا "file" (فایل)
    """
    settings = load_settings()
    user_settings = settings.get(str(user_id), {})
    return user_settings.get("default_mode", "album")  # پیشفرض آلبوم

def set_user_default_mode(user_id: int, mode: str):
    """تنظیم حالت پیشفرض کاربر"""
    settings = load_settings()
    user_id_str = str(user_id)
    
    if user_id_str not in settings:
        settings[user_id_str] = {}
    
    settings[user_id_str]["default_mode"] = mode
    save_settings(settings)

def get_user_settings_keyboard(user_id: int):
    """دریافت کیبورد تنظیمات بر اساس وضعیت فعلی کاربر"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
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
