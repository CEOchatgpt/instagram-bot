# url_validator.py - تابع‌های جدید برای validation

import re
from typing import Tuple

# عبارات منظم برای validation
INSTAGRAM_URL_PATTERN = re.compile(
    r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv|stories)/[\w-]+/?',
    re.IGNORECASE
)

# TikTok URLs می‌تونند خیلی متنوع باشن
TIKTOK_URL_PATTERNS = [
    re.compile(r'https?://(?:www\.)?tiktok\.com/@[\w.-]+/video/\d+', re.IGNORECASE),
    re.compile(r'https?://(?:www\.)?tiktok\.com/v/\d+', re.IGNORECASE),
    re.compile(r'https?://vm\.tiktok\.com/[\w]+/?', re.IGNORECASE),
    re.compile(r'https?://vt\.tiktok\.com/[\w]+/?', re.IGNORECASE),
]


def validate_and_detect_platform(url: str) -> Tuple[bool, str]:
    """
    URL رو validate می‌کنه و platform رو detect میکنه
    
    Returns:
        (is_valid, platform) — platform میتونه "instagram", "tiktok", یا ""
    """
    url = url.strip()
    
    # چک Instagram
    if INSTAGRAM_URL_PATTERN.search(url):
        return True, "instagram"
    
    # چک TikTok
    for pattern in TIKTOK_URL_PATTERNS:
        if pattern.search(url):
            return True, "tiktok"
    
    return False, ""


def is_valid_url_format(url: str) -> bool:
    """بررسی اینکه URL فرمت صحیحی داره"""
    url = url.strip()
    return url.startswith(('http://', 'https://'))


# ────────────────────────────────────────────────────────────
# بخش جایگزین برای handle_link (بهتر)
# ────────────────────────────────────────────────────────────

async def handle_link_improved(update: Update, context):
    """
    بهبودشده‌ی handle_link با:
    - بهتر URL validation
    - بهتر logging
    - بهتر error messages
    """
    url = update.message.text.strip()
    user_id = update.effective_user.id
    username = update.effective_user.username or f"user_{user_id}"
    
    # ۱. Validate URL Format
    if not is_valid_url_format(url):
        logger.warning(f"Invalid URL format from {username}: {url[:50]}")
        await update.message.reply_text(
            "❌ لینک نامعتبره!\n"
            "لطفاً لینک کاملی بفرس (با http:// یا https://)"
        )
        return
    
    # ۲. Detect Platform
    is_valid, platform = validate_and_detect_platform(url)
    if not is_valid:
        logger.warning(f"Unsupported platform from {username}: {url[:50]}")
        await update.message.reply_text(
            "❌ این پلتفرم پشتیبانی نمی‌شه!\n\n"
            "✅ پلتفرم‌های پشتیبانی:\n"
            "  • Instagram (pst, reel, tv)\n"
            "  • TikTok"
        )
        return
    
    # ۳. Rate Limit Check
    limited, wait = is_rate_limited(user_id)
    if limited:
        logger.info(f"Rate limited: {username} — {wait}s remaining")
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه دیگه امتحان کن.")
        return
    
    # ۴. Processing Start
    processing_msg = await update.message.reply_text(
        f"🔄 در حال دانلود از {platform.capitalize()}..."
    )
    logger.info(f"{username} requested {platform}: {url}")
    
    try:
        if platform == "instagram":
            result = await get_instagram_media(url)
            
            if not result:
                logger.warning(f"Failed to get Instagram media from {username}")
                await processing_msg.edit_text(
                    "❌ نتونستم محتوا رو پیدا کنم.\n\n"
                    "⚠️ ممکن دلایل:\n"
                    "  • لینک دسترسی‌پذیر نیست\n"
                    "  • اکانت private است\n"
                    "  • پست حذف شده"
                )
                return
            
            logger.info(f"Successfully downloaded Instagram media: {len(result['items'])} items")
            context.user_data["pending_result"] = result
            await processing_msg.delete()
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📷 عکس معمولی", callback_data="send_photo"),
                    InlineKeyboardButton("📁 فایل", callback_data="send_file"),
                ]
            ])
            await update.message.reply_text(
                "✨ نوع ارسال را انتخاب کن\n\n"
                "📷 عکس معمولی → نمایش مستقیم\n"
                "📁 فایل → کیفیت اصلی",
                reply_markup=keyboard
            )
        
        else:  # TikTok
            result = await get_tiktok_media(url)  # اگه async شد، بدون asyncio.to_thread
            
            if not result or not result.get("url"):
                logger.warning(f"Failed to get TikTok video from {username}")
                await processing_msg.edit_text(
                    "❌ نتونستم ویدیو تیک‌تاک رو دانلود کنم.\n\n"
                    "⚠️ ممکن دلایل:\n"
                    "  • لینک دسترسی‌پذیر نیست\n"
                    "  • ویدیو محدود است\n"
                    "  • ویدیو حذف شده"
                )
                return
            
            logger.info(f"Successfully downloaded TikTok video from {username}")
            await processing_msg.delete()
            await send_tiktok_video(update.message, result)
    
    except asyncio.TimeoutError:
        logger.error(f"Timeout while processing {platform} from {username}")
        await processing_msg.edit_text("⏱️ زمان‌بندی منقضی شد. دوباره امتحان کن.")
    
    except Exception as e:
        logger.error(f"Unexpected error in handle_link: {e}", exc_info=True)
        await processing_msg.edit_text("❌ خطایی ناشناخته رخ داد. دوباره امتحان کن.")
