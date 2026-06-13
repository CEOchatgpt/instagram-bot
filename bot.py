# bot.py - نسخه نهایی با پشتیبانی از کش هوشمند چند لایه و منوی انتخاب صحیح

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
    InlineQueryHandler, ContextTypes
)

from config import BOT_TOKEN, ADMIN_ID
from database import redis_client
from smart_cache import (
    save_file_to_channel,
    send_cached_media
)
from rapidapi_service import (
    get_instagram_media,
    get_instagram_profile,
    get_instagram_highlights,
    get_instagram_highlight_stories,
    get_user_reels_v2,
    check_and_get_stories,
    extract_media_id_from_url
)
from user_settings import get_user_default_mode, set_user_default_mode, get_user_settings_keyboard

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
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


def generate_media_key(media_id: str, media_type: str) -> str:
    """تولید کلید یکتا برای هر محتوا"""
    return f"{media_type}:{media_id}"


# ========== توابع اصلی ==========

async def start(update: Update, context):
    """شروع ربات - پشتیبانی از دیپ لینک"""
    
    if context.args and len(context.args) > 0:
        param = context.args[0]
        
        if param.startswith("profile_"):
            username = param.split("_")[1]
            await profile_command(update, context, username=username)
            return
        elif param.startswith("reels_"):
            username = param.split("_")[1]
            await reels_command(update, context, username=username)
            return
        elif param.startswith("highlights_"):
            username = param.split("_")[1]
            await highlights_command(update, context, username=username)
            return
        elif param.startswith("stories_"):
            username = param.split("_")[1]
            await stories_command(update, context, username=username)
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
        f"<b>👋 سلام {update.effective_user.first_name}!</b>\n\n"
        f"به ربات دانلود اینستاگرام خوش اومدی 🎉\n\n"
        f"✨ <b>قابلیت‌ها:</b>\n"
        f"• دانلود پست، ریلز، استوری و هایلایت\n"
        f"• مشاهده پروفایل و آمار\n"
        f"• دانلود تکی یا ترکیبی\n\n"
        f"📌 <i>لینک رو برام بفرست یا از دکمه‌ها استفاده کن</i>\n\n"
        f"💡 <i>محتوای محبوب برای همیشه در بات ذخیره میشه!</i>",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def profile_command(update: Update, context, username=None):
    """دریافت پروفایل با دکمه بازگشت به منوی انتخاب"""
    if username is None:
        if not context.args:
            await update.effective_message.reply_text(
                "⚠️ نحوه استفاده:\n<code>/profile username</code>\n\nمثال: /profile cristiano",
                parse_mode='HTML'
            )
            return
        username = context.args[0].strip("@")
    
    context.user_data['last_username'] = username
    processing = await update.effective_message.reply_text(f"📊 در حال دریافت پروفایل @{username}...")

    try:
        profile = await get_instagram_profile(username, context)
        
        if not profile:
            await processing.edit_text("❌ نتونستم پروفایل رو پیدا کنم.")
            return

        private_text = "🔒 خصوصی" if profile.get('is_private') else "🌐 عمومی"
        verified_text = "✅ تأیید شده" if profile.get('is_verified') else ""
        
        caption = (
            f"👤 <b>{profile.get('full_name', username)}</b>\n"
            f"🔖 @{profile.get('username', username)}\n"
            f"{private_text} {verified_text}\n\n"
            f"📝 {profile.get('biography', 'بدون بیو')[:280]}\n\n"
            f"❤️ {profile.get('followers', 0):,} دنبال‌کننده\n"
            f"👥 {profile.get('following', 0):,} دنبال‌شونده\n"
            f"📸 {profile.get('posts', 0):,} پست\n"
        )
        
        # دکمه بازگشت به منوی انتخاب
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


async def reels_command(update: Update, context, username=None):
    """دریافت ریل‌ها با دکمه بازگشت"""
    if username is None:
        if not context.args:
            await update.effective_message.reply_text(
                "⚠️ نحوه استفاده:\n<code>/reels username</code>\n\nمثال: /reels cristiano",
                parse_mode='HTML'
            )
            return
        username = context.args[0].strip("@")
    
    context.user_data['last_username'] = username
    user_id = update.effective_user.id
    
    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه صبر کن.")
        return
    
    processing_msg = await update.effective_message.reply_text(f"🎬 در حال دریافت ریل‌های @{username}...")
    
    try:
        result = await get_user_reels_v2(username, context)
        
        if not result or not result.get("items"):
            await processing_msg.edit_text(f"❌ هیچ ریلی برای @{username} پیدا نشد.")
            return
        
        items = result["items"]
        
        if len(items) == 0:
            await processing_msg.edit_text(f"❌ هیچ ریلی برای @{username} پیدا نشد.")
            return
        
        context.user_data['reels_data'] = {
            "username": username,
            "items": items,
            "current_page": 0,
            "total": len(items)
        }
        
        await processing_msg.delete()
        await show_reel_item(update, context, username, 0)
        
    except Exception as e:
        logger.error(f"Error in reels_command: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


async def highlights_command(update: Update, context, username=None):
    """دریافت هایلایت‌ها با دکمه بازگشت"""
    if username is None:
        if not context.args:
            await update.effective_message.reply_text(
                "⚠️ نحوه استفاده:\n<code>/highlights username</code>\n\nمثال: /highlights cristiano",
                parse_mode='HTML'
            )
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
            button_text = f"📚 {title[:30]}" + (f" ({count})" if count else "")
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"hl_{i}")])
        
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")])

        await processing.edit_text(
            f"📚 هایلایت‌های @{username}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Error in highlights_command: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


async def stories_command(update: Update, context, username=None):
    """دریافت استوری‌های کاربر"""
    if username is None:
        if not context.args:
            await update.effective_message.reply_text(
                "⚠️ نحوه استفاده:\n<code>/stories username</code>\n\nمثال: /stories cristiano",
                parse_mode='HTML'
            )
            return
        username = context.args[0].strip("@")
    
    context.user_data['last_username'] = username
    processing = await update.effective_message.reply_text(f"📖 در حال بررسی استوری‌های @{username}...")

    try:
        items = await check_and_get_stories(username, context)
        
        if not items or len(items) == 0:
            await processing.edit_text(
                f"❌ <b>@{username}</b> استوری ندارد یا پیج خصوصی است.\n\n"
                f"💡 استوری‌ها فقط ۲۴ ساعت روی پروفایل می‌مانند.",
                parse_mode='HTML'
            )
            return
        
        caption = f"📖 استوری‌های @{username}"
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")]
        ])
        
        if len(items) == 1:
            item = items[0]
            try:
                if item["type"] == "video":
                    await context.bot.send_video(
                        chat_id=update.effective_chat.id,
                        video=item["url"],
                        caption=caption,
                        supports_streaming=True,
                        reply_markup=reply_markup
                    )
                else:
                    await context.bot.send_photo(
                        chat_id=update.effective_chat.id,
                        photo=item["url"],
                        caption=caption,
                        reply_markup=reply_markup
                    )
            except Exception as e:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    caption=caption,
                    reply_markup=reply_markup
                )
        else:
            await send_media_group(update.effective_chat.id, context, items, caption)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✅ {len(items)} استوری از @{username} ارسال شد.\n\n🔙 برای بازگشت به منوی انتخاب کلیک کن:",
                reply_markup=reply_markup
            )
        
        await processing.delete()

    except Exception as e:
        logger.error(f"Error in stories_command: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


# ========== نمایش ریلز ==========

async def show_reel_item(update: Update, context, username: str, index: int):
    """نمایش یک ریل با دکمه بازگشت"""
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
    
    keyboard = []
    nav_buttons = []
    
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"reel_prev_{index}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{index+1}/{total}", callback_data="reel_info"))
    
    if index < total - 1:
        nav_buttons.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"reel_next_{index}"))
    
    keyboard.append(nav_buttons)
    keyboard.append([
        InlineKeyboardButton("📥 دانلود", callback_data=f"reel_download_{index}"),
        InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")
    ])
    
    markup = InlineKeyboardMarkup(keyboard)
    video_url = item["url"]
    chat_id = update.effective_chat.id
    
    try:
        await context.bot.send_video(
            chat_id=chat_id,
            video=video_url,
            caption=caption,
            supports_streaming=True,
            parse_mode='HTML',
            reply_markup=markup
        )
    except Exception as e:
        logger.warning(f"send_video failed: {e}")
        try:
            await context.bot.send_document(
                chat_id=chat_id,
                document=video_url,
                caption=caption,
                parse_mode='HTML',
                reply_markup=markup
            )
        except Exception as e2:
            logger.warning(f"send_document failed: {e2}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎬 <b>ریل از @{username}</b>\n\n{caption}\n\n🔗 لینک مستقیم:\n{video_url}",
                parse_mode='HTML',
                reply_markup=markup,
                disable_web_page_preview=True
            )


# ========== هندلر لینک ==========

async def handle_link(update: Update, context):
    url = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if "instagram.com" not in url:
        await update.message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return

    # تشخیص لینک صفحه اصلی پیج
    profile_pattern = r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)/?$'
    match = re.search(profile_pattern, url)
    
    if match and not re.search(r'/(p|reel|stories|tv|highlights)/', url):
        username = match.group(1)
        context.user_data['last_username'] = username
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👤 پروفایل", callback_data=f"quick_profile_{username}"),
                InlineKeyboardButton("🎬 ریلز", callback_data=f"quick_reels_{username}")
            ],
            [
                InlineKeyboardButton("📚 هایلایت", callback_data=f"quick_highlights_{username}"),
                InlineKeyboardButton("📖 استوری", callback_data=f"quick_stories_{username}")
            ],
            [
                InlineKeyboardButton("❌ لغو", callback_data="back_to_main")
            ]
        ])
        
        await update.message.reply_text(
            f"🔍 <b>{username}</b>\n\nکدوم اطلاعات رو میخوای؟",
            parse_mode='HTML',
            reply_markup=keyboard
        )
        return
    
    # لینک معمولی - تلاش برای کش
    media_id = extract_media_id_from_url(url)
    if media_id:
        media_key = generate_media_key(media_id, "post")
        # تلاش برای ارسال از کش کانال
        if await send_cached_media(context, chat_id, url, "reel"):
            return
    
    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه صبر کن.")
        return

    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")

    try:
        result = await get_instagram_media(url, context, chat_id)
        
        if not result or not result.get("items"):
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم.")
            return

        items = result.get("items", [])
        caption = result.get("caption", "دانلود از اینستاگرام")
        default_mode = get_user_default_mode(user_id)

        if len(items) == 1:
            item = items[0]
            if default_mode == "file":
                await context.bot.send_document(chat_id, item["url"], caption=caption)
            else:
                if item["type"] == "video":
                    await context.bot.send_video(chat_id, item["url"], supports_streaming=True, caption=caption)
                else:
                    await context.bot.send_photo(chat_id, item["url"], caption=caption)
        else:
            if default_mode == "album":
                await send_media_group(chat_id, context, items, caption)
            else:
                for i, item in enumerate(items):
                    await context.bot.send_document(chat_id, item["url"], caption=caption if i == 0 else None)
                    await asyncio.sleep(0.5)

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error in handle_link: {e}")
        await processing_msg.edit_text(f"❌ خطا: {str(e)[:100]}")


# ========== هندلر ورودی مستقیم ==========

async def handle_direct_input(update: Update, context):
    """هندلر اصلی برای ورودی مستقیم کاربر (یوزرنیم یا لینک)"""
    message = update.message
    text = message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # تشخیص لینک اینستاگرام
    is_insta_link = any(p in text.lower() for p in ["instagram.com/p/", "instagram.com/reel/", "instagram.com/tv/", "instagram.com/stories/"])

    if is_insta_link:
        await handle_link(update, context)
        return
    
    # بررسی یوزرنیم (با @ شروع شده)
    if text.startswith('@'):
        username = text.lstrip('@')
        # اعتبارسنجی یوزرنیم
        if not re.match(r"^[a-zA-Z0-9_.]+$", username):
            await message.reply_text("❌ یوزرنیم نامعتبر است.")
            return
        
        context.user_data['last_username'] = username
        
        # دریافت پروفایل
        processing = await message.reply_text(f"🔍 در حال بررسی پروفایل {username}...")
        profile = await get_instagram_profile(username, context)
        
        if not profile:
            await processing.edit_text("❌ پروفایل یافت نشد یا پیج خصوصی است.")
            return
        
        await processing.delete()
        
        # منوی انتخاب (پروفایل، ریلز، هایلایت، استوری)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("👤 پروفایل", callback_data=f"quick_profile_{username}"),
                InlineKeyboardButton("🎬 ریلز", callback_data=f"quick_reels_{username}")
            ],
            [
                InlineKeyboardButton("📚 هایلایت", callback_data=f"quick_highlights_{username}"),
                InlineKeyboardButton("📖 استوری", callback_data=f"quick_stories_{username}")
            ],
            [
                InlineKeyboardButton("❌ لغو", callback_data="back_to_main")
            ]
        ])
        
        caption = f"🔍 <b>{username}</b>\n\nکدوم اطلاعات رو میخوای؟"
        
        if profile.get("profile_pic"):
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=profile["profile_pic"],
                caption=caption,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        else:
            await message.reply_text(caption, parse_mode='HTML', reply_markup=keyboard)
        
        return
    
    # هیچکدوم
    await message.reply_text("❌ لطفاً یک یوزرنیم (با @) یا لینک اینستاگرام بفرست.")


# ========== سایر توابع کمکی ==========

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
        await query.edit_message_text("❌ اطلاعات هایلایت یافت نشد.")
        return
    
    highlight_id = highlight_info.get("id")
    title = highlight_info.get("title", "هایلایت")
    chat_id = query.message.chat_id
    
    processing = await query.edit_message_text(f"📥 در حال دانلود هایلایت «{title}»...")
    
    try:
        result = await get_instagram_highlight_stories(highlight_id, None, title, context)
        
        if not result or not result.get("items"):
            await processing.edit_text(f"❌ هایلایت «{title}» محتوا ندارد.")
            return

        items = result["items"]
        caption = f"📚 هایلایت: {title}"
        
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت به لیست هایلایت‌ها", callback_data="back_to_highlights_list")]
        ])

        if len(items) == 1:
            item = items[0]
            try:
                if item["type"] == "video":
                    await context.bot.send_video(
                        chat_id, item["url"], caption=caption, 
                        supports_streaming=True, reply_markup=reply_markup
                    )
                else:
                    await context.bot.send_photo(
                        chat_id, item["url"], caption=caption, reply_markup=reply_markup
                    )
            except:
                await context.bot.send_document(
                    chat_id, item["url"], caption=caption, reply_markup=reply_markup
                )
        else:
            await send_media_group(chat_id, context, items, caption)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ هایلایت «{title}» ارسال شد.\n\n🔙 برای بازگشت به لیست هایلایت‌ها کلیک کن:",
                reply_markup=reply_markup
            )

        await processing.delete()

    except Exception as e:
        logger.error(f"Highlight download error: {e}")
        await processing.edit_text(f"❌ خطا: {str(e)[:100]}")


async def handle_reel_callbacks(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    reels_data = context.user_data.get('reels_data')
    
    if not reels_data:
        await query.edit_message_text("❌ اطلاعات ریل منقضی شده. دوباره /reels رو امتحان کن.")
        return
    
    if data == "reel_close":
        await query.message.delete()
        context.user_data.pop('reels_data', None)
        return
    
    if data == "reel_info":
        await query.answer(f"ریل {reels_data['current_page']+1} از {reels_data['total']}")
        return
    
    if data.startswith("reel_prev_"):
        current_index = int(data.split("_")[2])
        new_index = current_index - 1
        reels_data["current_page"] = new_index
        context.user_data['reels_data'] = reels_data
        
        await query.message.delete()
        await show_reel_item(update, context, reels_data["username"], new_index)
        return
    
    if data.startswith("reel_next_"):
        current_index = int(data.split("_")[2])
        new_index = current_index + 1
        reels_data["current_page"] = new_index
        context.user_data['reels_data'] = reels_data
        
        await query.message.delete()
        await show_reel_item(update, context, reels_data["username"], new_index)
        return
    
    if data.startswith("reel_download_"):
        index = int(data.split("_")[2])
        if index < len(reels_data["items"]):
            item = reels_data["items"][index]
            
            msg = await query.message.reply_text("📥 در حال ارسال فایل...")
            try:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    filename=f"reel_{reels_data['username']}_{index+1}.mp4",
                    caption=f"🎬 ریل از @{reels_data['username']}\n{item['caption'][:100]}"
                )
                await msg.delete()
            except Exception as e:
                await msg.edit_text(f"❌ خطا در دانلود: {str(e)[:100]}")


async def show_settings_menu(update: Update, context, query=None):
    user_id = update.effective_user.id
    current_mode = get_user_default_mode(user_id)
    
    import time
    mode_text = "🎬 آلبوم ترکیبی" if current_mode == "album" else "📁 فایل (جداگانه)"
    
    text = (
        f"⚙️ <b>تنظیمات ارسال</b>\n\n"
        f"حالت فعلی: {mode_text}\n\n"
        f"📌 <b>توضیحات:</b>\n"
        f"• آلبوم ترکیبی: چند رسانه در یک پیام\n"
        f"• فایل جداگانه: هر رسانه به صورت جداگانه\n\n"
        f"<i>🕐 آخرین بروزرسانی: {time.strftime('%H:%M:%S')}</i>"
    )
    keyboard = get_user_settings_keyboard(user_id)
    
    if query:
        try:
            await query.edit_message_text(text, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e:
            if "Message is not modified" in str(e):
                await query.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)
            else:
                raise e
    else:
        await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)


async def help_command(update: Update, context):
    await update.effective_message.reply_text(
        "📖 <b>راهنمای ربات</b>\n\n"
        "🔹 <b>ارسال لینک:</b>\n"
        "   هر لینکی از اینستاگرام (پست، ریلز، استوری، هایلایت)\n\n"
        "🔹 <b>دستورات:</b>\n"
        "   /profile @username - اطلاعات پروفایل\n"
        "   /reels @username - دریافت ریل‌ها\n"
        "   /highlights @username - دریافت هایلایت‌ها\n"
        "   /stories @username - دریافت استوری‌ها\n"
        "   /settings - تنظیمات ارسال\n"
        "   /help - این راهنما\n\n"
        "💡 <b>نکته:</b> محتوای محبوب برای همیشه در بات ذخیره می‌شود!",
        parse_mode='HTML'
    )


async def settings_command(update: Update, context):
    await show_settings_menu(update, context)


# ========== اینلاین ==========

async def inline_query(update: Update, context):
    """هندلر جستجوی اینلاین"""
    query = update.inline_query.query.strip()
    bot_username = context.bot.username
    
    if not query:
        await update.inline_query.answer(
            [],
            cache_time=60,
            is_personal=True,
            switch_pm_text="🔍 یه یوزرنیم اینستا وارد کن...",
            switch_pm_parameter="start"
        )
        return
    
    username = query.lstrip('@')
    username = ''.join(c for c in username if c.isalnum() or c == '_')
    
    if not username:
        await update.inline_query.answer([], cache_time=60)
        return
    
    results = []
    
    results.append(InlineQueryResultArticle(
        id=str(uuid4()),
        title=f"{username}",
        description="مشاهده اطلاعات پروفایل، فالوورها، پست‌ها",
        input_message_content=InputTextMessageContent(
            f"🔍 برای مشاهده پروفایل <b>@{username}</b> روی دکمه زیر کلیک کن 👇",
            parse_mode='HTML'
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 مشاهده پروفایل", url=f"https://t.me/{bot_username}?start=profile_{username}")]
        ])
    ))
    
    results.append(InlineQueryResultArticle(
        id=str(uuid4()),
        title=f"{username}",
        description="دریافت آخرین ریل‌ها",
        input_message_content=InputTextMessageContent(
            f"🎬 برای دریافت ریل‌های <b>@{username}</b> روی دکمه زیر کلیک کن 👇",
            parse_mode='HTML'
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 دریافت ریل‌ها", url=f"https://t.me/{bot_username}?start=reels_{username}")]
        ])
    ))
    
    results.append(InlineQueryResultArticle(
        id=str(uuid4()),
        title=f"{username}",
        description="دریافت هایلایت‌های ذخیره شده",
        input_message_content=InputTextMessageContent(
            f"📚 برای دریافت هایلایت‌های <b>@{username}</b> روی دکمه زیر کلیک کن 👇",
            parse_mode='HTML'
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 دریافت هایلایت‌ها", url=f"https://t.me/{bot_username}?start=highlights_{username}")]
        ])
    ))

    results.append(InlineQueryResultArticle(
        id=str(uuid4()),
        title=f"{username}",
        description="مشاهده استوری‌های ۲۴ ساعت اخیر",
        input_message_content=InputTextMessageContent(
            f"📖 برای مشاهده استوری‌های <b>@{username}</b> روی دکمه زیر کلیک کن 👇",
            parse_mode='HTML'
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 مشاهده استوری‌ها", url=f"https://t.me/{bot_username}?start=stories_{username}")]
        ])
    ))
    
    await update.inline_query.answer(results, cache_time=60, is_personal=True)


# ========== هندلر کالبک ==========

async def handle_callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    # بازگشت به منوی انتخاب
    if data == "back_to_username_menu":
        username = context.user_data.get('last_username')
        if username:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("👤 پروفایل", callback_data=f"quick_profile_{username}"),
                    InlineKeyboardButton("🎬 ریلز", callback_data=f"quick_reels_{username}")
                ],
                [
                    InlineKeyboardButton("📚 هایلایت", callback_data=f"quick_highlights_{username}"),
                    InlineKeyboardButton("📖 استوری", callback_data=f"quick_stories_{username}")
                ],
                [
                    InlineKeyboardButton("❌ لغو", callback_data="back_to_main")
                ]
            ])
            
            await query.message.reply_text(
                f"🔍 <b>{username}</b>\n\nکدوم اطلاعات رو میخوای؟",
                parse_mode='HTML',
                reply_markup=keyboard
            )
            await query.message.delete()
        else:
            await query.edit_message_text(
                "🔙 به منوی اصلی برگشتی.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
                ])
            )
        return
    
    # بازگشت به لیست هایلایت‌ها
    if data == "back_to_highlights_list":
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
                    button_text = f"📚 {title[:30]}" + (f" ({count})" if count else "")
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"hl_{i}")])
                keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی انتخاب", callback_data="back_to_username_menu")])
                
                await query.message.reply_text(
                    f"📚 هایلایت‌های @{username}:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                await processing.delete()
                await query.message.delete()
            except Exception as e:
                await processing.edit_text(f"❌ خطا: {str(e)[:100]}")
        else:
            await query.edit_message_text(
                "🔙 به منوی اصلی برگشتی.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 منوی اصلی", callback_data="back_to_main")]
                ])
            )
        return
    
    # دکمه‌های سریع
    if data.startswith("quick_profile_"):
        username = data.split("_")[2]
        await query.message.delete()
        await profile_command(update, context, username=username)
        return
    
    elif data.startswith("quick_reels_"):
        username = data.split("_")[2]
        await query.message.delete()
        await reels_command(update, context, username=username)
        return
    
    elif data.startswith("quick_highlights_"):
        username = data.split("_")[2]
        await query.message.delete()
        await highlights_command(update, context, username=username)
        return

    elif data.startswith("quick_stories_"):
        username = data.split("_")[2]
        await query.message.delete()
        await stories_command(update, context, username=username)
        return
    
    # دکمه‌های منو
    elif data == "show_profile_menu":
        await query.edit_message_text(
            "👤 <b>پروفایل</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>",
            parse_mode='HTML'
        )
        return
    
    elif data == "show_reels_menu":
        await query.edit_message_text(
            "🎬 <b>ریلز</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>",
            parse_mode='HTML'
        )
        return
    
    elif data == "show_highlights_menu":
        await query.edit_message_text(
            "📚 <b>هایلایت</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>",
            parse_mode='HTML'
        )
        return

    elif data == "show_stories_menu":
        await query.edit_message_text(
            "📖 <b>استوری</b>\n\nلطفاً یوزرنیم رو با @ وارد کن:\nمثال: <code>@cristiano</code>",
            parse_mode='HTML'
        )
        return
    
    elif data.startswith("reel_"):
        await handle_reel_callbacks(update, context)
        return
    
    elif data.startswith("hl_"):
        await handle_highlight_callback(update, context)
        return
    
    elif data == "new_download":
        await query.edit_message_text("📎 لطفاً لینک اینستاگرام خود را ارسال کنید:")
    
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
        await start(update, context)


# ========== دستورات ادمین ==========

async def clear_cache_command(update: Update, context):
    """پاک کردن کش (فقط برای ادمین)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ شما دسترسی به این دستور ندارید.")
        return
    
    if not redis_client:
        await update.message.reply_text("❌ Redis در دسترس نیست.")
        return
    
    processing = await update.message.reply_text("🔄 در حال پاک کردن کش...")
    
    keys = redis_client.keys("cache:*")
    count = len(keys)
    
    for key in keys:
        redis_client.delete(key)
    
    file_keys = redis_client.keys("file_index:*")
    file_count = len(file_keys)
    for key in file_keys:
        redis_client.delete(key)
    
    await processing.edit_text(f"✅ {count} آیتم کش و {file_count} ایندکس فایل پاک شد.")


# ========== تابع اصلی ==========

def main():
    app = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()
    
    # دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("highlights", highlights_command))
    app.add_handler(CommandHandler("reels", reels_command))
    app.add_handler(CommandHandler("stories", stories_command))
    app.add_handler(CommandHandler("clearcache", clear_cache_command))
    
    # هندلرها
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_direct_input))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(InlineQueryHandler(inline_query))
    
    logger.info("🤖 ربات در حال اجراست...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    main()
