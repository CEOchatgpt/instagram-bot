# bot.py - نسخه نهایی با پشتیبانی از تنظیمات برای عکس تکی

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
    user_id = update.effective_user.id
    current_mode = get_user_default_mode(user_id)
    
    mode_text = "🎬 آلبوم ترکیبی" if current_mode == "album" else "📁 فایل"
    
    text = (
        "⚙️ <b>تنظیمات ارسال</b>\n\n"
        f"حالت فعلی: {mode_text}\n\n"
        "• آلبوم ترکیبی: عکس و ویدیو در یک آلبوم (پخش آنلاین)\n"
        "• فایل: همه چیز به صورت فایل (کیفیت اصلی)"
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
        "🔹 عکس تک → بر اساس تنظیمات شما\n"
        "🔹 کاروسل → بر اساس تنظیمات شما\n\n"
        "💡 از /settings برای تغییر حالت استفاده کن.",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def settings_command(update: Update, context):
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
        else:
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
    """ارسال همه به صورت فایل"""
    for i, item in enumerate(items):
        current_caption = caption if i == 0 else None
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
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم.")
            return

        context.user_data["pending_result"] = result
        await processing_msg.delete()

        items = result["items"]
        has_video = any(item["type"] == "video" for item in items)
        has_photo = any(item["type"] == "photo" for item in items)
        is_single = len(items) == 1
        default_mode = get_user_default_mode(user_id)
        
        print(f"🔍 کاربر {user_id} - حالت: {default_mode} - تعداد: {len(items)} - ویدیو: {has_video} - عکس: {has_photo}")

        # ========== ویدیو تک ==========
        if is_single and has_video:
            print(f"🎥 ویدیو تکی شناسایی شد - حالت: {default_mode}")
            if default_mode == "file":
                print("📁 ارسال ویدیو به صورت فایل (Document)")
                try:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text="🎥 ارسال ویدیو به صورت فایل...")
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=items[0]["url"],
                        caption=result.get("caption", "")
                    )
                    print("✅ ویدیو بصورت فایل ارسال شد")
                except Exception as e:
                    print(f"⚠️ خطا در ارسال فایل: {e}")
                    logger.error(f"Error sending video as document: {e}")
                    raise
            else:
                print("🎬 ارسال ویدیو به صورت قابل پخش (Video)")
                await context.bot.send_message(chat_id=update.effective_chat.id, text="🎥 در حال ارسال ویدیو...")
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=items[0]["url"],
                    supports_streaming=True,
                    caption=result.get("caption", "")
                )
            
            context.user_data.pop("pending_result", None)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ ارسال شد!")
            return

        # ========== عکس تک ==========
        if is_single and has_photo:
            print(f"📸 عکس تکی شناسایی شد - حالت: {default_mode}")
            if default_mode == "file":
                print("📁 ارسال عکس به صورت فایل (Document)")
                await context.bot.send_message(chat_id=update.effective_chat.id, text="📸 ارسال عکس به صورت فایل...")
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=items[0]["url"],
                    caption=result.get("caption", "")
                )
            else:
                print("🖼 ارسال عکس به صورت معمولی (Photo) - بدون منوی انتخاب")
                await context.bot.send_message(chat_id=update.effective_chat.id, text="📸 ارسال عکس...")
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=items[0]["url"],
                    caption=result.get("caption", "")
                )
            
            context.user_data.pop("pending_result", None)
            await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ ارسال شد!")
            return

        # ========== کاروسل ==========
        if default_mode == "album":
            print("🎬 ارسال کاروسل به صورت آلبوم ترکیبی")
            await send_media_group(update.effective_chat.id, context, items, result.get("caption", ""))
        else:
            print("📁 ارسال کاروسل به صورت فایل")
            await send_as_files(update.effective_chat.id, context, items, result.get("caption", ""))
        
        context.user_data.pop("pending_result", None)
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ ارسال شد!")

    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_format_choice(update: Update, context):
    query = update.callback_query
    await query.answer()

    choice = query.data
    user_id = update.effective_user.id
    
    # دکمه‌های منوی اصلی
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
            "📖 <b>راهنما</b>\n\nاز /settings برای تغییر حالت استفاده کن.",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    if choice == "new_download":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="show_settings")],
            [InlineKeyboardButton("❓ راهنما", callback_data="show_help")]
        ])
        await query.edit_message_text(
            "📎 <b>لینک اینستاگرام را بفرستید</b>",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    # دکمه‌های تنظیمات
    if choice == "set_mode_album":
        set_user_default_mode(user_id, "album")
        await query.answer("✅ حالت آلبوم فعال شد!")
        await show_settings_menu(update, context, query)
        return
    
    if choice == "set_mode_file":
        set_user_default_mode(user_id, "file")
        await query.answer("✅ حالت فایل فعال شد!")
        await show_settings_menu(update, context, query)
        return


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
