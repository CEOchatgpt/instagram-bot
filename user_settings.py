# user_settings.py - مدیریت تنظیمات کاربران

import json
import os
from typing import Dict, Any

SETTINGS_FILE = "user_settings.json"

def load_settings() -> Dict[str, Any]:
    """بارگذاری تنظیمات کاربران از فایل"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"✅ تنظیمات بارگذاری شد: {SETTINGS_FILE}")
                print(f"   محتوا: {data}")
                return data
        else:
            print(f"⚠️ فایل {SETTINGS_FILE} وجود ندارد - فایل جدید ایجاد می‌شود")
            return {}
    except json.JSONDecodeError as e:
        print(f"❌ خطای JSON: فایل تخریب شده است: {e}")
        print(f"   فایل را حذف می‌کنم...")
        try:
            os.remove(SETTINGS_FILE)
        except:
            pass
        return {}
    except Exception as e:
        print(f"❌ خطا در بارگذاری: {e}")
        return {}

def save_settings(settings: Dict[str, Any]):
    """ذخیره تنظیمات کاربران در فایل"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        print(f"✅ تنظیمات ذخیره شد!")
        print(f"   فایل: {SETTINGS_FILE}")
        print(f"   محتوا: {settings}")
        return True
    except Exception as e:
        print(f"❌ خطا در ذخیره: {e}")
        return False

def get_user_default_mode(user_id: int) -> str:
    """
    دریافت حالت پیشفرض کاربر
    مقادیر ممکن: "album" (آلبوم ترکیبی) یا "file" (فایل)
    """
    print(f"\n🔍 درخواست حالت برای کاربر {user_id}...")
    settings = load_settings()
    user_id_str = str(user_id)
    
    if user_id_str not in settings:
        print(f"   ⚠️ کاربر {user_id} در تنظیمات نیست - استفاده از پیشفرض (album)")
        return "album"
    
    user_settings = settings.get(user_id_str, {})
    mode = user_settings.get("default_mode", "album")
    print(f"   ✅ حالت: {mode}")
    return mode

def set_user_default_mode(user_id: int, mode: str):
    """تنظیم حالت پیشفرض کاربر"""
    print(f"\n🔄 تنظیم حالت برای کاربر {user_id}: {mode}")
    
    if mode not in ["album", "file"]:
        print(f"   ❌ حالت غیر معتبر: {mode}")
        return False
    
    settings = load_settings()
    user_id_str = str(user_id)
    
    if user_id_str not in settings:
        settings[user_id_str] = {}
    
    settings[user_id_str]["default_mode"] = mode
    success = save_settings(settings)
    
    if success:
        print(f"   ✅ تنظیم موفق!")
    return success

def debug_user_settings(user_id: int):
    """نمایش تمام تنظیمات یک کاربر برای debugging"""
    print(f"\n📊 DEBUG: تنظیمات کاربر {user_id}")
    settings = load_settings()
    user_id_str = str(user_id)
    print(f"   کاربران ثبت شده: {list(settings.keys())}")
    if user_id_str in settings:
        print(f"   تنظیمات این کاربر: {settings[user_id_str]}")
    else:
        print(f"   این کاربر هنوز تنظیم نکرده")

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
