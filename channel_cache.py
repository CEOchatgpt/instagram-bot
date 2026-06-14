# channel_cache.py - نسخه نهایی با پشتیبانی از قفل فایل، بکاپ و شناسه یکتا

import logging
import hashlib
import time
import asyncio
from typing import Optional, Any, List, Dict
from telegram.ext import ContextTypes
from config import (
    PROFILE_CHANNEL_ID,
    MEDIA_CHANNEL_ID,
    REELS_LIST_CHANNEL_ID,
    HIGHLIGHTS_LIST_CHANNEL_ID,
    USER_SETTING_CHANNEL_ID
)
from index_manager import (
    save_to_index, get_from_index, delete_from_index, 
    generate_storage_key, search_by_media_id
)

logger = logging.getLogger(__name__)

# کش حافظه برای کاهش درخواست به کانال
_memory_cache = {}
CACHE_TTL = 300  # 5 دقیقه


def _get_memory_cache(key: str) -> Optional[Any]:
    """دریافت از کش حافظه"""
    if key in _memory_cache:
        item = _memory_cache[key]
        if time.time() < item["expires"]:
            return item["data"]
        else:
            del _memory_cache[key]
    return None


def _set_memory_cache(key: str, data: Any, ttl: int = CACHE_TTL):
    """ذخیره در کش حافظه"""
    _memory_cache[key] = {"data": data, "expires": time.time() + ttl}


def _generate_key_hash(data_key: str) -> str:
    """تولید هش برای کلیدهای معمولی"""
    return hashlib.md5(data_key.encode()).hexdigest()[:16]


def _format_caption(caption: str, max_len: int = 300) -> str:
    """فرمت کردن کپشن برای ذخیره"""
    if not caption:
        return "بدون کپشن"
    if len(caption) > max_len:
        return caption[:max_len] + "..."
    return caption


def _extract_media_id_from_key(media_key: str) -> Optional[str]:
    """استخراج شناسه یکتا از کلید رسانه"""
    import re
    patterns = [
        r'(?:post|reel|tv):([A-Za-z0-9_-]+)',
        r'id:([A-Za-z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, media_key)
        if match:
            return match.group(1)
    return None


# ========== ذخیره و بازیابی پروفایل ==========

async def save_profile_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, profile_data: dict) -> Optional[int]:
    """ذخیره پروفایل به صورت readable در کانال"""
    
    if not PROFILE_CHANNEL_ID:
        logger.warning("⚠️ PROFILE_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        storage_key = generate_storage_key("profile", username)
        
        # چک کن قبلاً ذخیره شده؟
        existing = await get_from_index(storage_key)
        if existing:
            logger.info(f"📦 پروفایل {username} قبلاً در کانال ذخیره شده (msg_id: {existing['message_id']})")
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
                    chat_id=PROFILE_CHANNEL_ID,
                    photo=profile_data["profile_pic"],
                    caption=message_text,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"خطا در ارسال عکس: {e}")
                msg = await context.bot.send_message(
                    chat_id=PROFILE_CHANNEL_ID,
                    text=message_text,
                    parse_mode='HTML'
                )
        else:
            msg = await context.bot.send_message(
                chat_id=PROFILE_CHANNEL_ID,
                text=message_text,
                parse_mode='HTML'
            )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "profile", {
                "username": username,
                "full_name": profile_data.get("full_name", "")
            })
            
            # ذخیره در کش حافظه
            _set_memory_cache(f"profile:{username}", {
                "message_id": msg.message_id,
                "data": profile_data
            }, ttl=86400)
            
            logger.info(f"✅ پروفایل {username} ذخیره شد (msg_id: {msg.message_id})")
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره پروفایل: {e}")
        return None


async def get_profile_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    """بازیابی پروفایل از کانال"""
    
    if not PROFILE_CHANNEL_ID:
        return None
    
    storage_key = generate_storage_key("profile", username)
    cache_key = f"profile:{username}"
    
    # چک کش حافظه
    cached = _get_memory_cache(cache_key)
    if cached:
        logger.info(f"📦 پروفایل {username} از کش برگردانده شد")
        return cached.get("data")
    
    # چک ایندکس
    index_data = await get_from_index(storage_key)
    if not index_data:
        logger.info(f"🔍 پروفایل {username} در ایندکس یافت نشد")
        return None
    
    message_id = index_data.get("message_id")
    if not message_id:
        return None
    
    try:
        # فوروارد پیام به خودش برای گرفتن محتوا
        msg = await context.bot.forward_message(
            chat_id=PROFILE_CHANNEL_ID,
            from_chat_id=PROFILE_CHANNEL_ID,
            message_id=message_id
        )
        
        # استخراج دیتا از کپشن
        caption = msg.caption or msg.text or ""
        
        # ساخت دیکشنری پروفایل از روی کپشن
        profile_data = {
            "username": username,
            "full_name": username,
            "biography": "",
            "followers": 0,
            "following": 0,
            "posts": 0,
            "profile_pic": None,
            "is_private": False,
            "is_verified": False,
            "from_channel_cache": True
        }
        
        # تلاش برای استخراج از متن
        lines = caption.split("\n")
        for line in lines:
            if "🔖" in line:
                profile_data["username"] = line.replace("🔖", "").strip().lstrip("@")
            elif "📝" in line:
                profile_data["biography"] = line.replace("📝", "").strip()
            elif "❤️" in line:
                try:
                    parts = line.split("❤️")[1].split("دنبال‌کننده")[0].strip().replace(",", "")
                    profile_data["followers"] = int(parts) if parts.isdigit() else 0
                except:
                    pass
            elif "🔒" in line:
                profile_data["is_private"] = True
            elif "✅" in line and "تأیید" in line:
                profile_data["is_verified"] = True
        
        # اگه عکس داشت، از پیام بگیر
        if msg.photo:
            profile_data["profile_pic"] = msg.photo[-1].file_id
        
        # ذخیره در کش
        _set_memory_cache(cache_key, {"data": profile_data}, ttl=86400)
        
        logger.info(f"✅ پروفایل {username} از کانال بازیابی شد")
        return profile_data
        
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی پروفایل: {e}")
        return None


# ========== تابع اصلی ذخیره (با کلید مشخص) ==========

async def save_media_with_key(context: ContextTypes.DEFAULT_TYPE, storage_key: str, media_data: dict, original_url: str = None) -> Optional[int]:
    """
    ذخیره مدیا با کلید مشخص (برای اطمینان از یکسان بودن کلید در ذخیره و بازیابی)
    """
    if not MEDIA_CHANNEL_ID:
        logger.warning("⚠️ MEDIA_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        # چک کن قبلاً ذخیره شده؟
        from index_manager import get_from_index
        existing = await get_from_index(storage_key)
        if existing:
            logger.info(f"📦 مدیا {storage_key} قبلاً ذخیره شده (msg_id: {existing['message_id']})")
            return existing["message_id"]
        
        items = media_data.get("items", [])
        caption = media_data.get("caption", "بدون کپشن")
        formatted_caption = _format_caption(caption, 200)
        
        message_ids = []
        
        for idx, item in enumerate(items):
            item_type = item.get("type", "photo")
            item_url = item.get("url")
            
            if not item_url:
                continue
            
            item_caption = f"""📦 محتوای ذخیره شده
━━━━━━━━━━━━━━━━
🔑 کلید: {storage_key}
📌 {idx + 1}/{len(items)}
📝 {formatted_caption}
━━━━━━━━━━━━━━━━
💾 {time.strftime('%Y/%m/%d %H:%M:%S')}"""
            
            try:
                if item_type == "video":
                    msg = await context.bot.send_video(
                        chat_id=MEDIA_CHANNEL_ID,
                        video=item_url,
                        caption=item_caption[:1024],
                        parse_mode='HTML',
                        supports_streaming=True
                    )
                else:
                    msg = await context.bot.send_photo(
                        chat_id=MEDIA_CHANNEL_ID,
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
                        chat_id=MEDIA_CHANNEL_ID,
                        document=item_url,
                        caption=item_caption[:900],
                        parse_mode='HTML'
                    )
                    message_ids.append(msg.message_id)
                    await asyncio.sleep(0.3)
                except Exception as e2:
                    logger.error(f"خطا در ارسال داکیومنت: {e2}")
        
        if message_ids:
            from index_manager import save_to_index
            await save_to_index(storage_key, message_ids[0], "media", {
                "original_url": original_url,
                "item_count": len(message_ids),
                "message_ids": message_ids
            })
            
            _set_memory_cache(f"media:{storage_key}", {
                "message_ids": message_ids,
                "data": media_data
            }, ttl=86400)
            
            logger.info(f"✅ {len(message_ids)} رسانه ذخیره شد (key: {storage_key})")
            return message_ids[0]
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره مدیا: {e}")
        return None


# ========== تابع ذخیره با نرمال‌سازی کلید (جایگزین save_media_to_channel قبلی) ==========

async def save_media_to_channel(context: ContextTypes.DEFAULT_TYPE, media_key: str, media_data: dict) -> Optional[int]:
    """
    ذخیره محتوای مدیا - با نرمال‌سازی کلید برای اطمینان از یکسان بودن
    """
    from extract_instagram_id import normalize_url, extract_instagram_id
    
    # نرمال‌سازی کلید
    extracted = extract_instagram_id(media_key)
    if extracted:
        storage_key = f"media:{extracted['full_id']}"
    else:
        normalized = normalize_url(media_key)
        if "media:" in normalized:
            storage_key = normalized
        else:
            storage_key = f"media:{hashlib.md5(normalized.encode()).hexdigest()}"
    
    return await save_media_with_key(context, storage_key, media_data, media_key)


# ========== تابع بازیابی با کلید مشخص ==========

async def get_media_by_key(context: ContextTypes.DEFAULT_TYPE, storage_key: str) -> Optional[dict]:
    """
    بازیابی مدیا با کلید مستقیم (بدون نیاز به ساخت مجدد کلید)
    """
    if not MEDIA_CHANNEL_ID:
        return None
    
    cache_key = f"media:{storage_key}"
    
    # چک کش حافظه
    cached = _get_memory_cache(cache_key)
    if cached:
        logger.info(f"📦 مدیا {storage_key} از کش برگردانده شد")
        return cached.get("data")
    
    # چک ایندکس
    from index_manager import get_from_index
    index_data = await get_from_index(storage_key)
    if not index_data:
        logger.info(f"🔍 مدیا {storage_key} در ایندکس یافت نشد")
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
                chat_id=MEDIA_CHANNEL_ID,
                from_chat_id=MEDIA_CHANNEL_ID,
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


# ========== تابع بازیابی با نرمال‌سازی کلید (جایگزین get_media_from_channel قبلی) ==========

async def get_media_from_channel(context: ContextTypes.DEFAULT_TYPE, media_key: str) -> Optional[dict]:
    """
    بازیابی مدیا از کانال - با نرمال‌سازی کلید
    """
    from extract_instagram_id import normalize_url, extract_instagram_id
    
    # نرمال‌سازی کلید (همان روشی که در ذخیره استفاده شد)
    extracted = extract_instagram_id(media_key)
    if extracted:
        storage_key = f"media:{extracted['full_id']}"
    else:
        normalized = normalize_url(media_key)
        if "media:" in normalized:
            storage_key = normalized
        else:
            storage_key = f"media:{hashlib.md5(normalized.encode()).hexdigest()}"
    
    return await get_media_by_key(context, storage_key)

# ========== ذخیره و بازیابی لیست ریل‌ها ==========

async def save_reels_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, reels_data: dict) -> Optional[int]:
    """ذخیره لیست ریل‌ها"""
    
    if not REELS_LIST_CHANNEL_ID:
        return None
    
    try:
        storage_key = generate_storage_key("reels", username)
        
        existing = await get_from_index(storage_key)
        if existing:
            return existing["message_id"]
        
        items = reels_data.get("items", [])
        
        message_lines = [
            f"🎬 <b>لیست ریل‌های @{username}</b>",
            "━━━━━━━━━━━━━━━━",
            f"📊 تعداد: {len(items)} ریل",
            "",
            "<b>لیست:</b>"
        ]
        
        for idx, item in enumerate(items[:20]):
            caption = item.get("caption", "بدون کپشن")[:50]
            message_lines.append(f"{idx+1}. 🎬 {caption}")
        
        if len(items) > 20:
            message_lines.append(f"\n... و {len(items) - 20} ریل دیگر")
        
        message_lines.append("━━━━━━━━━━━━━━━━")
        message_lines.append(f"🔑 کلید: {storage_key}")
        message_lines.append(f"💾 {time.strftime('%Y/%m/%d %H:%M:%S')}")
        
        msg = await context.bot.send_message(
            chat_id=REELS_LIST_CHANNEL_ID,
            text="\n".join(message_lines),
            parse_mode='HTML'
        )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "reels", {
                "username": username,
                "reels_count": len(items)
            })
            
            _set_memory_cache(f"reels:{username}", {"data": reels_data}, ttl=86400)
            
            # ذخیره هر ریل به صورت جداگانه
            for idx, item in enumerate(items):
                reel_key = f"reel:{username}:{item.get('id', idx)}"
                reel_data = {"caption": item.get("caption", ""), "items": [{"type": "video", "url": item.get("url")}]}
                await save_media_to_channel(context, reel_key, reel_data)
            
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست ریل‌ها: {e}")
        return None


async def get_reels_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    """بازیابی لیست ریل‌ها"""
    cache_key = f"reels:{username}"
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    return None


# ========== ذخیره و بازیابی لیست هایلایت‌ها ==========

async def save_highlights_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, highlights: list) -> Optional[int]:
    """ذخیره لیست هایلایت‌ها"""
    
    if not HIGHLIGHTS_LIST_CHANNEL_ID:
        return None
    
    try:
        storage_key = generate_storage_key("highlights", username)
        
        existing = await get_from_index(storage_key)
        if existing:
            return existing["message_id"]
        
        message_lines = [
            f"📚 <b>هایلایت‌های @{username}</b>",
            "━━━━━━━━━━━━━━━━",
            f"📊 تعداد: {len(highlights)} هایلایت",
            "",
            "<b>لیست:</b>"
        ]
        
        for idx, h in enumerate(highlights[:20]):
            title = h.get("title", "بدون عنوان")
            count = h.get("count", 0)
            message_lines.append(f"{idx+1}. 📌 {title} ({count} آیتم)")
        
        if len(highlights) > 20:
            message_lines.append(f"\n... و {len(highlights) - 20} هایلایت دیگر")
        
        message_lines.append("━━━━━━━━━━━━━━━━")
        message_lines.append(f"🔑 کلید: {storage_key}")
        message_lines.append(f"💾 {time.strftime('%Y/%m/%d %H:%M:%S')}")
        
        msg = await context.bot.send_message(
            chat_id= HIGHLIGHTS_LIST_CHANNEL_ID,
            text="\n".join(message_lines),
            parse_mode='HTML'
        )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "highlights", {
                "username": username,
                "highlights_count": len(highlights)
            })
            
            _set_memory_cache(f"highlights:{username}", {"data": highlights}, ttl=86400)
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست هایلایت‌ها: {e}")
        return None


async def get_highlights_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[list]:
    """بازیابی لیست هایلایت‌ها"""
    cache_key = f"highlights:{username}"
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    
    # سعی کن از ایندکس هم پیدا کنی
    storage_key = generate_storage_key("highlights", username)
    index_data = await get_from_index(storage_key)
    if index_data:
        metadata = index_data.get("metadata", {})
        return metadata.get("highlights", [])
    
    return None


# ========== ذخیره و بازیابی تنظیمات کاربر ==========

async def save_user_setting_to_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int, mode: str) -> Optional[int]:
    """ذخیره تنظیمات کاربر در کانال"""
    
    if not USER_SETTING_CHANNEL_ID:
        return None
    
    try:
        storage_key = generate_storage_key("user_setting", str(user_id))
        
        mode_text = "🎬 آلبوم ترکیبی" if mode == "album" else "📁 فایل جداگانه"
        
        message_text = f"""⚙️ <b>تنظیمات کاربر</b>
━━━━━━━━━━━━━━━━
👤 کاربر: {user_id}
🎯 حالت: {mode}
📝 توضیح: {mode_text}

🔑 کلید: {storage_key}
💾 ذخیره: {time.strftime('%Y/%m/%d %H:%M:%S')}"""
        
        # حذف پیام قبلی
        existing = await get_from_index(storage_key)
        if existing:
            try:
                await context.bot.delete_message(
                    chat_id=USER_SETTING_CHANNEL_ID,
                    message_id=existing["message_id"]
                )
            except:
                pass
        
        msg = await context.bot.send_message(
            chat_id=USER_SETTING_CHANNEL_ID,
            text=message_text,
            parse_mode='HTML'
        )
        
        if msg:
            await save_to_index(storage_key, msg.message_id, "user_setting", {
                "user_id": user_id,
                "mode": mode
            })
            
            logger.info(f"✅ تنظیمات کاربر {user_id} ذخیره شد (mode: {mode})")
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره تنظیمات کاربر: {e}")
        return None


async def get_user_setting_from_channel(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> Optional[str]:
    """بازیابی تنظیمات کاربر از کانال"""
    
    if not USER_SETTING_CHANNEL_ID:
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
            chat_id=USER_SETTING_CHANNEL_ID,
            from_chat_id=USER_SETTING_CHANNEL_ID,
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

def clear_memory_cache():
    """پاک کردن کش حافظه"""
    global _memory_cache
    _memory_cache.clear()
    logger.info("🧹 کش حافظه پاک شد")


async def get_index_stats() -> Dict:
    """دریافت آمار ایندکس"""
    from index_manager import get_index_stats as get_stats
    return await get_stats()

# channel_cache.py - اضافه کردن این توابع:
