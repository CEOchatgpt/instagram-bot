# channel_cache.py - نسخه تمیز و بهینه

import logging
import hashlib
import time
import asyncio
from typing import Optional, Any, Dict, List
from telegram.ext import ContextTypes
from config import (
    PROFILE_CHANNEL_ID,
    POST_CHANNEL_ID,
    REEL_CHANNEL_ID,
    STORY_CHANNEL_ID,
    HIGHLIGHT_CHANNEL_ID,
    USER_SETTING_CHANNEL_ID
)
from index_manager import save_to_index, get_from_index, generate_storage_key

logger = logging.getLogger(__name__)

# کش حافظه
_memory_cache: Dict[str, dict] = {}
CACHE_TTL = 300


def _get_memory_cache(key: str) -> Optional[Any]:
    if key in _memory_cache:
        item = _memory_cache[key]
        if time.time() < item["expires"]:
            return item["data"]
        del _memory_cache[key]
    return None


def _set_memory_cache(key: str, data: Any, ttl: int = CACHE_TTL):
    _memory_cache[key] = {"data": data, "expires": time.time() + ttl}


def _format_caption(caption: str, max_len: int = 300) -> str:
    if not caption:
        return "بدون کپشن"
    return caption[:max_len] + "..." if len(caption) > max_len else caption


def _get_channel_for_type(content_type: str) -> str:
    channel_map = {
        'profile': PROFILE_CHANNEL_ID,
        'post': POST_CHANNEL_ID,
        'reel': REEL_CHANNEL_ID,
        'reels_list': REEL_CHANNEL_ID,
        'story': STORY_CHANNEL_ID,
        'highlight': HIGHLIGHT_CHANNEL_ID,
        'highlights_list': HIGHLIGHT_CHANNEL_ID,
        'user_setting': USER_SETTING_CHANNEL_ID,
    }
    channel_id = channel_map.get(content_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای نوع {content_type} تعریف نشده! استفاده از POST_CHANNEL_ID")
        return POST_CHANNEL_ID
    return channel_id


# ========== پروفایل ==========

async def save_profile_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, profile_data: dict) -> Optional[int]:
    channel_id = _get_channel_for_type('profile')
    if not channel_id:
        logger.warning("⚠️ PROFILE_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        storage_key = generate_storage_key("profile", username)
        existing = await get_from_index(storage_key)
        if existing:
            logger.info(f"📦 پروفایل {username} قبلاً ذخیره شده")
            return existing["message_id"]
        
        private_text = "🔒 خصوصی" if profile_data.get('is_private') else "🌐 عمومی"
        verified_text = "✅ تأیید شده" if profile_data.get('is_verified') else ""
        
        message_text = f"""👤 <b>پروفایل ذخیره شده</b>
━━━━━━━━━━━━━━━━
🔖 @{profile_data.get('username', username)}
📝 {profile_data.get('biography', 'بدون بیو')[:200]}

📊 آمار:
❤️ {profile_data.get('followers', 0):,} دنبال‌کننده
👥 {profile_data.get('following', 0):,} دنبال‌شونده
📸 {profile_data.get('posts', 0):,} پست

{private_text} {verified_text}
━━━━━━━━━━━━━━━━
🔑 کلید: {storage_key}
💾 ذخیره: {time.strftime('%Y/%m/%d %H:%M:%S')}"""
        
        if profile_data.get("profile_pic"):
            try:
                msg = await context.bot.send_photo(chat_id=channel_id, photo=profile_data["profile_pic"], caption=message_text, parse_mode='HTML')
            except:
                msg = await context.bot.send_message(chat_id=channel_id, text=message_text, parse_mode='HTML')
        else:
            msg = await context.bot.send_message(chat_id=channel_id, text=message_text, parse_mode='HTML')
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "profile", {"username": username, "full_name": profile_data.get("full_name", "")})
            _set_memory_cache(f"profile:{username}", {"data": profile_data}, ttl=86400)
            logger.info(f"✅ پروفایل {username} ذخیره شد")
            return msg.message_id
        return None
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره پروفایل: {e}")
        return None


async def get_profile_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    channel_id = _get_channel_for_type('profile')
    if not channel_id:
        return None
    
    storage_key = generate_storage_key("profile", username)
    cache_key = f"profile:{username}"
    
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    
    index_data = await get_from_index(storage_key)
    if not index_data:
        return None
    
    msg = await context.bot.forward_message(chat_id=channel_id, from_chat_id=channel_id, message_id=index_data["message_id"])
    
    profile_data = {
        "username": username, "full_name": username, "biography": "", "followers": 0,
        "following": 0, "posts": 0, "profile_pic": msg.photo[-1].file_id if msg.photo else None,
        "is_private": False, "is_verified": False, "from_channel_cache": True
    }
    _set_memory_cache(cache_key, {"data": profile_data}, ttl=86400)
    return profile_data


# ========== ذخیره مدیا ==========

async def save_media_to_channel(context: ContextTypes.DEFAULT_TYPE, media_key: str, media_data: dict, content_type: str = None) -> Optional[int]:
    from extract_instagram_id import extract_instagram_id
    
    if not content_type:
        extracted = extract_instagram_id(media_key)
        content_type = extracted.get('type', 'post') if extracted else 'post'
    
    channel_id = _get_channel_for_type(content_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای نوع {content_type} تنظیم نشده!")
        return None
    
    extracted = extract_instagram_id(media_key)
    if extracted and extracted.get('full_id'):
        storage_key = f"{content_type}:{extracted['full_id']}"
    else:
        storage_key = f"{content_type}:{hashlib.md5(media_key.encode()).hexdigest()}"
    
    try:
        existing = await get_from_index(storage_key)
        if existing:
            logger.info(f"📦 {content_type} قبلاً ذخیره شده: {storage_key}")
            return existing["message_id"]
        
        items, caption = media_data.get("items", []), media_data.get("caption", "بدون کپشن")
        formatted_caption = _format_caption(caption, 200)
        
        type_info = {'post': ('📷', 'پست'), 'reel': ('🎬', 'ریل'), 'story': ('📖', 'استوری'), 'highlight': ('📚', 'هایلایت')}.get(content_type, ('📦', 'محتوا'))
        
        message_ids = []
        for idx, item in enumerate(items):
            if not item.get("url"):
                continue
            
            item_caption = f"""{type_info[0]} <b>{type_info[1]} ذخیره شده</b>
━━━━━━━━━━━━━━━━
🔑 کلید: {storage_key}
📌 {idx + 1}/{len(items)}
📝 {formatted_caption}
━━━━━━━━━━━━━━━━
💾 {time.strftime('%Y/%m/%d %H:%M:%S')}"""
            
            try:
                if item["type"] == "video":
                    msg = await context.bot.send_video(chat_id=channel_id, video=item["url"], caption=item_caption[:1024], parse_mode='HTML', supports_streaming=True)
                else:
                    msg = await context.bot.send_photo(chat_id=channel_id, photo=item["url"], caption=item_caption[:1024], parse_mode='HTML')
                message_ids.append(msg.message_id)
                await asyncio.sleep(0.3)
            except:
                try:
                    msg = await context.bot.send_document(chat_id=channel_id, document=item["url"], caption=item_caption[:900], parse_mode='HTML')
                    message_ids.append(msg.message_id)
                    await asyncio.sleep(0.3)
                except Exception as e2:
                    logger.error(f"خطا در ارسال داکیومنت: {e2}")
        
        if message_ids:
            await save_to_index(storage_key, message_ids[0], content_type, {"original_key": media_key, "item_count": len(message_ids), "message_ids": message_ids})
            _set_memory_cache(f"{content_type}:{storage_key}", {"message_ids": message_ids, "data": media_data}, ttl=86400)
            logger.info(f"✅ {len(message_ids)} {type_info[1]} در کانال {content_type} ذخیره شد")
            return message_ids[0]
        return None
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره {content_type}: {e}")
        return None


# ========== لیست ریل‌ها ==========

async def save_reels_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, reels_data: dict) -> Optional[int]:
    channel_id = _get_channel_for_type('reels_list')
    if not channel_id:
        logger.warning("⚠️ REEL_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        storage_key = generate_storage_key("reels_list", username)
        existing = await get_from_index(storage_key)
        if existing:
            return existing["message_id"]
        
        items = reels_data.get("items", [])
        message_lines = [f"🎬 <b>لیست ریل‌های @{username}</b>", "━━━━━━━━━━━━━━━━", f"📊 تعداد: {len(items)} ریل", "", "<b>لیست ریل‌ها:</b>"]
        for idx, item in enumerate(items[:30]):
            message_lines.append(f"{idx+1}. 🎬 {item.get('caption', 'بدون کپشن')[:50]}")
        if len(items) > 30:
            message_lines.append(f"\n... و {len(items) - 30} ریل دیگر")
        message_lines.extend(["━━━━━━━━━━━━━━━━", f"🔑 کلید: {storage_key}", f"💾 {time.strftime('%Y/%m/%d %H:%M:%S')}"])
        
        msg = await context.bot.send_message(chat_id=channel_id, text="\n".join(message_lines), parse_mode='HTML')
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "reels_list", {"username": username, "reels_count": len(items)})
            _set_memory_cache(f"reels_list:{username}", {"data": reels_data}, ttl=86400)
            for idx, item in enumerate(items):
                reel_data = {"caption": item.get("caption", ""), "items": [{"type": "video", "url": item.get("url")}]}
                await save_media_to_channel(context, f"reel:{username}:{item.get('id', idx)}", reel_data, 'reel')
            return msg.message_id
        return None
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست ریل‌ها: {e}")
        return None


async def get_reels_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    cached = _get_memory_cache(f"reels_list:{username}")
    return cached.get("data") if cached else None


# ========== لیست هایلایت‌ها ==========

async def save_highlights_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, highlights: list) -> Optional[int]:
    channel_id = _get_channel_for_type('highlights_list')
    if not channel_id:
        logger.warning("⚠️ HIGHLIGHT_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        storage_key = generate_storage_key("highlights_list", username)
        existing = await get_from_index(storage_key)
        if existing:
            return existing["message_id"]
        
        message_lines = [f"📚 <b>لیست هایلایت‌های @{username}</b>", "━━━━━━━━━━━━━━━━", f"📊 تعداد: {len(highlights)} هایلایت", "", "<b>لیست هایلایت‌ها:</b>"]
        for idx, h in enumerate(highlights[:30]):
            message_lines.append(f"{idx+1}. 📌 {h.get('title', 'بدون عنوان')} ({h.get('count', 0)} آیتم)")
        if len(highlights) > 30:
            message_lines.append(f"\n... و {len(highlights) - 30} هایلایت دیگر")
        message_lines.extend(["━━━━━━━━━━━━━━━━", f"🔑 کلید: {storage_key}", f"💾 {time.strftime('%Y/%m/%d %H:%M:%S')}"])
        
        msg = await context.bot.send_message(chat_id=channel_id, text="\n".join(message_lines), parse_mode='HTML')
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "highlights_list", {"username": username, "highlights_count": len(highlights)})
            _set_memory_cache(f"highlights_list:{username}", {"data": highlights}, ttl=86400)
            return msg.message_id
        return None
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست هایلایت‌ها: {e}")
        return None


async def get_highlights_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[list]:
    cached = _get_memory_cache(f"highlights_list:{username}")
    if cached:
        return cached.get("data")
    
    storage_key = generate_storage_key("highlights_list", username)
    index_data = await get_from_index(storage_key)
    if index_data:
        return index_data.get("metadata", {}).get("highlights", [])
    return None


# ========== تنظیمات کاربر ==========

async def save_user_setting_to_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int, mode: str) -> Optional[int]:
    channel_id = _get_channel_for_type('user_setting')
    if not channel_id:
        logger.warning("⚠️ USER_SETTING_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        storage_key = generate_storage_key("user_setting", str(user_id))
        message_text = f"""⚙️ <b>تنظیمات کاربر</b>
━━━━━━━━━━━━━━━━
👤 کاربر: {user_id}
🎯 حالت: {mode}
💾 ذخیره: {time.strftime('%Y/%m/%d %H:%M:%S')}"""
        
        existing = await get_from_index(storage_key)
        if existing:
            try:
                await context.bot.delete_message(chat_id=channel_id, message_id=existing["message_id"])
            except:
                pass
        
        msg = await context.bot.send_message(chat_id=channel_id, text=message_text, parse_mode='HTML')
        if msg:
            await save_to_index(storage_key, msg.message_id, "user_setting", {"user_id": user_id, "mode": mode})
            logger.info(f"✅ تنظیمات کاربر {user_id} ذخیره شد")
            return msg.message_id
        return None
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره تنظیمات کاربر: {e}")
        return None


async def get_user_setting_from_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Optional[str]:
    channel_id = _get_channel_for_type('user_setting')
    if not channel_id:
        return None
    
    index_data = await get_from_index(generate_storage_key("user_setting", str(user_id)))
    if not index_data:
        return None
    
    try:
        msg = await context.bot.forward_message(chat_id=channel_id, from_chat_id=channel_id, message_id=index_data["message_id"])
        text = msg.caption or msg.text or ""
        if "حالت: file" in text or "mode: file" in text:
            return "file"
        return "album"
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی تنظیمات کاربر: {e}")
        return None


# ========== توابع کمکی ==========

async def get_media_by_key(context: ContextTypes.DEFAULT_TYPE, storage_key: str) -> Optional[dict]:
    content_type = storage_key.split(":")[0] if ":" in storage_key else "post"
    channel_id = _get_channel_for_type(content_type)
    if not channel_id:
        return None
    
    cache_key = f"{content_type}:{storage_key}"
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    
    index_data = await get_from_index(storage_key)
    if not index_data:
        return None
    
    message_ids = index_data.get("metadata", {}).get("message_ids", [])
    if not message_ids:
        msg_id = index_data.get("message_id")
        if msg_id:
            message_ids = [msg_id]
    
    if not message_ids:
        return None
    
    items, caption = [], ""
    for msg_id in message_ids[:10]:
        try:
            msg = await context.bot.forward_message(chat_id=channel_id, from_chat_id=channel_id, message_id=msg_id)
            if msg.caption:
                for line in msg.caption.split("\n"):
                    if "📝" in line:
                        caption = line.replace("📝", "").strip()
                        break
            if msg.video:
                items.append({"type": "video", "url": msg.video.file_id})
            elif msg.photo:
                items.append({"type": "photo", "url": msg.photo[-1].file_id})
            elif msg.document:
                items.append({"type": "document", "url": msg.document.file_id})
        except Exception as e:
            logger.warning(f"خطا در بازیابی پیام {msg_id}: {e}")
    
    if items:
        result = {"caption": caption, "items": items}
        _set_memory_cache(cache_key, {"data": result}, ttl=86400)
        return result
    return None


async def get_media_from_channel(context: ContextTypes.DEFAULT_TYPE, media_key: str) -> Optional[dict]:
    from extract_instagram_id import extract_instagram_id
    extracted = extract_instagram_id(media_key)
    if extracted:
        storage_key = f"{extracted['type']}:{extracted['full_id']}"
    else:
        storage_key = f"post:{hashlib.md5(media_key.encode()).hexdigest()}"
    return await get_media_by_key(context, storage_key)


def clear_memory_cache():
    global _memory_cache
    _memory_cache.clear()
    logger.info("🧹 کش حافظه پاک شد")
