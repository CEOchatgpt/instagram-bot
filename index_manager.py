# index_manager.py - نسخه تمیز بدون کش حافظه

import json
import os
import logging
import time
import asyncio
from typing import Optional, Dict, Any, List
from collections import defaultdict
import re

logger = logging.getLogger(__name__)

# فایل‌های محلی
INDEX_FILE = "channel_index.json"
SEARCH_INDEX_FILE = "search_index.json"

_write_lock = asyncio.Lock()

# برای ذخیره در کانال تلگرام
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


# ========== سیستم جستجوی سریع ==========

class SearchIndex:
    """ایندکس جستجوی سریع با چند لایه"""
    
    def __init__(self):
        self.by_keyword = defaultdict(list)
        self.by_type = defaultdict(list)
        self.by_username = defaultdict(list)
        self.by_media_id = {}
        self.last_updated = 0
    
    def rebuild_from_index(self, index: Dict):
        """بازسازی ایندکس جستجو از داده اصلی"""
        self.by_keyword.clear()
        self.by_type.clear()
        self.by_username.clear()
        self.by_media_id.clear()
        
        for key, value in index.items():
            data_type = value.get('type', 'unknown')
            self.by_type[data_type].append(key)
            
            keywords = re.findall(r'[a-zA-Z0-9_-]+', key)
            for kw in keywords:
                if len(kw) > 3:
                    self.by_keyword[kw.lower()].append(key)
            
            metadata = value.get('metadata', {})
            if metadata.get('username'):
                self.by_username[metadata['username'].lower()].append(key)
            
            if metadata.get('media_id'):
                self.by_media_id[metadata['media_id']] = key
            
            if ':' in key:
                possible_id = key.split(':')[-1]
                if len(possible_id) >= 8:
                    self.by_media_id[possible_id] = key
        
        self.last_updated = time.time()
        logger.info(f"🔍 ایندکس جستجو بازسازی شد")
    
    def search(self, keyword: str = None, content_type: str = None, 
               username: str = None, media_id: str = None, limit: int = 50) -> List[str]:
        results = set()
        
        if media_id and media_id in self.by_media_id:
            return [self.by_media_id[media_id]]
        
        if username:
            username_lower = username.lower()
            for uname, keys in self.by_username.items():
                if username_lower in uname:
                    results.update(keys)
        
        if keyword:
            keyword_lower = keyword.lower()
            for kw, keys in self.by_keyword.items():
                if keyword_lower in kw or kw in keyword_lower:
                    results.update(keys)
        
        if content_type and content_type in self.by_type:
            if results:
                results = results.intersection(self.by_type[content_type])
            else:
                results = set(self.by_type[content_type])
        
        return list(results)[:limit]
    
    def get_stats(self) -> Dict:
        return {
            'total_keywords': len(self.by_keyword),
            'total_types': len(self.by_type),
            'total_usernames': len(self.by_username),
            'total_media_ids': len(self.by_media_id),
        }


_search_index = SearchIndex()


def _save_search_index_sync():
    """ذخیره ایندکس جستجو در فایل"""
    try:
        data = {
            'by_keyword': dict(_search_index.by_keyword),
            'by_type': dict(_search_index.by_type),
            'by_username': dict(_search_index.by_username),
            'by_media_id': _search_index.by_media_id,
            'last_updated': _search_index.last_updated
        }
        with open(SEARCH_INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"خطا در ذخیره ایندکس جستجو: {e}")


def _load_search_index_sync():
    """بارگذاری ایندکس جستجو از فایل"""
    global _search_index
    try:
        if os.path.exists(SEARCH_INDEX_FILE):
            with open(SEARCH_INDEX_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            _search_index.by_keyword = defaultdict(list, data.get('by_keyword', {}))
            _search_index.by_type = defaultdict(list, data.get('by_type', {}))
            _search_index.by_username = defaultdict(list, data.get('by_username', {}))
            _search_index.by_media_id = data.get('by_media_id', {})
            _search_index.last_updated = data.get('last_updated', 0)
            logger.info(f"🔍 ایندکس جستجو از فایل بارگذاری شد")
            return True
    except Exception as e:
        logger.warning(f"خطا در بارگذاری ایندکس جستجو: {e}")
    return False


# ========== توابع کانال ایندکس ==========

async def _save_single_index_to_channel(key: str, data: Dict) -> Optional[int]:
    """ذخیره یک آیتم ایندکس به صورت پیام جداگانه"""
    if not INDEX_CHANNEL_ID or not _context:
        return None
    
    try:
        message_text = f"""📌 **ایندکس: `{key}`**
━━━━━━━━━━━━━━━━
📁 **نوع:** `{data.get('type', 'unknown')}`
📨 **Message ID:** `{data.get('message_id')}`
🕐 **زمان:** {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data.get('timestamp', time.time())))}

📦 **متادیتا:**
```json
{json.dumps(data.get('metadata', {}), ensure_ascii=False, indent=2)[:800]}
```"""
        
        if data.get('index_msg_id'):
            try:
                await _context.edit_message_text(
                    chat_id=INDEX_CHANNEL_ID,
                    message_id=data['index_msg_id'],
                    text=message_text,
                    parse_mode='Markdown'
                )
                return data['index_msg_id']
            except Exception as e:
                logger.warning(f"خطا در آپدیت: {e}")
        
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


# ========== توابع اصلی ایندکس ==========

def _load_index_sync() -> Dict:
    """بارگذاری از فایل محلی"""
    try:
        if os.path.exists(INDEX_FILE):
            with open(INDEX_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"خطا در بارگذاری فایل: {e}")
        return {}


def _save_index_sync(index: Dict):
    """ذخیره در فایل محلی"""
    try:
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        
        _search_index.rebuild_from_index(index)
        _save_search_index_sync()
        
    except Exception as e:
        logger.error(f"خطا در ذخیره فایل: {e}")


async def save_to_index(key: str, message_id: int, data_type: str, metadata: Dict = None):
    """ذخیره در ایندکس"""
    async with _write_lock:
        index = await asyncio.to_thread(_load_index_sync)
        
        existing = index.get(key, {})
        new_data = {
            "message_id": message_id,
            "type": data_type,
            "timestamp": time.time(),
            "metadata": metadata or {}
        }
        
        if existing.get('index_msg_id'):
            new_data['index_msg_id'] = existing['index_msg_id']
        
        index_msg_id = await _save_single_index_to_channel(key, new_data)
        if index_msg_id:
            new_data['index_msg_id'] = index_msg_id
        
        index[key] = new_data
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
            index_msg_id = index[key].get('index_msg_id')
            if index_msg_id and _context and INDEX_CHANNEL_ID:
                try:
                    await _context.delete_message(
                        chat_id=INDEX_CHANNEL_ID,
                        message_id=index_msg_id
                    )
                except:
                    pass
            
            del index[key]
            await asyncio.to_thread(_save_index_sync, index)
            logger.info(f"🗑️ حذف: {key}")
            return True
        return False


async def search_index(
    keyword: str = None,
    content_type: str = None,
    username: str = None,
    media_id: str = None,
    limit: int = 50
) -> List[Dict]:
    """جستجوی سریع در ایندکس"""
    index = await asyncio.to_thread(_load_index_sync)
    if not _search_index.by_keyword and index:
        await asyncio.to_thread(_search_index.rebuild_from_index, index)
    
    keys = await asyncio.to_thread(
        _search_index.search,
        keyword=keyword,
        content_type=content_type,
        username=username,
        media_id=media_id,
        limit=limit
    )
    
    results = []
    for key in keys:
        if key in index:
            results.append(index[key])
    return results


async def search_by_media_id(media_id: str) -> Optional[Dict]:
    """جستجو با شناسه مدیا"""
    results = await search_index(media_id=media_id, limit=1)
    return results[0] if results else None


async def search_by_username(username: str, limit: int = 50) -> List[Dict]:
    """جستجوی محتواهای یک یوزرنیم"""
    return await search_index(username=username, limit=limit)


async def search_by_type(content_type: str, limit: int = 100) -> List[Dict]:
    """جستجو بر اساس نوع محتوا"""
    return await search_index(content_type=content_type, limit=limit)


async def search_by_keyword(keyword: str) -> List[Dict]:
    """جستجو با کلمه کلیدی"""
    return await search_index(keyword=keyword)


async def sync_index_from_channel():
    """همگام‌سازی از فایل محلی"""
    index = await asyncio.to_thread(_load_index_sync)
    if index:
        logger.info(f"🔄 ایندکس بارگذاری شد - {len(index)} آیتم")
        return True
    
    logger.warning("⚠️ ایندکس خالی است")
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
    search_stats = _search_index.get_stats()
    
    stats = {
        "total_items": len(index),
        "by_type": {},
        "search_stats": search_stats,
        "oldest": None,
        "newest": None
    }
    
    for value in index.values():
        data_type = value.get("type", "unknown")
        stats["by_type"][data_type] = stats["by_type"].get(data_type, 0) + 1
        
        timestamp = value.get("timestamp")
        if timestamp:
            if stats["oldest"] is None or timestamp < stats["oldest"]:
                stats["oldest"] = timestamp
            if stats["newest"] is None or timestamp > stats["newest"]:
                stats["newest"] = timestamp
    
    return stats


async def get_all_keys() -> List[str]:
    index = await asyncio.to_thread(_load_index_sync)
    return list(index.keys())
