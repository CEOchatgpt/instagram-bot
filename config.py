# config.py
import os

# توکن‌ها از environment variables خونده میشن
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
RAPIDAPI_HOST = "instagram120.p.rapidapi.com"

# آیدی ادمین (از متغیر محیطی میخونیم)
ADMIN_ID = os.environ.get("ADMIN_ID")

# اگه ADMIN_ID عددی نیست، تبدیلش کن به int
if ADMIN_ID:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        print("⚠️ هشدار: ADMIN_ID باید عدد باشد!")
        ADMIN_ID = None

if not BOT_TOKEN:
    raise ValueError("❌ متغیر BOT_TOKEN تنظیم نشده!")
if not RAPIDAPI_KEY:
    raise ValueError("❌ متغیر RAPIDAPI_KEY تنظیم نشده!")
if not ADMIN_ID:
    print("⚠️ هشدار: متغیر ADMIN_ID تنظیم نشده! دستورات ادمین کار نخواهند کرد.")


# کانال دیتابیس (برای ذخیره دائمی لینک‌ها)
DATABASE_CHANNEL_ID = os.environ.get("DATABASE_CHANNEL_ID")  # مثال: -1001234567890

if not DATABASE_CHANNEL_ID:
    print("⚠️ هشدار: DATABASE_CHANNEL_ID تنظیم نشده! کش دائمی غیرفعال است.")


PROFILE_CHANNEL_ID = os.environ.get("PROFILE_CHANNEL_ID")      # برای پروفایل
MEDIA_CHANNEL_ID = os.environ.get("MEDIA_CHANNEL_ID")          # برای مدیا (پست، ریل، استوری، هایلایت)
REELS_LIST_CHANNEL_ID = os.environ.get("REELS_LIST_CHANNEL_ID") # برای لیست ریل‌ها
HIGHLIGHTS_LIST_CHANNEL_ID = os.environ.get("HIGHLIGHTS_LIST_CHANNEL_ID") # برای لیست هایلایت‌ها
USER_SETTING_CHANNEL_ID = os.environ.get("USER_SETTING_CHANNEL_ID") # برای تنظیمات کاربر
