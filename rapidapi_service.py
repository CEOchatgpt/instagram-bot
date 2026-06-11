# rapidapi_service.py - نسخه نهایی (پست + استوری + پروفایل)

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


async def get_instagram_profile(username: str):
    """دریافت اطلاعات پروفایل اینستاگرام"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json",
    }

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/profile"
            payload = {"username": username}

            async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
                resp.raise_for_status()
                data = await resp.json()

                print(f"📊 پروفایل @{username} دریافت شد")

                if isinstance(data, dict) and "result" in data:
                    p = data["result"]
                    return {
                        "username": p.get("username"),
                        "full_name": p.get("full_name", username),
                        "biography": p.get("biography", "بدون بیو"),
                        "followers": p.get("follower_count", 0),
                        "following": p.get("following_count", 0),
                        "posts": p.get("media_count", 0),
                        "profile_pic": p.get("profile_pic_url_hd") or p.get("profile_pic_url"),
                        "is_verified": p.get("is_verified", False),
                        "is_private": p.get("is_private", False),
                        "external_url": p.get("external_url"),
                    }
                return None

    except Exception as e:
        print(f"❌ خطا در دریافت پروفایل: {e}")
        return None


async def get_instagram_story(username: str, story_id: str = None):
    """دریافت استوری"""
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

                items = []
                stories = data.get("result") if isinstance(data, dict) else None
                
                if isinstance(stories, list):
                    for story in stories:
                        if not isinstance(story, dict):
                            continue

                        video_versions = story.get("video_versions") or story.get("video")
                        if video_versions and isinstance(video_versions, list) and video_versions:
                            best_video = max(video_versions, key=lambda x: x.get("height", 0) or 0)
                            items.append({"type": "video", "url": best_video.get("url")})
                            continue

                        image_versions = story.get("image_versions2", {}).get("candidates", [])
                        if image_versions:
                            best_image = max(image_versions, key=lambda x: x.get("height", 0))
                            items.append({"type": "photo", "url": best_image.get("url")})

                return {
                    "caption": f"📖 استوری @{username}",
                    "items": items
                } if items else {"caption": f"📖 استوری @{username}", "items": []}

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
        print(f"📖 لینک استوری تشخیص داده شد → @{username}")
        return await get_instagram_story(username, story_id)

    # پست / ریلز / کاروسل
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
                async with session.post(api_url, json={"url": post_url}, headers=headers, timeout=15) as response:
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
