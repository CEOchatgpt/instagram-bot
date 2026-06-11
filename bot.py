# bot.py - نسخه اصلاح شده برای رفع مشکل هایلایت

import aiohttp
import asyncio
import logging
import time
from collections import defaultdict
import json

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
    """دریافت و نمایش هایلایت‌های کاربر"""
    if not context.args:
        await update.effective_message.reply_text("⚠️ نحوه استفاده:\n/highlights leomessi")
        return

    username = context.args[0].strip("@")
    processing = await update.effective_message.reply_text(f"📚 در حال دریافت هایلایت‌های @{username}...")

    try:
        highlights_data = await get_instagram_highlights(username)
        
        # مدیریت انواع ساختارهای خروجی
        highlights_list = []
        if isinstance(highlights_data, list):
            highlights_list = highlights_data
        elif isinstance(highlights_data, dict):
            highlights_list = highlights_data.get("result") or highlights_data.get("items") or []
            if not highlights_list and any(k in highlights_data for k in ["id", "highlight_id"]):
                highlights_list = [highlights_data]

        if not highlights_list:
            await processing.edit_text("❌ هیچ هایلایتی پیدا نشد یا پیج خصوصی است.")
            return

        # ذخیره اطلاعات هایلایت‌ها در context.user_data
        context.user_data['current_highlights'] = []
        
        keyboard = []
        for i, h in enumerate(highlights_list[:15]):
            if not isinstance(h, dict):
                continue
                
            # استخراج شناسه هایلایت و تمیز کردن آن
            hl_id = h.get("id") or h.get("highlight_id") or h.get("pk")
            if not hl_id:
                continue
            
            # اگر شناسه شامل "highlight:" بود، فقط بخش عددی را نگه دار
            raw_id = str(hl_id)
            if ":" in raw_id:
                clean_id = raw_id.split(":")[-1]
                logger.info(f"Cleaned highlight ID: {raw_id} -> {clean_id}")
            else:
                clean_id = raw_id

            title = h.get("title", "هایلایت")
            # حذف کاراکترهای خاص از عنوان
            clean_title = title.replace(":", "").replace("\n", "").strip()
            count = h.get("count") or h.get("media_count") or 0
            
            # ایجاد یک شناسه یکتا برای دکمه
            button_id = f"hl_{i}"
            
            # ذخیره اطلاعات کامل (با شناسه تمیز شده)
            context.user_data['current_highlights'].append({
                "id": clean_id,  # ذخیره شناسه تمیز شده
                "original_id": raw_id,  # ذخیره شناسه اصلی برای دیباگ
                "title": clean_title,
                "username": username
            })
            
            button_text = f"📚 {clean_title}"
            if count and int(count) > 0:
                button_text = f"📚 {clean_title} ({count})"
            
            keyboard.append([InlineKeyboardButton(button_text, callback_data=button_id)])

        if not keyboard:
            await processing.edit_text("❌ خطا در پردازش هایلایت‌ها.")
            return

        await processing.edit_text(
            f"📚 هایلایت‌های @{username}:\n\nاز دکمه‌های زیر برای مشاهده هر هایلایت استفاده کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Error in highlights_command: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")

async def handle_highlight_callback(update: Update, context):
    """پردازش کلیک روی دکمه هایلایت"""
    query = update.callback_query
    await query.answer()
    
    callback_id = query.data
    
    # اگر callback_id با hl_ شروع نمی‌شود، نادیده بگیر
    if not callback_id.startswith("hl_"):
        return
    
    # دریافت اطلاعات هایلایت از حافظه
    highlights_list = context.user_data.get('current_highlights', [])
    
    # استخراج ایندکس از callback_id (مثلاً hl_0 -> 0)
    try:
        index = int(callback_id.split("_")[1])
        highlight_info = highlights_list[index] if index < len(highlights_list) else None
    except (IndexError, ValueError) as e:
        logger.error(f"Error parsing callback: {e}")
        highlight_info = None
    
    if not highlight_info:
        await query.edit_message_text("❌ اطلاعات هایلایت یافت نشد. لطفا دوباره از /highlights استفاده کنید.")
        return
    
    highlight_id = highlight_info.get("id")
    title = highlight_info.get("title", "هایلایت")
    username = highlight_info.get("username")
    
    logger.info(f"Processing highlight: {title}, ID: {highlight_id}, Username: {username}")
    
    # ارسال پیام در حال پردازش
    processing_msg = await query.edit_message_text(f"📥 در حال دریافت محتوای هایلایت «{title}»...")
    
    try:
        # دریافت استوری‌های هایلایت
        result = await get_instagram_highlight_stories(highlight_id, username, title)
        
        if not result or not result.get("items"):
            logger.warning(f"No items found for highlight {title}")
            await processing_msg.edit_text(
                f"❌ این هایلایت محتوا ندارد یا قابل دسترسی نیست.\n\n"
                f"📌 دلایل احتمالی:\n"
                f"• پیج خصوصی شده است\n"
                f"• هایلایت حذف شده است\n"
                f"• محدودیت دسترسی API\n\n"
                f"💡 راه حل: مستقیماً لینک اینستاگرام را در بات ارسال کنید."
            )
            return

        items = result["items"]
        caption = result["caption"]
        
        logger.info(f"✅ دریافت {len(items)} آیتم برای هایلایت {title}")

        if len(items) == 1:
            item = items[0]
            try:
                if item["type"] == "video":
                    await context.bot.send_video(
                        chat_id=query.message.chat_id, 
                        video=item["url"], 
                        caption=caption,
                        supports_streaming=True
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=query.message.chat_id, 
                        photo=item["url"], 
                        caption=caption
                    )
            except Exception as send_error:
                logger.error(f"Send error: {send_error}")
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=item["url"],
                    caption=caption
                )
        else:
            await send_media_group(query.message.chat_id, context, items, caption)

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Highlight download error: {e}")
        await processing_msg.edit_text(f"❌ خطا در دانلود: {str(e)[:150]}")
        
async def send_media_group(chat_id, context, items, caption):
    """ارسال آلبوم با مدیریت خطا"""
    media_group = []
    for i, item in enumerate(items):
        current_caption = caption if i == 0 else None
        try:
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
        except Exception as e:
            logger.error(f"Error creating media item: {e}")
            continue

    for i in range(0, len(media_group), 10):
        try:
            await context.bot.send_media_group(
                chat_id=chat_id,
                media=media_group[i:i+10]
            )
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.error(f"⚠️ خطا در ارسال گروه: {e}")
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
        logger.error(f"Error in handle_link: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_callback(update: Update, context):
    """مدیریت تمام کال‌بک‌ها"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
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
    
    # اگر با hl_ شروع می‌شود، به تابع هایلایت بفرست
    elif data.startswith("hl_"):
        await handle_highlight_callback(update, context)


def main():
    # افزایش timeout برای جلوگیری از خطای TimedOut
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    
    # هندلرهای فرمان
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("highlights", highlights_command))
    
    # هندلر لینک
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    
    # هندلر کال‌بک (برای همه دکمه‌ها)
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    print("🤖 ربات در حال اجراست...")
    app.run_polling()


if __name__ == "__main__":
    main()
