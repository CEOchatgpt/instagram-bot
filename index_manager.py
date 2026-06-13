# index_manager.py - نسخه اصلاح شده بدون خطا

import json
import os
import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

INDEX_FILE = "channel_index.json"
_index_cache = None
_cache_time = 0
CACHE_TTL = 60


def _load_index() -> Dict:
    """بارگذاری فایل ایندکس"""
    global _index_cache, _cache_time
    
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
        logger.error(f"خطا در بارگذاری ایندکس: {e}")
        return {}


def _save_index(index: Dict):
    """ذخیره فایل ایندکس"""
    global _index_cache, _cache_time
    
    try:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        _index_cache = index
        _cache_time = time.time()
        logger.info(f"✅ ایندکس ذخیره شد - {len(index)} آیتم")
    except Exception as e:
        logger.error(f"خطا در ذخیره ایندکس: {e}")


def save_to_index(key: str, message_id: int, data_type: str, metadata: Dict = None):
    """ذخیره ایندکس برای یک محتوا"""
    index = _load_index()
    
    index[key] = {
        "message_id": message_id,
        "type": data_type,
        "timestamp": time.time(),
        "metadata": metadata or {}
    }
    
    _save_index(index)
    logger.info(f"📝 ایندکس: {key} -> {message_id}")


def get_from_index(key: str) -> Optional[Dict]:
    """دریافت اطلاعات از ایندکس با کلید"""
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

def search_by_media_id(media_id: str) -> dict:
    index = _load_index()
    for key, value in index.items():
        if value.get('metadata', {}).get('media_id') == media_id:
            return value
        if media_id in key:
            return value
    return None

def generate_storage_key(data_type: str, identifier: str) -> str:
    """تولید کلید استاندارد برای ذخیره‌سازی"""
    return f"{data_type}:{identifier}"


def parse_storage_key(key: str) -> tuple:
    """تجزیه کلید به نوع و شناسه"""
    parts = key.split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "unknown", key
