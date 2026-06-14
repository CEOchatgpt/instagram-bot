# index_manager.py - نسخه با ذخیره در کانال تلگرام

import json
import os
import logging
import time
import asyncio
from typing import Optional, Dict, Any
from functools import wraps

logger = logging.getLogger(__name__)

# برای ذخیره محلی (کش موقت)
INDEX_FILE = "channel_index.json"
_index_cache = None
_cache_time = 0
CACHE_TTL = 60

# قفل برای جلوگیری از همزمانی
_write_lock = asyncio.Lock()

# آیدی کانال برای ذخیره دائمی ایندکس (از config میاد)
INDEX_CHANNEL_ID = None
_context = None  # context برای ارسال به تلگرام


def set_context(context):
    """تنظیم context برای دسترسی به بات"""
    global _context
    _context = context


def set_index_channel(channel_id: int):
    """تنظیم آیدی کانال ایندکس"""
    global INDEX_CHANNEL_ID
    INDEX_CHANNEL_ID = channel_id
    logger.info(f"📊 کانال ایندکس تنظیم شد: {INDEX_CHANNEL_ID}")


async def _save_index_to_channel(index: Dict):
    """ذخیره ایندکس در کانال تلگرام (دائمی)"""
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context:
        logger.warning("⚠️ کانال ایندکس یا context تنظیم نشده!")
        return False
    
    try:
        # تبدیل ایندکس به JSON
        index_json = json.dumps(index, ensure_ascii=False, indent=2)
        
        # اگر خیلی طولانی بود، فشرده کن
        if len(index_json) > 4000:
            index_json = json.dumps(index, ensure_ascii=False)
        
        # فرمت پیام
        message_text = f"📊 **ایندکس دیتابیس**\n🕐 آخرین بروزرسانی: {time.strftime('%Y-%m-%d %H:%M:%S')}\n📦 تعداد آیتم: {len(index)}\n\n```json\n{index_json[:3500]}\n```"
        
        # سعی می‌کنیم پیام قبلی را پیدا کنیم
        found_msg_id = None
        
        # روش صحیح: استفاده از get_updates به جای get_chat_history
        # یا نگهداری message_id در حافظه
        global _index_message_id
        if '_index_message_id' not in globals():
            global _index_message_id
            _index_message_id = None
        
        if _index_message_id:
            try:
                await _context.bot.edit_message_text(
                    chat_id=INDEX_CHANNEL_ID,
                    message_id=_index_message_id,
                    text=message_text,
                    parse_mode='Markdown'
                )
                logger.info(f"✅ ایندکس در کانال آپدیت شد (msg_id: {_index_message_id})")
                return True
            except Exception as e:
                logger.warning(f"خطا در آپدیت پیام: {e}")
                _index_message_id = None
        
        # ارسال پیام جدید
        msg = await _context.bot.send_message(
            chat_id=INDEX_CHANNEL_ID,
            text=message_text,
            parse_mode='Markdown'
        )
        _index_message_id = msg.message_id
        logger.info(f"✅ ایندکس در کانال ذخیره شد (msg_id: {msg.message_id})")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره ایندکس در کانال: {e}")
        return False


async def _load_index_from_channel() -> Optional[Dict]:
    """بارگذاری ایندکس از کانال تلگرام"""
    global INDEX_CHANNEL_ID, _context
    
    if not INDEX_CHANNEL_ID or not _context:
        logger.warning("⚠️ کانال ایندکس یا context تنظیم نشده!")
        return None
    
    try:
        # روش ساده: از یک پیام ثابت استفاده می‌کنیم
        # یا می‌توانیم از آخرین پیام کانال استفاده کنیم
        
        # گزینه 1: اگر message_id را در حافظه داریم
        global _index_message_id
        if '_index_message_id' in globals() and _index_message_id:
            try:
                msg = await _context.bot.forward_message(
                    chat_id=INDEX_CHANNEL_ID,
                    from_chat_id=INDEX_CHANNEL_ID,
                    message_id=_index_message_id
                )
                
                if msg.text and "```json" in msg.text:
                    json_text = msg.text.split("```json")[1].split("```")[0].strip()
                    index_data = json.loads(json_text)
                    logger.info(f"✅ ایندکس از کانال بارگذاری شد - {len(index_data)} آیتم")
                    await msg.delete()  # پاک کردن پیام فوروارد شده
                    return index_data
            except:
                pass
        
        # گزینه 2: درخواست از API برای دریافت آخرین پیام‌ها
        # این روش نیاز به admin rights دارد
        try:
            # استفاده از get_updates (این روش برای کانال‌ها محدود است)
            updates = await _context.bot.get_updates(limit=10)
            for update in updates:
                if update.channel_post and update.channel_post.chat_id == INDEX_CHANNEL_ID:
                    if update.channel_post.text and "ایندکس دیتابیس" in update.channel_post.text:
                        text = update.channel_post.text
                        if "```json" in text:
                            json_text = text.split("```json")[1].split("```")[0].strip()
                            index_data = json.loads(json_text)
                            _index_message_id = update.channel_post.message_id
                            logger.info(f"✅ ایندکس از کانال بارگذاری شد - {len(index_data)} آیتم")
                            return index_data
        except Exception as e:
            logger.warning(f"خطا در get_updates: {e}")
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در بارگذاری ایندکس از کانال: {e}")
        return None


def _load_index_sync() -> Dict:
    """بارگذاری فایل ایندکس (همزمان - اولویت با کانال)"""
    global _index_cache, _cache_time
    
    # چک کش
    if _index_cache is not None and (time.time() - _cache_time) < CACHE_TTL:
        return _index_cache
    
    # تلاش برای بارگذاری از کانال (از طریق asyncio)
    # این تابع sync است، پس باید به صورت ویژه handle کنیم
    
    # بارگذاری از فایل محلی (به عنوان fallback)
    try:
        if os.path.exists(INDEX_FILE):
            with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                _index_cache = json.load(f)
                _cache_time = time.time()
                logger.info(f"📁 ایندکس از فایل محلی بارگذاری شد - {len(_index_cache)} آیتم")
                return _index_cache
        else:
            _index_cache = {}
            return _index_cache
    except Exception as e:
        logger.error(f"خطا در بارگذاری ایندکس از فایل: {e}")
        return {}


def _save_index_sync(index: Dict):
    """ذخیره فایل ایندکس (همزمان)"""
    global _index_cache, _cache_time
    
    try:
        # همیشه در فایل محلی ذخیره کن
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        _index_cache = index
        _cache_time = time.time()
        logger.info(f"✅ ایندکس در فایل محلی ذخیره شد - {len(index)} آیتم")
        
    except Exception as e:
        logger.error(f"خطا در ذخیره ایندکس در فایل: {e}")


# ========== توابع عمومی با قفل ==========

async def save_to_index(key: str, message_id: int, data_type: str, metadata: Dict = None):
    """ذخیره در ایندکس (هم در فایل محلی، هم در کانال)"""
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
        
        # ذخیره در کانال تلگرام (دائمی)
        await _save_index_to_channel(index)
        
        logger.info(f"📝 ایندکس: {key} -> {message_id}")


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
            logger.info(f"🗑️ حذف از ایندکس: {key}")
            return True
        
        return False


async def find_by_type(data_type: str) -> list:
    """پیدا کردن با نوع"""
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
    """جستجو با کلمه کلیدی"""
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
    """دریافت همه کلیدها"""
    index = await asyncio.to_thread(_load_index_sync)
    return list(index.keys())


async def get_index_stats() -> Dict:
    """آمار ایندکس"""
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


async def search_by_media_id(media_id: str) -> dict:
    """جستجو با شناسه مدیا"""
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


async def sync_index_from_channel():
    """همگام‌سازی ایندکس از کانال (بعد از ریستارت)"""
    global _index_cache, _cache_time
    
    index = await _load_index_from_channel()
    if index:
        _index_cache = index
        _cache_time = time.time()
        
        # همچنین در فایل محلی ذخیره کن
        await asyncio.to_thread(_save_index_sync, index)
        logger.info(f"🔄 ایندکس از کانال همگام‌سازی شد - {len(index)} آیتم")
        return True
    
    logger.warning("⚠️ نتوانستم ایندکس را از کانال بارگذاری کنم")
    return False


async def repair_index_from_backup():
    """بازیابی ایندکس از بکاپ در صورت خرابی"""
    # اول تلاش از کانال
    index = await _load_index_from_channel()
    if index:
        await asyncio.to_thread(_save_index_sync, index)
        logger.info(f"✅ ایندکس از کانال بازیابی شد - {len(index)} آیتم")
        return True
    
    # سپس تلاش از فایل بکاپ محلی
    backup_file = f"{INDEX_FILE}.backup"
    if os.path.exists(backup_file):
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            await asyncio.to_thread(_save_index_sync, backup_data)
            logger.info(f"✅ ایندکس از فایل بکاپ بازیابی شد - {len(backup_data)} آیتم")
            return True
        except:
            pass
    
    logger.error("❌ هیچ منبع معتبری برای بازیابی ایندکس وجود ندارد")
    return False


async def validate_index() -> bool:
    """بررسی صحت فایل ایندکس"""
    try:
        index = await asyncio.to_thread(_load_index_sync)
        
        for key, value in index.items():
            if not isinstance(value, dict):
                logger.error(f"❌ ایندکس خراب: {key}")
                return False
            if "message_id" not in value:
                logger.error(f"❌ ایندکس خراب: {key} فاقد message_id")
                return False
        
        logger.info(f"✅ ایندکس معتبر است - {len(index)} آیتم")
        return True
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ ایندکس خراب (JSON Error): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ خطا در اعتبارسنجی ایندکس: {e}")
        return False
