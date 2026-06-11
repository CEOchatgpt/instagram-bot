# rapidapi_service.py - نسخه نهایی اصلاح‌شده (پست + استوری + پروفایل + هایلایت)

import re
import aiohttp
import asyncio
import json
from config import RAPIDAPI_KEY, RAPIDAPI_HOST

MAX_RETRIES = 3
RETRY_DELAY = 1


def format_caption(raw: str) -> str:
    text = re.sub(r'https?://\S+', '', raw)
    hashtags = re.findall(r'#\\w+', text)
    text = re.sub(r'#\\w+', '', text)
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
    """پروفایل با آمار دقیق"""
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST, "Content-Type": "application/json"}
    for ep in ["/api/instagram/userInfo", "/api/instagram/profile"]:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://{RAPIDAPI_HOST}{ep}"
                async with session.post(url, json={"username": username}, headers=headers, timeout=20) as resp:
                    data = await resp.json()
                    result = data.get("result") or data
                    if not isinstance(result, dict): continue
                    
                    return {
                        "username": result.get("username") or username,
                        "full_name": result.get("full_name") or result.get("name") or username,
                        "biography": result.get("biography", "بدون بیو"),
                        "followers": result.get("follower_count") or result.get("followers_count") or 0,
                        "following": result.get("following_count") or 0,
                        "posts": result.get("media_count") or 0,
                        "profile_pic": result.get("profile_pic_url_hd") or result.get("profile_pic_url"),
                    }
        except: continue
    return None


async def get_instagram_highlights(username: str):
    """دریافت لیست هایلایت‌های کاربر"""
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/highlights"
            async with session.post(url, json={"username": username}, headers=headers, timeout=20) as resp:
                data = await resp.json()
                result = data.get("result") or data
                highlights = []
                if isinstance(result, list):
                    for h in result:
                        if isinstance(h, dict):
                            highlights.append({
                                "title": h.get("title", "هایلایت"),
                                "highlight_id": h.get("highlight_id") or h.get("id"),
                                "count": h.get("count") or h.get("media_count") or 0  # اصلاح کلید برای حل مشکل عدد 0
                            })
                return highlights
    except Exception as e:
        print(f"❌ خطا در لیست هایلایت: {e}")
        return []


async def get_instagram_highlight_stories(highlight_id: str, title: str = "هایلایت"):
    """دریافت استوری‌های هایلایت با استفاده از متد پایدار و مستقیم لینک"""
    # ساخت لینک مستقیم و استاندارد هایلایت
    highlight_url = f"https://www.instagram.com/stories/highlights/{highlight_id}/"
    try:
        print(f"🔄 تلاش برای دریافت هایلایت از طریق لینک مستقیم: {highlight_url}")
        # استفاده از همان تابعی که لینک‌های مستقیم را با موفقیت دانلود می‌کند
        result = await get_instagram_media(highlight_url)
        if result and result.get("items"):
            # جایگزین کردن کپشن با عنوان اصلی هایلایت
            result["caption"] = f"📚 {title}"
            return result
    except Exception as e:
        print(f"❌ خطا در متد مستقیم هایلایت: {e}")
    
    # روش زاپاس (Fallback) در صورت ناموفق بودن روش اول
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST, "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/highlightStories"
            payload = {"highlightId": str(highlight_id), "highlight_id": str(highlight_id)}
            async with session.post(url, json=payload, headers=headers, timeout=25) as resp:
                data = await resp.json()
                items = []
                result_data = data.get("result") or data.get("items") or data
                
                if isinstance(result_data, dict) and "items" in result_data:
                    stories = result_data["items"]
                elif isinstance(result_data, list):
                    stories = result_data
                else:
                    stories = [result_data] if isinstance(result_data, dict) else []

                for story in stories:
                    if not isinstance(story, dict): continue
                    
                    # بررسی ویدیو
                    video = story.get("video_versions") or story.get("video") or story.get("video_url")
                    if video:
                        url_val = video[0].get("url") if isinstance(video, list) else (video if isinstance(video, str) else story.get("video_url"))
                        if url_val: items.append({"type": "video", "url": url_val}); continue
                    
                    # بررسی عکس
                    images = story.get("image_versions2", {}).get("candidates", []) or story.get("images", []) or story.get("display_url")
                    if images:
                        url_val = images[0].get("url") if isinstance(images, list) else (images if isinstance(images, str) else story.get("display_url"))
                        if url_val: items.append({"type": "photo", "url": url_val})
                
                return {"caption": f"📚 {title}", "items": items} if items else None
    except Exception as e:
        print(f"❌ خطا در روش زاپاس هایلایت: {e}")
        return None


async def get_instagram_story(username: str, story_id: str = None):
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST, "Content-Type": "application/json"}
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
    except:
        return None


async def get_instagram_media(post_url: str) -> dict | None:
    if not post_url or "instagram.com" not in post_url:
        return None

    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        return await get_instagram_story(story_match.group(1), story_match.group(2))

    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/links"
    headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST, "Content-Type": "application/json"}
    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json={"url": post_url}, headers=headers, timeout=15) as response:
                    response.raise_for_status()
                    data = await response.json()
            break
        except:
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
