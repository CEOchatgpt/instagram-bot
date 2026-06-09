# bot.py
import logging
import os
from telegram import Update, InputMediaVideo, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from config import BOT_TOKEN
from rapidapi_service import get_instagram_media

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def start(update: Update, context):
    await update.message.reply_text(
        "🎬 سلام! لینک پست اینستاگرام رو بفرست تا برات بفرستم."
    )


async def handle_link(update: Update, context):
    url = update.message.text.strip()

    if "instagram.com" not in url:
        await update.message.reply_text("❌ فقط لینک اینستاگرام قبول میکنم!")
        return

    processing_msg = await update.message.reply_text("🔄 در حال پردازش...")

    try:
        media_items = get_instagram_media(url)

        if not media_items:
            await processing_msg.edit_text("❌ نتونستم محتوا رو پیدا کنم. مطمئن شو پست عمومیه.")
            return

        await processing_msg.edit_text("📤 در حال ارسال...")

        # اگه فقط یه آیتم داریم
        if len(media_items) == 1:
            item = media_items[0]
            if item["type"] == "video":
                await update.message.reply_video(
                    video=item["url"],
                    supports_streaming=True,
                    caption="✅"
                )
            else:
                await update.message.reply_photo(
                    photo=item["url"],
                    caption="✅"
                )

        # اگه چند آیتم داریم (کاروسل) — media group میفرستیم
        else:
            media_group = []
            for i, item in enumerate(media_items):
                caption = "✅" if i == 0 else None
                if item["type"] == "video":
                    media_group.append(InputMediaVideo(media=item["url"], caption=caption))
                else:
                    media_group.append(InputMediaPhoto(media=item["url"], caption=caption))

            # تلگرام حداکثر ۱۰ تا در یه گروه قبول میکنه
            for i in range(0, len(media_group), 10):
                await update.message.reply_media_group(media=media_group[i:i+10])

        await processing_msg.delete()

    except Exception as e:
        logger.error(f"Error: {e}")
        await processing_msg.edit_text(f"❌ خطایی رخ داد: {str(e)}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))

    print("🚀 ربات روشن شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
