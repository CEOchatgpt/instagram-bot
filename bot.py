import logging
import time
import asyncio
from collections import defaultdict

from telegram import Update, InputMediaVideo, InputMediaPhoto, InputMediaDocument, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# ایمپورت درست از config
from config import (
    BOT_TOKEN, 
    RATE_LIMIT, 
    WINDOW_SECS,
    RAPIDAPI_KEY_INSTAGRAM,
    RAPIDAPI_KEY_TIKTOK,
    RAPIDAPI_KEY_YOUTUBE
)

from rapidapi_service import get_instagram_media
from services.tiktok_service import get_tiktok_media
from services.youtube_service import get_youtube_media

# ── Logging ─────────────────────────────────────────────────────
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Rate Limiting ───────────────────────────────────────────────
user_requests: dict[int, list[float]] = defaultdict(list)

def is_rate_limited(user_id: int) -> tuple[bool, int]:
    now = time.time()
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < WINDOW_SECS]
    if len(user_requests[user_id]) >= RATE_LIMIT:
        oldest = user_requests[user_id][0]
        return True, int(WINDOW_SECS - (now - oldest)) + 1
    user_requests[user_id].append(now)
    return False, 0


# ── Start & Help ────────────────────────────────────────────────
async def start(update: Update, context):
    await update.message.reply_text(
        "🎬 سلام! لینک پست مورد نظرت رو بفرست.\n\n"
        "✅ پشتیبانی از:\n"
        "• Instagram\n"
        "• TikTok\n"
        "• YouTube (ویدیو و Shorts)\n\n"
        f"⚠️ محدودیت: {RATE_LIMIT} درخواست هر {WINDOW_SECS} ثانیه"
    )


async def help_command(update: Update, context):
    await update.message.reply_text("📖 لینک اینستاگرام، تیک‌تاک یا یوتیوب بفرست.")


# ── Handle Link ─────────────────────────────────────────────────
async def handle_link(update: Update, context):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    url_lower = url.lower()

    if "instagram.com" in url_lower:
        platform = "instagram"
    elif "tiktok.com" in url_lower or "vm.tiktok.com" in url_lower:
        platform = "tiktok"
    elif "youtube.com" in url_lower or "youtu.be" in url_lower:
        platform = "youtube"
    else:
        await update.message.reply_text("❌ فقط لینک اینستاگرام، تیک‌تاک و یوتیوب قبول میکنم!")
        return

    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! لطفا {wait} ثانیه صبر کن.")
        return

    processing_msg = await update.message.reply_text(f"🔄 در حال پردازش {platform.capitalize()}...")

    try:
        if platform == "instagram":
            await _handle_instagram(update, context, url, processing_msg)
        elif platform == "tiktok":
            await _handle_tiktok(update, context, url, processing_msg)
        elif platform == "youtube":
            await _handle_youtube(update, context, url, processing_msg)
    except Exception as e:
        logger.error(f"Error handling {platform}: {e}", exc_info=True)
        await processing_msg.edit_text("❌ خطایی رخ داد. دوباره امتحان کن.")


# ── Instagram Handler ───────────────────────────────────────────
async def _handle_instagram(update, context, url, processing_msg):
    result = await get_instagram_media(url)
    if not result or not result.get("items"):
        await processing_msg.edit_text("❌ نتونستم محتوای اینستاگرام رو پیدا کنم.")
        return

    context.user_data["pending_result"] = result
    await processing_msg.delete()

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📷 عکس معمولی", callback_data="send_photo"),
        InlineKeyboardButton("📁 فایل", callback_data="send_file"),
    ]])
    await update.message.reply_text("✨ نوع ارسال را انتخاب کن:", reply_markup=keyboard)


# ── TikTok Handler ──────────────────────────────────────────────
async def _handle_tiktok(update, context, url, processing_msg):
    result = await get_tiktok_media(url)
    if not result or not result.get("url"):
        await processing_msg.edit_text("❌ نتونستم ویدیو تیک‌تاک رو دانلود کنم.")
        return

    await processing_msg.delete()
    try:
        await update.message.reply_video(
            video=result["url"],
            caption=result.get("caption", "🎵 TikTok Video"),
            supports_streaming=True
        )
    except Exception as e:
        logger.error(f"TikTok send error: {e}")
        await update.message.reply_text("❌ خطا در ارسال تیک‌تاک")


# ── YouTube Handler ─────────────────────────────────────────────
async def _handle_youtube(update, context, url, processing_msg):
    result = await asyncio.to_thread(get_youtube_media, url)
    
    if not result or not result.get("url"):
        await processing_msg.edit_text("❌ نتونستم ویدیو یوتیوب رو دانلود کنم.")
        return

    await processing_msg.delete()
    try:
        await update.message.reply_video(
            video=result["url"],
            caption=result.get("caption", "🎥 YouTube Video"),
            supports_streaming=True
        )
    except Exception as e:
        logger.error(f"YouTube send error: {e}")
        await update.message.reply_text("❌ خطا در ارسال ویدیو یوتیوب")


# ── Instagram Callback ──────────────────────────────────────────
async def handle_format_choice(update: Update, context):
    query = update.callback_query
    await query.answer()

    as_file = (query.data == "send_file")
    result = context.user_data.get("pending_result")

    if not result:
        await query.edit_message_text("❌ اطلاعات منقضی شده. لینک رو دوباره بفرست.")
        return

    caption = result.get("caption", "")
    items = result.get("items", [])
    await query.delete_message()

    sending_msg = await context.bot.send_message(chat_id=update.effective_chat.id, text="📤 در حال ارسال...")

    try:
        if len(items) == 1:
            item = items[0]
            if item["type"] == "video":
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=item["url"],
                    caption=caption,
                    supports_streaming=not as_file
                )
            elif as_file:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=item["url"], caption=caption)
            else:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=item["url"], caption=caption)
        else:
            # کاروسل
            media_group = []
            for i, item in enumerate(items):
                c = caption if i == 0 else None
                if item["type"] == "video":
                    media_group.append(InputMediaVideo(media=item["url"], caption=c))
                else:
                    media_group.append(InputMediaPhoto(media=item["url"], caption=c))
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
        
        await sending_msg.delete()
    except Exception as e:
        logger.error(f"Error sending Instagram: {e}")
        await sending_msg.edit_text("❌ خطا در ارسال")


# ── Main ────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_format_choice, pattern="^(send_photo|send_file)$"))

    logger.info("ربات با موفقیت شروع شد!")
    app.run_polling()


if __name__ == "__main__":
    main()
