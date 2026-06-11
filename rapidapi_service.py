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


# تابع get_instagram_highlight_stories را با این نسخه جایگزین کنید

async def get_instagram_highlight_stories(highlight_id: str, username: str = None, title: str = "Highlight"):
    """دریافت استوری‌های داخل یک هایلایت بر اساس ID و username"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    # روش اول: تلاش با highlightId
    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/highlightStories"
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                # تلاش با پارامتر highlightId
                async with session.get(api_url, params={"highlightId": str(highlight_id)}, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # بررسی ساختارهای مختلف پاسخ
                        result = data.get("result") or data.get("data") or data
                        
                        # اگر result یک دیکشنری با کلید items یا stories داشت
                        items_list = []
                        if isinstance(result, dict):
                            items_list = result.get("items") or result.get("stories") or result.get("media") or []
                        elif isinstance(result, list):
                            items_list = result
                        
                        if items_list:
                            formatted_items = []
                            for item in items_list:
                                if not isinstance(item, dict):
                                    continue
                                    
                                # پیدا کردن URL رسانه
                                video_url = None
                                photo_url = None
                                
                                # چک کردن ویدیو
                                if item.get("video_url"):
                                    video_url = item.get("video_url")
                                elif item.get("video_versions") and isinstance(item.get("video_versions"), list):
                                    video_url = item.get("video_versions")[0].get("url")
                                
                                # چک کردن تصویر
                                if not video_url:
                                    if item.get("image_url"):
                                        photo_url = item.get("image_url")
                                    elif item.get("image_versions2", {}).get("candidates"):
                                        candidates = item.get("image_versions2", {}).get("candidates", [])
                                        if candidates:
                                            photo_url = max(candidates, key=lambda x: x.get("height", 0)).get("url")
                                    elif item.get("display_url"):
                                        photo_url = item.get("display_url")
                                
                                if video_url:
                                    formatted_items.append({"type": "video", "url": video_url})
                                elif photo_url:
                                    formatted_items.append({"type": "photo", "url": photo_url})
                            
                            if formatted_items:
                                return {"items": formatted_items, "caption": f"📚 هایلایت: {title}"}
            
            # اگر روش اول جواب نداد و username داریم، روش دوم را امتحان کن
            if username and not formatted_items:
                return await get_instagram_highlight_stories_via_username(username, highlight_id, title)
                
        except Exception as e:
            logger.error(f"Error in highlight stories (attempt {attempt}): {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)
    
    return None


async def get_instagram_highlight_stories_via_username(username: str, highlight_id: str, title: str):
    """روش جایگزین: دریافت استوری‌های هایلایت از طریق username و highlight_id"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # استفاده از اندپوینت stories با highlightId
            url = f"https://{RAPIDAPI_HOST}/api/instagram/stories"
            payload = {"username": username, "highlight_id": highlight_id}
            
            async with session.post(url, json=payload, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    result = data.get("result") or data.get("data") or data
                    
                    items_list = []
                    if isinstance(result, dict):
                        items_list = result.get("items") or result.get("stories") or []
                    elif isinstance(result, list):
                        items_list = result
                    
                    if items_list:
                        formatted_items = []
                        for item in items_list:
                            if not isinstance(item, dict):
                                continue
                            
                            # پیدا کردن URL
                            video_url = item.get("video_url") or (item.get("video_versions", [{}])[0].get("url") if item.get("video_versions") else None)
                            photo_url = item.get("image_url") or (item.get("image_versions2", {}).get("candidates", [{}])[0].get("url") if item.get("image_versions2") else None)
                            
                            if video_url:
                                formatted_items.append({"type": "video", "url": video_url})
                            elif photo_url:
                                formatted_items.append({"type": "photo", "url": photo_url})
                        
                        if formatted_items:
                            return {"items": formatted_items, "caption": f"📚 هایلایت: {title}"}
    except Exception as e:
        logger.error(f"Error in highlight stories via username: {e}")
    
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


import logging
logger = logging.getLogger(__name__)
