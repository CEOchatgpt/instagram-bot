# index_manager.py - نسخه با قفل فایل (Thread-Safe)

import json
import os
import logging
import time
import fcntl
import asyncio
from typing import Optional, Dict, Any
from functools import wraps

logger = logging.getLogger(__name__)

INDEX_FILE = "channel_index.json"
_index_cache = None
_cache_time = 0
CACHE_TTL = 60

# قفل برای جلوگیری از همزمانی
_write_lock = asyncio.Lock()


def _sync_wrapper(func):
    """تبدیل تابع همزمان به ناهمزمان با قفل"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with _write_lock:
            return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper


def _load_index_sync() -> Dict:
    """بارگذاری فایل ایندکس (همزمان - Thread-safe)"""
    global _index_cache, _cache_time
    
    # چک کش
    if _index_cache is not None and (time.time() - _cache_time) < CACHE_TTL:
        return _index_cache
    
    try:
        if os.path.exists(INDEX_FILE):
            with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                # قفل اشتراکی برای خوندن
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                try:
                    _index_cache = json.load(f)
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                _cache_time = time.time()
                return _index_cache
        else:
            _index_cache = {}
            return _index_cache
    except Exception as e:
        logger.error(f"خطا در بارگذاری ایندکس: {e}")
        return {}


def _save_index_sync(index: Dict):
    """ذخیره فایل ایندکس (همزمان - Thread-safe با قفل انحصاری)"""
    global _index_cache, _cache_time
    
    # ایجاد بکاپ قبل از ذخیره
    if os.path.exists(INDEX_FILE):
        try:
            backup_file = f"{INDEX_FILE}.backup"
            with open(INDEX_FILE, 'r', encoding='utf-8') as f_src:
                with open(backup_file, 'w', encoding='utf-8') as f_dst:
                    f_dst.write(f_src.read())
        except Exception as e:
            logger.warning(f"خطا در ایجاد بکاپ: {e}")
    
    try:
        # اول ذخیره در فایل موقت
        temp_file = f"{INDEX_FILE}.tmp"
        with open(temp_file, 'w', encoding='utf-8') as f:
            # قفل انحصاری برای نوشتن
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                json.dump(index, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        
        # جایگزینی اتمیک (atomic replace)
        os.replace(temp_file, INDEX_FILE)
        
        _index_cache = index
        _cache_time = time.time()
        logger.info(f"✅ ایندکس ذخیره شد - {len(index)} آیتم")
        
        # حذف بکاپ قدیمی بعد از ذخیره موفق
        backup_file = f"{INDEX_FILE}.backup"
        if os.path.exists(backup_file):
            try:
                os.remove(backup_file)
            except:
                pass
                
    except Exception as e:
        logger.error(f"خطا در ذخیره ایندکس: {e}")
        # تلاش برای بازیابی از بکاپ
        backup_file = f"{INDEX_FILE}.backup"
        if os.path.exists(backup_file):
            try:
                os.replace(backup_file, INDEX_FILE)
                logger.info(f"✅ ایندکس از بکاپ بازیابی شد")
            except:
                logger.error(f"❌ خطا در بازیابی از بکاپ")


# ========== توابع عمومی با قفل ==========

async def save_to_index(key: str, message_id: int, data_type: str, channel_id: int, metadata: Dict = None):
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
        
        index[key] = {
            "message_id": message_id,
            "channel_id": channel_id,  # اضافه شد
            "type": data_type,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        
        await asyncio.to_thread(_save_index_sync, index)
        logger.info(f"📝 ایندکس: {key} -> {message_id}")


async def get_from_index(key: str) -> Optional[Dict]:
    """دریافت از ایندکس (فقط خواندن - نیازی به قفل نیست)"""
    index = await asyncio.to_thread(_load_index_sync)
    return index.get(key)


async def delete_from_index(key: str) -> bool:
    """حذف از ایندکس با قفل"""
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
        
        if key in index:
            del index[key]
            await asyncio.to_thread(_save_index_sync, index)
            logger.info(f"🗑️ حذف از ایندکس: {key}")
            return True
        
        return False


async def find_by_type(data_type: str) -> list:
    """پیدا کردن با نوع (فقط خواندن)"""
    index = await asyncio.to_thread(_load_index_sync)
    results = []
    
    for key, value in index.items():
        if value.get("type") == data_type:
            results.append({
                "key": key,
                "message_id": value["message_id"],
                "metadata": value.get("metadata", {})
            })
    
    return results


async def find_by_keyword(keyword: str) -> list:
    """جستجو با کلمه کلیدی (فقط خواندن)"""
    index = await asyncio.to_thread(_load_index_sync)
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


async def get_all_keys() -> list:
    """دریافت همه کلیدها (فقط خواندن)"""
    index = await asyncio.to_thread(_load_index_sync)
    return list(index.keys())


async def get_index_stats() -> Dict:
    """آمار ایندکس (فقط خواندن)"""
    index = await asyncio.to_thread(_load_index_sync)
    
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


async def clean_old_index(max_age_days: int = 30):
    """پاک کردن ایندکس‌های قدیمی با قفل"""
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
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
            await asyncio.to_thread(_save_index_sync, index)
            logger.info(f"🧹 {len(to_delete)} آیتم قدیمی از ایندکس پاک شد")
        
        return len(to_delete)


async def search_by_media_id(media_id: str) -> dict:
    """جستجو با شناسه مدیا (فقط خواندن)"""
    index = await asyncio.to_thread(_load_index_sync)
    for key, value in index.items():
        if value.get('metadata', {}).get('media_id') == media_id:
            return value
        if media_id in key:
            return value
    return None


def generate_storage_key(data_type: str, identifier: str) -> str:
    """تولید کلید استاندارد"""
    return f"{data_type}:{identifier}"


def parse_storage_key(key: str) -> tuple:
    """تجزیه کلید به نوع و شناسه"""
    parts = key.split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "unknown", key


# ========== ابزارهای بازیابی ==========

async def repair_index_from_backup():
    """بازیابی ایندکس از بکاپ در صورت خرابی"""
    backup_file = f"{INDEX_FILE}.backup"
    
    if not os.path.exists(backup_file):
        logger.warning("⚠️ فایل بکاپ وجود ندارد")
        return False
    
    try:
        async with _write_lock:
            # بارگذاری بکاپ
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # ذخیره به عنوان ایندکس اصلی
            await asyncio.to_thread(_save_index_sync, backup_data)
            logger.info(f"✅ ایندکس از بکاپ بازیابی شد - {len(backup_data)} آیتم")
            return True
            
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی از بکاپ: {e}")
        return False


async def validate_index() -> bool:
    """بررسی صحت فایل ایندکس"""
    try:
        index = await asyncio.to_thread(_load_index_sync)
        
        # چک کردن ساختار
        for key, value in index.items():
            if not isinstance(value, dict):
                logger.error(f"❌ ایندکس خراب: {key}不是一个 dict")
                return False
            if "message_id" not in value:
                logger.error(f"❌ ایندکس خراب: {key} فاقد message_id")
                return False
        
        logger.info(f"✅ ایندکس معتبر است - {len(index)} آیتم")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ ایندکس خراب (JSON Decode Error): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ خطا در اعتبارسنجی ایندکس: {e}")
        return False
