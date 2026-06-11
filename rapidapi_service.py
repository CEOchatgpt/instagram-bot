# rapidapi_service.py - نسخه کامل با تمام قابلیت‌های RapidAPI

import re
import aiohttp
import asyncio
from typing import Dict, Any, Optional
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


class RapidAPIInstagram:
    def __init__(self):
        self.headers = {
            "X-RapidAPI-Key": RAPIDAPI_KEY,
            "X-RapidAPI-Host": RAPIDAPI_HOST,
            "Content-Type": "application/json",
        }
        self.base_url = f"https://{RAPIDAPI_HOST}/api/instagram"

    async def _request(self, method: str, endpoint: str, json_data: Dict = None) -> Dict | None:
        url = f"{self.base_url}/{endpoint}"
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with aiohttp.ClientSession() as session:
                    if method == "POST":
                        async with session.post(url, json=json_data, headers=self.headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                            resp.raise_for_status()
                            return await resp.json()
                    else:
                        async with session.get(url, headers=self.headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                            resp.raise_for_status()
                            return await resp.json()
            except Exception as e:
                if attempt == MAX_RETRIES:
                    print(f"❌ خطا در {endpoint}: {e}")
                    return None
                await asyncio.sleep(RETRY_DELAY * (2 ** (attempt - 1)))
        return None

    # ==================== توابع اصلی ====================

    async def get_links(self, url: str) -> Dict | None:
        """روش فعلی - برای پست و ریلز معمولی"""
        data = await self._request("POST", "links", {"url": url})
        return self._process_links_response(data)

    async def get_posts(self, username: str, max_id: str = "") -> Dict | None:
        data = await self._request("POST", "posts", {"username": username, "maxId": max_id})
        return data

    async def get_reels(self, username: str, max_id: str = "") -> Dict | None:
        data = await self._request("POST", "reels", {"username": username, "maxId": max_id})
        return data

    async def get_stories(self, username: str) -> Dict | None:
        return await self._request("POST", "stories", {"username": username})

    async def get_story(self, username: str, story_id: str) -> Dict | None:
        return await self._request("POST", "story", {"username": username, "storyId": story_id})

    async def get_highlights(self, username: str) -> Dict | None:
        return await self._request("POST", "highlights", {"username": username})

    async def get_highlight_stories(self, highlight_id: str) -> Dict | None:
        return await self._request("POST", "highlightStories", {"highlightId": highlight_id})

    async def get_profile(self, username: str) -> Dict | None:
        return await self._request("POST", "profile", {"username": username})

    async def get_user_info(self, username: str) -> Dict | None:
        return await self._request("POST", "userInfo", {"username": username})

    async def get_media_by_shortcode(self, shortcode: str) -> Dict | None:
        return await self._request("POST", "mediaByShortcode", {"shortcode": shortcode})

    # ==================== پردازش پاسخ ====================
    def _process_links_response(self, data: Any) -> Dict | None:
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

            # تشخیص نوع
            first_url = urls[0]
            ext = first_url.get("extension", "").lower()
            if ext == "mp4" or first_url.get("name", "").upper() == "MP4":
                items.append({"type": "video", "url": best["url"]})
            else:
                items.append({"type": "photo", "url": best["url"]})

        return {"caption": caption, "items": items} if items else None


#インスタンス جهانی
rapid_api = RapidAPIInstagram()


async def get_instagram_media(post_url: str) -> dict | None:
    """هوشمندترین تابع اصلی - تشخیص نوع لینک"""
    
    url = post_url.strip()
    
    # ۱. لینک مستقیم پست / ریلز / کاروسل
    if any(x in url for x in ["/p/", "/reel/", "/tv/", "/feed/"]):
        return await rapid_api.get_links(url)

    # ۲. لینک استوری
    if "/stories/" in url:
        match = re.search(r'/stories/([^/]+)/(\d+)', url)
        if match:
            username, story_id = match.groups()
            return await rapid_api.get_story(username, story_id)
        else:
            username = re.search(r'/stories/([^/]+)', url)
            if username:
                return await rapid_api.get_stories(username.group(1))

    # ۳. لینک پروفایل
    if "/profile/" in url or re.match(r'https?://(?:www\.)?instagram\.com/([^/]+)/?$', url):
        match = re.search(r'instagram\.com/([^/]+)', url)
        if match:
            username = match.group(1).strip('/')
            return await rapid_api.get_profile(username)

    # ۴. لینک هایلایت
    if "/highlight/" in url:
        match = re.search(r'highlight/(\d+)', url)
        if match:
            return await rapid_api.get_highlight_stories(match.group(1))

    # fallback به روش قدیمی
    return await rapid_api.get_links(url)
