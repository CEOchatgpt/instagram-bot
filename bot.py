# bot.py

import logging  # کتابخونه‌ی استاندارد پایتون برای ثبت لاگ (پیام‌های خطا و اطلاعاتی)

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


# هندلر دستور /start — وقتی کاربر ربات رو شروع میکنه اجرا میشه
async def start(update: Update, context):
    await update.message.reply_text(
        "🎬 سلام! لینک پست اینستاگرام رو بفرست تا برات بفرستم."
    )


# هندلر اصلی — هر بار که کاربر یه متن (غیر از دستور) بفرسته اجرا میشه
async def handle_link(update: Update, context):
    url = update.message.text.strip()  # متن پیام رو میگیره و فاصله‌های اضافه رو حذف میکنه

    # چک میکنه لینک واقعاً اینستاگرام باشه
    if "instagram.com" not in url:
        await update.message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return  # اگه اینستاگرام نبود، ادامه نمیده

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

    # هندلر پیام‌های متنی (غیر از دستورات) رو ثبت میکنه
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("🚀 ربات روشن شد...")

    # ربات رو شروع میکنه و منتظر پیام میمونه (polling = هر چند ثانیه از تلگرام میپرسه پیام جدید داری؟)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# اگه این فایل مستقیم اجرا بشه (نه import بشه)، تابع main رو اجرا میکنه
if __name__ == '__main__':
    main()
