# config.py
import os

# توکن‌ها
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")
RAPIDAPI_HOST = "instagram120.p.rapidapi.com"

# ادمین
ADMIN_ID = os.environ.get("ADMIN_ID")
if ADMIN_ID:
    try:
        ADMIN_ID = int(ADMIN_ID)
    except ValueError:
        print("⚠️ هشدار: ADMIN_ID باید عدد باشد!")
        ADMIN_ID = None

# ========== کانال‌ها ==========
PROFILE_CHANNEL_ID = os.environ.get("PROFILE_CHANNEL_ID")      # پروفایل‌ها
POST_CHANNEL_ID = os.environ.get("POST_CHANNEL_ID")            # پست‌های معمولی
REEL_CHANNEL_ID = os.environ.get("REEL_CHANNEL_ID")            # ریل‌ها + لیست ریل‌ها
STORY_CHANNEL_ID = os.environ.get("STORY_CHANNEL_ID")          # استوری‌ها
HIGHLIGHT_CHANNEL_ID = os.environ.get("HIGHLIGHT_CHANNEL_ID")  # هایلایت‌ها + لیست هایلایت‌ها
USER_SETTING_CHANNEL_ID = os.environ.get("USER_SETTING_CHANNEL_ID")  # تنظیمات کاربر
INDEX_CHANNEL_ID = os.environ.get("INDEX_CHANNEL_ID")

# برای سازگاری با کد قدیمی (اختیاری)
MEDIA_CHANNEL_ID = POST_CHANNEL_ID

# چک کردن متغیرهای ضروری
if not BOT_TOKEN:
    raise ValueError("❌ متغیر BOT_TOKEN تنظیم نشده!")
if not RAPIDAPI_KEY:
    raise ValueError("❌ متغیر RAPIDAPI_KEY تنظیم نشده!")

print("🔧 تنظیمات کانال‌ها:")
print(f"  📝 PROFILE_CHANNEL_ID: {PROFILE_CHANNEL_ID}")
print(f"  📷 POST_CHANNEL_ID: {POST_CHANNEL_ID}")
print(f"  🎬 REEL_CHANNEL_ID (ریل + لیست): {REEL_CHANNEL_ID}")
print(f"  📖 STORY_CHANNEL_ID: {STORY_CHANNEL_ID}")
print(f"  📚 HIGHLIGHT_CHANNEL_ID (هایلایت + لیست): {HIGHLIGHT_CHANNEL_ID}")
print(f"  ⚙️ USER_SETTING_CHANNEL_ID: {USER_SETTING_CHANNEL_ID}")
