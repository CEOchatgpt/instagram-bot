# rapidapi_service.py - نسخه کامل با پشتیبانی از کش دو لایه برای همه محتواها

import re
import aiohttp
import asyncio
import json
import logging
import hashlib
import time
from config import RAPIDAPI_KEY, RAPIDAPI_HOST
from database import redis_client 
from channel_cache import get_profile_from_channel, save_profile_to_channel, get_media_from_channel, save_media_to_channel
# اضافه کردن import جدید در اول فایل
from smart_cache import (
    save_file_to_channel, get_file_from_channel,
    save_profile_to_channel_smart, get_profile_from_channel_smart,
    get_cached_media_smart, set_cached_media_smart,
    generate_media_key, get_channel_for_media
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

def extract_media_id_from_url(post_url: str) -> str:
    """استخراج Media ID از لینک اینستاگرام"""
    patterns = [
        r'instagram\.com/p/([A-Za-z0-9_-]+)',
        r'instagram\.com/reel/([A-Za-z0-9_-]+)',
        r'instagram\.com/tv/([A-Za-z0-9_-]+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, post_url)
        if match:
            return match.group(1)
    return None
    

# ========== توابع کش لایه 1 (Redis - موقت) ==========

def get_cached_profile(username: str):
    """دریافت پروفایل از کش Redis"""
    if not redis_client:
        return None
    key = f"cache:profile:{username}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None

def set_cached_profile(username: str, profile_data: dict, ttl_seconds: int = 3600):
    """ذخیره پروفایل در کش Redis"""
    if not redis_client:
        return
    key = f"cache:profile:{username}"
    redis_client.setex(key, ttl_seconds, json.dumps(profile_data))
    logger.info(f"✅ پروفایل {username} در Redis کش شد (TTL: {ttl_seconds}s)")

def get_cached_media(media_key: str):
    """دریافت مدیا از کش Redis"""
    if not redis_client:
        return None
    key_hash = hashlib.md5(media_key.encode()).hexdigest()
    key = f"cache:media:{key_hash}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None

def set_cached_media(media_key: str, media_data: dict, ttl_seconds: int = 7200):
    """ذخیره مدیا در کش Redis"""
    if not redis_client:
        return
    key_hash = hashlib.md5(media_key.encode()).hexdigest()
    key = f"cache:media:{key_hash}"
    redis_client.setex(key, ttl_seconds, json.dumps(media_data))
    logger.info(f"✅ مدیا در Redis کش شد (TTL: {ttl_seconds}s)")


# ========== تابع پروفایل (کش دو لایه) ==========

async def get_instagram_profile(username: str, context=None):
    """دریافت پروفایل - کش دو لایه (Redis + کانال تلگرام)"""
    
    # لایه 1: کش Redis (سریع، موقت)
    cached = get_cached_profile(username)
    if cached:
        logger.info(f"📦 پروفایل {username} از Redis کش برگردانده شد")
        return cached
    
    # لایه 2: کش دائمی (کانال تلگرام)
    if context:
        try:
            channel_cached = await get_profile_from_channel(context, username)
            if channel_cached:
                logger.info(f"🏦 پروفایل {username} از کانال دیتابیس برگردانده شد")
                set_cached_profile(username, channel_cached, ttl_seconds=3600)
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن از کانال دیتابیس: {e}")
    
    # لایه 3: API
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
                
                profile = {
                    "username": user_data.get("username") or username,
                    "full_name": user_data.get("full_name") or username,
                    "biography": user_data.get("biography") or "بدون بیو",
                    "followers": user_data.get("follower_count", 0),
                    "following": user_data.get("following_count", 0),
                    "posts": user_data.get("media_count", 0),
                    "profile_pic": user_data.get("hd_profile_pic_url_info", {}).get("url") or user_data.get("profile_pic_url"),
                    "is_private": user_data.get("is_private", False),
                    "is_verified": user_data.get("is_verified", False),
                }
                
                # ذخیره در هر دو لایه
                set_cached_profile(username, profile, ttl_seconds=3600)
                if context:
                    await save_profile_to_channel(context, username, profile)
                
                return profile
                
    except Exception as e:
        logger.error(f"Error in get_instagram_profile: {e}")
        return None


# ========== تابع مدیا (پست، ریلز، استوری، هایلایت) ==========

# ... (بقیه کد بالا مثل قبل)

async def get_instagram_media(post_url: str, context=None, user_chat_id: int = None) -> dict | None:
    """دریافت پست/ریلز - با ذخیره فایل واقعی در کانال"""
    
    if not post_url or "instagram.com" not in post_url:
        return None
    
    media_id = extract_media_id_from_url(post_url)
    media_key = generate_media_key(media_id or post_url, "post")
    
    # اولویت ۱: ارسال مستقیم از کش کانال
    if user_chat_id and context:
        success = await get_file_from_channel(context, media_key, user_chat_id)
        if success:
            return {"from_cache": True, "items": []}
    
    # اولویت ۲: Redis
    cached = await get_cached_media_smart(media_key)
    if cached:
        return cached
    
    # اولویت ۳: API
    logger.info(f"🌐 دریافت از API: {post_url}")
    
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/media"
            async with session.post(url, json={"url": post_url}, headers=headers, timeout=30) as resp:
                data = await resp.json()
                
                # پردازش نتیجه API (بسته به ساختار RapidAPI)
                result = data.get("result") or data
                
                items = []
                if isinstance(result, dict) and "items" in result:
                    items = result["items"]
                elif isinstance(result, list):
                    items = result
                
                if not items:
                    return None
                
                processed_items = []
                for item in items:
                    item_type = "video" if item.get("is_video") or item.get("type") == "video" else "photo"
                    media_url = item.get("video_url") or item.get("url")
                    
                    if media_url:
                        processed_items.append({
                            "type": item_type,
                            "url": media_url,
                            "caption": format_caption(item.get("caption", ""))
                        })
                        
                        # **ذخیره فایل واقعی در کانال**
                        if context:
                            await save_file_to_channel(
                                context=context,
                                file_url=media_url,
                                media_type=item_type,
                                caption=processed_items[-1]["caption"],
                                media_key=f"{media_key}_{item.get('id', '')}"
                            )
                
                final_result = {
                    "items": processed_items,
                    "caption": format_caption(result.get("caption", ""))
                }
                
                await set_cached_media_smart(media_key, final_result)
                return final_result
                
    except Exception as e:
        logger.error(f"Error in get_instagram_media: {e}")
        return None



# ========== توابع استوری و هایلایت ==========

async def get_instagram_story(username: str, story_id: str = None, context=None):
    """دریافت استوری کاربر با پشتیبانی از کش"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    story_key = f"story:{username}:{story_id if story_id else 'latest'}"
    
    # چک کش
    cached = get_cached_media(story_key)
    if cached:
        logger.info(f"📦 استوری {username} از Redis کش برگردانده شد")
        return cached
    
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
                
                if result and result.get("items"):
                    set_cached_media(story_key, result, ttl_seconds=3600)
                    if context:
                        await save_media_to_channel(context, story_key, result)
                
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
    """بررسی و دریافت استوری‌های کاربر با کش در Redis و کانال"""
    
    story_key = f"story:{username}:latest"
    
    # لایه 1: چک کش Redis
    cached = get_cached_media(story_key)
    if cached:
        logger.info(f"📦 استوری‌های {username} از Redis کش برگردانده شد")
        return cached
    
    # لایه 2: چک کش کانال
    if context:
        try:
            channel_cached = await get_media_from_channel(context, story_key)
            if channel_cached:
                logger.info(f"🏦 استوری‌های {username} از کانال دیتابیس برگردانده شد")
                set_cached_media(story_key, channel_cached, ttl_seconds=1800)  # 30 دقیقه
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن استوری از کانال: {e}")
    
    # لایه 3: از API بگیر
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
                    
                    # چک کردن ویدیو
                    video_versions = story.get("video_versions") or story.get("video")
                    if video_versions and isinstance(video_versions, list) and video_versions:
                        best = max(video_versions, key=lambda x: x.get("height", 0) or 0)
                        items.append({"type": "video", "url": best.get("url")})
                        continue
                    
                    # چک کردن عکس
                    candidates = story.get("image_versions2", {}).get("candidates", [])
                    if candidates:
                        best = max(candidates, key=lambda x: x.get("height", 0))
                        items.append({"type": "photo", "url": best.get("url")})
                
                result = items if items else None
                
                # ذخیره در کش (استوری‌ها زود منقضی میشن، TTL کم)
                if result:
                    # ذخیره در Redis با TTL 30 دقیقه
                    set_cached_media(story_key, result, ttl_seconds=1800)
                    
                    # ذخیره در کانال تلگرام
                    if context:
                        story_data = {"caption": f"📖 استوری‌های @{username}", "items": result}
                        await save_media_to_channel(context, story_key, story_data)
                        logger.info(f"✅ استوری‌های {username} در کانال دیتابیس ذخیره شد")
                
                return result
                
    except Exception as e:
        logger.error(f"Error checking stories for {username}: {e}")
        return None


# ========== تابع ریلز ==========

async def get_user_reels_v2(username: str, context=None):
    """دریافت ریل‌ها با ذخیره در کش و کانال"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    reels_key = f"reels:{username}"
    
    # چک کش برای لیست ریل‌ها
    cached = get_cached_media(reels_key)
    if cached:
        logger.info(f"📦 لیست ریل‌های {username} از Redis کش برگردانده شد")
        return cached
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://{RAPIDAPI_HOST}/api/instagram/posts"
            payload = {"username": username, "maxId": ""}
            
            logger.info(f"V2: Fetching posts for {username}")
            
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
                
                logger.info(f"V2: Found {len(posts_list)} posts for {username}")
                
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
                                
                                # چک کن قبلاً ذخیره شده؟
                                if not get_cached_media(reel_key):
                                    set_cached_media(reel_key, reel_result, ttl_seconds=86400)  # 24 ساعت
                                    await save_media_to_channel(context, reel_key, reel_result)
                
                result_data = {
                    "items": items,
                    "next_max_id": "",
                    "username": username
                } if items else None
                
                # ذخیره لیست ریل‌ها در کش
                if result_data:
                    set_cached_media(reels_key, result_data, ttl_seconds=3600)  # 1 ساعت
                    if context:
                        await save_media_to_channel(context, reels_key, result_data)
                
                return result_data
                
    except asyncio.TimeoutError:
        logger.error(f"Timeout error for {username}")
        return None
    except Exception as e:
        logger.error(f"Error in get_user_reels_v2 for {username}: {e}")
        return None


async def get_instagram_highlights(username: str, context=None):
    """دریافت لیست هایلایت‌های کاربر با کش"""
    
    highlights_key = f"highlights:{username}"
    
    # چک کش
    cached = get_cached_media(highlights_key)
    if cached:
        logger.info(f"📦 لیست هایلایت‌های {username} از Redis کش برگردانده شد")
        return cached
    
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
                
                # ذخیره در کش
                if highlights:
                    set_cached_media(highlights_key, highlights, ttl_seconds=21600)  # 6 ساعت
                    if context:
                        await save_media_to_channel(context, highlights_key, highlights)
                
                return highlights
                
    except Exception as e:
        logger.error(f"Error getting highlights: {e}")
        return []
