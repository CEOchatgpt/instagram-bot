# rapidapi_service.py - نسخه بهبود یافته برای استوری

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


async def get_instagram_story(username: str, story_id: str = None):
    """دریافت استوری با پرینت کامل برای دیباگ"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            if story_id:
                url = f"https://{RAPIDAPI_HOST}/api/instagram/story"
                payload = {"username": username, "storyId": story_id}
            else:
                url = f"https://{RAPIDAPI_HOST}/api/instagram/stories"
                payload = {"username": username}

            async with session.post(url, json=payload, headers=headers, timeout=25) as resp:
                resp.raise_for_status()
                data = await resp.json()

                print(f"\n🔍 پاسخ کامل API استوری برای @{username}:")
                print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])  # ۲۰۰۰ کاراکتر اول

                items = []

                # تلاش برای پیدا کردن لینک‌ها در ساختارهای مختلف
                if isinstance(data, dict):
                    # مسیرهای رایج
                    candidates = [
                        data.get("items"),
                        data.get("stories"),
                        data.get("story"),
                        data.get("data"),
                        [data]  # اگر خودش یک آیتم باشه
                    ]

                    for candidate in candidates:
                        if not candidate:
                            continue
                        if not isinstance(candidate, list):
                            candidate = [candidate]

                        for item in candidate:
                            if not isinstance(item, dict):
                                continue

                            # پیدا کردن ویدیو
                            video_url = None
                            if item.get("video_url"):
                                video_url = item.get("video_url")
                            elif item.get("video_versions"):
                                video_url = item.get("video_versions", [{}])[0].get("url")
                            elif item.get("video"):
                                video_url = item.get("video")

                            if video_url:
                                items.append({"type": "video", "url": video_url})
                                continue

                            # پیدا کردن عکس
                            image_url = None
                            if item.get("image_url"):
                                image_url = item.get("image_url")
                            elif item.get("image_versions"):
                                image_url = item.get("image_versions", [{}])[0].get("url")
                            elif item.get("image"):
                                image_url = item.get("image")

                            if image_url:
                                items.append({"type": "photo", "url": image_url})

                if items:
                    print(f"✅ {len(items)} آیتم استوری پیدا شد")
                    return {"caption": f"📖 استوری @{username}", "items": items}
                else:
                    print("⚠️ هیچ آیتمی پیدا نشد - داده خام برگردانده می‌شود")
                    return {"caption": f"📖 استوری @{username}", "items": [], "raw": data}

    except Exception as e:
        print(f"❌ خطا در دریافت استوری: {e}")
        return None


async def get_instagram_media(post_url: str) -> dict | None:
    if not post_url or "instagram.com" not in post_url:
        return None

    # تشخیص استوری
    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        username = story_match.group(1)
        story_id = story_match.group(2)
        print(f"📖 لینک استوری تشخیص داده شد → @{username} (ID: {story_id})")
        return await get_instagram_story(username, story_id)

    # === بخش پست/ریلز قبلی (بدون تغییر) ===
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
                    api_url, json={"url": post_url}, headers=headers, timeout=15
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
            break
        except Exception as e:
            print(f"⚠️ تلاش {attempt} ناموفق: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * (2 ** (attempt - 1)))

    if not isinstance(data, list) or not data:
        return None

    raw_caption = data[0].get("meta", {}).get("title", "")
    caption = format_caption(raw_caption)
    items = []

    for item in data:
        urls = item.get("urls", [])
        if not urls:
            continue
        best = max(urls, key=lambda x: x.get("quality", 0))
        extension = urls[0].get("extension", "").lower()

        if extension == "mp4":
            items.append({"type": "video", "url": best["url"]})
        else:
            items.append({"type": "photo", "url": best["url"]})

    return {"caption": caption, "items": items} if items else None
