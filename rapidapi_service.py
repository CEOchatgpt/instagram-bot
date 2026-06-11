# rapidapi_service.py - نسخه دیباگ کامل

import re
import aiohttp
import asyncio
import json
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

    # ========== دیباگ: چاپ کامل پاسخ برای یک پست کاروسل ==========
    print("\n" + "="*60)
    print("📦 پاسخ کامل API (برای کاروسل):")
    print("="*60)
    # فقط 3000 کاراکتر اول رو چاپ میکنیم تا خیلی طولانی نشه
    print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])
    print("="*60 + "\n")
    # ============================================================

    raw_caption = data[0].get("meta", {}).get("title", "")
    caption = format_caption(raw_caption)

    items = []

    for idx, item in enumerate(data):
        print(f"\n--- آیتم {idx + 1} ---")
        print(f"کلیدهای موجود: {list(item.keys())}")
        
        # چاپ همه فیلدهای مهم
        if "pictureUrl" in item:
            print(f"pictureUrl: {item['pictureUrl'][:100]}...")
        if "urls" in item:
            print(f"urls: {item['urls']}")
        if "media_type" in item:
            print(f"media_type: {item['media_type']}")
        if "type" in item:
            print(f"type: {item['type']}")
        if "__typename" in item:
            print(f"__typename: {item['__typename']}")
        
        urls = item.get("urls", [])
        picture_url = item.get("pictureUrl")
        
        # تشخیص بر اساس فیلدهای موجود
        if urls:
            best = max(urls, key=lambda x: x.get("quality", 0))
            items.append({"type": "video", "url": best["url"]})
            print("✅ تشخیص: ویدیو (بر اساس urls)")
        elif picture_url:
            # اینجا باید بررسی کنیم که picture_url واقعاً به عکس اشاره داره یا ویدیو
            # بعضی APIها برای ویدیو هم pictureUrl می‌دهند (thumbnail)
            items.append({"type": "photo", "url": picture_url})
            print("✅ تشخیص: عکس (بر اساس pictureUrl)")
        else:
            print("⚠️ هیچ مدیایی پیدا نشد")

    print(f"\n📊 نتیجه نهایی: {len(items)} مدیا")
    for i, item in enumerate(items):
        print(f"  - {i+1}: {item['type']}")
    print("="*60)

    return {"caption": caption, "items": items} if items else None
