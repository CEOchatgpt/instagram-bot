# database.py - بدون Redis، فقط کانال تلگرام
import os
import json
import hashlib
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# این فایل فقط یک لایه انتزاعی ساده است
# داده‌ها مستقیماً در channel_cache.py ذخیره می‌شن

# برای rate limiting از دیکشنری ساده استفاده می‌کنیم
# (در محیط Production می‌تونی از Redis فقط برای rate limit استفاده کنی)
_rate_limit_storage = {}  # user_id -> list of timestamps

def get_user_mode(user_id: int) -> str:
    """دریافت حالت کاربر - از channel_cache می‌خوانیم"""
    # فعلاً fallback روی album
    # در ورژن بعدی می‌تونیم از کانال هم بخونیم
    return "album"

def set_user_mode(user_id: int, mode: str):
    """ذخیره حالت کاربر - در کانال ذخیره می‌کنیم"""
    if mode not in ["album", "file"]:
        return
    # اینجا می‌تونیم توی کانال ذخیره کنیم
    # برای سادگی فعلاً توی دیکشنری می‌ذاریم
    _rate_limit_storage[f"mode_{user_id}"] = mode
    logger.info(f"✅ حالت کاربر {user_id} به {mode} تغییر کرد (ذخیره در حافظه موقت)")

def get_user_mode_from_memory(user_id: int) -> str:
    """دریافت حالت از حافظه موقت"""
    mode = _rate_limit_storage.get(f"mode_{user_id}")
    return mode if mode in ["album", "file"] else "album"

def init_db():
    """آماده‌سازی - فقط لاگ میندازه"""
    logger.info("✅ دیتابیس در حالت بدون Redis راه‌اندازی شد (تنها کانال تلگرام)")
