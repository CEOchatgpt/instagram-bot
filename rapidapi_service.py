# rapidapi_service.py - نسخه با پشتیبانی از channel و بهبود یافته

import re
import aiohttp
import asyncio
import json
import logging
from config import RAPIDAPI_KEY, RAPIDAPI_HOST
from database import redis_client 
from channel_cache import get_profile_from_channel, save_profile_to_channel, get_media_from_channel, save_media_to_channel

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1


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


async def get_instagram_profile(username: str, context=None):
    """دریافت پروفایل - کش دو لایه (Redis + کانال تلگرام)"""
    
    # لایه 1: کش Redis (سریع، موقت)
    cached = get_cached_profile(username)
    if cached:
        logger.info(f"📦 پروفایل {username} از Redis کش برگردانده شد")
        return cached
    
    # لایه 2: کش دائمی (کانال تلگرام) - فقط اگه context وجود داشته باشه
    if context:
        try:
            from channel_cache import get_profile_from_channel
            channel_cached = await get_profile_from_channel(context, username)
            if channel_cached:
                logger.info(f"🏦 پروفایل {username} از کانال دیتابیس برگردانده شد")
                # ذخیره در Redis برای دفعات بعد
                set_cached_profile(username, channel_cached, ttl_seconds=3600)
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن از کانال دیتابیس: {e}")
    
    # لایه 3: API (فقط برای محتوای جدید)
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
                
                # ذخیره در کش Redis
                set_cached_profile(username, profile, ttl_seconds=3600)
                
                # ذخیره در کانال تلگرام (دائمی) - فقط اگه context وجود داشته باشه
                if context:
                    try:
                        from channel_cache import save_profile_to_channel
                        await save_profile_to_channel(context, username, profile)
                    except Exception as e:
                        logger.warning(f"خطا در ذخیره در کانال دیتابیس: {e}")
                
                return profile
                
    except Exception as e:
        logger.error(f"Error in get_instagram_profile: {e}")
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


async def get_instagram_media(post_url: str, context=None) -> dict | None:
    """دریافت محتوای پست - کش دو لایه (Redis + کانال تلگرام)"""
    
    if not post_url or "instagram.com" not in post_url:
        return None
    
    # لایه 1: کش Redis (سریع، موقت)
    cached = get_cached_media(post_url)
    if cached:
        logger.info(f"📦 مدیا {post_url[:50]}... از Redis کش برگردانده شد")
        return cached
    
    # لایه 2: کش دائمی (کانال تلگرام)
    if context:
        try:
            channel_cached = await get_media_from_channel(context, post_url)
            if channel_cached:
                logger.info(f"🏦 مدیا {post_url[:50]}... از کانال دیتابیس برگردانده شد")
                # ذخیره در Redis برای دفعات بعد
                set_cached_media(post_url, channel_cached, ttl_seconds=7200)
                return channel_cached
        except Exception as e:
            logger.warning(f"خطا در خواندن مدیا از کانال: {e}")
    
    # لایه 3: API (فقط برای محتوای جدید)
    logger.info(f"🌐 مدیا {post_url[:50]}... در کش نبود - ارسال درخواست به API")
    
    # تشخیص استوری
    story_match = re.search(r'instagram\.com/stories/([^/]+)/?(\d+)?', post_url)
    if story_match:
        result = await get_instagram_story(story_match.group(1), story_match.group(2))
        if result and result.get("items"):
            if context:
                await save_media_to_channel(context, post_url, result)
            set_cached_media(post_url, result, ttl_seconds=7200)
        return result
    
    # تشخیص هایلایت
    highlight_match = re.search(r'instagram\.com/stories/highlights/([^/]+)/?', post_url)
    if highlight_match:
        clean_id = highlight_match.group(1)
        highlight_url = f"https://www.instagram.com/stories/highlights/{clean_id}/"
        return await get_instagram_media(highlight_url, context)
    
    # API اصلی برای لینک‌های معمولی
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
    
    # ذخیره در هر دو لایه کش
    if result:
        set_cached_media(post_url, result, ttl_seconds=7200)  # Redis
        if context:
            await save_media_to_channel(context, post_url, result)  # کانال تلگرام
    
    return result
    

async def get_instagram_highlight_stories(highlight_id: str, username: str = None, title: str = "Highlight", context=None):
    clean_id = highlight_id
    if highlight_id and ":" in str(highlight_id):
        clean_id = str(highlight_id).split(":")[-1]
    
    highlight_url = f"https://www.instagram.com/stories/highlights/{clean_id}/"
    logger.info(f"Fetching highlight: {highlight_url}")
    
    return await get_instagram_media(highlight_url, context)


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


async def get_user_reels_v2(username: str):
    """دریافت ریل‌ها از endpoint posts"""
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
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
                            
                            items.append({
                                "id": post.get("id", ""),
                                "url": video_url,
                                "caption": caption_text[:200],
                                "like_count": post.get("like_count", 0),
                                "comment_count": post.get("comment_count", 0),
                                "play_count": post.get("play_count", 0),
                            })
                
                logger.info(f"V2 - Found {len(items)} reels for {username}")
                
                return {
                    "items": items,
                    "next_max_id": "",
                    "username": username
                } if items else None
                
    except asyncio.TimeoutError:
        logger.error(f"Timeout error for {username}")
        return None
    except Exception as e:
        logger.error(f"Error in get_user_reels_v2 for {username}: {e}")
        return None

async def check_and_get_stories(username: str):
    """بررسی و دریافت استوری‌های کاربر"""
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
                
                return items if items else None
                
    except Exception as e:
        logger.error(f"Error checking stories for {username}: {e}")
        return None

# اینا برای اضافه کردن کش به سرور هست تا از درخواست های مصرفی جلوگیری بشه
def get_cached_profile(username: str):
    """دریافت پروفایل از کش"""
    if not redis_client:
        return None
    key = f"cache:profile:{username}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None

def set_cached_profile(username: str, profile_data: dict, ttl_seconds: int = 3600):
    """ذخیره پروفایل در کش (پیشفرض ۱ ساعت)"""
    if not redis_client:
        return
    key = f"cache:profile:{username}"
    redis_client.setex(key, ttl_seconds, json.dumps(profile_data))
    logger.info(f"✅ پروفایل {username} در کش ذخیره شد (TTL: {ttl_seconds}s)")

def get_cached_media(media_url: str):
    """دریافت مدیا از کش"""
    if not redis_client:
        return None
    # تبدیل لینک به یک کلید ساده
    import hashlib
    key_hash = hashlib.md5(media_url.encode()).hexdigest()
    key = f"cache:media:{key_hash}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return None

def set_cached_media(media_url: str, media_data: dict, ttl_seconds: int = 7200):
    """ذخیره مدیا در کش (پیشفرض ۲ ساعت)"""
    if not redis_client:
        return
    import hashlib
    key_hash = hashlib.md5(media_url.encode()).hexdigest()
    key = f"cache:media:{key_hash}"
    redis_client.setex(key, ttl_seconds, json.dumps(media_data))
    logger.info(f"✅ مدیا در کش ذخیره شد (TTL: {ttl_seconds}s)")

# ========== توابع کمکی برای مدیا کش دو لایه ==========

async def get_media_from_channel(context, media_url: str):
    """بازیابی مدیا از کانال تلگرام"""
    from config import DATABASE_CHANNEL_ID
    if not DATABASE_CHANNEL_ID or not context:
        return None
    
    if not redis_client:
        return None
    
    try:
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        key = f"channel_media:{url_hash}"
        message_id = redis_client.get(key)
        
        if not message_id:
            return None
        
        message_id = int(message_id)
        
        msg = await context.bot.forward_message(
            chat_id=DATABASE_CHANNEL_ID,
            from_chat_id=DATABASE_CHANNEL_ID,
            message_id=message_id
        )
        
        if msg.text and "📦" in msg.text:
            start = msg.text.find("{")
            end = msg.text.rfind("}")
            if start != -1 and end != -1:
                json_str = msg.text[start:end+1]
                data = json.loads(json_str)
                return data.get("data")
                
    except Exception as e:
        logger.warning(f"خطا در بازیابی مدیا از کانال: {e}")
        if redis_client:
            url_hash = hashlib.md5(media_url.encode()).hexdigest()
            redis_client.delete(f"channel_media:{url_hash}")
        return None
    
    return None

async def save_media_to_channel(context, media_url: str, media_data: dict):
    """ذخیره مدیا در کانال تلگرام"""
    from config import DATABASE_CHANNEL_ID
    if not DATABASE_CHANNEL_ID or not context:
        return None
    
    try:
        url_hash = hashlib.md5(media_url.encode()).hexdigest()
        
        # چک کن قبلاً ذخیره شده؟
        if redis_client and redis_client.exists(f"channel_media:{url_hash}"):
            logger.info(f"📦 مدیا قبلاً در کانال ذخیره شده، اسکیپ")
            return None
        
        message_data = {
            "type": "media",
            "url": media_url,
            "data": media_data,
            "hash": url_hash,
            "created_at": time.time()
        }
        
        message_text = f"📦 #MEDIA_{url_hash[:8]}\n{json.dumps(message_data, ensure_ascii=False)}"
        
        msg = await context.bot.send_message(
            chat_id=DATABASE_CHANNEL_ID,
            text=message_text[:4090],
            disable_web_page_preview=True
        )
        
        if redis_client:
            redis_client.setex(f"channel_media:{url_hash}", 2592000, str(msg.message_id))
        
        logger.info(f"✅ مدیا در کانال دیتابیس ذخیره شد (message_id: {msg.message_id})")
        return msg.message_id
        
    except Exception as e:
        logger.error(f"❌ خطا در ذخیره مدیا در کانال: {e}")
        return None


