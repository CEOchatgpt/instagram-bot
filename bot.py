# bot.py - نسخه نهایی با پشتیبانی از حالت فایل برای ویدیوهای تکی

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
from user_settings import get_user_default_mode, set_user_default_mode, get_user_settings_keyboard

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

RATE_LIMIT = 20
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
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="show_settings")],
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


async def show_settings_menu(update: Update, context, query=None):
    """نمایش منوی تنظیمات"""
    user_id = update.effective_user.id
    current_mode = get_user_default_mode(user_id)
    
    mode_text = "🎬 آلبوم ترکیبی (عکس+ویدیو)" if current_mode == "album" else "📁 فایل (همه چیز به صورت فایل)"
    
    text = (
        "⚙️ <b>تنظیمات ارسال</b>\n\n"
        f"حالت فعلی: {mode_text}\n\n"
        "حالت پیشفرض ارسال رو انتخاب کن:\n"
        "• آلبوم ترکیبی: عکس و ویدیو در یک آلبوم (پخش آنلاین ویدیو)\n"
        "• فایل: همه چیز به صورت فایل (کیفیت اصلی، حجم بالاتر)"
    )
    
    keyboard = get_user_settings_keyboard(user_id)
    
    if query:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


async def help_command(update: Update, context):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
    ])
    await update.message.reply_text(
        "📖 <b>راهنمای ربات</b>\n\n"
        "🔹 ریلز → بر اساس تنظیمات شما\n"
        "🔹 عکس تک → دو گزینه\n"
        "🔹 کاروسل → بر اساس تنظیمات شما\n\n"
        "💡 می‌تونی از طریق /settings حالت ارسال رو تغییر بدی.\n\n"
        "⚡ ساخته شده با Python + python-telegram-bot",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def settings_command(update: Update, context):
    """دستور /settings"""
    await show_settings_menu(update, context)


async def send_media_group(chat_id, context, items, caption):
    """ارسال آلبوم ترکیبی"""
    media_group = []
    for i, item in enumerate(items):
        current_caption = caption if i == 0 else None
        if item["type"] == "video":
            media_group.append(InputMediaVideo(
                media=item["url"], 
                caption=current_caption,
                supports_streaming=True
            ))
        else:  # photo
            media_group.append(InputMediaPhoto(
                media=item["url"], 
                caption=current_caption
            ))
    
    for i in range(0, len(media_group), 10):
        await context.bot.send_media_group(
            chat_id=chat_id,
            media=media_group[i:i+10]
        )


async def send_as_files(chat_id, context, items, caption):
    """ارسال همه مدیاها به صورت فایل جداگانه (هم عکس هم ویدیو)"""
    for i, item in enumerate(items):
        current_caption = caption if i == 0 else None
        # همه چیز به صورت Document فرستاده میشه
        await context.bot.send_document(
            chat_id=chat_id,
            document=item["url"],
            caption=current_caption
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
        default_mode = get_user_default_mode(user_id)

        # ========== ویدیو تک ==========
        if is_single and has_video:
            if default_mode == "file":
                await context.bot.send_message(chat_id=update.effective_chat.id, text="🎥 ویدیو پیدا شد، در حال ارسال به صورت فایل...")
                item = items[0]
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    caption=result.get("caption", "")
                )
            else:
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

        # ========== عکس تک ==========
        if is_single and has_photo:
            text = "📸 <b>عکس پیدا شد!</b>\n\nچطور برات بفرستم؟"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 عکس معمولی", callback_data="send_photo")],
                [InlineKeyboardButton("📁 فایل (کیفیت اصلی)", callback_data="send_file")]
            ])
            await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)
            return

        # ========== کاروسل ==========
        if default_mode == "album":
            await send_media_group(update.effective_chat.id, context, items, result.get("caption", ""))
        else:
            await send_as_files(update.effective_chat.id, context, items, result.get("caption", ""))
        
        context.user_data.pop("pending_result", None)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ ارسال شد!")

    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.edit_text("❌ خطایی رخ داد. دوباره امتحان کن.")


async def handle_format_choice(update: Update, context):
    query = update.callback_query
    await query.answer()

    choice = query.data
    user_id = update.effective_user.id
    
    # پردازش دکمه‌های تنظیمات
    if choice == "show_settings":
        await show_settings_menu(update, context, query)
        return
    
    if choice == "back_to_main":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 دانلود جدید", callback_data="new_download")],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="show_settings")],
            [InlineKeyboardButton("❓ راهنما", callback_data="show_help")]
        ])
        await query.edit_message_text(
            "<b>👋 صفحه اصلی</b>\n\nلینک اینستاگرام خود را بفرستید.",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    if choice == "show_help":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ])
        await query.edit_message_text(
            "📖 <b>راهنمای ربات</b>\n\n"
            "🔹 ریلز → بر اساس تنظیمات شما\n"
            "🔹 عکس تک → دو گزینه\n"
            "🔹 کاروسل → بر اساس تنظیمات شما\n\n"
            "💡 می‌تونی از طریق /settings حالت ارسال رو تغییر بدی.",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    if choice == "set_mode_album":
        set_user_default_mode(user_id, "album")
        await query.answer("✅ حالت آلبوم ترکیبی فعال شد! ویدیوها قابل پخش آنلاین هستند.")
        await show_settings_menu(update, context, query)
        return
    
    if choice == "set_mode_file":
        set_user_default_mode(user_id, "file")
        await query.answer("✅ حالت فایل فعال شد! همه چیز به صورت فایل ارسال میشود.")
        await show_settings_menu(update, context, query)
        return
    
    if choice == "new_download":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="show_settings")],
            [InlineKeyboardButton("❓ راهنما", callback_data="show_help")]
        ])
        await query.edit_message_text(
            "📎 <b>لینک اینستاگرام را بفرستید</b>\n\n"
            "هر پست، ریلز یا استوری عمومی رو برام بفرست تا برات دانلود کنم.",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    # پردازش ارسال مدیا برای عکس‌های تکی (که منو دارن)
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
            else:  # send_file
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    caption=caption
                )

        await sending_msg.delete()
        context.user_data.pop("pending_result", None)

    except Exception as e:
        logger.error(f"Error: {e}")
        await sending_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_format_choice))

    print("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
