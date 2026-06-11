# bot.py - نسخه نهایی اصلاح‌شده و پایدار با پشتیبانی کامل از هایلایت

import aiohttp
import asyncio
import logging
import time
from collections import defaultdict

from telegram import (
    Update, InputMediaVideo, InputMediaPhoto,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
)

from config import BOT_TOKEN
from rapidapi_service import (
    get_instagram_media,
    get_instagram_profile,
    get_instagram_highlights,
    get_instagram_highlight_stories
)
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
    
    await update.effective_message.reply_text(
        "<b>👋 سلام! ربات دانلود اینستاگرام</b>\n\n"
        "لینک پست، ریلز، استوری یا هایلایت بفرست.\n"
        "یا دستور /highlights @username بزن.\n\n"
        "<i>ساخته شده با ❤️</i>",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def profile_command(update: Update, context):
    if not context.args:
        await update.effective_message.reply_text("⚠️ نحوه استفاده:\n/profile cristiano")
        return
    username = context.args[0].strip("@")
    processing = await update.effective_message.reply_text(f"📊 در حال دریافت پروفایل @{username}...")

    try:
        profile = await get_instagram_profile(username)
        if not profile:
            await processing.edit_text("❌ نتونستم پروفایل رو پیدا کنم.")
            return

        caption = (
            f"👤 <b>{profile.get('full_name', username)}</b>\n"
            f"🔖 @{profile.get('username', username)}\n\n"
            f"📝 {profile.get('biography', 'بدون بیو')[:280]}\n\n"
            f"❤️ {profile.get('followers', 0):,} دنبال‌کننده\n"
            f"👥 {profile.get('following', 0):,} دنبال‌شونده\n"
            f"📸 {profile.get('posts', 0):,} پست\n"
        )

        if profile.get("profile_pic"):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=profile["profile_pic"],
                caption=caption,
                parse_mode='HTML'
            )
        else:
            await processing.edit_text(caption, parse_mode='HTML')
        await processing.delete()

    except Exception as e:
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


async def highlights_command(update: Update, context):
    if not context.args:
        await update.effective_message.reply_text("⚠️ نحوه استفاده:\n/highlights cristiano")
        return

    username = context.args[0].strip("@")
    processing = await update.effective_message.reply_text(f"📚 در حال دریافت هایلایت‌های @{username}...")

    try:
        highlights = await get_instagram_highlights(username)
        if not highlights:
            await processing.edit_text("❌ هیچ هایلایتی پیدا نشد.")
            return

        keyboard = []
        for h in highlights[:15]:
            # استخراج درست شمارنده مدیا
            highlight_count = h.get("count") or h.get("media_count") or 0
            keyboard.append([InlineKeyboardButton(
                f"📚 {h.get('title', 'هایلایت')} ({highlight_count})",
                callback_data=f"hl:{h.get('highlight_id')}:{h.get('title', 'هایلایت')}"
            )])

        await processing.edit_text(
            f"📚 هایلایت‌های @{username} ({len(highlights)} مورد)",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_highlight_callback(update: Update, context):
    query = update.callback_query
    await query.answer()

    try:
        # تفکیک دقیق داده‌های دکمه شیشه‌ای
        data_parts = query.data.split(":", 2)
        highlight_id = data_parts[1]
        title = data_parts[2] if len(data_parts) > 2 else "هایلایت"
    except Exception as e:
        logger.error(f"Callback split error: {e}")
        await query.edit_message_text("❌ خطای پردازش دکمه.")
        return

    processing = await query.edit_message_text(f"📥 در حال دانلود «{title}»...\n(ممکن است چند ثانیه زمان ببرد)")

    try:
        result = await get_instagram_highlight_stories(highlight_id, title)
        if not result or not result.get("items"):
            await processing.edit_text("❌ این هایلایت محتوایی برای نمایش ندارد یا اکانت خصوصی (Private) است.")
            return

        items = result["items"]
        caption = result["caption"]

        if len(items) == 1:
            item = items[0]
            if item["type"] == "video":
                await context.bot.send_video(query.message.chat_id, item["url"], caption=caption)
            else:
                await context.bot.send_photo(query.message.chat_id, item["url"], caption=caption)
        else:
            await send_media_group(query.message.chat_id, context, items, caption)

        await processing.delete()

    except Exception as e:
        logger.error(f"Highlight Callback error: {e}")
        await processing.edit_text(f"❌ خطا در ارسال محتوا: {str(e)[:100]}")

async def send_media_group(chat_id, context, items, caption):
    """ارسال آلبوم با مدیریت Flood"""
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
        try:
            await context.bot.send_media_group(
                chat_id=chat_id,
                media=media_group[i:i+10]
            )
            await asyncio.sleep(1.5)
        except Exception as e:
            print(f"⚠️ خطا در ارسال گروه: {e}")
            await asyncio.sleep(2)


async def show_settings_menu(update: Update, context, query=None):
    user_id = update.effective_user.id
    current_mode = get_user_default_mode(user_id)
    mode_text = "🎬 آلبوم ترکیبی" if current_mode == "album" else "📁 فایل"
    
    text = f"⚙️ <b>تنظیمات ارسال</b>\n\nحالت فعلی: {mode_text}"
    keyboard = get_user_settings_keyboard(user_id)
    
    if query:
        await query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


async def help_command(update: Update, context):
    await update.effective_message.reply_text(
        "📖 <b>راهنما</b>\n\n"
        "• لینک پست/ریلز/استوری بفرست\n"
        "• /profile username → پروفایل\n"
        "• /highlights username → لیست هایلایت‌ها\n"
        "• /settings → تنظیمات",
        parse_mode='HTML'
    )


async def settings_command(update: Update, context):
    await show_settings_menu(update, context)


async def handle_link(update: Update, context):
    url = update.message.text.strip()
    user_id = update.effective_user.id

    if "instagram.com" not in url:
        await update.effective_message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return

    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.effective_message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه صبر کن.")
        return

    processing_msg = await update.effective_message.reply_text("🔄 در حال پردازش...")

    try:
        result = await get_instagram_media(url)
        if not result or not result.get("items"):
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم.")
            return

        items = result.get("items", [])
        caption = result.get("caption", "دانلود از اینستاگرام")

        has_video = any(item["type"] == "video" for item in items)
        has_photo = any(item["type"] == "photo" for item in items)
        is_single = len(items) == 1
        default_mode = get_user_default_mode(user_id)

        if is_single and has_video:
            if default_mode == "file":
                await context.bot.send_document(chat_id=update.effective_chat.id, document=items[0]["url"], caption=caption)
            else:
                await context.bot.send_video(chat_id=update.effective_chat.id, video=items[0]["url"], supports_streaming=True, caption=caption)
        elif is_single and has_photo:
            if default_mode == "file":
                await context.bot.send_document(chat_id=update.effective_chat.id, document=items[0]["url"], caption=caption)
            else:
                await context.bot.send_photo(chat_id=update.effective_chat.id, photo=items[0]["url"], caption=caption)
        else:
            if default_mode == "album":
                await send_media_group(update.effective_chat.id, context, items, caption)
            else:
                for item in items:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id, 
                        document=item["url"], 
                        caption=caption if items.index(item) == 0 else None
                    )

        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ ارسال شد!")
        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_format_choice(update: Update, context):
    query = update.callback_query
    await query.answer()
    choice = query.data
    user_id = update.effective_user.id

    if choice == "show_settings":
        await show_settings_menu(update, context, query)
    elif choice == "set_mode_album":
        set_user_default_mode(user_id, "album")
        await show_settings_menu(update, context, query)
    elif choice == "set_mode_file":
        set_user_default_mode(user_id, "file")
        await show_settings_menu(update, context, query)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("highlights", highlights_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_highlight_callback, pattern="^hl:"))
    app.add_handler(CallbackQueryHandler(handle_format_choice))

    print("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
