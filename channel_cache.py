# channel_cache.py - ذخیره محتوای واقعی در کانال تلگرام

import logging
import hashlib
import json
import time
import asyncio
from typing import Optional, Any, List, Dict
from telegram.ext import ContextTypes
from config import DATABASE_CHANNEL_ID

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
    """تولید هش برای کلید"""
    return hashlib.md5(data_key.encode()).hexdigest()[:16]


def _format_caption_for_channel(caption: str, max_len: int = 300) -> str:
    """فرمت کردن کپشن برای ذخیره در کانال"""
    if not caption:
        return "بدون کپشن"
    if len(caption) > max_len:
        return caption[:max_len] + "..."
    return caption


async def save_profile_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, profile_data: dict) -> Optional[int]:
    """ذخیره پروفایل به صورت readable در کانال"""
    
    if not DATABASE_CHANNEL_ID:
        logger.warning("⚠️ DATABASE_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        key_hash = _generate_key_hash(f"profile:{username}")
        cache_key = f"profile:{username}"
        
        # ساخت پیام readable
        private_text = "🔒 خصوصی" if profile_data.get('is_private') else "🌐 عمومی"
        verified_text = "✅ تأیید شده" if profile_data.get('is_verified') else ""
        
        message_text = f"""
👤 <b>پروفایل ذخیره شده</b>
━━━━━━━━━━━━━━━━
🔖 <b>@{profile_data.get('username', username)}</b>
📝 {profile_data.get('biography', 'بدون بیو')[:200]}

📊 <b>آمار:</b>
❤️ {profile_data.get('followers', 0):,} دنبال‌کننده
👥 {profile_data.get('following', 0):,} دنبال‌شونده
📸 {profile_data.get('posts', 0):,} پست

{private_text} {verified_text}
━━━━━━━━━━━━━━━━
💾 ذخیره‌شده در: {time.strftime('%Y/%m/%d %H:%M:%S')}
🔑 کلید: {key_hash}
"""
        
        # ارسال عکس پروفایل به صورت جداگانه
        msg = None
        if profile_data.get("profile_pic"):
            try:
                msg = await context.bot.send_photo(
                    chat_id=DATABASE_CHANNEL_ID,
                    photo=profile_data["profile_pic"],
                    caption=message_text,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"خطا در ارسال عکس پروفایل: {e}")
                msg = await context.bot.send_message(
                    chat_id=DATABASE_CHANNEL_ID,
                    text=message_text,
                    parse_mode='HTML'
                )
        else:
            msg = await context.bot.send_message(
                chat_id=DATABASE_CHANNEL_ID,
                text=message_text,
                parse_mode='HTML'
            )
        
        if msg:
            # ذخیره متادیتا در کش
            _set_memory_cache(cache_key, {
                "message_id": msg.message_id,
                "data": profile_data,
                "type": "profile"
            }, ttl=86400)  # 24 ساعت کش
            
            logger.info(f"✅ پروفایل {username} در کانال ذخیره شد (msg_id: {msg.message_id})")
            return msg.message_id
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره پروفایل: {e}")
        return None


async def get_profile_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    """بازیابی پروفایل از کانال"""
    
    if not DATABASE_CHANNEL_ID:
        return None
    
    cache_key = f"profile:{username}"
    
    # چک کش حافظه
    cached = _get_memory_cache(cache_key)
    if cached:
        logger.info(f"📦 پروفایل {username} از حافظه کش برگردانده شد")
        return cached.get("data")
    
    # برای بازیابی کامل، باید message_id رو بدونیم
    # اینجا یک روش ساده: می‌تونیم message_id رو توی یه فایل یا متغیر محیطی ذخیره کنیم
    # فعلاً null برمی‌گردونیم تا از API گرفته بشه
    
    logger.info(f"🔍 پروفایل {username} در کش حافظه یافت نشد")
    return None


async def save_media_to_channel(context: ContextTypes.DEFAULT_TYPE, media_key: str, media_data: dict) -> Optional[int]:
    """ذخیره محتوای مدیا به صورت فایل واقعی در کانال"""
    
    if not DATABASE_CHANNEL_ID:
        logger.warning("⚠️ DATABASE_CHANNEL_ID تنظیم نشده!")
        return None
    
    try:
        key_hash = _generate_key_hash(media_key)
        items = media_data.get("items", [])
        caption = media_data.get("caption", "بدون کپشن")
        formatted_caption = _format_caption_for_channel(caption, 300)
        
        cache_key = f"media:{key_hash}"
        message_ids = []
        
        # ذخیره هر آیتم به صورت جداگانه
        for idx, item in enumerate(items):
            item_type = item.get("type", "photo")
            item_url = item.get("url")
            
            if not item_url:
                continue
            
            # ساخت کپشن برای این آیتم
            item_caption = f"""
📦 <b>محتوای ذخیره شده</b>
━━━━━━━━━━━━━━━━
🔑 کلید: {key_hash}
📌 شماره: {idx + 1}/{len(items)}
📝 {formatted_caption}
━━━━━━━━━━━━━━━━
💾 ذخیره‌شده در: {time.strftime('%Y/%m/%d %H:%M:%S')}
"""
            
            try:
                if item_type == "video":
                    msg = await context.bot.send_video(
                        chat_id=DATABASE_CHANNEL_ID,
                        video=item_url,
                        caption=item_caption if len(item_caption) < 1024 else item_caption[:900] + "...",
                        parse_mode='HTML',
                        supports_streaming=True
                    )
                else:
                    msg = await context.bot.send_photo(
                        chat_id=DATABASE_CHANNEL_ID,
                        photo=item_url,
                        caption=item_caption if len(item_caption) < 1024 else item_caption[:900] + "...",
                        parse_mode='HTML'
                    )
                
                message_ids.append(msg.message_id)
                await asyncio.sleep(0.5)  # تاخیر بین ارسال‌ها
                
            except Exception as e:
                logger.warning(f"خطا در ارسال آیتم {idx}: {e}")
                # اگه ارسال مستقیم نشد، به صورت داکیومنت بفرست
                try:
                    msg = await context.bot.send_document(
                        chat_id=DATABASE_CHANNEL_ID,
                        document=item_url,
                        caption=item_caption[:900],
                        parse_mode='HTML'
                    )
                    message_ids.append(msg.message_id)
                    await asyncio.sleep(0.5)
                except Exception as e2:
                    logger.error(f"خطا در ارسال داکیومنت: {e2}")
        
        if message_ids:
            # ذخیره متادیتا در کش
            _set_memory_cache(cache_key, {
                "message_ids": message_ids,
                "data": media_data,
                "type": "media",
                "count": len(message_ids)
            }, ttl=86400)  # 24 ساعت
            
            logger.info(f"✅ {len(message_ids)} رسانه برای کلید {key_hash} در کانال ذخیره شد")
            return message_ids[0]
        
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره مدیا: {e}")
        return None


async def get_media_from_channel(context: ContextTypes.DEFAULT_TYPE, media_key: str) -> Optional[dict]:
    """بازیابی مدیا از کانال - با فوروارد کردن پیام‌ها"""
    
    if not DATABASE_CHANNEL_ID:
        return None
    
    key_hash = _generate_key_hash(media_key)
    cache_key = f"media:{key_hash}"
    
    # چک کش حافظه
    cached = _get_memory_cache(cache_key)
    if cached:
        logger.info(f"📦 مدیا {key_hash} از حافظه کش برگردانده شد")
        return cached.get("data")
    
    # برای بازیابی، باید پیام‌ها رو از کانال فوروارد کنیم
    # این نیازمند اینه که message_idها رو ذخیره کرده باشیم
    # فعلاً یه پیاده‌سازی ساده:
    
    try:
        # جستجو در کانال با استفاده از کلید
        # (این روش کامل نیست، برای بهبود نیاز به ایندکس داره)
        
        # یه پیام تست می‌فرستیم تا ببینیم کلید وجود داره؟
        # در عمل بهتره message_idها رو توی یه فایل یا متغیر محیطی ذخیره کنی
        
        logger.info(f"🔍 مدیا {key_hash} در حال جستجو در کانال...")
        
        # فعلاً null برمی‌گردونیم
        return None
        
    except Exception as e:
        logger.error(f"❌ خطا در بازیابی مدیا: {e}")
        return None


async def save_reels_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, reels_data: dict) -> Optional[int]:
    """ذخیره لیست ریل‌ها به صورت readable در کانال"""
    
    if not DATABASE_CHANNEL_ID:
        return None
    
    try:
        key_hash = _generate_key_hash(f"reels:{username}")
        items = reels_data.get("items", [])
        
        # ساخت پیام لیست ریل‌ها
        message_lines = [
            f"🎬 <b>لیست ریل‌های @{username}</b>",
            "━━━━━━━━━━━━━━━━",
            f"📊 تعداد: {len(items)} ریل",
            "",
            "<b>لیست ریل‌ها:</b>"
        ]
        
        for idx, item in enumerate(items[:20]):  # حداکثر 20 تا
            caption_preview = item.get("caption", "بدون کپشن")[:50]
            message_lines.append(f"{idx+1}. 🎬 {caption_preview}")
        
        if len(items) > 20:
            message_lines.append(f"\n... و {len(items) - 20} ریل دیگر")
        
        message_lines.append("━━━━━━━━━━━━━━━━")
        message_lines.append(f"🔑 کلید: {key_hash}")
        message_lines.append(f"💾 ذخیره‌شده در: {time.strftime('%Y/%m/%d %H:%M:%S')}")
        
        message_text = "\n".join(message_lines)
        
        msg = await context.bot.send_message(
            chat_id=DATABASE_CHANNEL_ID,
            text=message_text,
            parse_mode='HTML'
        )
        
        cache_key = f"reels:{username}"
        _set_memory_cache(cache_key, {
            "message_id": msg.message_id,
            "data": reels_data,
            "type": "reels"
        }, ttl=86400)
        
        logger.info(f"✅ لیست ریل‌های {username} در کانال ذخیره شد (msg_id: {msg.message_id})")
        
        # همچنین هر ریل رو به صورت جداگانه ذخیره کن
        for idx, item in enumerate(items):
            reel_key = f"reel:{username}:{item.get('id', idx)}"
            reel_data = {"caption": item.get("caption", ""), "items": [{"type": "video", "url": item.get("url")}]}
            await save_media_to_channel(context, reel_key, reel_data)
        
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست ریل‌ها: {e}")
        return None


async def save_highlights_list_to_channel(context: ContextTypes.DEFAULT_TYPE, username: str, highlights: list) -> Optional[int]:
    """ذخیره لیست هایلایت‌ها به صورت readable در کانال"""
    
    if not DATABASE_CHANNEL_ID:
        return None
    
    try:
        key_hash = _generate_key_hash(f"highlights:{username}")
        
        message_lines = [
            f"📚 <b>هایلایت‌های @{username}</b>",
            "━━━━━━━━━━━━━━━━",
            f"📊 تعداد: {len(highlights)} هایلایت",
            "",
            "<b>لیست هایلایت‌ها:</b>"
        ]
        
        for idx, h in enumerate(highlights[:20]):
            title = h.get("title", "بدون عنوان")
            count = h.get("count", 0)
            message_lines.append(f"{idx+1}. 📌 {title} ({count} آیتم)")
        
        if len(highlights) > 20:
            message_lines.append(f"\n... و {len(highlights) - 20} هایلایت دیگر")
        
        message_lines.append("━━━━━━━━━━━━━━━━")
        message_lines.append(f"🔑 کلید: {key_hash}")
        message_lines.append(f"💾 ذخیره‌شده در: {time.strftime('%Y/%m/%d %H:%M:%S')}")
        
        message_text = "\n".join(message_lines)
        
        msg = await context.bot.send_message(
            chat_id=DATABASE_CHANNEL_ID,
            text=message_text,
            parse_mode='HTML'
        )
        
        cache_key = f"highlights:{username}"
        _set_memory_cache(cache_key, {
            "message_id": msg.message_id,
            "data": highlights,
            "type": "highlights"
        }, ttl=86400)
        
        logger.info(f"✅ لیست هایلایت‌های {username} در کانال ذخیره شد (msg_id: {msg.message_id})")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره لیست هایلایت‌ها: {e}")
        return None


async def get_reels_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[dict]:
    """بازیابی لیست ریل‌ها از کانال"""
    cache_key = f"reels:{username}"
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    return None


async def get_highlights_list_from_channel(context: ContextTypes.DEFAULT_TYPE, username: str) -> Optional[list]:
    """بازیابی لیست هایلایت‌ها از کانال"""
    cache_key = f"highlights:{username}"
    cached = _get_memory_cache(cache_key)
    if cached:
        return cached.get("data")
    return None
