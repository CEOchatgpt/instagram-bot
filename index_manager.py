# index_manager.py - نسخه نهایی ساده با ذخیره در فایل

import json
import os
import logging
import time
import asyncio
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# فایل‌های محلی
INDEX_FILE = "channel_index.json"
INDEX_META_FILE = "index_meta.json"  # فقط برای ذخیره message_id

_index_cache = None
_cache_time = 0
CACHE_TTL = 60

_write_lock = asyncio.Lock()

# برای کانال تلگرام
INDEX_CHANNEL_ID = None
_context = None


def set_context(context):
    global _context
    _context = context


def set_index_channel(channel_id: int):
    global INDEX_CHANNEL_ID
    INDEX_CHANNEL_ID = channel_id
    logger.info(f"📊 کانال ایندکس: {INDEX_CHANNEL_ID}")


def _save_meta(message_id: int):
    """ذخیره message_id در فایل"""
    try:
        with open(INDEX_META_FILE, 'w', encoding='utf-8') as f:
            json.dump({"message_id": message_id, "time": time.time()}, f)
    except Exception as e:
        logger.warning(f"خطا در ذخیره meta: {e}")


def _load_meta() -> Optional[int]:
    """بارگذاری message_id از فایل"""
    try:
        if os.path.exists(INDEX_META_FILE):
            with open(INDEX_META_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("message_id")
    except Exception as e:
        logger.warning(f"خطا در بارگذاری meta: {e}")
    return None


async def _save_index_to_channel(index: Dict):
    """ذخیره ایندکس در کانال تلگرام"""
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context:
        return False
    
    try:
        # تبدیل به JSON
        index_json = json.dumps(index, ensure_ascii=False, indent=2)
        if len(index_json) > 3500:
            index_json = json.dumps(index, ensure_ascii=False)
        
        message_text = f"📊 **ایندکس دیتابیس**\n🕐 {time.strftime('%Y-%m-%d %H:%M:%S')}\n📦 {len(index)} آیتم\n\n```json\n{index_json}\n```"
        
        # چک کردن پیام قبلی
        msg_id = _load_meta()
        
        if msg_id:
            try:
                await _context.bot.edit_message_text(
                    chat_id=INDEX_CHANNEL_ID,
                    message_id=msg_id,
                    text=message_text,
                    parse_mode='Markdown'
                )
                logger.info(f"✅ ایندکس آپدیت شد (msg_id: {msg_id})")
                return True
            except Exception as e:
                logger.warning(f"خطا در آپدیت: {e} - ارسال جدید")
                msg_id = None
        
        # ارسال پیام جدید
        msg = await _context.bot.send_message(
            chat_id=INDEX_CHANNEL_ID,
            text=message_text,
            parse_mode='Markdown'
        )
        _save_meta(msg.message_id)
        logger.info(f"✅ ایندکس جدید ارسال شد (msg_id: {msg.message_id})")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره در کانال: {e}")
        return False


async def _load_index_from_channel() -> Optional[Dict]:
    """بارگذاری ایندکس از کانال تلگرام"""
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context:
        return None
    
    try:
        msg_id = _load_meta()
        if not msg_id:
            logger.info("📭 پیام ایندکسی در meta وجود ندارد")
            return None
        
        # دریافت پیام با فوروارد کردن
        msg = await _context.bot.forward_message(
            chat_id=INDEX_CHANNEL_ID,
            from_chat_id=INDEX_CHANNEL_ID,
            message_id=msg_id
        )
        
        # استخراج JSON
        text = msg.text or ""
        if "```json" in text:
            json_text = text.split("```json")[1].split("```")[0].strip()
            index_data = json.loads(json_text)
            logger.info(f"✅ ایندکس از کانال بارگذاری شد - {len(index_data)} آیتم")
            
            # پاک کردن پیام فوروارد شده
            await msg.delete()
            
            return index_data
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در بارگذاری از کانال: {e}")
        return None


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
                logger.debug(f"📁 ایندکس از فایل: {len(_index_cache)} آیتم")
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
        logger.debug(f"💾 ایندکس در فایل: {len(index)} آیتم")
        
    except Exception as e:
        logger.error(f"خطا در ذخیره فایل: {e}")


# ========== توابع اصلی ==========

async def save_to_index(key: str, message_id: int, data_type: str, metadata: Dict = None):
    """ذخیره در ایندکس"""
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
        
        index[key] = {
            "message_id": message_id,
            "type": data_type,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        
        # ذخیره در فایل محلی
        await asyncio.to_thread(_save_index_sync, index)
        
        # ذخیره در کانال تلگرام (اختیاری)
        await _save_index_to_channel(index)
        
        logger.info(f"📝 {key} -> {message_id}")


async def get_from_index(key: str) -> Optional[Dict]:
    """دریافت از ایندکس"""
    index = await asyncio.to_thread(_load_index_sync)
    return index.get(key)


async def delete_from_index(key: str) -> bool:
    """حذف از ایندکس"""
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
        
        if key in index:
            del index[key]
            await asyncio.to_thread(_save_index_sync, index)
            await _save_index_to_channel(index)
            logger.info(f"🗑️ حذف: {key}")
            return True
        return False


async def sync_index_from_channel():
    """همگام‌سازی از کانال (بعد از ریستارت)"""
    index = await _load_index_from_channel()
    if index:
        await asyncio.to_thread(_save_index_sync, index)
        logger.info(f"🔄 همگام‌سازی شد - {len(index)} آیتم")
        return True
    
    logger.warning("⚠️ همگام‌سازی ناموفق")
    return False


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
