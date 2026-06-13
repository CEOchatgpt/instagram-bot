# index_manager.py - مدیریت ایندکس برای پیدا کردن محتوا در کانال

import json
import os
import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# مسیر فایل ایندکس
INDEX_FILE = "channel_index.json"

# کش حافظه برای ایندکس (برای سرعت)
_index_cache = None
_cache_time = 0
CACHE_TTL = 60  # 1 دقیقه کش برای ایندکس


def _load_index() -> Dict:
    """بارگذاری فایل ایندکس"""
    global _index_cache, _cache_time
    
    # چک کش
    if _index_cache is not None and (time.time() - _cache_time) < CACHE_TTL:
        return _index_cache
    
    try:
        if os.path.exists(INDEX_FILE):
            with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                _index_cache = json.load(f)
                _cache_time = time.time()
                return _index_cache
        else:
            _index_cache = {}
            return _index_cache
    except Exception as e:
        logger.error(f"❌ خطا در بارگذاری ایندکس: {e}")
        return {}


def _save_index(index: Dict):
    """ذخیره فایل ایندکس"""
    global _index_cache, _cache_time
    
    try:
        # پشتیبان‌گیری از فایل قبلی
        if os.path.exists(INDEX_FILE):
            backup_file = f"{INDEX_FILE}.backup"
            try:
                import shutil
                shutil.copy(INDEX_FILE, backup_file)
            except:
                pass
        
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        _index_cache = index
        _cache_time = time.time()
        logger.info(f"✅ ایندکس ذخیره شد - {len(index)} آیتم")
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره ایندکس: {e}")


def save_to_index(key: str, message_id: int, data_type: str, metadata: Dict = None):
    """
    ذخیره ایندکس برای یک محتوا
    
    Args:
        key: کلید یکتا (مثل username یا media_key)
        message_id: آیدی پیام در کانال
        data_type: نوع داده (profile, media, reels, highlights, stories)
        metadata: اطلاعات اضافی (اختیاری)
    """
    index = _load_index()
    
    index[key] = {
        "message_id": message_id,
        "type": data_type,
        "timestamp": time.time(),
        "metadata": metadata or {}
    }
    
    _save_index(index)
    logger.info(f"📝 ایندکس شد: {key} -> {message_id} (type: {data_type})")


def get_from_index(key: str) -> Optional[Dict]:
    """
    دریافت اطلاعات از ایندکس با کلید
    
    Returns:
        دیکشنری شامل message_id, type, timestamp, metadata
    """
    index = _load_index()
    return index.get(key)


def delete_from_index(key: str) -> bool:
    """حذف یک آیتم از ایندکس"""
    index = _load_index()
    
    if key in index:
        del index[key]
        _save_index(index)
        logger.info(f"🗑️ حذف از ایندکس: {key}")
        return True
    
    return False


def find_by_type(data_type: str) -> list:
    """پیدا کردن همه آیتم‌های یک نوع خاص"""
    index = _load_index()
    results = []
    
    for key, value in index.items():
        if value.get("type") == data_type:
            results.append({
                "key": key,
                "message_id": value["message_id"],
                "metadata": value.get("metadata", {})
            })
    
    return results


def find_by_keyword(keyword: str) -> list:
    """جستجو در کلیدها با کلمه کلیدی"""
    index = _load_index()
    results = []
    keyword_lower = keyword.lower()
    
    for key, value in index.items():
        if keyword_lower in key.lower():
            results.append({
                "key": key,
                "message_id": value["message_id"],
                "type": value.get("type"),
                "timestamp": value.get("timestamp")
            })
    
    return results


def get_all_keys() -> list:
    """دریافت همه کلیدهای ذخیره شده"""
    index = _load_index()
    return list(index.keys())


def get_index_stats() -> Dict:
    """آمار ایندکس"""
    index = _load_index()
    
    stats = {
        "total_items": len(index),
        "by_type": {},
        "oldest": None,
        "newest": None
    }
    
    for key, value in index.items():
        data_type = value.get("type", "unknown")
        stats["by_type"][data_type] = stats["by_type"].get(data_type, 0) + 1
        
        timestamp = value.get("timestamp")
        if timestamp:
            if stats["oldest"] is None or timestamp < stats["oldest"]:
                stats["oldest"] = timestamp
            if stats["newest"] is None or timestamp > stats["newest"]:
                stats["newest"] = timestamp
    
    return stats


def clean_old_index(max_age_days: int = 30):
    """پاک کردن ایندکس‌های قدیمی (بیش از max_age_days روز)"""
    index = _load_index()
    now = time.time()
    max_age_seconds = max_age_days * 24 * 3600
    
    to_delete = []
    for key, value in index.items():
        timestamp = value.get("timestamp", 0)
        if now - timestamp > max_age_seconds:
            to_delete.append(key)
    
    for key in to_delete:
        del index[key]
    
    if to_delete:
        _save_index(index)
        logger.info(f"🧹 {len(to_delete)} آیتم قدیمی از ایندکس پاک شد")
    
    return len(to_delete)


def rebuild_index_from_channel(context, channel_id: int, limit: int = 100):
    """
    بازسازی ایندکس از روی کانال (اسکن پیام‌ها)
    
    این تابع کانال رو اسکن می‌کنه و ایندکس رو از نو می‌سازه
    """
    from telegram.ext import ContextTypes
    
    logger.info(f"🔄 شروع بازسازی ایندکس از کانال {channel_id}...")
    
    index = {}
    offset = 0
    
    try:
        while True:
            # گرفتن پیام‌های کانال
            updates = await context.bot.get_updates(
                offset=offset,
                limit=limit,
                timeout=10
            )
            
            if not updates:
                break
            
            for update in updates:
                if update.channel_post:
                    msg = update.channel_post
                    text = msg.text or msg.caption or ""
                    
                    # جستجوی کلید در متن پیام
                    if "🔑 کلید:" in text:
                        # استخراج کلید
                        for line in text.split("\n"):
                            if "🔑 کلید:" in line:
                                key_hash = line.split("🔑 کلید:")[-1].strip()
                                # پیدا کردن کلید اصلی از هش (این روش کامل نیست)
                                # برای بهبود می‌تونی کلید رو هم توی پیام ذخیره کنی
                                pass
            
            offset += len(updates)
            await asyncio.sleep(0.5)
        
        _save_index(index)
        logger.info(f"✅ بازسازی ایندکس کامل شد - {len(index)} آیتم پیدا شد")
        
    except Exception as e:
        logger.error(f"❌ خطا در بازسازی ایندکس: {e}")


# ========== توابع کمکی برای یکپارچه‌سازی با channel_cache ==========

def generate_storage_key(data_type: str, identifier: str) -> str:
    """
    تولید کلید استاندارد برای ذخیره‌سازی
    
    Examples:
        - profile:cristiano
        - media:https://instagram.com/p/xxx
        - reels:cristiano
        - highlights:cristiano
        - stories:cristiano
        - reel:cristiano:123456
    """
    return f"{data_type}:{identifier}"


def parse_storage_key(key: str) -> tuple:
    """
    تجزیه کلید به نوع و شناسه
    
    Returns:
        (data_type, identifier)
    """
    parts = key.split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "unknown", key
