import os
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

from config import BOT_TOKEN, RATE_LIMIT, WINDOW_SECS
from rapidapi_service import get_instagram_media
from services.tiktok_service import get_tiktok_media
from youtube_service import (
    is_youtube_url,
    get_youtube_info,
    download_youtube_video,
    cleanup_file,
    format_duration,
    MAX_DURATION_SECS,
)

# ── لاگ ──────────────────────────────────────────────────────
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Rate Limiting ─────────────────────────────────────────────
user_requests: dict[int, list[float]] = defaultdict(list)

def is_rate_limited(user_id: int) -> tuple[bool, int]:
    now = time.time()
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < WINDOW_SECS]
    if len(user_requests[user_id]) >= RATE_LIMIT:
        oldest = user_requests[user_id][0]
        return True, int(WINDOW_SECS - (now - oldest)) + 1
    user_requests[user_id].append(now)
    return False, 0


# ── دستورات پایه ─────────────────────────────────────────────
async def start(update: Update, context):
    await update.message.reply_text(
        "🎬 سلام! لینک پست مورد نظرت رو بفرست.\n\n"
        "✅ پلتفرم‌های پشتیبانی‌شده:\n"
        "  • Instagram (پست، ریلز، کاروسل)\n"
        "  • TikTok (ویدیو)\n"
        "  • YouTube (ویدیو، Shorts)\n\n"
        f"⚠️ محدودیت: هر {WINDOW_SECS} ثانیه، {RATE_LIMIT} درخواست"
    )


async def help_command(update: Update, context):
    await update.message.reply_text(
        "📖 راهنمای ربات\n\n"
        "🔹 نحوه استفاده:\n"
        "  لینک پست عمومی رو بفرست\n\n"
        "🔹 پلتفرم‌های پشتیبانی‌شده:\n"
        "  • Instagram (پست، ریلز، کاروسل)\n"
        "  • TikTok (ویدیو)\n"
        "  • YouTube (ویدیو، Shorts — حداکثر ۱۵ دقیقه)\n\n"
        "🔹 دستورات:\n"
        "  /start — شروع ربات\n"
        "  /help  — نمایش راهنما\n\n"
        "⚡ ساخته‌شده با Python & python-telegram-bot"
    )


# ── هندلر اصلی لینک‌ها ───────────────────────────────────────
async def handle_link(update: Update, context):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    url_lower = url.lower()

    # تشخیص پلتفرم
    if "instagram.com" in url_lower:
        platform = "instagram"
    elif "tiktok.com" in url_lower or "vm.tiktok.com" in url_lower:
        platform = "tiktok"
    elif is_youtube_url(url):
        platform = "youtube"
    else:
        await update.message.reply_text(
            "❌ فقط لینک اینستاگرام، تیک‌تاک و یوتیوب قبول میکنم!"
        )
        return

    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه دیگه امتحان کن.")
        return

    processing_msg = await update.message.reply_text(
        f"🔄 در حال بررسی لینک {platform.capitalize()}..."
    )

    try:
        if platform == "instagram":
            await _handle_instagram(update, context, url, processing_msg)
        elif platform == "tiktok":
            await _handle_tiktok(update, context, url, processing_msg)
        else:
            await _handle_youtube(update, context, url, processing_msg)
    except Exception as e:
        logger.error(f"Error in handle_link: {e}", exc_info=True)
        await processing_msg.edit_text("❌ خطایی ناشناخته رخ داد. دوباره امتحان کن.")


# ── اینستاگرام ───────────────────────────────────────────────
async def _handle_instagram(update, context, url, processing_msg):
    result = await get_instagram_media(url)
    if not result:
        await processing_msg.edit_text(
            "❌ نتونستم محتوا رو پیدا کنم.\n\n"
            "⚠️ ممکنه دلایل:\n"
            "  • لینک نامعتبر یا دسترسی‌پذیر نیست\n"
            "  • اکانت private است\n"
            "  • پست حذف شده"
        )
        return

    context.user_data["pending_result"] = result
    await processing_msg.delete()

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📷 عکس معمولی", callback_data="send_photo"),
        InlineKeyboardButton("📁 فایل", callback_data="send_file"),
    ]])
    await update.message.reply_text(
        "✨ نوع ارسال را انتخاب کن\n\n"
        "📷 عکس معمولی → نمایش مستقیم\n"
        "📁 فایل → کیفیت اصلی",
        reply_markup=keyboard
    )


# ── تیک‌تاک ──────────────────────────────────────────────────
async def _handle_tiktok(update, context, url, processing_msg):
    result = await get_tiktok_media(url)
    if not result or not result.get("url"):
        await processing_msg.edit_text(
            "❌ نتونستم ویدیو تیک‌تاک رو دانلود کنم.\n\n"
            "⚠️ ممکنه دلایل:\n"
            "  • لینک نامعتبر\n"
            "  • ویدیو محدود یا حذف‌شده"
        )
        return

    await processing_msg.delete()
    try:
        await update.message.reply_video(
            video=result["url"],
            caption=result.get("caption", "🎵 TikTok Video"),
            supports_streaming=True
        )
    except Exception as e:
        logger.error(f"Error sending TikTok video: {e}")
        await update.message.reply_text("❌ خطا در ارسال ویدیو تیک‌تاک")


# ── یوتیوب ───────────────────────────────────────────────────
async def _handle_youtube(update, context, url, processing_msg):
    info = await get_youtube_info(url)
    if not info:
        await processing_msg.edit_text(
            "❌ نتونستم اطلاعات ویدیو رو بگیرم.\n\n"
            "⚠️ ممکنه دلایل:\n"
            "  • ویدیو خصوصی یا حذف‌شده\n"
            "  • لینک نامعتبر\n"
            "  • محدودیت جغرافیایی"
        )
        return

    duration = info.get('duration', 0)
    if duration > MAX_DURATION_SECS:
        await processing_msg.edit_text(
            f"❌ ویدیو خیلی طولانیه!\n"
            f"مدت: {format_duration(duration)}\n"
            f"حداکثر مجاز: {MAX_DURATION_SECS // 60} دقیقه"
        )
        return

    context.user_data["yt_url"] = url
    context.user_data["yt_info"] = info
    await processing_msg.delete()

    # ساخت کیبورد کیفیت
    available = {f['quality'] for f in info.get('formats', [])}
    quality_labels = [("1080", "🔵 1080p"), ("720", "🟢 720p"),
                      ("480", "🟡 480p"),   ("360", "🟠 360p")]

    buttons, row = [], []
    for q, label in quality_labels:
        if q in available:
            row.append(InlineKeyboardButton(label, callback_data=f"yt_q_{q}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🎵 فقط صدا (MP3)", callback_data="yt_q_audio")])

    await update.message.reply_text(
        f"🎬 *{info['title']}*\n"
        f"👤 {info['uploader']}  •  ⏱ {format_duration(duration)}\n\n"
        "کیفیت دانلود رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="Markdown"
    )


async def handle_youtube_quality(update: Update, context):
    """callback برای انتخاب کیفیت یوتیوب"""
    query = update.callback_query
    await query.answer()

    quality = query.data.replace("yt_q_", "")
    url = context.user_data.get("yt_url")
    info = context.user_data.get("yt_info", {})

    if not url:
        await query.edit_message_text("❌ لینک منقضی شده. دوباره بفرست.")
        return

    quality_display = {'1080': '1080p', '720': '720p', '480': '480p',
                       '360': '360p', 'audio': 'MP3'}.get(quality, quality)
    await query.edit_message_text(f"⏬ در حال دانلود با کیفیت {quality_display}...")

    success, title_or_err, filepath = await download_youtube_video(url, quality)

    if not success:
        await query.edit_message_text(
            f"❌ دانلود ناموفق بود.\n\nجزئیات: {title_or_err[:200]}"
        )
        return

    # چک سایز (محدودیت ۵۰MB تلگرام)
    if os.path.getsize(filepath) > 50 * 1024 * 1024:
        cleanup_file(filepath)
        await query.edit_message_text(
            "❌ فایل بزرگتر از ۵۰MB هست.\n"
            "یه کیفیت پایین‌تر امتحان کن."
        )
        return

    caption = f"🎬 {title_or_err}"
    if info.get('uploader'):
        caption += f"\n👤 {info['uploader']}"

    sending_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id, text="📤 در حال ارسال..."
    )

    try:
        await query.delete_message()
        with open(filepath, 'rb') as f:
            if quality == 'audio':
                await context.bot.send_audio(
                    chat_id=update.effective_chat.id,
                    audio=f, caption=caption, title=title_or_err,
                )
            else:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=f, caption=caption, supports_streaming=True,
                )
        await sending_msg.delete()
        context.user_data.pop("yt_url", None)
        context.user_data.pop("yt_info", None)

    except Exception as e:
        logger.error(f"Error sending YouTube media: {e}")
        await sending_msg.edit_text(f"❌ خطا در ارسال: {str(e)[:200]}")
    finally:
        cleanup_file(filepath)


# ── اینستاگرام: انتخاب فرمت ──────────────────────────────────
async def _download_media(url: str, filename: str):
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
        chat_id=update.effective_chat.id, text="📤 در حال ارسال..."
    )

    try:
        if len(items) == 1:
            item = items[0]
            if item["type"] == "video":
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=item["url"], supports_streaming=not as_file, caption=caption
                )
            elif as_file:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"], caption=caption
                )
            else:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=item["url"], caption=caption
                )
        else:
            media_group = []
            for i, item in enumerate(items):
                c = caption if i == 0 else None
                if item["type"] == "video":
                    media_group.append(InputMediaVideo(media=item["url"], caption=c))
                elif as_file:
                    media_group.append(InputMediaDocument(media=item["url"], caption=c))
                else:
                    photo_file = await _download_media(item["url"], f"photo_{i}.jpg")
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


# ── main ──────────────────────────────────────────────────────
def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    # یوتیوب: pattern دقیق — باید قبل از handler عمومی اینستاگرام باشه
    application.add_handler(CallbackQueryHandler(handle_youtube_quality, pattern="^yt_q_"))
    application.add_handler(CallbackQueryHandler(handle_format_choice))

    print("🤖 ربات با پشتیبانی Instagram + TikTok + YouTube شروع به کار کرد...")
    application.run_polling()


if __name__ == "__main__":
    main()
