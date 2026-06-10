# bot.py

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
    await update.message.reply_text(
        "🎬 سلام! لینک پست اینستاگرام رو بفرست تا برات بفرستم.\n\n"
        f"⚠️ محدودیت: هر {WINDOW_SECS} ثانیه، {RATE_LIMIT} درخواست"
    )


# هندلر دستور /help — راهنمای کامل ربات رو نشون میده
async def help_command(update: Update, context):
    await update.message.reply_text(
        "📖 راهنمای ربات\n\n"
        "🔹 نحوه استفاده:\n"
        "  لینک هر پست عمومی اینستاگرام رو بفرست\n"
        "  ربات عکس یا ویدیوش رو برات میفرسته\n\n"
        "🔹 انواع پست‌های پشتیبانی‌شده:\n"
        "  • پست تک عکس / تک ویدیو\n"
        "  • پست کاروسل (چند عکس/ویدیو)\n"
        "  • ریلز\n\n"
        "🔹 محدودیت‌ها:\n"
        f"  • حداکثر {RATE_LIMIT} درخواست در {WINDOW_SECS} ثانیه\n"
        "  • فقط پست‌های عمومی قابل دانلودن\n\n"
        "🔹 دستورات:\n"
        "  /start — شروع ربات\n"
        "  /help  — نمایش همین راهنما\n\n"
        "⚡ ساخته‌شده با Python & python-telegram-bot"
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
        await update.message.reply_text(f"⏳ زیادی سریع! {wait} ثانیه دیگه امتحان کن.")
        return

    # یه پیام "در حال پردازش" میفرسته تا کاربر بدونه داره کار میکنه
    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")

    try:
        # تابع async رو صدا میزنه و منتظر جواب میمونه
        result = await get_instagram_media(url)

        if not result:
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم. مطمئن شو پست عمومیه.")
            return

        # نتیجه رو توی user_data ذخیره میکنیم تا بعد از انتخاب کاربر بهش دسترسی داشته باشیم
        # user_data یه دیکشنری مخصوص هر کاربره که تلگرام برامون نگهش میداره
        context.user_data["pending_result"] = result

        await processing_msg.delete()  # پیام "در حال پردازش" رو حذف میکنه

        # دو دکمه inline میسازه — کاربر یکی رو انتخاب میکنه
        # callback_data مقداریه که وقتی کاربر دکمه رو میزنه به ربات برمیگرده
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📷 عکس معمولی", callback_data="send_photo"),
                InlineKeyboardButton("📁 فایل", callback_data="send_file"),
            ]
        ])
        await update.message.reply_text(
    "✨ نوع ارسال را انتخاب کن\n\n"
    "📷 عکس معمولی\n"
    "• نمایش مستقیم داخل تلگرام\n\n"
    "📁 فایل\n"
    "• کیفیت اصلی بدون فشرده سازی",
    reply_markup=keyboard
)

    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.edit_text(f"❌ خطایی رخ داد: {str(e)}")

# ─────────────────────────────────────────────────────────────
# دانلود فایل از URL
# علت:
# بعضی URL های اینستاگرام وقتی مستقیم به تلگرام داده میشن،
# تلگرام اونها رو به صورت Document تشخیص میده.
# با دانلود فایل و ارسال مستقیم، عکس حتماً به صورت Photo ارسال میشه.
# ─────────────────────────────────────────────────────────────
async def download_media(url: str, filename: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()

            data = await response.read()

            file_obj = BytesIO(data)
            file_obj.name = filename

            return file_obj
            
# هندلر کلیک دکمه — وقتی کاربر روی "عکس معمولی" یا "فایل" کلیک میکنه اجرا میشه
async def handle_format_choice(update: Update, context):
    query = update.callback_query  # اطلاعات کلیک رو میگیره
    await query.answer()  # به تلگرام میگه دکمه دریافت شد (حالت loading دکمه رو برمیداره)

    # انتخاب کاربر رو میخونه: "send_photo" یا "send_file"
    as_file = (query.data == "send_file")

    # نتیجه‌ای که قبلاً توی handle_link ذخیره کرده بودیم رو میخونه
    result = context.user_data.get("pending_result")
    if not result:
        # اگه ربات ریستارت شده باشه، user_data پاک میشه
        await query.edit_message_text("❌ اطلاعات منقضی شده. لینک رو دوباره بفرست.")
        return

    caption = result["caption"]  # کپشن آماده‌شده
    items = result["items"]      # لیست مدیاها

    await query.delete_message()  # پیام "به چه صورت بفرستم؟" رو حذف میکنه

    # یه پیام وضعیت جدید میفرسته
    sending_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📤 در حال ارسال..."
    )

    try:
        if len(items) == 1:
            item = items[0]

            if item["type"] == "video":
                # ویدیو همیشه به صورت ویدیو فرستاده میشه
                # اگه کاربر "فایل" انتخاب کرده، supports_streaming غیرفعاله
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=item["url"],
                    supports_streaming=not as_file,
                    caption=caption
                )
            elif as_file:
                # عکس به صورت فایل — تلگرام فشرده‌سازی نمیکنه، کیفیت اصلی حفظ میشه
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=item["url"],
                    caption=caption
                )
            else:
                # عکس معمولی — تلگرام نمایش میده ولی ممکنه کیفیت رو کمی کاهش بده
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=item["url"],
                    caption=caption
                )

       else:
    # ─────────────────────────────────────────────────────────
    # ارسال کاروسل
    # ─────────────────────────────────────────────────────────
    media_group = []

    for i, item in enumerate(items):

        # کپشن فقط روی اولین آیتم نمایش داده میشه
        c = caption if i == 0 else None

        if item["type"] == "video":

            # ویدیوها رو مستقیم اضافه میکنیم
            media_group.append(
                InputMediaVideo(
                    media=item["url"],
                    caption=c
                )
            )

        elif as_file:

            # ─────────────────────────────────────────────
            # حالت فایل:
            # عکس بدون فشرده سازی ارسال میشه
            # ─────────────────────────────────────────────
            media_group.append(
                InputMediaDocument(
                    media=item["url"],
                    caption=c
                )
            )

        else:

            # ─────────────────────────────────────────────
            # حالت عکس معمولی:
            # اول دانلود میکنیم تا تلگرام مطمئن بشه Photo هست
            # و به Document تبدیلش نکنه
            # ─────────────────────────────────────────────

            photo_file = await download_media(
                item["url"],
                f"photo_{i}.jpg"
            )

            media_group.append(
                InputMediaPhoto(
                    media=photo_file,
                    caption=c
                )
            )

    # تلگرام حداکثر ۱۰ آیتم در هر آلبوم قبول میکنه
    for i in range(0, len(media_group), 10):

        await context.bot.send_media_group(
            chat_id=update.effective_chat.id,
            media=media_group[i:i + 10]
        )

        await sending_msg.delete()  # پیام "در حال ارسال..." رو حذف میکنه

        # بعد از ارسال موفق، داده رو از user_data پاک میکنه تا حافظه اشغال نشه
        context.user_data.pop("pending_result", None)

    except Exception as e:
        logger.error(f"Error sending media: {e}")
        await sending_msg.edit_text(f"❌ خطا در ارسال: {str(e)}")


def main():
    # اپلیکیشن ربات رو با توکن میسازه
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))         # هندلر /start
    app.add_handler(CommandHandler("help", help_command))   # هندلر /help
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))  # هندلر لینک‌ها

    # هندلر کلیک روی دکمه‌های inline رو ثبت میکنه
    app.add_handler(CallbackQueryHandler(handle_format_choice))

    print("🚀 ربات روشن شد...")
    # ربات رو شروع میکنه و منتظر پیام میمونه
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# اگه این فایل مستقیم اجرا بشه (نه import بشه)، تابع main رو اجرا میکنه
if __name__ == '__main__':
    main()
