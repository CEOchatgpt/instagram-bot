# bot.py - نسخه نهایی تمیز و بهینه

import asyncio
import logging
import time
import re
from collections import defaultdict
from uuid import uuid4

from telegram import (
    Update, InputMediaVideo, InputMediaPhoto,
    InlineKeyboardButton, InlineKeyboardMarkup,
    InlineQueryResultArticle, InputTextMessageContent,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
    InlineQueryHandler
)

from config import BOT_TOKEN, ADMIN_ID
from rapidapi_service import (
    get_instagram_media, get_instagram_profile, get_instagram_highlights,
    get_instagram_highlight_stories, get_user_reels_v2, check_and_get_stories
)
from database import get_user_mode, set_user_mode, get_user_settings_keyboard, init_db
from channel_cache import (
    save_profile_to_channel, get_profile_from_channel, save_media_to_channel,
    get_media_from_channel, save_reels_list_to_channel, get_reels_list_from_channel,
    save_highlights_list_to_channel, get_highlights_list_from_channel,
    save_user_setting_to_channel, get_user_setting_from_channel, get_media_by_key,
    clear_memory_cache
)
from extract_instagram_id import extract_instagram_id
from index_manager import (
    get_from_index, set_context, set_index_channel, sync_index_from_channel,
    search_by_media_id, search_by_keyword, search_by_username
)

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Rate Limiting
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


# ========== ارسال گروهی ==========
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


# ========== منوی اصلی ==========
async def start(update: Update, context):
    if context.args and len(context.args) > 0:
        param = context.args[0]
        if param.startswith("profile_"):
            await profile_command(update, context, username=param.split("_")[1])
            return
        elif param.startswith("reels_"):
            await reels_command(update, context, username=param.split("_")[1])
            return
        elif param.startswith("highlights_"):
            await highlights_command(update, context, username=param.split("_")[1])
            return
        elif param.startswith("stories_"):
            await stories_command(update, context, username=param.split("_")[1])
            return
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 دانلود با لینک", callback_data="new_download")],
        [InlineKeyboardButton("👤 پروفایل", callback_data="show_profile_menu"),
         InlineKeyboardButton("🎬 ریلز", callback_data="show_reels_menu")],
        [InlineKeyboardButton("📚 هایلایت", callback_data="show_highlights_menu"),
         InlineKeyboardButton("📖 استوری", callback_data="show_stories_menu")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="show_settings"),
         InlineKeyboardButton("❓ راهنما", callback_data="show_help")]
    ])
    await update.effective_message.reply_text(
        f"<b>👋 سلام {update.effective_user.first_name}!</b>\n\nبه ربات دانلود اینستاگرام خوش اومدی 🎉\n\n✨ <b>قابلیت‌ها:</b>\n• دانلود پست، ریلز، استوری و هایلایت\n• مشاهده پروفایل و آمار\n• دانلود تکی یا ترکیبی\n\n📌 <i>لینک رو برام بفرست یا از دکمه‌ها استفاده کن</i>",
        parse_mode='HTML', reply_markup=keyboard
    )



# ========== پروفایل (فقط عکس + اسم + یوزرنیم) ==========
async def profile_command(update: Update, context, username=None):
    if username is None:
        if not context.args:
            await update.effective_message.reply_text("⚠️ نحوه استفاده:\n<code>/profile username</code>\n\nمثال: /profile cristiano", parse_mode='HTML')
            return
        username = context.args[0].strip("@")
    
    context.user_data['last_username'] = username
    processing = await update.effective_message.reply_text(f"📊 در حال دریافت پروفایل @{username}...")
    
    try:
        profile = await get_instagram_profile(username, context)
        if not profile:
            await processing.edit_text("❌ نتونستم پروفایل رو پیدا کنم.")
            return
        
        caption = f"👤 <b>{profile.get('full_name', username)}</b>\n🔖 @{profile.get('username', username)}"
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")]
        ])
        
        if profile.get("profile_pic"):
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=profile["profile_pic"],
                caption=caption,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            await processing.delete()
        else:
            await processing.edit_text(caption, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Error in profile_command: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


# ========== ریلز ==========
async def reels_command(update: Update, context, username=None):
    if username is None:
        if not context.args:
            await update.effective_message.reply_text("⚠️ نحوه استفاده:\n<code>/reels username</code>\n\nمثال: /reels cristiano", parse_mode='HTML')
            return
        username = context.args[0].strip("@")
    
    context.user_data['last_username'] = username
    if is_rate_limited(update.effective_user.id)[0]:
        await update.message.reply_text(f"⏳ زیادی سریع! {is_rate_limited(update.effective_user.id)[1]} ثانیه صبر کن.")
        return
    
    processing_msg = await update.effective_message.reply_text(f"🎬 در حال دریافت ریل‌های @{username}...")
    
    try:
        result = await get_user_reels_v2(username, context)
        if not result or not result.get("items") or len(result["items"]) == 0:
            await processing_msg.edit_text(f"❌ هیچ ریلی برای @{username} پیدا نشد.")
            return
        
        context.user_data['reels_data'] = {"username": username, "items": result["items"], "current_page": 0, "total": len(result["items"])}
        await processing_msg.delete()
        await show_reel_item(update, context, username, 0)
    except Exception as e:
        logger.error(f"Error in reels_command: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


async def show_reel_item(update: Update, context, username: str, index: int):
    reels_data = context.user_data.get('reels_data')
    if not reels_data or index >= len(reels_data["items"]):
        return
    
    item = reels_data["items"][index]
    total = reels_data["total"]
    caption_lines = [f"🎬 <b>ریل از @{username}</b>", ""]
    if item['caption'] and item['caption'] != "بدون کپشن":
        caption_lines.append(item['caption'])
        caption_lines.append("")
    if item.get('like_count', 0) > 0:
        caption_lines.append(f"❤️ {item['like_count']:,} لایک")
    if item.get('comment_count', 0) > 0:
        caption_lines.append(f"💬 {item['comment_count']:,} کامنت")
    if item.get('play_count', 0) > 0:
        caption_lines.append(f"▶️ {item['play_count']:,} بازدید")
    caption = "\n".join(caption_lines)
    
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"reel_prev_{index}"))
    nav_buttons.append(InlineKeyboardButton(f"{index+1}/{total}", callback_data="reel_info"))
    if index < total - 1:
        nav_buttons.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"reel_next_{index}"))
    
    keyboard = [nav_buttons, [InlineKeyboardButton("📥 دانلود", callback_data=f"reel_download_{index}"), InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")]]
    markup = InlineKeyboardMarkup(keyboard)
    video_url = item["url"]
    
    if "instagram.com/channel/" in video_url:
        media_result = await get_instagram_media(video_url, context)
        if media_result and media_result.get("items"):
            video_url = media_result["items"][0]["url"]
    
    try:
        await context.bot.send_video(chat_id=update.effective_chat.id, video=video_url, caption=caption, supports_streaming=True, parse_mode='HTML', reply_markup=markup)
    except:
        try:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=video_url, caption=caption, parse_mode='HTML', reply_markup=markup)
        except:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎬 <b>ریل از @{username}</b>\n\n{caption}\n\n🔗 لینک مستقیم:\n{video_url}", parse_mode='HTML', reply_markup=markup, disable_web_page_preview=True)


# ========== هایلایت ==========
async def highlights_command(update: Update, context, username=None):
    if username is None:
        if not context.args:
            await update.effective_message.reply_text("⚠️ نحوه استفاده:\n<code>/highlights username</code>\n\nمثال: /highlights cristiano", parse_mode='HTML')
            return
        username = context.args[0].strip("@")
    
    context.user_data['last_username'] = username
    processing = await update.effective_message.reply_text(f"📚 در حال دریافت هایلایت‌های @{username}...")
    
    try:
        highlights_list = await get_instagram_highlights(username, context)
        if not highlights_list:
            await processing.edit_text(f"❌ هیچ هایلایتی برای @{username} پیدا نشد.")
            return
        
        context.user_data['current_highlights'] = highlights_list
        keyboard = []
        for i, h in enumerate(highlights_list[:20]):
            title = h.get("title", "هایلایت")
            count = h.get("count", 0)
            keyboard.append([InlineKeyboardButton(f"📚 {title[:30]}" + (f" ({count})" if count else ""), callback_data=f"hl_{i}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")])
        await processing.edit_text(f"📚 هایلایت‌های @{username}:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error in highlights_command: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_highlight_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("hl_"):
        return
    
    highlights_list = context.user_data.get('current_highlights', [])
    try:
        index = int(query.data.split("_")[1])
        highlight_info = highlights_list[index] if index < len(highlights_list) else None
    except:
        highlight_info = None
    
    if not highlight_info:
        await query.edit_message_text("❌ اطلاعات هایلایت یافت نشد.")
        return
    
    processing = await query.edit_message_text(f"📥 در حال دانلود هایلایت «{highlight_info.get('title', 'هایلایت')}»...")
    
    try:
        result = await get_instagram_highlight_stories(highlight_info.get("id"), None, highlight_info.get("title", "Highlight"), context)
        if not result or not result.get("items"):
            await processing.edit_text(f"❌ هایلایت «{highlight_info.get('title')}» محتوا ندارد.")
            return
        
        items, caption = result["items"], f"📚 هایلایت: {highlight_info.get('title')}"
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به لیست هایلایت‌ها", callback_data="back_to_highlights_list")]])
        
        if len(items) == 1:
            item = items[0]
            try:
                if item["type"] == "video":
                    await context.bot.send_video(query.message.chat_id, item["url"], caption=caption, supports_streaming=True, reply_markup=reply_markup)
                else:
                    await context.bot.send_photo(query.message.chat_id, item["url"], caption=caption, reply_markup=reply_markup)
            except:
                await context.bot.send_document(query.message.chat_id, item["url"], caption=caption, reply_markup=reply_markup)
        else:
            await send_media_group(query.message.chat_id, context, items, caption)
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"✅ هایلایت «{highlight_info.get('title')}» ارسال شد.\n\n🔙 برای بازگشت به لیست هایلایت‌ها روی دکمه زیر کلیک کن:", reply_markup=reply_markup)
        await processing.delete()
    except Exception as e:
        logger.error(f"Highlight download error: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


# ========== استوری ==========
async def stories_command(update: Update, context, username=None):
    if username is None:
        if not context.args:
            await update.effective_message.reply_text("⚠️ نحوه استفاده:\n<code>/stories username</code>\n\nمثال: /stories cristiano", parse_mode='HTML')
            return
        username = context.args[0].strip("@")
    
    context.user_data['last_username'] = username
    processing = await update.effective_message.reply_text(f"📖 در حال بررسی استوری‌های @{username}...")
    
    try:
        items = await check_and_get_stories(username, context)
        if not items or len(items) == 0:
            await processing.edit_text(f"❌ <b>@{username}</b> استوری ندارد یا پیج خصوصی است.\n\n💡 استوری‌ها فقط ۲۴ ساعت روی پروفایل می‌مانند.", parse_mode='HTML')
            return
        
        caption, reply_markup = f"📖 استوری‌های @{username}", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")]])
        
        if len(items) == 1:
            item = items[0]
            try:
                if item["type"] == "video":
                    await context.bot.send_video(chat_id=update.effective_chat.id, video=item["url"], caption=caption, supports_streaming=True, reply_markup=reply_markup)
                else:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=item["url"], caption=caption, reply_markup=reply_markup)
            except:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=item["url"], caption=caption, reply_markup=reply_markup)
        else:
            await send_media_group(update.effective_chat.id, context, items, caption)
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"✅ {len(items)} استوری از @{username} ارسال شد.\n\n🔙 برای بازگشت به منوی انتخاب کلیک کن:", reply_markup=reply_markup)
        await processing.delete()
    except Exception as e:
        logger.error(f"Error in stories_command: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


# ========== تنظیمات ==========
async def show_settings_menu(update: Update, context, query=None):
    user_id = update.effective_user.id
    current_mode = await get_user_mode(user_id, context)
    mode_text = "🎬 آلبوم ترکیبی" if current_mode == "album" else "📁 فایل جداگانه"
    
    text = f"⚙️ <b>تنظیمات ارسال</b>\n\nحالت فعلی: {mode_text}\n\n📌 <b>توضیحات:</b>\n• آلبوم ترکیبی: چند رسانه در یک پیام\n• فایل جداگانه: هر رسانه به صورت جداگانه\n\n<i>🕐 آخرین بروزرسانی: {time.strftime('%H:%M:%S')}</i>"
    
    # استفاده از کیبورد با نمایش حالت فعال
    from database import get_user_settings_keyboard_with_mode
    keyboard = get_user_settings_keyboard_with_mode(current_mode)
    
    if query:
        try:
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e:
            if "Message is not modified" not in str(e):
                raise e
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


async def settings_command(update: Update, context):
    await show_settings_menu(update, context)


async def help_command(update: Update, context):
    await update.effective_message.reply_text(
        "📖 <b>راهنمای ربات</b>\n\n🔹 <b>ارسال لینک:</b>\n   هر لینکی از اینستاگرام (پست، ریلز، استوری، هایلایت)\n\n"
        "🔹 <b>دستورات:</b>\n   /profile @username - اطلاعات پروفایل\n   /reels @username - دریافت ریل‌ها\n"
        "   /highlights @username - دریافت هایلایت‌ها\n   /stories @username - دریافت استوری‌ها\n"
        "   /settings - تنظیمات ارسال\n   /help - این راهنما\n\n🔹 <b>نکته:</b>\n   می‌توانید فقط شناسه پست (مثلاً DZcDzv9iJOJ) را هم ارسال کنید.",
        parse_mode='HTML'
    )


# ========== هندلر لینک ==========
async def handle_link(update: Update, context):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    if "instagram.com" not in url:
        await update.message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return
    
    profile_pattern = r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?$'
    match = re.search(profile_pattern, url)
    if match and not re.search(r'/(p|reel|stories|tv|highlights)/', url):
        username = match.group(1)
        context.user_data['last_username'] = username
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 پروفایل", callback_data=f"quick_profile_{username}"), InlineKeyboardButton("🎬 ریلز", callback_data=f"quick_reels_{username}")],
            [InlineKeyboardButton("📚 هایلایت", callback_data=f"quick_highlights_{username}"), InlineKeyboardButton("📖 استوری", callback_data=f"quick_stories_{username}")],
            [InlineKeyboardButton("❌ لغو", callback_data="back_to_main")]
        ])
        await update.message.reply_text(f"🔍 <b>{username}</b>\n\nکدوم اطلاعات رو میخوای؟", parse_mode='HTML', reply_markup=keyboard)
        return
    
    if is_rate_limited(user_id)[0]:
        await update.message.reply_text(f"⏳ زیادی سریع! {is_rate_limited(user_id)[1]} ثانیه صبر کن.")
        return
    
    extracted = extract_instagram_id(url)
    if extracted:
        check_key = f"media:{extracted['full_id']}"
        logger.info(f"🔍 چک کردن ایندکس با کلید: {check_key}")
        index_data = await get_from_index(check_key)
        if index_data:
            logger.info(f"✅ آیتم در ایندکس پیدا شد! ارسال از کش...")
            cached_result = await get_media_by_key(context, check_key)
            if cached_result and cached_result.get("items"):
                items, caption = cached_result["items"], cached_result.get("caption", "دانلود از اینستاگرام")
                default_mode = await get_user_mode(user_id, context)
                status_msg = await update.message.reply_text("📦 ارسال از حافظه کش...")
                try:
                    if len(items) == 1:
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
                                await asyncio.sleep(0.5)
                    await status_msg.delete()
                    return
                except Exception as e:
                    logger.warning(f"خطا در ارسال از کش: {e}")
                    await status_msg.edit_text("🔄 خطا در ارسال از کش، تلاش مجدد از API...")
    
    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")
    try:
        result = await get_instagram_media(url, context)
        if not result or not result.get("items"):
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم.")
            return
        
        items, caption, default_mode = result.get("items", []), result.get("caption", "دانلود از اینستاگرام"), await get_user_mode(user_id, context)
        
        if len(items) == 1:
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
                    await asyncio.sleep(0.5)
        await processing_msg.delete()
    except Exception as e:
        logger.error(f"Error in handle_link: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


# ========== هندلر ورودی مستقیم ==========
async def handle_direct_input(update: Update, context):
    if not update.message:
        return
    text = update.message.text.strip()
    
    # شناسه یکتا
    if re.match(r'^[A-Za-z0-9_-]{8,15}$', text):
        processing = await update.message.reply_text("🔍 در حال جستجوی شناسه در دیتابیس...")
        found = await search_by_media_id(text)
        if not found:
            results = await search_by_keyword(text)
            found = results[0] if results else None
        if found:
            cache_key = found.get('key')
            if cache_key:
                cached_result = await get_media_by_key(context, cache_key)
                if cached_result and cached_result.get("items"):
                    await processing.delete()
                    items, caption, default_mode = cached_result["items"], cached_result.get("caption", "دانلود از اینستاگرام"), await get_user_mode(update.effective_user.id, context)
                    if len(items) == 1:
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
                                await asyncio.sleep(0.5)
                    return
        else:
            await processing.edit_text(f"📥 شناسه {text} در دیتابیس نیست. در حال دریافت از اینستاگرام...")
            update.message.text = f"https://www.instagram.com/p/{text}/"
    
    # یوزرنیم
    if text.startswith('@'):
        username = text.lstrip('@')
        results = await search_by_username(username, limit=1)
        if results:
            profile = await get_profile_from_channel(context, username)
            if profile:
                await profile_command(update, context, username=username)
                return
        
        context.user_data['last_username'] = username
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 پروفایل", callback_data=f"quick_profile_{username}"), InlineKeyboardButton("🎬 ریلز", callback_data=f"quick_reels_{username}")],
            [InlineKeyboardButton("📚 هایلایت", callback_data=f"quick_highlights_{username}"), InlineKeyboardButton("📖 استوری", callback_data=f"quick_stories_{username}")],
            [InlineKeyboardButton("❌ لغو", callback_data="back_to_main")]
        ])
        await update.message.reply_text(f"🔍 <b>{username}</b>\n\nکدوم اطلاعات رو میخوای؟", parse_mode='HTML', reply_markup=keyboard)
        return
    
    if "instagram.com" in text:
        await handle_link(update, context)
        return
    
    await update.message.reply_text("❌ لطفاً یک یوزرنیم (با @) یا لینک اینستاگرام بفرست.")


# ========== هندلر کالبک ==========
async def handle_reel_callbacks(update: Update, context):
    query = update.callback_query
    await query.answer()
    data, reels_data = query.data, context.user_data.get('reels_data')
    
    if not reels_data:
        await query.edit_message_text("❌ اطلاعات ریل منقضی شده. دوباره /reels رو امتحان کن.")
        return
    
    if data == "reel_close":
        await query.message.delete()
        context.user_data.pop('reels_data', None)
    elif data == "reel_info":
        await query.answer(f"ریل {reels_data['current_page']+1} از {reels_data['total']}")
    elif data.startswith("reel_prev_"):
        new_index = int(data.split("_")[2]) - 1
        reels_data["current_page"] = new_index
        await query.message.delete()
        await show_reel_item(update, context, reels_data["username"], new_index)
    elif data.startswith("reel_next_"):
        new_index = int(data.split("_")[2]) + 1
        reels_data["current_page"] = new_index
        await query.message.delete()
        await show_reel_item(update, context, reels_data["username"], new_index)
    elif data.startswith("reel_download_"):
        index = int(data.split("_")[2])
        if index < len(reels_data["items"]):
            item = reels_data["items"][index]
            msg = await query.message.reply_text("📥 در حال ارسال فایل...")
            try:
                await context.bot.send_document(chat_id=update.effective_chat.id, document=item["url"], filename=f"reel_{reels_data['username']}_{index+1}.mp4", caption=f"🎬 ریل از @{reels_data['username']}\n{item['caption'][:100]}")
                await msg.delete()
            except Exception as e:
                await msg.edit_text(f"❌ خطا در دانلود: {str(e)[:100]}")


async def handle_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    data, user_id = query.data, update.effective_user.id
    
    if data == "back_to_username_menu":
        username = context.user_data.get('last_username')
        if username:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("👤 پروفایل", callback_data=f"quick_profile_{username}"), InlineKeyboardButton("🎬 ریلز", callback_data=f"quick_reels_{username}")],
                [InlineKeyboardButton("📚 هایلایت", callback_data=f"quick_highlights_{username}"), InlineKeyboardButton("📖 استوری", callback_data=f"quick_stories_{username}")],
                [InlineKeyboardButton("❌ لغو", callback_data="back_to_main")]
            ])
            await query.message.reply_text(f"🔍 <b>{username}</b>\n\nکدوم اطلاعات رو میخوای؟", parse_mode='HTML', reply_markup=keyboard)
            await query.message.delete()
        else:
            await query.edit_message_text("🔙 به منوی اصلی برگشتی.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]]))
    elif data == "back_to_highlights_list":
        username = context.user_data.get('last_username')
        if username:
            processing = await query.message.reply_text(f"📚 در حال دریافت هایلایت‌های @{username}...")
            try:
                highlights_list = await get_instagram_highlights(username, context)
                if not highlights_list:
                    await processing.edit_text(f"❌ هیچ هایلایتی برای @{username} پیدا نشد.")
                    return
                context.user_data['current_highlights'] = highlights_list
                keyboard = []
                for i, h in enumerate(highlights_list[:20]):
                    title = h.get("title", "هایلایت")
                    count = h.get("count", 0)
                    keyboard.append([InlineKeyboardButton(f"📚 {title[:30]}" + (f" ({count})" if count else ""), callback_data=f"hl_{i}")])
                keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")])
                await query.message.reply_text(f"📚 هایلایت‌های @{username}:", reply_markup=InlineKeyboardMarkup(keyboard))
                await processing.delete()
                await query.message.delete()
            except Exception as e:
                await processing.edit_text(f"❌ خطا: {str(e)[:100]}")
        else:
            await query.edit_message_text("🔙 به منوی اصلی برگشتی.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]]))
    elif data.startswith("quick_profile_"):
        await query.message.delete()
        await profile_command(update, context, username=data.split("_")[2])
    elif data.startswith("quick_reels_"):
        await query.message.delete()
        await reels_command(update, context, username=data.split("_")[2])
    elif data.startswith("quick_highlights_"):
        await query.message.delete()
        await highlights_command(update, context, username=data.split("_")[2])
    elif data.startswith("quick_stories_"):
        await query.message.delete()
        await stories_command(update, context, username=data.split("_")[2])
    elif data == "show_profile_menu":
        await query.edit_message_text("👤 <b>پروفایل</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>", parse_mode='HTML')
    elif data == "show_reels_menu":
        await query.edit_message_text("🎬 <b>ریلز</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>", parse_mode='HTML')
    elif data == "show_highlights_menu":
        await query.edit_message_text("📚 <b>هایلایت</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>", parse_mode='HTML')
    elif data == "show_stories_menu":
        await query.edit_message_text("📖 <b>استوری</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>", parse_mode='HTML')
    elif data.startswith("reel_"):
        await handle_reel_callbacks(update, context)
    elif data.startswith("hl_"):
        await handle_highlight_callback(update, context)
    elif data == "new_download":
        await query.edit_message_text("📎 لطفاً لینک اینستاگرام خود را ارسال کنید:")
    elif data == "show_settings":
        await show_settings_menu(update, context, query)
    elif data == "show_help":
        await help_command(update, context)
    elif data == "set_mode_album":
        await set_user_mode(user_id, "album", context)
        await show_settings_menu(update, context, query)
    elif data == "set_mode_file":
        await set_user_mode(user_id, "file", context)
        await show_settings_menu(update, context, query)
    elif data == "back_to_main":
        await start(update, context)


# ========== دستورات ادمین ==========
async def clear_cache_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ شما دسترسی به این دستور ندارید.")
        return
    
    await update.message.reply_text("✅ تمام کش‌های حافظه پاک شد.")


async def stats_command(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ شما دسترسی به این دستور ندارید.")
        return
    from index_manager import get_index_stats
    stats = await get_index_stats()
    text = f"📊 <b>آمار ربات</b>\n━━━━━━━━━━━━━━━━\n📦 کل آیتم‌های ایندکس: {stats['total_items']}\n\n📁 <b>تفکیک شده:</b>\n"
    for data_type, count in stats['by_type'].items():
        text += f"   • {data_type}: {count}\n"
    await update.message.reply_text(text, parse_mode='HTML')


# ========== اینلاین مود ==========
async def inline_query(update: Update, context):
    query = update.inline_query.query.strip()
    bot_username = context.bot.username
    if not query:
        await update.inline_query.answer([], cache_time=60, is_personal=True, switch_pm_text="🔍 یه یوزرنیم اینستا وارد کن...", switch_pm_parameter="start")
        return
    
    username = ''.join(c for c in query.lstrip('@') if c.isalnum() or c == '_')
    if not username:
        await update.inline_query.answer([], cache_time=60)
        return
    
    results = []
    for title, desc, start in [("مشاهده پروفایل", "مشاهده اطلاعات پروفایل، فالوورها، پست‌ها", f"profile_{username}"),
                                 ("دریافت ریل‌ها", "دریافت آخرین ریل‌ها", f"reels_{username}"),
                                 ("دریافت هایلایت‌ها", "دریافت هایلایت‌های ذخیره شده", f"highlights_{username}"),
                                 ("مشاهده استوری‌ها", "مشاهده استوری‌های ۲۴ ساعت اخیر", f"stories_{username}")]:
        results.append(InlineQueryResultArticle(id=str(uuid4()), title=f"{username}", description=desc,
            input_message_content=InputTextMessageContent(f"🔍 برای {title} <b>@{username}</b> روی دکمه زیر کلیک کن 👇", parse_mode='HTML'),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(title, url=f"https://t.me/{bot_username}?start={start}")]])))
    await update.inline_query.answer(results, cache_time=60, is_personal=True)


# ========== راه‌اندازی ==========
async def post_init(application: Application):
    logger.info("🚀 در حال آماده‌سازی ربات...")
    set_context(application.bot)
    from config import INDEX_CHANNEL_ID
    if INDEX_CHANNEL_ID:
        try:
            set_index_channel(int(INDEX_CHANNEL_ID))
            await sync_index_from_channel()
            logger.info("✅ ایندکس از کانال همگام‌سازی شد")
        except Exception as e:
            logger.error(f"❌ خطا در همگام‌سازی ایندکس: {e}")
    else:
        logger.warning("⚠️ INDEX_CHANNEL_ID تنظیم نشده!")
    logger.info("✅ ربات آماده اجراست!")


def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    app.post_init = post_init
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("highlights", highlights_command))
    app.add_handler(CommandHandler("reels", reels_command))
    app.add_handler(CommandHandler("stories", stories_command))
    app.add_handler(CommandHandler("clearcache", clear_cache_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_direct_input))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(InlineQueryHandler(inline_query))
    
    logger.info("🤖 ربات در حال اجراست...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
