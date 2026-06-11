# bot.py - نسخه کامل بازنویسی شده

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
        await update.effective_message.reply_text("⚠️ نحوه استفاده:\n/highlights leomessi")
        return

    username = context.args[0].strip("@")
    processing = await update.effective_message.reply_text(f"📚 در حال دریافت هایلایت‌های @{username}...")

    try:
        highlights_list = await get_instagram_highlights(username)

        if not highlights_list:
            await processing.edit_text("❌ هیچ هایلایتی پیدا نشد یا پیج خصوصی است.")
            return

        context.user_data['current_highlights'] = highlights_list
        
        keyboard = []
        for i, h in enumerate(highlights_list[:15]):
            title = h.get("title", "هایلایت")
            count = h.get("count", 0)
            button_text = f"📚 {title}" + (f" ({count})" if count else "")
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"hl_{i}")])

        if not keyboard:
            await processing.edit_text("❌ خطا در پردازش هایلایت‌ها.")
            return

        await processing.edit_text(
            f"📚 هایلایت‌های @{username}:\n\nاز دکمه‌های زیر برای مشاهده استفاده کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Error in highlights_command: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_highlight_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    callback_id = query.data
    if not callback_id.startswith("hl_"):
        return
    
    highlights_list = context.user_data.get('current_highlights', [])
    
    try:
        index = int(callback_id.split("_")[1])
        highlight_info = highlights_list[index] if index < len(highlights_list) else None
    except (IndexError, ValueError):
        highlight_info = None
    
    if not highlight_info:
        await query.edit_message_text("❌ اطلاعات هایلایت یافت نشد. لطفا دوباره از /highlights استفاده کنید.")
        return
    
    highlight_id = highlight_info.get("id")
    title = highlight_info.get("title", "هایلایت")
    
    processing = await query.edit_message_text(f"📥 در حال دانلود هایلایت «{title}»...")
    
    try:
        result = await get_instagram_highlight_stories(highlight_id, None, title)
        
        if not result or not result.get("items"):
            await processing.edit_text(
                f"❌ این هایلایت محتوا ندارد یا قابل دسترسی نیست.\n\n"
                f"💡 می‌توانید لینک زیر را مستقیماً ارسال کنید:\n"
                f"https://www.instagram.com/stories/highlights/{highlight_id}/"
            )
            return

        items = result["items"]
        caption = f"📚 هایلایت: {title}"

        if len(items) == 1:
            item = items[0]
            try:
                if item["type"] == "video":
                    await context.bot.send_video(query.message.chat_id, item["url"], caption=caption, supports_streaming=True)
                else:
                    await context.bot.send_photo(query.message.chat_id, item["url"], caption=caption)
            except:
                await context.bot.send_document(query.message.chat_id, item["url"], caption=caption)
        else:
            await send_media_group(query.message.chat_id, context, items, caption)

        await processing.delete()

    except Exception as e:
        logger.error(f"Highlight download error: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


async def send_media_group(chat_id, context, items, caption):
    media_group = []
    for i, item in enumerate(items):
        current_caption = caption if i == 0 else None
        try:
            if item["type"] == "video":
                media_group.append(InputMediaVideo(media=item["url"], caption=current_caption, supports_streaming=True))
            else:
                media_group.append(InputMediaPhoto(media=item["url"], caption=current_caption))
        except:
            continue

    for i in range(0, len(media_group), 10):
        try:
            await context.bot.send_media_group(chat_id=chat_id, media=media_group[i:i+10])
            await asyncio.sleep(1.5)
        except:
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
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


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

        items = result.get("items", [])
        caption = result.get("caption", "دانلود از اینستاگرام")
        default_mode = get_user_default_mode(user_id)
        is_single = len(items) == 1

        if is_single:
            item = items[0]
            if default_mode == "file":
                await context.bot.send_document(update.effective_chat.id, item["url"], caption=caption)
            else:
                if item["type"] == "video":
                    await context.bot.send_video(update.effective_chat.id, item["url"], supports_streaming=True, caption=caption)
                else:
                    await context.bot.send_photo(update.effective_chat.id, item["url"], caption=caption)
        else:
            if default_mode == "album":
                await send_media_group(update.effective_chat.id, context, items, caption)
            else:
                for i, item in enumerate(items):
                    await context.bot.send_document(update.effective_chat.id, item["url"], caption=caption if i == 0 else None)

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error in handle_link: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id

    # هندل کردن دکمه‌های ریل
    if data.startswith("reel_"):
        await handle_reel_callbacks(update, context)
        return
    
    if data == "new_download":
        await query.edit_message_text("لطفاً لینک اینستاگرام خود را ارسال کنید:")
    
    elif data == "show_settings":
        await show_settings_menu(update, context, query)
    
    elif data == "show_help":
        await help_command(update, context)
    
    elif data == "set_mode_album":
        set_user_default_mode(user_id, "album")
        await show_settings_menu(update, context, query)
    
    elif data == "set_mode_file":
        set_user_default_mode(user_id, "file")
        await show_settings_menu(update, context, query)
    
    elif data == "back_to_main":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 دانلود جدید", callback_data="new_download")],
            [InlineKeyboardButton("⚙️ تنظیمات", callback_data="show_settings")],
            [InlineKeyboardButton("❓ راهنما", callback_data="show_help")]
        ])
        await query.edit_message_text(
            "<b>👋 سلام! ربات دانلود اینستاگرام</b>\n\n"
            "لینک پست، ریلز، استوری یا هایلایت بفرست.\n"
            "یا دستور /highlights @username بزن.\n\n"
            "<i>ساخته شده با ❤️</i>",
            parse_mode='HTML',
            reply_markup=keyboard
        )
    
    elif data.startswith("hl_"):
        await handle_highlight_callback(update, context)

# به bot.py اضافه کنید

async def reels_command(update: Update, context):
    """
    دستور /reels username - نمایش لیست ریل‌های یک کاربر
    """
    if not context.args:
        await update.effective_message.reply_text(
            "⚠️ نحوه استفاده:\n"
            "/reels username\n\n"
            "مثال: /reels cristiano"
        )
        return
    
    username = context.args[0].strip("@")
    user_id = update.effective_user.id
    
    # بررسی rate limit
    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه صبر کن.")
        return
    
    processing_msg = await update.effective_message.reply_text(
        f"🎬 در حال دریافت ریل‌های @{username}...\n"
        f"این کار چند ثانیه طول میکشه."
    )
    
    try:
        result = await get_user_reels(username)
        
        if not result or not result.get("items"):
            await processing_msg.edit_text(
                f"❌ هیچ ریلی برای @{username} پیدا نشد.\n\n"
                "احتمالا پیج خصوصی است یا ریل‌ای وجود ندارد."
            )
            return
        
        items = result["items"]
        next_max_id = result.get("next_max_id", "")
        
        # ذخیره در user_data برای صفحه‌بندی
        context.user_data['reels_data'] = {
            "username": username,
            "items": items,
            "next_max_id": next_max_id,
            "current_page": 0,
            "total": len(items)
        }
        
        # نمایش اولین ریل
        await show_reel_item(update, context, processing_msg, 0)
        
    except Exception as e:
        logger.error(f"Error in reels_command: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


async def show_reel_item(update: Update, context, message, index: int):
    """
    نمایش یک ریل خاص با دکمه‌های قبلی/بعدی
    """
    reels_data = context.user_data.get('reels_data')
    if not reels_data or index >= len(reels_data["items"]):
        return
    
    item = reels_data["items"][index]
    username = reels_data["username"]
    total = reels_data["total"]
    
    # ساخت کپشن
    caption = (
        f"🎬 <b>ریل از @{username}</b>\n\n"
        f"📝 {item['caption']}\n\n"
        f"❤️ {item['like_count']:,} لایک | 💬 {item['comment_count']:,} کامنت"
    )
    
    # دکمه‌های ناوبری
    keyboard = []
    nav_buttons = []
    
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"reel_prev_{index}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{index+1}/{total}", callback_data="reel_info"))
    
    if index < total - 1:
        nav_buttons.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"reel_next_{index}"))
    
    keyboard.append(nav_buttons)
    
    # دکمه دانلود و بستن
    keyboard.append([
        InlineKeyboardButton("📥 دانلود این ریل", callback_data=f"reel_download_{index}"),
        InlineKeyboardButton("❌ بستن", callback_data="reel_close")
    ])
    
    markup = InlineKeyboardMarkup(keyboard)
    
    # ارسال ویدیو
    try:
        await message.edit_text("📤 در حال ارسال ریل...")
        
        await context.bot.send_video(
            chat_id=update.effective_chat.id,
            video=item["url"],
            caption=caption,
            supports_streaming=True,
            parse_mode='HTML',
            reply_markup=markup,
            timeout=60
        )
        
        await message.delete()  # پاک کردن پیام "در حال پردازش"
        
    except Exception as e:
        logger.error(f"Error sending reel: {e}")
        # اگه ویدیو مستقیم فرستاده نشد، به صورت داکیومنت بفرست
        try:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=item["url"],
                caption=caption,
                parse_mode='HTML',
                reply_markup=markup
            )
            await message.delete()
        except Exception as e2:
            await message.edit_text(f"❌ خطا در ارسال ریل: {str(e2)[:100]}")


async def handle_reel_callbacks(update: Update, context):
    """
    هندل کردن دکمه‌های ریل (قبلی، بعدی، دانلود، بستن)
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    reels_data = context.user_data.get('reels_data')
    
    if not reels_data:
        await query.edit_message_text("❌ اطلاعات ریل منقضی شده. دوباره /reels رو امتحان کن.")
        return
    
    if data == "reel_close":
        # حذف پیام و پاک کردن دیتا
        await query.message.delete()
        context.user_data.pop('reels_data', None)
        return
    
    if data == "reel_info":
        # فقط اطلاعات نمایش داده بشه
        await query.answer(f"ریل {reels_data['current_page']+1} از {reels_data['total']}")
        return
    
    # پردازش قبلی/بعدی
    if data.startswith("reel_prev_"):
        current_index = int(data.split("_")[2])
        new_index = current_index - 1
        reels_data["current_page"] = new_index
        context.user_data['reels_data'] = reels_data
        
        # حذف پیام قبلی و نمایش جدید
        await query.message.delete()
        # ایجاد پیام جدید برای نمایش
        fake_update = update
        fake_update.effective_message = query.message
        fake_msg = await fake_update.effective_chat.send_message("🔄 در حال بارگذاری...")
        await show_reel_item(update, context, fake_msg, new_index)
        return
    
    if data.startswith("reel_next_"):
        current_index = int(data.split("_")[2])
        new_index = current_index + 1
        reels_data["current_page"] = new_index
        context.user_data['reels_data'] = reels_data
        
        await query.message.delete()
        fake_update = update
        fake_update.effective_message = query.message
        fake_msg = await fake_update.effective_chat.send_message("🔄 در حال بارگذاری...")
        await show_reel_item(update, context, fake_msg, new_index)
        return
    
    # دانلود ریل
    if data.startswith("reel_download_"):
        index = int(data.split("_")[2])
        item = reels_data["items"][index]
        
        await query.message.reply_text("📥 در حال ارسال فایل...")
        try:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=item["url"],
                filename=f"reel_{reels_data['username']}_{item['id']}.mp4",
                caption=f"🎬 ریل از @{reels_data['username']}\n{item['caption'][:100]}"
            )
        except Exception as e:
            await query.message.reply_text(f"❌ خطا در دانلود: {str(e)[:100]}")



def main():
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("highlights", highlights_command))
    app.add_handler(CommandHandler("reels", reels_command))  # <-- جدید

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
