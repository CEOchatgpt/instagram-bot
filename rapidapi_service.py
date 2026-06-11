# rapidapi_service.py - نسخه کامل با پشتیبانی از ریلز

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
    """فرمت کردن کپشن"""
    if not raw:
        return "بدون کپشن"
    text = re.sub(r'https?://\S+', '', raw)
    hashtags = re.findall(r'#\\w+', text)
    text = re.sub(r'#\\w+', '', text)
    text = text.strip()
    if not text:
        text = "بدون کپشن"
    hashtag_line = " ".join(hashtags)
    caption = "✅\n\n" + text
    if hashtag_line:
        caption += f"\n\n{hashtag_line}"
    if len(caption) > 1024:
        cut = caption[:1020].rsplit(" ", 1)[0]
        caption = cut + " ..."
    return caption


async def get_instagram_profile(username: str):
    """دریافت اطلاعات پروفایل کاربر"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    for ep in ["/api/instagram/userInfo", "/api/instagram/profile"]:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"https://{RAPIDAPI_HOST}{ep}"
                async with session.post(url, json={"username": username}, headers=headers, timeout=20) as resp:
                    data = await resp.json()
                    result = data.get("result") or data
                    if not isinstance(result, dict):
                        continue
                    
                    return {
                        "username": result.get("username") or username,
                        "full_name": result.get("full_name") or result.get("name") or username,
                        "biography": result.get("biography", "بدون بیو"),
                        "followers": result.get("follower_count") or result.get("followers_count") or 0,
                        "following": result.get("following_count") or 0,
                        "posts": result.get("media_count") or 0,
                        "profile_pic": result.get("profile_pic_url_hd") or result.get("profile_pic_url"),
                        "is_private": result.get("is_private", False),
                        "is_verified": result.get("is_verified", False),
                    }
        except Exception as e:
            logger.error(f"Error in {ep}: {e}")
            continue
    
    return None


async def get_instagram_highlights(username: str):
    """دریافت لیست هایلایت‌های کاربر"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
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
                            raw_id = h.get("id") or h.get("highlight_id")
                            if raw_id and ":" in str(raw_id):
                                clean_id = str(raw_id).split(":")[-1]
                            else:
                                clean_id = str(raw_id) if raw_id else None
                            
                            highlights.append({
                                "title": h.get("title", "هایلایت"),
                                "id": clean_id,
                                "count": h.get("count") or h.get("media_count") or 0,
                                "cover": h.get("cover_url") or h.get("cover"),
                            })
                
                return highlights
    except Exception as e:
        logger.error(f"Error getting highlights: {e}")
        return []


async def get_instagram_media(post_url: str) -> dict | None:
    """دریافت محتوای پست از لینک مستقیم"""
    if not post_url or "instagram.com" not in post_url:
        return None

    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        return await get_instagram_story(story_match.group(1), story_match.group(2))

    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/links"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
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
            logger.warning(f"Attempt {attempt} failed: {e}")
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


async def get_instagram_highlight_stories(highlight_id: str, username: str = None, title: str = "Highlight"):
    """دریافت استوری‌های یک هایلایت"""
    clean_id = highlight_id
    if highlight_id and ":" in str(highlight_id):
        clean_id = str(highlight_id).split(":")[-1]
    
    highlight_url = f"https://www.instagram.com/stories/highlights/{clean_id}/"
    logger.info(f"Fetching highlight: {highlight_url}")
    
    return await get_instagram_media(highlight_url)


async def get_instagram_story(username: str, story_id: str = None):
    """دریافت استوری کاربر"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
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
                        if not isinstance(story, dict):
                            continue
                        
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
        logger.error(f"Error getting story: {e}")
        return None


async def get_user_reels(username: str, max_id: str = ""):
    """
    دریافت لیست ریل‌های یک کاربر
    Returns: {
        "items": [{"id": "...", "url": "...", "caption": "...", "like_count": 0, "comment_count": 0}],
        "next_max_id": "...",
        "username": "..."
    }
    """
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/reels"
            payload = {"username": username, "maxId": max_id}
            
            logger.info(f"Fetching reels for {username} with max_id: {max_id}")
            
            async with session.post(url, json=payload, headers=headers, timeout=25) as resp:
                data = await resp.json()
                
                # لاگ برای دیباگ
                logger.info(f"Reels API response status: {resp.status}")
                
                result = data.get("result") or data
                
                if not result:
                    logger.warning(f"No result for {username}")
                    return None
                
                items = []
                
                # پیدا کردن لیست ریل‌ها در ساختار پاسخ
                reel_list = []
                if isinstance(result, dict):
                    if "reels" in result:
                        reel_list = result["reels"]
                    elif "items" in result:
                        reel_list = result["items"]
                    elif "media" in result:
                        reel_list = result["media"]
                    else:
                        # بررسی اگر خود result شامل آیتم‌هاست
                        for key in ["graphql", "data", "user", "edge_owner_to_timeline_media"]:
                            if key in result:
                                reel_list = result[key].get("edges", []) or result[key].get("media", [])
                                break
                        if not reel_list and isinstance(result, list):
                            reel_list = result
                elif isinstance(result, list):
                    reel_list = result
                
                if not reel_list:
                    logger.warning(f"No reels list found for {username}")
                    logger.info(f"Result structure: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                    return None
                
                for reel in reel_list:
                    if not isinstance(reel, dict):
                        continue
                    
                    # استخراج رسانه واقعی (بعضی APIها داخل node یا media می‌گذارند)
                    media_item = reel
                    if "node" in reel:
                        media_item = reel["node"]
                    if "media" in reel:
                        media_item = reel["media"]
                    
                    video_url = None
                    
                    # روش‌های مختلف دریافت ویدیو
                    video_versions = media_item.get("video_versions")
                    if video_versions and isinstance(video_versions, list) and video_versions:
                        best = max(video_versions, key=lambda x: x.get("height", 0) or x.get("width", 0))
                        video_url = best.get("url")
                    
                    if not video_url:
                        video_url = media_item.get("video_url")
                    
                    if not video_url:
                        clips = media_item.get("clips", [])
                        if clips and isinstance(clips, list) and clips:
                            video_url = clips[0].get("url")
                    
                    if not video_url:
                        # چک کردن اگر ویدیو نیست، رد کن
                        continue
                    
                    # استخراج کپشن
                    caption = media_item.get("caption", "")
                    if not caption:
                        caption = media_item.get("title", "")
                    if not caption:
                        caption = media_item.get("text", "")
                    if not caption:
                        caption = "بدون کپشن"
                    
                    # استخراج آیدی
                    reel_id = media_item.get("id") or media_item.get("pk") or media_item.get("code") or ""
                    
                    items.append({
                        "id": reel_id,
                        "url": video_url,
                        "caption": caption[:200] if caption else "بدون کپشن",
                        "thumbnail": media_item.get("thumbnail_url") or media_item.get("cover_url") or "",
                        "like_count": media_item.get("like_count", 0),
                        "comment_count": media_item.get("comment_count", 0),
                        "play_count": media_item.get("play_count", 0),
                    })
                
                # گرفتن next_max_id برای صفحه‌بندی
                next_max_id = ""
                if isinstance(result, dict):
                    next_max_id = result.get("next_max_id") or result.get("max_id") or ""
                
                logger.info(f"Found {len(items)} reels for {username}")
                
                return {
                    "items": items,
                    "next_max_id": next_max_id,
                    "username": username
                }
                
    except Exception as e:
        logger.error(f"Error getting reels for {username}: {e}")
        return None


async def get_user_reels_v2(username: str):
    """نسخه جایگزین برای دریافت ریل‌ها از endpoint posts"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/posts"
            payload = {"username": username, "maxId": ""}
            
            async with session.post(url, json=payload, headers=headers, timeout=25) as resp:
                data = await resp.json()
                result = data.get("result") or data
                
                items = []
                posts_list = result.get("items", []) if isinstance(result, dict) else []
                
                for post in posts_list:
                    if not isinstance(post, dict):
                        continue
                    
                    # بررسی اگر ویدیو/ریل است
                    media_type = post.get("media_type", 0)
                    is_video = post.get("is_video", False) or media_type == 2
                    
                    if is_video:
                        video_url = post.get("video_url") or post.get("video_versions", [{}])[0].get("url")
                        if video_url:
                            items.append({
                                "id": post.get("id", ""),
                                "url": video_url,
                                "caption": post.get("caption", "بدون کپشن"),
                                "like_count": post.get("like_count", 0),
                                "comment_count": post.get("comment_count", 0),
                                "play_count": post.get("play_count", 0),
                            })
                
                logger.info(f"V2 - Found {len(items)} reels for {username}")
                
                return {
                    "items": items,
                    "next_max_id": "",
                    "username": username
                }
    except Exception as e:
        logger.error(f"Error in get_user_reels_v2: {e}")
        return None
