# bot.py

import logging  # کتابخونه‌ی استاندارد پایتون برای ثبت لاگ (پیام‌های خطا و اطلاعاتی)
import time     # برای گرفتن زمان فعلی و محاسبه فاصله بین درخواست‌ها
from collections import defaultdict  # دیکشنری با مقدار پیش‌فرض — برای ساختن تاریخچه هر کاربر

from telegram import Update, InputMediaVideo, InputMediaPhoto  # کلاس‌های اصلی تلگرام
from telegram.ext import Application, CommandHandler, MessageHandler, filters  # ابزارهای ساخت ربات

from config import BOT_TOKEN  # توکن ربات از فایل تنظیمات
from rapidapi_service import get_instagram_media  # تابعی که مدیای اینستاگرام رو میگیره

# تنظیم فرمت لاگ‌ها: زمان - نام ماژول - سطح خطا - پیام
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO  # فقط پیام‌های INFO به بالا رو نشون بده
)
logger = logging.getLogger(__name__)  # یه logger مخصوص این فایل میسازه

# ── تنظیمات Rate Limiting ──────────────────────────────────────────────────
RATE_LIMIT  = 3   # هر کاربر حداکثر این تعداد درخواست میتونه توی پنجره زمانی بده
WINDOW_SECS = 60  # پنجره زمانی به ثانیه — بعد از این مدت، شمارنده ریست میشه

# دیکشنری که برای هر user_id یه لیست از زمان‌های درخواست نگه میداره
# defaultdict(list) یعنی اگه کاربر جدید بود، خودش لیست خالی میسازه
user_requests: dict[int, list[float]] = defaultdict(list)
# ──────────────────────────────────────────────────────────────────────────


def is_rate_limited(user_id: int) -> tuple[bool, int]:
    """
    چک میکنه آیا کاربر به حد مجاز رسیده یا نه.
    خروجی: (آیا محدود شده؟, چند ثانیه باید صبر کنه)
    """
    now = time.time()  # زمان فعلی به ثانیه (عدد اعشاری مثل 1718000000.45)

    # فقط درخواست‌هایی که توی پنجره زمانی هستن رو نگه میداره، قدیمی‌ترها رو حذف میکنه
    user_requests[user_id] = [
        t for t in user_requests[user_id]
        if now - t < WINDOW_SECS  # اگه کمتر از WINDOW_SECS ثانیه پیش بود، نگهش میداره
    ]

    # چک میکنه تعداد درخواست‌های باقیمونده به حد مجاز رسیده یا نه
    if len(user_requests[user_id]) >= RATE_LIMIT:
        # قدیمی‌ترین درخواست رو پیدا میکنه و حساب میکنه چقدر باید صبر کنه
        oldest = user_requests[user_id][0]
        wait_secs = int(WINDOW_SECS - (now - oldest)) + 1  # +1 برای اطمینان
        return True, wait_secs  # محدود شده

    # محدود نشده — زمان این درخواست رو به تاریخچه اضافه میکنه
    user_requests[user_id].append(now)
    return False, 0  # آزاده


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
        return  # اگه اینستاگرام نبود، ادامه نمیده

    # ── بررسی Rate Limit ──────────────────────────────────────────────────
    limited, wait = is_rate_limited(user_id)
    if limited:
        # به کاربر میگه چقدر باید صبر کنه
        await update.message.reply_text(
            f"⏳ زیادی سریع! {wait} ثانیه دیگه امتحان کن."
        )
        return  # بدون پردازش برمیگرده
    # ──────────────────────────────────────────────────────────────────────

    # یه پیام "در حال پردازش" میفرسته تا کاربر بدونه داره کار میکنه
    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")

    try:
        # تابع async رو صدا میزنه و منتظر جواب میمونه (بدون block کردن بقیه)
        result = await get_instagram_media(url)

        # اگه نتیجه‌ای نبود (پست خصوصی یا لینک اشتباه)
        if not result:
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم. مطمئن شو پست عمومیه.")
            return

        caption = result["caption"]  # کپشن آماده‌شده رو از نتیجه میگیره
        items = result["items"]      # لیست مدیاها (عکس‌ها و ویدیوها) رو از نتیجه میگیره

        # پیام وضعیت رو آپدیت میکنه
        await processing_msg.edit_text("📤 در حال ارسال...")

        if len(items) == 1:
            # فقط یه مدیا داریم (پست معمولی)
            item = items[0]
            if item["type"] == "video":
                # ویدیو رو با کپشن میفرسته، supports_streaming یعنی قبل از دانلود کامل پخش بشه
                await update.message.reply_video(
                    video=item["url"],
                    supports_streaming=True,
                    caption=caption
                )
            else:
                # عکس رو با کپشن میفرسته
                await update.message.reply_photo(
                    photo=item["url"],
                    caption=caption
                )
        else:
            # چند مدیا داریم (پست کاروسل)
            media_group = []  # لیست آبجکت‌های مدیا برای ارسال گروهی

            # روی همه مدیاها حلقه میزنه، i شماره‌ی آیتم هست
            for i, item in enumerate(items):
                c = caption if i == 0 else None  # کپشن فقط روی اولین آیتم گذاشته میشه

                if item["type"] == "video":
                    media_group.append(InputMediaVideo(media=item["url"], caption=c))
                else:
                    media_group.append(InputMediaPhoto(media=item["url"], caption=c))

            # تلگرام حداکثر ۱۰ مدیا در یه گروه قبول میکنه، پس هر ۱۰ تا رو جداگانه میفرسته
            for i in range(0, len(media_group), 10):
                await update.message.reply_media_group(media=media_group[i:i+10])

        await processing_msg.delete()  # پیام "در حال ارسال..." رو حذف میکنه

    except Exception as e:
        logger.error(f"Error: {e}")  # خطا رو در لاگ ثبت میکنه
        await processing_msg.edit_text(f"❌ خطایی رخ داد: {str(e)}")  # به کاربر نشون میده


def main():
    # اپلیکیشن ربات رو با توکن میسازه
    app = Application.builder().token(BOT_TOKEN).build()

    # هندلر دستور /start رو ثبت میکنه
    app.add_handler(CommandHandler("start", start))

    # هندلر دستور /help رو ثبت میکنه
    app.add_handler(CommandHandler("help", help_command))

    # هندلر پیام‌های متنی (غیر از دستورات) رو ثبت میکنه
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("🚀 ربات روشن شد...")

    # ربات رو شروع میکنه و منتظر پیام میمونه (polling = هر چند ثانیه از تلگرام میپرسه پیام جدید داری؟)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# اگه این فایل مستقیم اجرا بشه (نه import بشه)، تابع main رو اجرا میکنه
if __name__ == '__main__':
    main()
