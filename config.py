import os
import sys

# ====================== توکن‌ها و کلیدهای API ======================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# کلیدهای جداگانه (هر سرویس کلید خودش رو داره)
RAPIDAPI_KEY_INSTAGRAM = os.environ.get("RAPIDAPI_KEY_INSTAGRAM", "").strip()
RAPIDAPI_KEY_TIKTOK = os.environ.get("RAPIDAPI_KEY_TIKTOK", "").strip()
RAPIDAPI_KEY_YOUTUBE = os.environ.get("RAPIDAPI_KEY_YOUTUBE", "").strip()

# اگر یکی از کلیدها خالی بود، از RAPIDAPI_KEY اصلی استفاده کن (fallback)
if not RAPIDAPI_KEY_INSTAGRAM:
    RAPIDAPI_KEY_INSTAGRAM = os.environ.get("RAPIDAPI_KEY", "").strip()
if not RAPIDAPI_KEY_TIKTOK:
    RAPIDAPI_KEY_TIKTOK = os.environ.get("RAPIDAPI_KEY", "").strip()
if not RAPIDAPI_KEY_YOUTUBE:
    RAPIDAPI_KEY_YOUTUBE = os.environ.get("RAPIDAPI_KEY", "").strip()

# ====================== هاست‌های RapidAPI ======================

RAPIDAPI_HOST_INSTAGRAM = "instagram120.p.rapidapi.com"
RAPIDAPI_HOST_TIKTOK = "tiktok-api23.p.rapidapi.com"
RAPIDAPI_HOST_YOUTUBE = "youtube138.p.rapidapi.com"   # ← تغییر به API جدید

# ====================== Rate Limiting ======================

RATE_LIMIT = int(os.environ.get("RATE_LIMIT", 5))
WINDOW_SECS = int(os.environ.get("WINDOW_SECS", 60))

# ====================== اعتبارسنجی ======================

def validate_config():
    errors = []

    if not BOT_TOKEN:
        errors.append("❌ BOT_TOKEN تنظیم نشده!")

    if not RAPIDAPI_KEY_INSTAGRAM:
        errors.append("⚠️ RAPIDAPI_KEY_INSTAGRAM تنظیم نشده!")
    if not RAPIDAPI_KEY_TIKTOK:
        errors.append("⚠️ RAPIDAPI_KEY_TIKTOK تنظیم نشده!")
    if not RAPIDAPI_KEY_YOUTUBE:
        errors.append("⚠️ RAPIDAPI_KEY_YOUTUBE تنظیم نشده!")

