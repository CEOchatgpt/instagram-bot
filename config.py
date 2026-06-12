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
