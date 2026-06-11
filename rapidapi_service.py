# rapidapi_service.py - نسخه نهایی و درست

import re
import aiohttp
import asyncio
from config import RAPIDAPI_KEY, RAPIDAPI_HOST

MAX_RETRIES = 3
RETRY_DELAY = 1


def format_caption(raw: str) -> str:
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
                print(f"❌ HTTP {e.status}")
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

    raw_caption = data[0].get("meta", {}).get("title", "")
    caption = format_caption(raw_caption)

    items = []

    for item in data:
        urls = item.get("urls", [])
        
        # تشخیص نوع فایل از روی extension
        is_video = False
        is_photo = False
        
        if urls:
            # نگاه کن ببین اولین url چه فرمتی داره
            first_url = urls[0]
            extension = first_url.get("extension", "").lower()
            
            if extension == "mp4":
                is_video = True
            elif extension in ["jpg", "jpeg", "png", "gif"]:
                is_photo = True
        
        # اگه نتونستیم از روی extension تشخیص بدیم، از روی کیفیت تشخیص بده
        if not is_video and not is_photo and urls:
            # ویدیوها معمولاً کیفیت‌های 480, 720, 1080 دارن
            # عکس‌ها کیفیت‌های 1080, 3024, 3088 دارن
            quality = urls[0].get("quality", 0)
            if quality <= 1080:
                # احتمالاً ویدیو - ولی باز هم مطمئن نیستیم
                # از روی name هم چک کن
                name = urls[0].get("name", "").upper()
                if name == "MP4":
                    is_video = True
                else:
                    is_photo = True
            else:
                is_photo = True
        
        # انتخاب بهترین کیفیت
        if urls:
            best = max(urls, key=lambda x: x.get("quality", 0))
            if is_video:
                items.append({"type": "video", "url": best["url"]})
                print(f"✅ ویدیو - کیفیت: {best.get('quality')}")
            else:
                items.append({"type": "photo", "url": best["url"]})
                print(f"✅ عکس - کیفیت: {best.get('quality')}")
        else:
            print(f"⚠️ آیتم بدون urls")

    return {"caption": caption, "items": items} if items else None
