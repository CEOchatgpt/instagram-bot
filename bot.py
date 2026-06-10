import aiohttp
from io import BytesIO
import logging
import time
import asyncio
from collections import defaultdict

from telegram import (
    Update,
    InputMediaVideo,
    InputMediaPhoto,
    InputMediaDocument,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config import BOT_TOKEN
from rapidapi_service import get_instagram_media
from services.tiktok_service import get_tiktok_media   # ← جدید

# تنظیم لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Rate Limiting ───────────────────────────────────────────────────
RATE_LIMIT  = 3
WINDOW_SECS = 60

user_requests: dict[int, list[float]] = defaultdict(list)

def is_rate_limited(user_id: int) -> tuple[bool, int]:
    now = time.time()
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < WINDOW_SECS]

    if len(user_requests[user_id]) >= RATE_LIMIT:
        oldest = user_requests[user_id][0]
        wait_secs = int(WINDOW_SECS - (now - oldest)) + 1
        return True, wait_secs

    user_requests[user_id].append(now)
    return False, 0


async def start(update: Update, context):
    await update.message.reply_text(
        "🎬 سلام! لینک پست اینستاگرام یا تیک‌تاک رو بفرست.\n\n"
        f"⚠️ محدودیت: هر {WINDOW_SECS} ثانیه، {RATE_LIMIT} درخواست"
    )


async def help_command(update: Update, context):
    await update.message.reply_text(
        "📖 راهنمای ربات\n\n"
        "🔹 نحوه استفاده:\n"
        "  لینک پست عمومی اینستاگرام یا تیک‌تاک رو بفرست\n\n"
        "🔹 پلتفرم‌های پشتیبانی‌شده:\n"
        "  • Instagram (پست، ریلز، کاروسل)\n"
        "  • TikTok (ویدیو)\n\n"
        "🔹 دستورات:\n"
        "  /start — شروع ربات\n"
        "  /help  — نمایش راهنما\n\n"
        "⚡ ساخته‌شده با Python & python-telegram-bot"
    )


# ─────────────────────────────────────────────────────────────
# ارسال ویدیو تیک‌تاک
# ─────────────────────────────────────────────────────────────
async def send_tiktok_video(message, media):
    """ارسال ویدیو تیک‌تاک"""
    try:
        processing = await message.reply_text("📥 در حال دانلود و ارسال ویدیو...")

        video_file = await download_video_for_telegram(media["url"])

        if video_file:
            await message.reply_video(
                video=video_file,
                caption=media.get("caption", "🎵 TikTok Video"),
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120
            )
        else:
            # fallback مستقیم (اگر دانلود نشد)
            await message.reply_video(
                video=media["url"],
                caption=media.get("caption", "🎵 TikTok Video"),
                supports_streaming=True
            )
        
        await processing.delete()
        
    except Exception as e:
        logger.error(f"Error sending tiktok video: {e}", exc_info=True)
        await message.reply_text("❌ خطا در ارسال ویدیو.\nممکنه حجم ویدیو زیاد باشه یا لینک مشکل داشته باشه.\nبعداً دوباره امتحان کن.")
        
# هندلر اصلی لینک‌ها
async def handle_link(update: Update, context):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    url_lower = url.lower()

    # تشخیص پلتفرم
    if "instagram.com" in url_lower:
        platform = "instagram"
    elif "tiktok.com" in url_lower or "vm.tiktok.com" in url_lower:
        platform = "tiktok"
    else:
        await update.message.reply_text("❌ فقط لینک اینستاگرام و تیک‌تاک قبول میکنم!")
        return

    # Rate Limit
    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه دیگه امتحان کن.")
        return

    processing_msg = await update.message.reply_text(f"🔄 در حال دانلود از {platform.capitalize()}...")

    try:
        if platform == "instagram":
            result = await get_instagram_media(url)
            
            if not result:
                await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم. لینک رو چک کن.")
                return

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
            await processing_msg.edit_text("🔄 در حال دانلود با yt-dlp (بدون واترمارک)...")
            result = await get_tiktok_media_yt_dlp(url)
            
            if not result or not result.get("url"):
                await processing_msg.edit_text("❌ نتونستم ویدیو تیک‌تاک رو دانلود کنم.")
                return

            await processing_msg.delete()
            await send_tiktok_video(update.message, result)

    except Exception as e:
        logger.error(f"Error in handle_link: {e}")
        await processing_msg.edit_text(f"❌ خطایی رخ داد: {str(e)}")


# ─────────────────────────────────────────────────────────────
# بقیه توابع (دانلود مدیا + انتخاب فرمت) بدون تغییر
# ─────────────────────────────────────────────────────────────
async def download_media(url: str, filename: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.read()
            file_obj = BytesIO(data)
            file_obj.name = filename
            return file_obj


async def handle_format_choice(update: Update, context):
    query = update.callback_query
    await query.answer()

    as_file = (query.data == "send_file")
    result = context.user_data.get("pending_result")

    if not result:
        await query.edit_message_text("❌ اطلاعات منقضی شده. لینک رو دوباره بفرست.")
        return

    caption = result["caption"]
    items = result["items"]

    await query.delete_message()

    sending_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📤 در حال ارسال..."
    )

    try:
        if len(items) == 1:
            item = items[0]
            if item["type"] == "video":
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=item["url"],
                    supports_streaming=not as_file,
                    caption=caption
                )
            elif as_file:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    caption=caption
                )
            else:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=item["url"],
                    caption=caption
                )

        else:
            # کاروسل
            media_group = []
            for i, item in enumerate(items):
                c = caption if i == 0 else None
                if item["type"] == "video":
                    media_group.append(InputMediaVideo(media=item["url"], caption=c))
                elif as_file:
                    media_group.append(InputMediaDocument(media=item["url"], caption=c))
                else:
                    photo_file = await download_media(item["url"], f"photo_{i}.jpg")
                    media_group.append(InputMediaPhoto(media=photo_file, caption=c))

            for i in range(0, len(media_group), 10):
                await context.bot.send_media_group(
                    chat_id=update.effective_chat.id,
                    media=media_group[i:i + 10]
                )

        await sending_msg.delete()
        context.user_data.pop("pending_result", None)

    except Exception as e:
        logger.error(f"Error sending media: {e}")
        await sending_msg.edit_text(f"❌ خطا در ارسال: {str(e)}")


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    application.add_handler(CallbackQueryHandler(handle_format_choice))

    print("🤖 ربات با پشتیبانی TikTok + Instagram شروع به کار کرد...")
    application.run_polling()


if __name__ == "__main__":
    main()
