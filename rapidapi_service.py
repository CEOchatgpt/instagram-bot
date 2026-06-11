# rapidapi_service.py - نسخه نهایی (پست + استوری + پروفایل بهبود یافته)

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
    """دریافت پروفایل با اولویت userInfo برای آمار دقیق"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json",
    }

    # اول userInfo رو امتحان کن (آمار بهتر)
    for endpoint in ["/api/instagram/userInfo", "/api/instagram/profile"]:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://{RAPIDAPI_HOST}{endpoint}"
                payload = {"username": username}

                async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                    print(f"📊 endpoint {endpoint} برای @{username} استفاده شد")

                    result = data.get("result") or data
                    if not isinstance(result, dict):
                        continue

                    return {
                        "username": result.get("username") or username,
                        "full_name": result.get("full_name") or result.get("name") or username,
                        "biography": result.get("biography", "بدون بیو"),
                        "followers": result.get("follower_count") or result.get("followers_count") or 0,
                        "following": result.get("following_count") or result.get("followings_count") or 0,
                        "posts": result.get("media_count") or result.get("posts_count") or 0,
                        "profile_pic": result.get("profile_pic_url_hd") or result.get("profile_pic_url") or result.get("hd_profile_pic_url_info", {}).get("url"),
                        "is_verified": result.get("is_verified", False),
                        "is_private": result.get("is_private", False),
                        "external_url": result.get("external_url"),
                    }

        except Exception as e:
            print(f"⚠️ خطا در {endpoint}: {e}")
            continue

    print("❌ هیچ endpoint پروفایل کار نکرد")
    return None


# بقیه توابع (get_instagram_story و get_instagram_media) بدون تغییر بمانند
# (کد قبلی‌ت رو نگه دار)
async def get_instagram_story(username: str, story_id: str = None):
    # ... کد قبلی استوری ...
    # (برای صرفه‌جویی در فضا، اگر نیاز به کپی کامل داری بگو)
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
                data = await resp.json()
                items = []
                stories = data.get("result") if isinstance(data, dict) else None
                if isinstance(stories, list):
                    for story in stories:
                        if not isinstance(story, dict): continue
                        video_versions = story.get("video_versions") or story.get("video")
                        if video_versions and isinstance(video_versions, list) and video_versions:
                            best = max(video_versions, key=lambda x: x.get("height", 0))
                            items.append({"type": "video", "url": best.get("url")})
                            continue
                        candidates = story.get("image_versions2", {}).get("candidates", [])
                        if candidates:
                            best = max(candidates, key=lambda x: x.get("height", 0))
                            items.append({"type": "photo", "url": best.get("url")})
                return {"caption": f"📖 استوری @{username}", "items": items}
    except:
        return None


async def get_instagram_media(post_url: str) -> dict | None:
    # کد قبلی‌ت (تشخیص استوری + پست)
    if not post_url or "instagram.com" not in post_url:
        return None

    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        return await get_instagram_story(story_match.group(1), story_match.group(2))

    # بقیه کد پست/ریلز...
    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/links"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json",
    }
    # ... (کد قبلی رو اینجا کپی کن)
    # برای کوتاه شدن، کد قبلی‌ت رو نگه دار
    pass  # placeholder - کد قبلی رو بذار
