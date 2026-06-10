import aiohttp
from io import BytesIO
import logging
import time
from collections import defaultdict

from telegram import (
    Update, InputMediaVideo, InputMediaPhoto, InputMediaDocument,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
)

from config import BOT_TOKEN
from rapidapi_service import get_instagram_media

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate Limiting
RATE_LIMIT = 3
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
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 دانلود جدید", callback_data="new_download")],
        [InlineKeyboardButton("❓ راهنما", callback_data="show_help")]
    ])
    
    await update.message.reply_text(
        "<b>👋 سلام! ربات دانلود اینستاگرام</b>\n\n"
        "لینک هر پست، ریلز یا کاروسل عمومی رو بفرست.\n"
        "من با کیفیت بالا و ظاهر تمیز برات می‌فرستم 🎥📸\n\n"
        "<i>ساخته شده با ❤️</i>",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def help_command(update: Update, context):
    await update.message.reply_text(
        "📖 <b>راهنمای ربات</b>\n\n"
        "🔹 ریلز → فوراً ویدیو\n"
        "🔹 عکس تک → دو گزینه\n"
        "🔹 کاروسل → آلبوم یکپارچه (عکس معمولی) یا فایل\n\n"
        "⚡ ساخته شده با Python + python-telegram-bot",
        parse_mode='HTML'
    )


async def handle_link(update: Update, context):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    if "instagram.com" not in url:
        await update.message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return

    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه صبر کن.")
        return

    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")

    try:
        result = await get_instagram_media(url)
        if not result or not result.get("items"):
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم. پست باید عمومی باشه.")
            return

        context.user_data["pending_result"] = result
        await processing_msg.delete()

        items = result["items"]
        has_video = any(item["type"] == "video" for item in items)
        has_photo = any(item["type"] == "photo" for item in items)
        is_single = len(items) == 1

        # ریلز/ویدیو تک → فوراً ارسال
        if is_single and has_video:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="🎥 ویدیو پیدا شد، در حال ارسال...")
            item = items[0]
            await context.bot.send_video(
                chat_id=update.effective_chat.id,
                video=item["url"],
                supports_streaming=True,
                caption=result.get("caption", "")
            )
            context.user_data.pop("pending_result", None)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ ارسال شد! لینک بعدی رو بفرست 🚀")
            return

        # عکس تک
        if is_single and has_photo:
            text = "📸 <b>عکس پیدا شد!</b>\n\nچطور برات بفرستم؟"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 عکس معمولی", callback_data="send_photo")],
                [InlineKeyboardButton("📁 فایل (کیفیت اصلی)", callback_data="send_file")]
            ])
        else:
            # کاروسل
            text = f"📚 <b>کاروسل پیدا شد!</b> ({len(items)} رسانه)\n\nچطور ارسال کنم؟"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 عکس‌های معمولی (آلبوم)", callback_data="send_photo")],
                [InlineKeyboardButton("📁 همه به صورت فایل", callback_data="send_file")]
            ])

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.edit_text("❌ خطایی رخ داد. دوباره امتحان کن.")


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

    choice = query.data
    result = context.user_data.get("pending_result")
    if not result:
        await query.edit_message_text("❌ اطلاعات منقضی شد. لینک رو دوباره بفرست.")
        return

    caption = result.get("caption", "")
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
                    video=item["url"],
                    supports_streaming=True,
                    caption=caption
                )
            elif choice == "send_photo":
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=item["url"],
                    caption=caption
                )
            else:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    caption=caption
                )
        else:
            # ==================== کاروسل - آلبوم یکپارچه ====================
            if choice == "send_photo":
                # ارسال به صورت آلبوم (media group) — عکس‌های معمولی
                media_group = []
                for i, item in enumerate(items):
                    current_caption = caption if i == 0 else None
                    media_group.append(InputMediaPhoto(media=item["url"], caption=current_caption))

                # ارسال در دسته‌های حداکثر ۱۰ تایی
                for i in range(0, len(media_group), 10):
                    await context.bot.send_media_group(
                        chat_id=update.effective_chat.id,
                        media=media_group[i:i+10]
                    )
            else:
                # ارسال به صورت فایل (document)
                media_group = []
                for i, item in enumerate(items):
                    c = caption if i == 0 else None
                    if item["type"] == "video":
                        media_group.append(InputMediaVideo(media=item["url"], caption=c))
                    else:
                        media_group.append(InputMediaDocument(media=item["url"], caption=c))

                for i in range(0, len(media_group), 10):
                    await context.bot.send_media_group(
                        chat_id=update.effective_chat.id,
                        media=media_group[i:i+10]
                    )

        await sending_msg.delete()
        context.user_data.pop("pending_result", None)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ با موفقیت ارسال شد!\n\nلینک بعدی رو بفرست 🚀"
        )

    except Exception as e:
        logger.error(f"Error sending: {e}")
        await sending_msg.edit_text(f"❌ خطا در ارسال: {str(e)}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_format_choice))

    print("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
