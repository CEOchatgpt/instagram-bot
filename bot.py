import aiohttp
from io import BytesIO
import logging  # کتابخونه‌ی استاندارد پایتون برای ثبت لاگ (پیام‌های خطا و اطلاعاتی)
import time     # برای گرفتن زمان فعلی و محاسبه فاصله بین درخواست‌ها
from collections import defaultdict  # دیکشنری با مقدار پیش‌فرض — برای ساختن تاریخچه هر کاربر

from telegram import (
    Update,
    InputMediaVideo,       # برای ارسال ویدیو توی گروه مدیا
    InputMediaPhoto,       # برای ارسال عکس توی گروه مدیا
    InputMediaDocument,    # برای ارسال فایل توی گروه مدیا (بدون فشرده‌سازی تلگرام)
    InlineKeyboardButton,  # یه دکمه‌ی کلیکی زیر پیام
    InlineKeyboardMarkup,  # ظرف دکمه‌ها — یه یا چند ردیف از دکمه‌ها
)
from telegram.ext import (
    Application,
    CommandHandler,      # هندلر دستوراتی مثل /start و /help
    MessageHandler,      # هندلر پیام‌های متنی معمولی
    CallbackQueryHandler, # هندلر کلیک روی دکمه‌های inline
    filters,
)

from config import BOT_TOKEN  # توکن ربات از فایل تنظیمات
from rapidapi_service import get_instagram_media  # تابعی که مدیای اینستاگرام رو میگیره

# تنظیم فرمت لاگ‌ها: زمان - نام ماژول - سطح خطا - پیام
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # فقط پیام‌های INFO به بالا رو نشون بده
)
logger = logging.getLogger(__name__)  # یه logger مخصوص این فایل میسازه

# ── تنظیمات Rate Limiting ───────────────────────────────────────────────────
RATE_LIMIT  = 3   # هر کاربر حداکثر این تعداد درخواست میتونه توی پنجره زمانی بده
WINDOW_SECS = 60  # پنجره زمانی به ثانیه — بعد از این مدت، شمارنده ریست میشه

# دیکشنری که برای هر user_id یه لیست از زمان‌های درخواست نگه میداره
user_requests: dict[int, list[float]] = defaultdict(list)
# ────────────────────────────────────────────────────────────────────────────


def is_rate_limited(user_id: int) -> tuple[bool, int]:
    """
    چک میکنه آیا کاربر به حد مجاز رسیده یا نه.
    خروجی: (آیا محدود شده؟, چند ثانیه باید صبر کنه)
    """
    now = time.time()  # زمان فعلی به ثانیه

    # فقط درخواست‌هایی که توی پنجره زمانی هستن رو نگه میداره، قدیمی‌ترها رو حذف میکنه
    user_requests[user_id] = [t for t in user_requests[user_id] if now - t < WINDOW_SECS]

    if len(user_requests[user_id]) >= RATE_LIMIT:
        # قدیمی‌ترین درخواست رو پیدا میکنه و حساب میکنه چقدر باید صبر کنه
        oldest = user_requests[user_id][0]
        wait_secs = int(WINDOW_SECS - (now - oldest)) + 1  # +1 برای اطمینان
        return True, wait_secs  # محدود شده

    # محدود نشده — زمان این درخواست رو به تاریخچه اضافه میکنه
    user_requests[user_id].append(now)
    return False, 0


# هندلر دستور /start — وقتی کاربر ربات رو شروع میکنه اجرا میشه
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


# هندلر دستور /help — راهنمای کامل ربات رو نشون میده
async def help_command(update: Update, context):
    await update.message.reply_text(
        "📖 <b>راهنمای ربات</b>\n\n"
        "🔹 فقط لینک اینستاگرام بفرست\n"
        "🔹 پست تک عکس/ویدیو، کاروسل، ریلز پشتیبانی میشه\n"
        "🔹 محدودیت: " + str(RATE_LIMIT) + f" درخواست هر {WINDOW_SECS} ثانیه\n\n"
        "⚡ ساخته شده با Python + python-telegram-bot",
        parse_mode='HTML'
    )


# هندلر اصلی — هر بار که کاربر یه متن (غیر از دستور) بفرسته اجرا میشه
async def handle_link(update: Update, context):
    url = update.message.text.strip()  # متن پیام رو میگیره و فاصله‌های اضافه رو حذف میکنه
    user_id = update.effective_user.id  # آیدی یکتای کاربر تلگرام رو میگیره

    # چک میکنه لینک واقعاً اینستاگرام باشه
    if "instagram.com" not in url:
        await update.message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return

    # بررسی rate limit — اگه کاربر زیادی سریع درخواست داده، رد میکنه
    limited, wait = is_rate_limited(user_id)
    if limited:
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه صبر کن.")
        return

    # یه پیام "در حال پردازش" میفرسته تا کاربر بدونه داره کار میکنه
    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")

    try:
        # تابع async رو صدا میزنه و منتظر جواب میمونه
        result = await get_instagram_media(url)

        if not result or not result.get("items"):
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم. پست باید عمومی باشه.")
            return

        # نتیجه رو توی user_data ذخیره میکنیم تا بعد از انتخاب کاربر بهش دسترسی داشته باشیم
        context.user_data["pending_result"] = result
        await processing_msg.delete()

        # ==================== تغییر مهم: تشخیص هوشمند نوع محتوا ====================
        items = result["items"]
        has_video = any(item["type"] == "video" for item in items)
        has_photo = any(item["type"] == "photo" for item in items)
        is_single = len(items) == 1

        # ساخت کیبورد و متن متفاوت بسته به عکس/ویدیو/کاروسل
        if is_single and has_video:
            text = "🎥 <b>ویدیو پیدا شد!</b>\n\nچطور برات بفرستم؟"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 ارسال ویدیو", callback_data="send_video")],
                [InlineKeyboardButton("📁 فایل (کیفیت اصلی)", callback_data="send_file")]
            ])
        elif is_single and has_photo:
            text = "📸 <b>عکس پیدا شد!</b>\n\nچطور برات بفرستم؟"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 عکس معمولی", callback_data="send_photo")],
                [InlineKeyboardButton("📁 فایل (کیفیت اصلی)", callback_data="send_file")]
            ])
        else:
            # کاروسل (چند رسانه‌ای)
            text = f"📚 <b>کاروسل پیدا شد!</b> ({len(items)} رسانه)\n\nچطور ارسال کنم؟"
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 عکس‌های معمولی", callback_data="send_photo")],
                [InlineKeyboardButton("📁 همه به صورت فایل", callback_data="send_file")]
            ])

        await update.message.reply_text(text, parse_mode='HTML', reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.edit_text("❌ خطایی رخ داد. دوباره امتحان کن.")


# ─────────────────────────────────────────────────────────────
# دانلود فایل از URL
# ─────────────────────────────────────────────────────────────
async def download_media(url: str, filename: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.read()
            file_obj = BytesIO(data)
            file_obj.name = filename
            return file_obj


# هندلر کلیک دکمه — وقتی کاربر روی دکمه‌ها کلیک میکنه اجرا میشه
async def handle_format_choice(update: Update, context):
    query = update.callback_query  # اطلاعات کلیک رو میگیره
    await query.answer()  # به تلگرام میگه دکمه دریافت شد

    choice = query.data
    result = context.user_data.get("pending_result")
    if not result:
        await query.edit_message_text("❌ اطلاعات منقضی شد. لینک رو دوباره بفرست.")
        return

    caption = result["caption"]  # کپشن آماده‌شده
    items = result["items"]      # لیست مدیاها

    await query.delete_message()  # پیام انتخاب رو حذف میکنه

    # یه پیام وضعیت جدید میفرسته
    sending_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📤 در حال ارسال..."
    )

    try:
        if len(items) == 1:
            item = items[0]

            # ==================== تغییر مهم: ارسال هوشمند بر اساس نوع ====================
            if item["type"] == "video":
                # ویدیو همیشه به صورت ویدیو فرستاده میشه (حتی اگر فایل انتخاب شده باشه)
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=item["url"],
                    supports_streaming=True,
                    caption=caption
                )
            elif choice == "send_photo":
                # عکس معمولی — نمایش مستقیم داخل چت
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=item["url"],
                    caption=caption
                )
            else:  # send_file
                # عکس/ویدیو به صورت فایل (کیفیت اصلی)
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    caption=caption
                )

        else:
            # ─────────────────────────────────────────────────────────
            # ارسال کاروسل (بیشتر از یک آیتم)
            # ─────────────────────────────────────────────────────────
            media_group = []
            for i, item in enumerate(items):
                c = caption if i == 0 else None

                if item["type"] == "video":
                    media_group.append(InputMediaVideo(media=item["url"], caption=c))
                elif choice == "send_photo":
                    # عکس معمولی
                    photo_file = await download_media(item["url"], f"photo_{i}.jpg")
                    media_group.append(InputMediaPhoto(media=photo_file, caption=c))
                else:
                    # به صورت فایل
                    media_group.append(InputMediaDocument(media=item["url"], caption=c))

            # ارسال آلبوم‌ها در دسته‌های ۱۰ تایی
            for i in range(0, len(media_group), 10):
                await context.bot.send_media_group(
                    chat_id=update.effective_chat.id,
                    media=media_group[i:i + 10]
                )

        await sending_msg.delete()

        # بعد از ارسال موفق، داده رو از user_data پاک میکنه
        context.user_data.pop("pending_result", None)

        # پیام موفقیت
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="✅ با موفقیت ارسال شد!\n\nلینک بعدی رو بفرست 🚀"
        )

    except Exception as e:
        logger.error(f"Error sending media: {e}")
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
