# channel_cache.py - نسخه ساده با کانال‌های ترکیبی

import logging
import hashlib
import time
import asyncio
from typing import Optional, Any, Dict
from telegram.ext import ContextTypes
from config import (
    PROFILE_CHANNEL_ID,
    POST_CHANNEL_ID,
    REEL_CHANNEL_ID,
    STORY_CHANNEL_ID,
    HIGHLIGHT_CHANNEL_ID,
    USER_SETTING_CHANNEL_ID
)
from index_manager import (
    save_to_index, get_from_index, 
    generate_storage_key
)

logger = logging.getLogger(__name__)

# کش حافظه
_memory_cache = {}
CACHE_TTL = 300


def _get_memory_cache(key: str) -> Optional[Any]:
    if key in _memory_cache:
        item = _memory_cache[key]
        if time.time() < item["expires"]:
            return item["data"]
        else:
            del _memory_cache[key]
    return None


def _set_memory_cache(key: str, data: Any, ttl: int = CACHE_TTL):
    _memory_cache[key] = {"data": data, "expires": time.time() + ttl}


def _format_caption(caption: str, max_len: int = 300) -> str:
    if not caption:
        return "بدون کپشن"
    if len(caption) > max_len:
        return caption[:max_len] + "..."
    return caption


def _get_channel_for_type(content_type: str) -> str:
    """
    تعیین کانال مناسب بر اساس نوع محتوا
    """
    channel_map = {
        'profile': PROFILE_CHANNEL_ID,
        'post': POST_CHANNEL_ID,
        'reel': REEL_CHANNEL_ID,        # ریل‌ها
        'reels_list': REEL_CHANNEL_ID,   # لیست ریل‌ها هم در همین کانال
        'story': STORY_CHANNEL_ID,
        'highlight': HIGHLIGHT_CHANNEL_ID,      # هایلایت‌ها
        'highlights_list': HIGHLIGHT_CHANNEL_ID, # لیست هایلایت‌ها هم در همین کانال
        'user_setting': USER_SETTING_CHANNEL_ID,
    }
    
    channel_id = channel_map.get(content_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای نوع {content_type} تعریف نشده! استفاده از POST_CHANNEL_ID")
        return POST_CHANNEL_ID
    
    return channel_id


# ========== پروفایل ==========

async def save_profile_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, profile_data: dict) -> Optional[int]:
    """ذخیره پروفایل"""
    
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
        
        msg = None
        if profile_data.get("profile_pic"):
            try:
                msg = await context.bot.send_photo(
                    chat_id=channel_id,
                    photo=profile_data["profile_pic"],
                    caption=message_text,
                    parse_mode='HTML'
                )
            except:
                msg = await context.bot.send_message(
                    chat_id=channel_id,
                    text=message_text,
                    parse_mode='HTML'
                )
        else:
            msg = await context.bot.send_message(
                chat_id=channel_id,
                text=message_text,
                parse_mode='HTML'
            )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "profile", {
                "username": username,
                "full_name": profile_data.get("full_name", "")
            })
            _set_memory_cache(f"profile:{username}", {"data": profile_data}, ttl=86400)
            logger.info(f"✅ پروفایل {username} ذخیره شد")
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره پروفایل: {e}")
        return None


async def get_profile_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    """بازیابی پروفایل"""
    
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
    
    message_id = index_data.get("message_id")
    if not message_id:
        return None
    
    try:
        msg = await context.bot.forward_message(
            chat_id=channel_id,
            from_chat_id=channel_id,
            message_id=message_id
        )
        
        profile_data = {
            "username": username,
            "full_name": username,
            "biography": "",
            "followers": 0,
            "following": 0,
            "posts": 0,
            "profile_pic": msg.photo[-1].file_id if msg.photo else None,
            "is_private": False,
            "is_verified": False,
            "from_channel_cache": True
        }
        
        _set_memory_cache(cache_key, {"data": profile_data}, ttl=86400)
        return profile_data
        
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی پروفایل: {e}")
        return None


# ========== ذخیره مدیا (پست، ریل، استوری، هایلایت) ==========

async def save_media_to_channel(context: ContextTypes.DEFAULT_TYPE, media_key: str, media_data: dict, content_type: str = None) -> Optional[int]:
    """
    ذخیره مدیا در کانال مناسب
    
    content_type: 'post', 'reel', 'story', 'highlight'
    """
    from extract_instagram_id import extract_instagram_id
    
    # تشخیص نوع اگر داده نشده
    if not content_type:
        extracted = extract_instagram_id(media_key)
        if extracted:
            content_type = extracted.get('type', 'post')
        else:
            content_type = 'post'
    
    # تعیین کانال
    channel_id = _get_channel_for_type(content_type)
    if not channel_id:
        logger.warning(f"⚠️ کانالی برای نوع {content_type} تنظیم نشده!")
        return None
    
    # ساخت کلید یکتا
    extracted = extract_instagram_id(media_key)
    if extracted and extracted.get('full_id'):
        storage_key = f"{content_type}:{extracted['full_id']}"
    else:
        storage_key = f"{content_type}:{hashlib.md5(media_key.encode()).hexdigest()}"
    
    try:
        # چک کردن تکراری نبودن
        existing = await get_from_index(storage_key)
        if existing:
            logger.info(f"📦 {content_type} قبلاً ذخیره شده: {storage_key}")
            return existing["message_id"]
        
        items = media_data.get("items", [])
        caption = media_data.get("caption", "بدون کپشن")
        formatted_caption = _format_caption(caption, 200)
        
        # ایموجی و نام متناسب با نوع
        type_info = {
            'post': {'emoji': '📷', 'name': 'پست'},
            'reel': {'emoji': '🎬', 'name': 'ریل'},
            'story': {'emoji': '📖', 'name': 'استوری'},
            'highlight': {'emoji': '📚', 'name': 'هایلایت'},
        }.get(content_type, {'emoji': '📦', 'name': 'محتوا'})
        
        message_ids = []
        
        for idx, item in enumerate(items):
            item_type = item.get("type", "photo")
            item_url = item.get("url")
            
            if not item_url:
                continue
            
            item_caption = f"""{type_info['emoji']} <b>{type_info['name']} ذخیره شده</b>
━━━━━━━━━━━━━━━━
🔑 کلید: {storage_key}
📌 {idx + 1}/{len(items)}
📝 {formatted_caption}
━━━━━━━━━━━━━━━━
💾 {time.strftime('%Y/%m/%d %H:%M:%S')}"""
            
            try:
                if item_type == "video":
                    msg = await context.bot.send_video(
                        chat_id=channel_id,
                        video=item_url,
                        caption=item_caption[:1024],
                        parse_mode='HTML',
                        supports_streaming=True
                    )
                else:
                    msg = await context.bot.send_photo(
                        chat_id=channel_id,
                        photo=item_url,
                        caption=item_caption[:1024],
                        parse_mode='HTML'
                    )
                
                message_ids.append(msg.message_id)
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.warning(f"خطا در ارسال آیتم {idx}: {e}")
                try:
                    msg = await context.bot.send_document(
                        chat_id=channel_id,
                        document=item_url,
                        caption=item_caption[:900],
                        parse_mode='HTML'
                    )
                    message_ids.append(msg.message_id)
                    await asyncio.sleep(0.3)
                except Exception as e2:
                    logger.error(f"خطا در ارسال داکیومنت: {e2}")
        
        if message_ids:
            await save_to_index(storage_key, message_ids[0], content_type, {
                "original_key": media_key,
                "item_count": len(message_ids),
                "message_ids": message_ids
            })
            
            _set_memory_cache(f"{content_type}:{storage_key}", {
                "message_ids": message_ids,
                "data": media_data
            }, ttl=86400)
            
            logger.info(f"✅ {len(message_ids)} {type_info['name']} در کانال {content_type} ذخیره شد")
            return message_ids[0]
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره {content_type}: {e}")
        return None


# ========== لیست ریل‌ها (ذخیره در همان کانال REEL_CHANNEL_ID) ==========

async def save_reels_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, reels_data: dict) -> Optional[int]:
    """ذخیره لیست ریل‌ها در کانال ریل (همان REEL_CHANNEL_ID)"""
    
    channel_id = _get_channel_for_type('reels_list')  # این هم REEL_CHANNEL_ID برمی‌گرداند
    if not channel_id:
        logger.warning("⚠️ REEL_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        storage_key = generate_storage_key("reels_list", username)
        
        existing = await get_from_index(storage_key)
        if existing:
            return existing["message_id"]
        
        items = reels_data.get("items", [])
        
        message_lines = [
            f"🎬 <b>لیست ریل‌های @{username}</b>",
            "━━━━━━━━━━━━━━━━",
            f"📊 تعداد: {len(items)} ریل",
            "",
            "<b>لیست ریل‌ها:</b>"
        ]
        
        for idx, item in enumerate(items[:30]):
            caption = item.get("caption", "بدون کپشن")[:50]
            message_lines.append(f"{idx+1}. 🎬 {caption}")
        
        if len(items) > 30:
            message_lines.append(f"\n... و {len(items) - 30} ریل دیگر")
        
        message_lines.append("━━━━━━━━━━━━━━━━")
        message_lines.append(f"🔑 کلید: {storage_key}")
        message_lines.append(f"💾 {time.strftime('%Y/%m/%d %H:%M:%S')}")
        
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text="\n".join(message_lines),
            parse_mode='HTML'
        )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "reels_list", {
                "username": username,
                "reels_count": len(items)
            })
            
            _set_memory_cache(f"reels_list:{username}", {"data": reels_data}, ttl=86400)
            
            # ذخیره هر ریل به صورت جداگانه در همین کانال
            for idx, item in enumerate(items):
                reel_key = f"reel:{username}:{item.get('id', idx)}"
                reel_data = {"caption": item.get("caption", ""), "items": [{"type": "video", "url": item.get("url")}]}
                await save_media_to_channel(context, reel_key, reel_data, 'reel')
            
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست ریل‌ها: {e}")
        return None


async def get_reels_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    """بازیابی لیست ریل‌ها"""
    cache_key = f"reels_list:{username}"
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    
    storage_key = generate_storage_key("reels_list", username)
    index_data = await get_from_index(storage_key)
    if index_data:
        metadata = index_data.get("metadata", {})
        return {"items": []}  # placeholder
    
    return None


# ========== لیست هایلایت‌ها (ذخیره در همان کانال HIGHLIGHT_CHANNEL_ID) ==========

async def save_highlights_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, highlights: list) -> Optional[int]:
    """ذخیره لیست هایلایت‌ها در کانال هایلایت (همان HIGHLIGHT_CHANNEL_ID)"""
    
    channel_id = _get_channel_for_type('highlights_list')  # این هم HIGHLIGHT_CHANNEL_ID برمی‌گرداند
    if not channel_id:
        logger.warning("⚠️ HIGHLIGHT_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        storage_key = generate_storage_key("highlights_list", username)
        
        existing = await get_from_index(storage_key)
        if existing:
            return existing["message_id"]
        
        message_lines = [
            f"📚 <b>لیست هایلایت‌های @{username}</b>",
            "━━━━━━━━━━━━━━━━",
            f"📊 تعداد: {len(highlights)} هایلایت",
            "",
            "<b>لیست هایلایت‌ها:</b>"
        ]
        
        for idx, h in enumerate(highlights[:30]):
            title = h.get("title", "بدون عنوان")
            count = h.get("count", 0)
            message_lines.append(f"{idx+1}. 📌 {title} ({count} آیتم)")
        
        if len(highlights) > 30:
            message_lines.append(f"\n... و {len(highlights) - 30} هایلایت دیگر")
        
        message_lines.append("━━━━━━━━━━━━━━━━")
        message_lines.append(f"🔑 کلید: {storage_key}")
        message_lines.append(f"💾 {time.strftime('%Y/%m/%d %H:%M:%S')}")
        
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text="\n".join(message_lines),
            parse_mode='HTML'
        )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "highlights_list", {
                "username": username,
                "highlights_count": len(highlights)
            })
            
            _set_memory_cache(f"highlights_list:{username}", {"data": highlights}, ttl=86400)
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست هایلایت‌ها: {e}")
        return None


async def get_highlights_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[list]:
    """بازیابی لیست هایلایت‌ها"""
    cache_key = f"highlights_list:{username}"
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    
    storage_key = generate_storage_key("highlights_list", username)
    index_data = await get_from_index(storage_key)
    if index_data:
        metadata = index_data.get("metadata", {})
        return metadata.get("highlights", [])
    
    return None


# ========== تنظیمات کاربر ==========

async def save_user_setting_to_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int, mode: str) -> Optional[int]:
    """ذخیره تنظیمات کاربر"""
    
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
                await context.bot.delete_message(
                    chat_id=channel_id,
                    message_id=existing["message_id"]
                )
            except:
                pass
        
        msg = await context.bot.send_message(
            chat_id=channel_id,
            text=message_text,
            parse_mode='HTML'
        )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "user_setting", {
                "user_id": user_id,
                "mode": mode
            })
            
            logger.info(f"✅ تنظیمات کاربر {user_id} ذخیره شد")
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره تنظیمات کاربر: {e}")
        return None


async def get_user_setting_from_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Optional[str]:
    """بازیابی تنظیمات کاربر"""
    
    channel_id = _get_channel_for_type('user_setting')
    if not channel_id:
        return None
    
    storage_key = generate_storage_key("user_setting", str(user_id))
    
    index_data = await get_from_index(storage_key)
    if not index_data:
        return None
    
    message_id = index_data.get("message_id")
    if not message_id:
        return None
    
    try:
        msg = await context.bot.forward_message(
            chat_id=channel_id,
            from_chat_id=channel_id,
            message_id=message_id
        )
        
        text = msg.caption or msg.text or ""
        
        if "حالت: album" in text or "mode: album" in text:
            return "album"
        elif "حالت: file" in text or "mode: file" in text:
            return "file"
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی تنظیمات کاربر: {e}")
        return None


# ========== توابع کمکی ==========

async def get_media_by_key(context: ContextTypes.DEFAULT_TYPE, storage_key: str) -> Optional[dict]:
    """بازیابی مدیا با کلید"""
    
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
    
    metadata = index_data.get("metadata", {})
    message_ids = metadata.get("message_ids", [])
    
    if not message_ids:
        message_id = index_data.get("message_id")
        if message_id:
            message_ids = [message_id]
    
    if not message_ids:
        return None
    
    items = []
    caption = ""
    
    for msg_id in message_ids[:10]:
        try:
            msg = await context.bot.forward_message(
                chat_id=channel_id,
                from_chat_id=channel_id,
                message_id=msg_id
            )
            
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
    """سازگاری با کد قدیمی"""
    from extract_instagram_id import extract_instagram_id
    
    extracted = extract_instagram_id(media_key)
    if extracted:
        storage_key = f"{extracted['type']}:{extracted['full_id']}"
    else:
        storage_key = f"post:{hashlib.md5(media_key.encode()).hexdigest()}"
    
    return await get_media_by_key(context, storage_key)


def clear_memory_cache():
    """پاک کردن کش حافظه"""
    global _memory_cache
    _memory_cache.clear()
    logger.info("🧹 کش حافظه پاک شد")
