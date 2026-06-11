# rapidapi_service.py - نسخه اصلاح شده برای رفع خطای هایلایت

import re
import aiohttp
import asyncio
import json
import logging
from config import RAPIDAPI_KEY, RAPIDAPI_HOST

logger = logging.getLogger(__name__)

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
        except Exception as e:
            logger.error(f"Profile error: {e}")
            continue
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
                                "count": h.get("count") or h.get("media_count") or 0
                            })
                return highlights
    except Exception as e:
        logger.error(f"Error getting highlights: {e}")
        return []


async def get_instagram_highlight_stories(highlight_id: str, username: str = None, title: str = "Highlight"):
    """دریافت استوری‌های داخل یک هایلایت - نسخه کاملاً بازنویسی شده"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    # روش‌های مختلف برای دریافت محتوای هایلایت
    methods = [
        # روش 1: استفاده از highlightId با endpoint highlights
        {"url": f"https://{RAPIDAPI_HOST}/api/instagram/highlightStories", "params": {"highlightId": str(highlight_id)}},
        
        # روش 2: استفاده از highlight_id با endpoint stories
        {"url": f"https://{RAPIDAPI_HOST}/api/instagram/stories", "params": {"highlight_id": str(highlight_id)}},
        
        # روش 3: اگر username داریم، از آن استفاده کن
        {"url": f"https://{RAPIDAPI_HOST}/api/instagram/highlights", "params": {"username": username}} if username else None,
    ]
    
    # حذف متدهای None
    methods = [m for m in methods if m is not None]
    
    for method in methods:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    logger.info(f"Trying method: {method['url']} with params: {method['params']}")
                    
                    # برای برخی APIها باید از POST استفاده کرد
                    if "stories" in method['url']:
                        async with session.post(method['url'], json=method['params'], headers=headers, timeout=15) as response:
                            if response.status == 200:
                                data = await response.json()
                                items = await extract_items_from_response(data, title)
                                if items:
                                    return {"items": items, "caption": f"📚 هایلایت: {title}"}
                    else:
                        async with session.get(method['url'], params=method['params'], headers=headers, timeout=15) as response:
                            if response.status == 200:
                                data = await response.json()
                                items = await extract_items_from_response(data, title)
                                if items:
                                    return {"items": items, "caption": f"📚 هایلایت: {title}"}
                                
            except Exception as e:
                logger.error(f"Error in method {method['url']} (attempt {attempt}): {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY * attempt)
    
    return None


async def extract_items_from_response(data, title):
    """استخراج آیتم‌های مدیا از پاسخ API"""
    items = []
    
    # بررسی ساختارهای مختلف پاسخ
    result = data.get("result") or data.get("data") or data
    
    # اگر result یک دیکشنری است
    if isinstance(result, dict):
        # بررسی کلیدهای مختلف
        for key in ["items", "stories", "media", "highlight_stories"]:
            if key in result and isinstance(result[key], list):
                items = result[key]
                break
        
        # اگر آیتمی پیدا نشد و خود دیکشنری شامل مدیاهاست
        if not items and "video_url" in result or "image_url" in result:
            items = [result]
    
    # اگر result یک لیست است
    elif isinstance(result, list):
        items = result
    
    # اگر خود data یک لیست است
    elif isinstance(data, list):
        items = data
    
    if not items:
        logger.warning(f"No items found in response for {title}")
        return []
    
    # تبدیل آیتم‌ها به فرمت استاندارد
    formatted_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        
        video_url = None
        photo_url = None
        
        # روش‌های مختلف پیدا کردن ویدیو
        if item.get("video_url"):
            video_url = item.get("video_url")
        elif item.get("video_versions") and isinstance(item.get("video_versions"), list):
            video_versions = item.get("video_versions")
            if video_versions:
                video_url = video_versions[0].get("url")
        elif item.get("videos"):
            videos = item.get("videos")
            if isinstance(videos, dict) and videos.get("url"):
                video_url = videos.get("url")
        
        # روش‌های مختلف پیدا کردن عکس
        if not video_url:
            if item.get("image_url"):
                photo_url = item.get("image_url")
            elif item.get("image_versions2", {}).get("candidates"):
                candidates = item.get("image_versions2", {}).get("candidates", [])
                if candidates:
                    # بزرگترین کیفیت را انتخاب کن
                    photo_url = max(candidates, key=lambda x: x.get("height", 0)).get("url")
            elif item.get("display_url"):
                photo_url = item.get("display_url")
            elif item.get("thumbnail_url"):
                photo_url = item.get("thumbnail_url")
        
        if video_url:
            formatted_items.append({"type": "video", "url": video_url})
            logger.info(f"Found video: {video_url[:50]}...")
        elif photo_url:
            formatted_items.append({"type": "photo", "url": photo_url})
            logger.info(f"Found photo: {photo_url[:50]}...")
    
    logger.info(f"Extracted {len(formatted_items)} items from response")
    return formatted_items


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
    except Exception as e:
        logger.error(f"Story error: {e}")
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
        except Exception as e:
            logger.error(f"Media fetch error (attempt {attempt}): {e}")
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
