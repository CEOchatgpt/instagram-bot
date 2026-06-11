# rapidapi_service.py - نسخه نهایی با استخراج هوشمند آمار پروفایل

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
    """دریافت پروفایل با استخراج هوشمند آمار"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json",
    }

    endpoints = ["/api/instagram/userInfo", "/api/instagram/profile"]

    for ep in endpoints:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://{RAPIDAPI_HOST}{ep}"
                payload = {"username": username}

                async with session.post(url, json=payload, headers=headers, timeout=20) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                    print(f"📊 تست endpoint: {ep} برای @{username}")

                    # پیدا کردن بخش نتیجه
                    result = data.get("result") or data
                    if not isinstance(result, dict):
                        continue

                    # استخراج هوشمند کلیدها (تمام نام‌های ممکن)
                    profile = {
                        "username": result.get("username") or username,
                        "full_name": result.get("full_name") or result.get("name") or username,
                        "biography": result.get("biography", "") or result.get("bio", "بدون بیو"),
                        "profile_pic": (result.get("profile_pic_url_hd") or 
                                      result.get("profile_pic_url") or 
                                      result.get("hd_profile_pic_url_info", {}).get("url")),
                        "is_verified": result.get("is_verified", False),
                        "is_private": result.get("is_private", False),
                        "external_url": result.get("external_url"),
                    }

                    # استخراج آمار (همه کلیدهای رایج)
                    profile["followers"] = (
                        result.get("follower_count") or 
                        result.get("followers_count") or 
                        result.get("edge_followed_by", {}).get("count") or 
                        result.get("followers") or 0
                    )
                    profile["following"] = (
                        result.get("following_count") or 
                        result.get("followings_count") or 
                        result.get("edge_follow", {}).get("count") or 
                        result.get("following") or 0
                    )
                    profile["posts"] = (
                        result.get("media_count") or 
                        result.get("posts_count") or 
                        result.get("edge_owner_to_timeline_media", {}).get("count") or 
                        result.get("posts") or 0
                    )

                    print(f"✅ آمار استخراج شده: {profile['followers']} follower, {profile['following']} following, {profile['posts']} پست")

                    return profile

        except Exception as e:
            print(f"⚠️ خطا در {ep}: {e}")
            continue

    print("❌ هیچ endpoint کار نکرد")
    return None


# توابع استوری و رسانه (بدون تغییر)
async def get_instagram_story(username: str, story_id: str = None):
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
                            best = max(video_versions, key=lambda x: x.get("height", 0) or 0)
                            items.append({"type": "video", "url": best.get("url")})
                            continue
                        candidates = story.get("image_versions2", {}).get("candidates", [])
                        if candidates:
                            best = max(candidates, key=lambda x: x.get("height", 0))
                            items.append({"type": "photo", "url": best.get("url")})
                return {"caption": f"📖 استوری @{username}", "items": items}
    except Exception as e:
        print(f"❌ خطا استوری: {e}")
        return None


async def get_instagram_media(post_url: str) -> dict | None:
    if not post_url or "instagram.com" not in post_url:
        return None

    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        username = story_match.group(1)
        story_id = story_match.group(2)
        print(f"📖 لینک استوری تشخیص داده شد → @{username}")
        return await get_instagram_story(username, story_id)

    # پست/ریلز
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
        if not urls: continue
        best = max(urls, key=lambda x: x.get("quality", 0))
        extension = urls[0].get("extension", "").lower()
        if extension == "mp4":
            items.append({"type": "video", "url": best["url"]})
        else:
            items.append({"type": "photo", "url": best["url"]})

    return {"caption": caption, "items": items} if items else None
