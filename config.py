import os
import sys

# ====================== تنظیمات اصلی ======================

# توکن ربات تلگرام
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# کلید RapidAPI (برای همه سرویس‌ها: Instagram + YouTube + ...)
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "").strip()

# تنظیمات Rate Limit
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", 5))      # تعداد درخواست مجاز
WINDOW_SECS = int(os.environ.get("WINDOW_SECS", 60))   # در هر چند ثانیه

# ====================== اعتبارسنجی ======================

def validate_config():
    errors = []

    if not BOT_TOKEN:
        errors.append("❌ BOT_TOKEN تنظیم نشده است!")

    if not RAPIDAPI_KEY:
        errors.append("⚠️ RAPIDAPI_KEY تنظیم نشده است! (دانلود از اینستاگرام و یوتیوب کار نمی‌کند)")

    if errors:
        print("\n".join(errors))
        print("\n💡 راهنما:")
        print("   • در محیط لوکال: فایل .env بساز یا متغیرها را export کن")
        print("   • در Heroku/Railway: در Settings > Config Vars اضافه کن")
        sys.exit(1)

    print("✅ تنظیمات config.py با موفقیت لود شد")


# اجرای اعتبارسنجی هنگام ایمپورت
validate_config()
