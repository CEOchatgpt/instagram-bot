# rapidapi_service.py - نسخه کامل بازنویسی شده

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
        except:
            continue
    return None


async def get_instagram_highlights(username: str):
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
                            raw_id = h.get("id") or h.get("highlight_id")
                            if raw_id and ":" in str(raw_id):
                                clean_id = str(raw_id).split(":")[-1]
                            else:
                                clean_id = str(raw_id) if raw_id else None
                            
                            highlights.append({
                                "title": h.get("title", "هایلایت"),
                                "id": clean_id,
                                "count": h.get("count") or h.get("media_count") or 0
                            })
                return highlights
    except Exception as e:
        logger.error(f"Error getting highlights: {e}")
        return []


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


async def get_instagram_highlight_stories(highlight_id: str, username: str = None, title: str = "Highlight"):
    clean_id = highlight_id
    if highlight_id and ":" in str(highlight_id):
        clean_id = str(highlight_id).split(":")[-1]
    
    highlight_url = f"https://www.instagram.com/stories/highlights/{clean_id}/"
    logger.info(f"Fetching highlight: {highlight_url}")
    
    return await get_instagram_media(highlight_url)


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


# به rapidapi_service.py اضافه کنید

async def get_user_reels(username: str, max_id: str = ""):
    """
    دریافت لیست ریل‌های یک کاربر
    Returns: {
        "items": [{"id": "...", "url": "...", "caption": "...", "video_url": "..."}],
        "next_max_id": "..."
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
            
            async with session.post(url, json=payload, headers=headers, timeout=25) as resp:
                data = await resp.json()
                result = data.get("result") or data
                
                if not result:
                    return None
                
                items = []
                reel_list = result.get("reels") or result.get("items") or result
                
                # اگه result لیست نیست و دیکشنری هست
                if isinstance(reel_list, dict):
                    # ممکنه ریل‌ها توی کلید media باشن
                    reel_list = reel_list.get("media", []) or reel_list.get("items", []) or [reel_list]
                
                if isinstance(reel_list, list):
                    for reel in reel_list:
                        if not isinstance(reel, dict):
                            continue
                        
                        # استخراج ویدیو با بهترین کیفیت
                        video_url = None
                        
                        # روش اول: video_versions
                        video_versions = reel.get("video_versions")
                        if video_versions and isinstance(video_versions, list):
                            best = max(video_versions, key=lambda x: x.get("height", 0) or x.get("width", 0))
                            video_url = best.get("url")
                        
                        # روش دوم: video_url مستقیم
                        if not video_url:
                            video_url = reel.get("video_url")
                        
                        # روش سوم: clips
                        if not video_url:
                            clips = reel.get("clips", [])
                            if clips and isinstance(clips, list):
                                video_url = clips[0].get("url")
                        
                        if not video_url:
                            continue
                        
                        # استخراج کپشن
                        caption = reel.get("caption", "")
                        if not caption:
                            caption = reel.get("title", "")
                        if not caption:
                            caption = reel.get("text", "")
                        
                        # استخراج آیدی ریل
                        reel_id = reel.get("id") or reel.get("pk") or reel.get("code")
                        
                        items.append({
                            "id": reel_id,
                            "url": video_url,
                            "caption": caption[:200] if caption else "بدون کپشن",
                            "thumbnail": reel.get("thumbnail_url") or reel.get("cover_url"),
                            "like_count": reel.get("like_count", 0),
                            "comment_count": reel.get("comment_count", 0),
                            "play_count": reel.get("play_count", 0),
                        })
                
                # گرفتن next_max_id برای صفحه‌بندی
                next_max_id = result.get("next_max_id") or result.get("max_id") or ""
                
                return {
                    "items": items,
                    "next_max_id": next_max_id,
                    "username": username
                }
                
    except Exception as e:
        logger.error(f"Error getting reels for {username}: {e}")
        return None


async def download_single_reel(reel_url: str):
    """
    دانلود یک ریل با لینک مستقیم (مثل پست معمولی)
    """
    return await get_instagram_media(reel_url)
