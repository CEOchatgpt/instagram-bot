# rapidapi_service.py - نسخه بدون Redis (فقط کانال تلگرام) با پروفایل فوق‌العاده سبک

import re
import aiohttp
import asyncio
import json
import logging
import hashlib
from config import RAPIDAPI_KEY, RAPIDAPI_HOST
from channel_cache import (
    get_profile_from_channel, 
    save_profile_to_channel, 
    get_media_from_channel, 
    save_media_to_channel
)

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1


# ========== توابع کمکی ==========

def extract_caption_text(caption_field):
    """استخراج متن کپشن از ساختارهای مختلف"""
    if not caption_field:
        return ""
    
    if isinstance(caption_field, str):
        return caption_field
    
    if isinstance(caption_field, dict):
        if "text" in caption_field:
            return caption_field["text"]
        if "caption" in caption_field:
            return extract_caption_text(caption_field["caption"])
        for key in ["content", "body", "description", "title"]:
            if key in caption_field:
                return str(caption_field[key])
        return ""
    
    return str(caption_field) if caption_field else ""


def format_caption(raw) -> str:
    """فرمت کردن کپشن"""
    text = extract_caption_text(raw)
    
    if not text:
        return "بدون کپشن"
    
    text = re.sub(r'https?://\S+', '', text)
    hashtags = re.findall(r'#\w+', text)
    text = re.sub(r'#\w+', '', text)
    text = text.strip()
    
    if not text:
        text = "بدون کپشن"
    
    if hashtags:
        hashtag_line = " ".join(hashtags)
        text = text + "\n\n" + hashtag_line
    
    if len(text) > 1024:
        text = text[:1020].rsplit(" ", 1)[0] + " ..."
    
    return text


# ========== تابع پروفایل (فقط کانال تلگرام - سبک) ==========

async def get_instagram_profile(username: str, context=None):
    """
    دریافت پروفایل - فقط نام کامل و عکس پروفایل
    کش فقط در کانال تلگرام (بدون Redis)
    """
    
    # لایه 1: کش کانال تلگرام
    if context:
        try:
            channel_cached = await get_profile_from_channel(context, username)
            if channel_cached:
                logger.info(f"🏦 پروفایل {username} از کانال دیتابیس برگردانده شد")
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن از کانال دیتابیس: {e}")
    
    # لایه 2: API
    logger.info(f"🌐 پروفایل {username} در کش نبود - ارسال درخواست به API")
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/userInfo"
            async with session.post(url, json={"username": username}, headers=headers, timeout=20) as resp:
                data = await resp.json()
                
                result_list = data.get("result", [])
                if not result_list or not isinstance(result_list, list):
                    return None
                
                first_result = result_list[0] if result_list else {}
                user_data = first_result.get("user", {})
                
                if not user_data:
                    return None
                
                # ========== فقط حداقل اطلاعات (نام کامل + عکس) ==========
                profile = {
                    "username": user_data.get("username") or username,
                    "full_name": user_data.get("full_name") or username,
                    "profile_pic": user_data.get("hd_profile_pic_url_info", {}).get("url") or user_data.get("profile_pic_url"),
                }
                
                # ذخیره در کانال برای دفعات بعد (فقط اگه عکس داشته باشه)
                if context and profile.get("profile_pic"):
                    await save_profile_to_channel(context, username, profile)
                    logger.info(f"✅ پروفایل {username} در کانال دیتابیس ذخیره شد")
                
                return profile
                
    except Exception as e:
        logger.error(f"Error in get_instagram_profile: {e}")
        return None


# ========== تابع مدیا (پست، ریلز، استوری، هایلایت) ==========

async def get_instagram_media(post_url: str, context=None) -> dict | None:
    """
    دریافت محتوای پست - کش فقط در کانال تلگرام
    پشتیبانی از: پست، ریلز، استوری، هایلایت
    """
    
    if not post_url or "instagram.com" not in post_url:
        return None
    
    # کلید یکتا برای این محتوا
    media_key = post_url
    
    # لایه 1: کش کانال تلگرام
    if context:
        try:
            channel_cached = await get_media_from_channel(context, media_key)
            if channel_cached:
                logger.info(f"🏦 مدیا {post_url[:50]}... از کانال دیتابیس برگردانده شد")
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن مدیا از کانال: {e}")
    
    # لایه 2: API
    logger.info(f"🌐 مدیا {post_url[:50]}... در کش نبود - ارسال درخواست به API")
    
    # تشخیص استوری
    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        result = await get_instagram_story(story_match.group(1), story_match.group(2), context)
        if result and result.get("items") and context:
            await save_media_to_channel(context, media_key, result)
        return result
    
    # تشخیص هایلایت
    highlight_match = re.search(r'instagram\.com/stories/highlights/([^/]+)/?', post_url)
    if highlight_match:
        clean_id = highlight_match.group(1)
        highlight_url = f"https://www.instagram.com/stories/highlights/{clean_id}/"
        return await get_instagram_media(highlight_url, context)
    
    # API اصلی برای لینک‌های معمولی (پست و ریلز)
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
                    if response.status == 200:
                        data = await response.json()
                        break
                    else:
                        logger.warning(f"Attempt {attempt} got status {response.status}")
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
    
    result = {"caption": caption, "items": items} if items else None
    
    # ذخیره در کانال برای دفعات بعد
    if result and context:
        await save_media_to_channel(context, media_key, result)
        logger.info(f"✅ مدیا در کانال دیتابیس ذخیره شد")
    
    return result


# ========== توابع استوری ==========

async def get_instagram_story(username: str, story_id: str = None, context=None):
    """دریافت استوری کاربر با کش در کانال تلگرام"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    story_key = f"story:{username}:{story_id if story_id else 'latest'}"
    
    # چک کش کانال
    if context:
        try:
            channel_cached = await get_media_from_channel(context, story_key)
            if channel_cached:
                logger.info(f"🏦 استوری {username} از کانال دیتابیس برگردانده شد")
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن استوری از کانال: {e}")
    
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
                
                result = {"caption": f"📖 استوری @{username}", "items": items} if items else None
                
                if result and result.get("items") and context:
                    await save_media_to_channel(context, story_key, result)
                    logger.info(f"✅ استوری {username} در کانال دیتابیس ذخیره شد")
                
                return result
                
    except Exception as e:
        logger.error(f"Error getting story: {e}")
        return None


async def get_instagram_highlight_stories(highlight_id: str, username: str = None, title: str = "Highlight", context=None):
    """دریافت استوری‌های یک هایلایت"""
    clean_id = highlight_id
    if highlight_id and ":" in str(highlight_id):
        clean_id = str(highlight_id).split(":")[-1]
    
    highlight_url = f"https://www.instagram.com/stories/highlights/{clean_id}/"
    logger.info(f"Fetching highlight: {highlight_url}")
    
    return await get_instagram_media(highlight_url, context)


async def check_and_get_stories(username: str, context=None):
    """بررسی و دریافت استوری‌های کاربر با کش در کانال تلگرام"""
    
    story_key = f"story:{username}:latest"
    
    # لایه 1: کش کانال تلگرام
    if context:
        try:
            channel_cached = await get_media_from_channel(context, story_key)
            if channel_cached:
                logger.info(f"🏦 استوری‌های {username} از کانال دیتابیس برگردانده شد")
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن استوری از کانال: {e}")
    
    # لایه 2: از API بگیر
    logger.info(f"🌐 استوری‌های {username} در کش نبود - ارسال درخواست به API")
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/stories"
            async with session.post(url, json={"username": username}, headers=headers, timeout=20) as resp:
                data = await resp.json()
                stories = data.get("result") if isinstance(data, dict) else None
                
                if not stories or not isinstance(stories, list) or len(stories) == 0:
                    logger.info(f"⚠️ کاربر {username} استوری ندارد")
                    return None
                
                items = []
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
                
                result = items if items else None
                
                # ذخیره در کانال تلگرام
                if result and context:
                    story_data = {"caption": f"📖 استوری‌های @{username}", "items": result}
                    await save_media_to_channel(context, story_key, story_data)
                    logger.info(f"✅ استوری‌های {username} در کانال دیتابیس ذخیره شد")
                
                return result
                
    except Exception as e:
        logger.error(f"Error checking stories for {username}: {e}")
        return None


# ========== تابع ریلز (دریافت لیست ریل‌های کاربر) ==========

async def get_user_reels_v2(username: str, context=None):
    """دریافت لیست ریل‌های کاربر با کش در کانال تلگرام"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    reels_key = f"reels:{username}"
    
    # چک کش کانال
    if context:
        try:
            channel_cached = await get_media_from_channel(context, reels_key)
            if channel_cached:
                logger.info(f"🏦 لیست ریل‌های {username} از کانال دیتابیس برگردانده شد")
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن ریل از کانال: {e}")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/posts"
            payload = {"username": username, "maxId": ""}
            
            logger.info(f"Fetching posts for {username}")
            
            async with session.post(url, json=payload, headers=headers, timeout=30) as resp:
                data = await resp.json()
                result = data.get("result") or data
                
                items = []
                posts_list = []
                
                if isinstance(result, dict):
                    if "items" in result:
                        posts_list = result["items"]
                    elif "edges" in result:
                        for edge in result["edges"]:
                            if "node" in edge:
                                posts_list.append(edge["node"])
                elif isinstance(result, list):
                    posts_list = result
                
                logger.info(f"Found {len(posts_list)} posts for {username}")
                
                if not posts_list:
                    return None
                
                for post in posts_list:
                    if not isinstance(post, dict):
                        continue
                    
                    media_type = post.get("media_type", 0)
                    is_video = post.get("is_video", False) or media_type == 2
                    
                    if is_video:
                        video_url = post.get("video_url")
                        if not video_url:
                            video_versions = post.get("video_versions", [])
                            if video_versions:
                                best = max(video_versions, key=lambda x: x.get("height", 0))
                                video_url = best.get("url")
                        
                        if video_url and video_url.startswith(('http://', 'https://')):
                            raw_caption = post.get("caption", "")
                            caption_text = extract_caption_text(raw_caption)
                            
                            if not caption_text:
                                caption_text = "بدون کپشن"
                            
                            reel_data = {
                                "id": post.get("id", ""),
                                "url": video_url,
                                "caption": caption_text[:200],
                                "like_count": post.get("like_count", 0),
                                "comment_count": post.get("comment_count", 0),
                                "play_count": post.get("play_count", 0),
                            }
                            
                            items.append(reel_data)
                            
                            # ذخیره هر ریل به صورت جداگانه در کانال
                            if context:
                                reel_key = f"reel:{username}:{post.get('id', '')}"
                                reel_result = {"caption": caption_text, "items": [{"type": "video", "url": video_url}]}
                                await save_media_to_channel(context, reel_key, reel_result)
                
                result_data = {
                    "items": items,
                    "next_max_id": "",
                    "username": username
                } if items else None
                
                # ذخیره لیست ریل‌ها در کش کانال
                if result_data and context:
                    await save_media_to_channel(context, reels_key, result_data)
                    logger.info(f"✅ لیست ریل‌های {username} در کانال دیتابیس ذخیره شد")
                
                return result_data
                
    except asyncio.TimeoutError:
        logger.error(f"Timeout error for {username}")
        return None
    except Exception as e:
        logger.error(f"Error in get_user_reels_v2 for {username}: {e}")
        return None


# ========== تابع هایلایت (دریافت لیست هایلایت‌های کاربر) ==========

async def get_instagram_highlights(username: str, context=None):
    """دریافت لیست هایلایت‌های کاربر با کش در کانال تلگرام"""
    
    highlights_key = f"highlights:{username}"
    
    # چک کش کانال
    if context:
        try:
            channel_cached = await get_media_from_channel(context, highlights_key)
            if channel_cached:
                logger.info(f"🏦 لیست هایلایت‌های {username} از کانال دیتابیس برگردانده شد")
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن هایلایت از کانال: {e}")
    
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
                
                # ذخیره در کش کانال
                if highlights and context:
                    await save_media_to_channel(context, highlights_key, highlights)
                    logger.info(f"✅ لیست هایلایت‌های {username} در کانال دیتابیس ذخیره شد")
                
                return highlights
                
    except Exception as e:
        logger.error(f"Error getting highlights: {e}")
        return []
