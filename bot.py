# bot.py
import logging
import os
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN
from rapidapi_service import get_instagram_video_url

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context):
    await update.message.reply_text(
        "🎬 سلام! لینک پست اینستاگرام رو بفرست تا ویدئوش رو برات بفرستم."
    )


async def handle_link(update: Update, context):
    url = update.message.text.strip()

    # فقط لینک‌های اینستاگرام قبول میکنیم
    if "instagram.com" not in url:
        await update.message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return

    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")

    try:
        # گرفتن لینک مستقیم ویدئو از RapidAPI
        video_url = get_instagram_video_url(url)

        if not video_url:
            await processing_msg.edit_text("❌ نتونستم ویدئو رو پیدا کنم. مطمئن شو پست عمومیه.")
            return

        await processing_msg.edit_text("📤 در حال ارسال ویدئو...")

        # ارسال ویدئو مستقیم از URL — بدون دانلود روی سرور!
        await update.message.reply_video(
            video=video_url,
            supports_streaming=True,
            caption="✅ اینجاست!"
        )

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error handling link: {e}")
        await processing_msg.edit_text(f"❌ خطایی رخ داد: {str(e)}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
