# database.py - نسخه Redis
import os
import redis
import json

# گرفتن آدرس Redis از متغیر محیطی
REDIS_URL = os.environ.get("REDIS_URL")

if not REDIS_URL:
    print("⚠️ هشدار: REDIS_URL پیدا نشد! از دیتابیس موقتی استفاده میشه")
    # برای تست لوکال (بدون Redis)
    redis_client = None
else:
    redis_client = redis.from_url(REDIS_URL)
    print("✅ اتصال به Redis برقرار شد")

def get_user_mode(user_id: int) -> str:
    """دریافت حالت کاربر از Redis"""
    if not redis_client:
        return "album"  # Fallback برای لوکال
    
    key = f"user:{user_id}:mode"
    mode = redis_client.get(key)
    
    if mode:
        return mode.decode()
    return "album"

def set_user_mode(user_id: int, mode: str):
    """ذخیره حالت کاربر در Redis (برای 1 سال)"""
    if not redis_client:
        return
    
    if mode not in ["album", "file"]:
        return
    
    key = f"user:{user_id}:mode"
    # 365 روز = 31536000 ثانیه
    redis_client.setex(key, 31536000, mode)
    print(f"✅ حالت کاربر {user_id} به {mode} تغییر کرد")

def init_db():
    """آماده‌سازی دیتابیس (فقط لاگ میندازه)"""
    if redis_client:
        # تست اتصال
        try:
            redis_client.ping()
            print("✅ Redis آماده کار است")
        except:
            print("❌ خطا در اتصال به Redis")
    else:
        print("⚠️ Redis در دسترس نیست - از حافظه موقتی استفاده میشه")

# اجرای اولیه
init_db()
