# config.py
import os
import sys

# ────────────────────────────────────────────────────────────
# بارگذاری متغیرهای محیطی (Environment Variables)
# ────────────────────────────────────────────────────────────

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "").strip()
TIKTOK_RAPIDAPI_KEY = os.environ.get("TIKTOK_RAPIDAPI_KEY", "").strip()

# ────────────────────────────────────────────────────────────
# API Hosts
# ────────────────────────────────────────────────────────────

RAPIDAPI_HOST = "instagram120.p.rapidapi.com"
RAPIDAPI_HOST_TIKTOK = "tiktok-api23.p.rapidapi.com"

# ────────────────────────────────────────────────────────────
# Rate Limiting (می‌تونی توی environment variable تغییر بدی)
# ────────────────────────────────────────────────────────────

RATE_LIMIT = int(os.environ.get("RATE_LIMIT", 3))
WINDOW_SECS = int(os.environ.get("WINDOW_SECS", 60))

# ────────────────────────────────────────────────────────────
# Validation (چک کردن اجباری توکن‌ها)
# ────────────────────────────────────────────────────────────

def validate_config():
    """تمام تنظیمات رو چک میکنه. اگه مشکل باشه، خطا میده"""
    errors = []
    
    if not BOT_TOKEN:
        errors.append("❌ متغیر BOT_TOKEN تنظیم نشده!")
    
    if not RAPIDAPI_KEY:
        errors.append("❌ متغیر RAPIDAPI_KEY تنظیم نشده!")
    
    if not TIKTOK_RAPIDAPI_KEY:
        errors.append("⚠️  متغیر TIKTOK_RAPIDAPI_KEY تنظیم نشده (TikTok کار نمیکنه!)")
    
    if RATE_LIMIT <= 0:
        errors.append("❌ RATE_LIMIT باید از ۰ بیشتر باشه!")
    
    if WINDOW_SECS <= 0:
        errors.append("❌ WINDOW_SECS باید از ۰ بیشتر باشه!")
    
    # خطاهای جدی رو print کن
    if errors:
        for error in errors:
            print(error)
        
        # اگه توکن‌های اصلی نباشن، بند کن
        if not BOT_TOKEN or not RAPIDAPI_KEY:
            print("\n❌ توکن‌های اجباری موجود نیستن. بند شدم.")
            sys.exit(1)
        else:
            print("\n⚠️  برخی توکن‌ها موجود نیستن — برخی ویژگی‌ها کار نمیکنند!")

# هنگام import این فایل، validation رو انجام بده
validate_config()

# ────────────────────────────────────────────────────────────
# Debug Info (اختیاری)
# ────────────────────────────────────────────────────────────

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

if DEBUG:
    print("🔧 DEBUG MODE ENABLED")
    print(f"  Rate Limit: {RATE_LIMIT} req / {WINDOW_SECS} sec")
    print(f"  BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
    print(f"  RAPIDAPI_KEY: {'✅' if RAPIDAPI_KEY else '❌'}")
    print(f"  TIKTOK_RAPIDAPI_KEY: {'✅' if TIKTOK_RAPIDAPI_KEY else '❌'}")
