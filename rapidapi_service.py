import re
import aiohttp
from config import RAPIDAPI_KEY, RAPIDAPI_HOST

async def get_instagram_story(username: str, story_id: str = None):
    """دریافت استوری اینستاگرام"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            if story_id:
                # دریافت یک استوری خاص
                url = f"https://{RAPIDAPI_HOST}/api/instagram/story"
                payload = {"username": username, "storyId": story_id}
            else:
                # دریافت همه استوری‌های کاربر
                url = f"https://{RAPIDAPI_HOST}/api/instagram/stories"
                payload = {"username": username}

            async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
                resp.raise_for_status()
                data = await resp.json()

                print("📋 پاسخ API استوری:", data)  # برای دیباگ

                items = []

                # پردازش ساختار احتمالی پاسخ
                if isinstance(data, dict):
                    # بعضی APIها items دارند
                    story_items = data.get("items") or data.get("stories") or [data]
                    
                    for item in story_items:
                        if not isinstance(item, dict):
                            continue
                            
                        if item.get("video_url") or item.get("video_versions"):
                            video_url = item.get("video_url") or item.get("video_versions", [{}])[0].get("url")
                            if video_url:
                                items.append({"type": "video", "url": video_url})
                        elif item.get("image_url") or item.get("image_versions"):
                            image_url = item.get("image_url") or item.get("image_versions", [{}])[0].get("url")
                            if image_url:
                                items.append({"type": "photo", "url": image_url})

                if not items:
                    # اگر ساختار متفاوت بود، داده خام رو برگردون
                    return {"caption": f"📖 استوری @{username} (ساختار جدید)", "raw": data}

                caption = f"📖 استوری از @{username}"
                return {"caption": caption, "items": items}

    except Exception as e:
        print(f"❌ خطا در دریافت استوری: {e}")
        return None


async def get_instagram_media(post_url: str):
    """تابع اصلی دریافت پست، ریلز و استوری"""
    
    if not post_url or "instagram.com" not in post_url:
        return None

    # تشخیص لینک استوری
    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        username = story_match.group(1)
        story_id = story_match.group(2)
        print(f"📖 لینک استوری تشخیص داده شد → @{username} (ID: {story_id})")
        return await get_instagram_story(username, story_id)

    # تشخیص لینک‌های معمولی (پست / ریلز / کاروسل)
    # اینجا کد قبلی خودت رو بذار (تابع get_instagram_media قدیمی‌ت)
    # برای اینکه کامل باشه، یک نسخه ساده ازش می‌ذارم:

    try:
        headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/links"
            payload = {"url": post_url}

            async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
                resp.raise_for_status()
                data = await resp.json()

                print("📋 پاسخ API پست:", data)  # دیباگ

                # پردازش پاسخ پست (باید با کد قبلی‌ت تطبیق بدم)
                caption = data.get("caption", "📸 پست اینستاگرام")
                items = []

                if isinstance(data, dict) and "items" in data:
                    for item in data["items"]:
                        if item.get("video_url"):
                            items.append({"type": "video", "url": item["video_url"]})
                        elif item.get("image_url"):
                            items.append({"type": "photo", "url": item["image_url"]})

                return {"caption": caption, "items": items} if items else None

    except Exception as e:
        print(f"❌ خطا در دریافت پست: {e}")
        return None
