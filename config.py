# config.py
import os

# توکن‌ها از environment variables خونده میشن — هیچ‌وقت توی کد ننویس!
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
TIKTOK_RAPIDAPI_KEY = os.environ.get("TIKTOK_RAPIDAPI_KEY")
RAPIDAPI_HOST = "instagram120.p.rapidapi.com"
RAPIDAPI_HOST_TIKTOK = "tiktok-api23.p.rapidapi.com"

if not BOT_TOKEN:
    raise ValueError("❌ متغیر BOT_TOKEN تنظیم نشده!")
if not RAPIDAPI_KEY:
    raise ValueError("❌ متغیر RAPIDAPI_KEY تنظیم نشده!")
