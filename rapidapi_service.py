# rapidapi_service.py - نسخه اصلاح شده کامل

import re
import aiohttp
import asyncio
from config import RAPIDAPI_KEY, RAPIDAPI_HOST

MAX_RETRIES = 3
RETRY_DELAY = 1


def format_caption(raw: str) -> str:
    """تمیز کردن کپشن اینستاگرام"""
    text = re.sub(r'https?://\S+', '', raw)
    hashtags = re.findall(r'#\w+', text)
    text = re.sub(r'#\w+', '', text)
    text = text.strip()
    if not text:
        text = "بدون کپشن"
    hashtag_line = " ".join(hashtags)
    caption = "تق ✅\n\n" + text
    if hashtag_line:
        caption += f"\n\n{hashtag_line}"
    if len(caption) > 1024:
        cut = caption[:1020].rsplit(" ", 1)[0]
        caption = cut + " ..."
    return caption


async def get_instagram_media(post_url: str) -> dict | None:
    """دریافت مدیاهای اینستاگرام از API"""
    
    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/links"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json",
    }

    data = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    api_url,
                    json={"url": post_url},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
            break

        except aiohttp.ClientResponseError as e:
            if e.status < 500:
                print(f"❌ HTTP {e.status} از RapidAPI")
                return None
            print(f"⚠️ HTTP {e.status} — تلاش {attempt}/{MAX_RETRIES}")

        except (TimeoutError, aiohttp.ServerConnectionError):
            print(f"⏱ خطای اتصال — تلاش {attempt}/{MAX_RETRIES}")

        except Exception as e:
            print(f"❌ خطا: {e}")
            return None

        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
        else:
            print("❌ همه تلاش‌ها ناموفق بود")
            return None

    if not isinstance(data, list) or not data:
        return None

    # دریافت کپشن
    raw_caption = data[0].get("meta", {}).get("title", "")
    caption = format_caption(raw_caption)

    items = []

    for item in data:
        # روش اول: بررسی نوع مستقیم از فیلدهای API
        media_type = item.get("media_type") or item.get("type") or item.get("__typename", "")
        
        # تبدیل به string برای مقایسه راحت
        media_type_str = str(media_type).lower()
        
        # چک کردن ویدیو
        is_video = False
        is_photo = False
        
        # بررسی بر اساس media_type
        if media_type_str in ["video", "graphvideo", "2"]:
            is_video = True
        elif media_type_str in ["image", "graphimage", "1"]:
            is_photo = True
        
        # اگر media_type مشخص نبود، بر اساس وجود urls یا pictureUrl تشخیص بده
        urls = item.get("urls", [])
        picture_url = item.get("pictureUrl")
        
        if not is_video and not is_photo:
            if urls:
                is_video = True
            elif picture_url:
                is_photo = True
        
        # اضافه کردن به لیست items
        if is_video and urls:
            # انتخاب بهترین کیفیت ویدیو
            best = max(urls, key=lambda x: x.get("quality", 0))
            items.append({"type": "video", "url": best["url"]})
            print(f"✅ ویدیو اضافه شد - کیفیت: {best.get('quality', 'unknown')}")
            
        elif is_photo and picture_url:
            items.append({"type": "photo", "url": picture_url})
            print(f"✅ عکس اضافه شد")
            
        else:
            print(f"⚠️ آیتم ناشناس: {list(item.keys())}")

    # دیباگ: نمایش نتیجه نهایی
    print(f"\n📊 نتیجه نهایی: {len(items)} مدیا")
    for i, item in enumerate(items):
        print(f"  - {i+1}: {item['type']}")
    print("=" * 50)

    return {"caption": caption, "items": items} if items else None
