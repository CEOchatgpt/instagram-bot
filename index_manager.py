# index_manager.py - نسخه با چند پیام در کانال ایندکس

import json
import os
import logging
import time
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

INDEX_FILE = "channel_index.json"
_index_cache = None
_cache_time = 0
CACHE_TTL = 60

_write_lock = asyncio.Lock()

INDEX_CHANNEL_ID = None
_context = None


def set_context(context):
    global _context
    _context = context
    logger.info(f"📡 Context تنظیم شد")


def set_index_channel(channel_id: int):
    global INDEX_CHANNEL_ID
    INDEX_CHANNEL_ID = channel_id
    logger.info(f"📊 کانال ایندکس: {INDEX_CHANNEL_ID}")


# ========== توابع جدید: ذخیره هر کلید به صورت جداگانه ==========

async def _save_single_index_to_channel(key: str, data: Dict):
    """
    ذخیره یک آیتم ایندکس به صورت پیام جداگانه در کانال
    """
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context:
        return None
    
    try:
        # ساخت پیام برای این کلید
        message_text = f"""📌 **ایندکس: {key}**
━━━━━━━━━━━━━━━━
🆔 **شناسه:** `{key}`
📁 **نوع:** {data.get('type', 'unknown')}
📨 **Message ID:** {data.get('message_id')}
🕐 **زمان:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data.get('timestamp', time.time())))}

📦 **متادیتا:**
```json
{json.dumps(data.get('metadata', {}), ensure_ascii=False, indent=2)[:500]}
```"""
        
        # ارسال پیام جدید در کانال ایندکس
        msg = await _context.send_message(
            chat_id=INDEX_CHANNEL_ID,
            text=message_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ ایندکس برای {key} ذخیره شد (msg_id: {msg.message_id})")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره ایندکس {key}: {e}")
        return None


async def _update_single_index_in_channel(key: str, data: Dict, index_msg_id: int):
    """
    به‌روزرسانی یک آیتم ایندکس در کانال
    """
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context or not index_msg_id:
        return False
    
    try:
        message_text = f"""📌 **ایندکس: {key}**
━━━━━━━━━━━━━━━━
🆔 **شناسه:** `{key}`
📁 **نوع:** {data.get('type', 'unknown')}
📨 **Message ID:** {data.get('message_id')}
🕐 **زمان:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data.get('timestamp', time.time())))}

📦 **متادیتا:**
```json
{json.dumps(data.get('metadata', {}), ensure_ascii=False, indent=2)[:500]}
```"""
        
        await _context.edit_message_text(
            chat_id=INDEX_CHANNEL_ID,
            message_id=index_msg_id,
            text=message_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ ایندکس {key} به‌روزرسانی شد")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در به‌روزرسانی ایندکس {key}: {e}")
        return False


async def _delete_single_index_in_channel(index_msg_id: int):
    """
    حذف یک آیتم ایندکس از کانال
    """
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context or not index_msg_id:
        return False
    
    try:
        await _context.delete_message(
            chat_id=INDEX_CHANNEL_ID,
            message_id=index_msg_id
        )
        logger.info(f"✅ ایندکس حذف شد (msg_id: {index_msg_id})")
        return True
    except Exception as e:
        logger.error(f"❌ خطا در حذف ایندکس: {e}")
        return False


# ========== توابع اصلی ==========

def _load_index_sync() -> Dict:
    """بارگذاری از فایل محلی"""
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
        logger.error(f"خطا در بارگذاری فایل: {e}")
        return {}


def _save_index_sync(index: Dict):
    """ذخیره در فایل محلی"""
    global _index_cache, _cache_time
    
    try:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        _index_cache = index
        _cache_time = time.time()
        
    except Exception as e:
        logger.error(f"خطا در ذخیره فایل: {e}")


async def save_to_index(key: str, message_id: int, data_type: str, metadata: Dict = None):
    """
    ذخیره در ایندکس - هر کلید یک پیام جداگانه در کانال
    """
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
        
        existing = index.get(key)
        new_data = {
            "message_id": message_id,
            "type": data_type,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        
        # اگر قبلاً وجود داشت و message_id ایندکس داشت
        if existing and existing.get("index_msg_id"):
            # به‌روزرسانی پیام قبلی
            await _update_single_index_in_channel(key, new_data, existing["index_msg_id"])
            new_data["index_msg_id"] = existing["index_msg_id"]
        else:
            # ایجاد پیام جدید در کانال ایندکس
            index_msg_id = await _save_single_index_to_channel(key, new_data)
            if index_msg_id:
                new_data["index_msg_id"] = index_msg_id
        
        index[key] = new_data
        
        # ذخیره در فایل محلی
        await asyncio.to_thread(_save_index_sync, index)
        
        logger.info(f"📝 {key} -> msg_id: {message_id}")


async def get_from_index(key: str) -> Optional[Dict]:
    """دریافت از ایندکس"""
    index = await asyncio.to_thread(_load_index_sync)
    return index.get(key)


async def delete_from_index(key: str) -> bool:
    """حذف از ایندکس"""
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
        
        if key in index:
            # حذف پیام از کانال ایندکس
            index_msg_id = index[key].get("index_msg_id")
            if index_msg_id:
                await _delete_single_index_in_channel(index_msg_id)
            
            del index[key]
            await asyncio.to_thread(_save_index_sync, index)
            logger.info(f"🗑️ حذف: {key}")
            return True
        return False


async def sync_index_from_channel():
    """
    همگام‌سازی ایندکس از کانال - با اسکن کردن پیام‌های کانال
    """
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context:
        return False
    
    try:
        index = {}
        offset = 0
        
        # دریافت تاریخچه پیام‌های کانال ایندکس
        # توجه: این نیاز به دسترسی ادمین دارد
        while True:
            try:
                # استفاده از get_updates برای کانال (محدودیت دارد)
                # روش بهتر: نگهداری یک فایل جداگانه برای mapping
                break
            except:
                break
        
        if index:
            await asyncio.to_thread(_save_index_sync, index)
            logger.info(f"🔄 همگام‌سازی شد - {len(index)} آیتم")
            return True
        
        logger.warning("⚠️ همگام‌سازی ناموفق")
        return False
        
    except Exception as e:
        logger.error(f"❌ خطا در همگام‌سازی: {e}")
        return False


# ========== توابع کمکی ==========

def generate_storage_key(data_type: str, identifier: str) -> str:
    return f"{data_type}:{identifier}"


def parse_storage_key(key: str) -> tuple:
    parts = key.split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "unknown", key


async def get_index_stats() -> Dict:
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


# index_manager.py - اضافه کردن توابع جستجو

async def search_index(
    keyword: str = None,
    content_type: str = None,
    username: str = None,
    days_back: int = None,
    limit: int = 50
) -> list:
    """
    جستجوی پیشرفته در ایندکس
    
    پارامترها:
    - keyword: کلمه کلیدی برای جستجو در کلیدها و متادیتا
    - content_type: نوع محتوا ('post', 'reel', 'story', 'highlight', 'profile')
    - username: یوزرنیم برای فیلتر کردن
    - days_back: تعداد روزهای گذشته
    - limit: حداکثر تعداد نتایج
    """
    index = await asyncio.to_thread(_load_index_sync)
    results = []
    now = time.time()
    
    for key, value in index.items():
        # فیلتر بر اساس نوع
        if content_type and value.get('type') != content_type:
            continue
        
        # فیلتر بر اساس تاریخ
        if days_back:
            timestamp = value.get('timestamp', 0)
            if now - timestamp > days_back * 86400:
                continue
        
        # فیلتر بر اساس یوزرنیم
        if username:
            metadata = value.get('metadata', {})
            item_username = metadata.get('username') or metadata.get('original_key', '')
            if username.lower() not in item_username.lower():
                continue
        
        # جستجوی کلمه کلیدی
        if keyword:
            keyword_lower = keyword.lower()
            match_found = (
                keyword_lower in key.lower() or
                keyword_lower in str(value.get('metadata', {})).lower()
            )
            if not match_found:
                continue
        
        # اضافه کردن به نتایج
        results.append({
            'key': key,
            'type': value.get('type'),
            'message_id': value.get('message_id'),
            'timestamp': value.get('timestamp'),
            'metadata': value.get('metadata', {}),
            'index_msg_id': value.get('index_msg_id')
        })
        
        if len(results) >= limit:
            break
    
    # مرتب‌سازی بر اساس زمان (جدیدترین اول)
    results.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    
    return results


async def search_by_username(username: str, limit: int = 50) -> list:
    """جستجوی همه محتواهای یک یوزرنیم"""
    return await search_index(username=username, limit=limit)


async def search_by_type(content_type: str, limit: int = 100) -> list:
    """جستجو بر اساس نوع محتوا"""
    return await search_index(content_type=content_type, limit=limit)


async def search_recent(days: int = 7, limit: int = 100) -> list:
    """جستجوی محتواهای اخیر"""
    return await search_index(days_back=days, limit=limit)


async def search_media_id(media_id: str) -> dict:
    """جستجو با شناسه مدیا (مثل DZLDbXgjNPj)"""
    index = await asyncio.to_thread(_load_index_sync)
    
    for key, value in index.items():
        if media_id in key:
            return {
                'key': key,
                'type': value.get('type'),
                'message_id': value.get('message_id'),
                'metadata': value.get('metadata', {}),
                'index_msg_id': value.get('index_msg_id')
            }
        
        # چک کردن توی متادیتا
        media_id_in_meta = value.get('metadata', {}).get('media_id')
        if media_id_in_meta == media_id:
            return {
                'key': key,
                'type': value.get('type'),
                'message_id': value.get('message_id'),
                'metadata': value.get('metadata', {}),
                'index_msg_id': value.get('index_msg_id')
            }
    
    return None


async def get_index_statistics() -> Dict:
    """آمار کامل ایندکس"""
    index = await asyncio.to_thread(_load_index_sync)
    
    stats = {
        'total': len(index),
        'by_type': {},
        'by_month': {},
        'latest': None,
        'oldest': None
    }
    
    for key, value in index.items():
        # آمار بر اساس نوع
        data_type = value.get('type', 'unknown')
        stats['by_type'][data_type] = stats['by_type'].get(data_type, 0) + 1
        
        # آمار بر اساس ماه
        timestamp = value.get('timestamp')
        if timestamp:
            month = time.strftime('%Y-%m', time.localtime(timestamp))
            stats['by_month'][month] = stats['by_month'].get(month, 0) + 1
            
            if not stats['latest'] or timestamp > stats['latest']:
                stats['latest'] = timestamp
            if not stats['oldest'] or timestamp < stats['oldest']:
                stats['oldest'] = timestamp
    
    return stats
