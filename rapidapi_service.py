# rapidapi_service.py - نسخه نهایی با پشتیبانی کامل عکس و ویدیو استوری

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
    """دریافت استوری با پشتیبانی کامل ویدیو"""
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
                print(json.dumps(data, indent=2, ensure_ascii=False)[:3000])

                items = []

                stories = data.get("result") if isinstance(data, dict) else None
                
                if isinstance(stories, list):
                    for story in stories:
                        if not isinstance(story, dict):
                            continue

                        # === اولویت اول: ویدیو ===
                        video_found = False
                        
                        # مسیرهای مختلف ویدیو
                        video_versions = (
                            story.get("video_versions") or 
                            story.get("video") or
                            story.get("videos")
                        )
                        
                        if video_versions:
                            if isinstance(video_versions, list) and video_versions:
                                # بهترین کیفیت ویدیو
                                best_video = max(video_versions, key=lambda x: x.get("height", 0) or x.get("width", 0))
                                video_url = best_video.get("url")
                            else:
                                video_url = video_versions.get("url") if isinstance(video_versions, dict) else video_versions
                            
                            if video_url:
                                items.append({"type": "video", "url": video_url})
                                video_found = True

                        # === اگر ویدیو نبود، عکس ===
                        if not video_found:
                            image_versions = story.get("image_versions2", {}).get("candidates", [])
                            if image_versions:
                                best_image = max(image_versions, key=lambda x: x.get("height", 0))
                                items.append({
                                    "type": "photo",
                                    "url": best_image.get("url")
                                })

                if items:
                    video_count = sum(1 for i in items if i["type"] == "video")
                    photo_count = len(items) - video_count
                    print(f"✅ استخراج شد: {video_count} ویدیو + {photo_count} عکس")
                    return {
                        "caption": f"📖 استوری @{username}",
                        "items": items
                    }
                else:
                    print("⚠️ هیچ آیتمی پیدا نشد")
                    return {
                        "caption": f"📖 استوری @{username}",
                        "items": [],
                        "raw": data
                    }

    except Exception as e:
        print(f"❌ خطا در دریافت استوری: {e}")
        return None


async def get_instagram_media(post_url: str) -> dict | None:
    """تابع اصلی"""
    if not post_url or "instagram.com" not in post_url:
        return None

    # تشخیص استوری
    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        username = story_match.group(1)
        story_id = story_match.group(2)
        print(f"📖 لینک استوری تشخیص داده شد → @{username} (ID: {story_id})")
        return await get_instagram_story(username, story_id)

    # بخش پست/ریلز (بدون تغییر)
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
