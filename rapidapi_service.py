# rapidapi_service.py
import requests
import re
from config import RAPIDAPI_KEY, RAPIDAPI_HOST


def extract_shortcode(url: str) -> str | None:
    """
    shortcode رو از لینک اینستاگرام استخراج میکنه
    مثال: instagram.com/reel/DVhgP23DSZ2/ → DVhgP23DSZ2
    """
    pattern = r'instagram\.com/(?:reel|p|tv)/([A-Za-z0-9_-]+)'
    match = re.search(pattern, url)
    return match.group(1) if match else None


def get_instagram_video_url(post_url: str) -> str | None:
    """
    لینک مستقیم ویدئوی اینستاگرام رو از RapidAPI میگیره.
    """
    shortcode = extract_shortcode(post_url)
    if not shortcode:
        print(f"❌ نتونستم shortcode رو از لینک استخراج کنم: {post_url}")
        return None

    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/mediaByShortcode"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }

    payload = {"shortcode": shortcode}

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        # پیدا کردن URL ویدئو توی response
        video_url = (
            data.get("video_url") or
            data.get("url") or
            _deep_find_video_url(data)
        )

        return video_url

    except requests.exceptions.Timeout:
        print("⏱ RapidAPI timeout")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error از RapidAPI: {e}")
        return None
    except Exception as e:
        print(f"❌ خطا در RapidAPI: {e}")
        return None


def _deep_find_video_url(data) -> str | None:
    """
    توی response به دنبال video_url میگرده (چون ساختار API ممکنه تودرتو باشه)
    """
    if isinstance(data, dict):
        for key, value in data.items():
            if key == "video_url" and isinstance(value, str) and value.startswith("http"):
                return value
            result = _deep_find_video_url(value)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _deep_find_video_url(item)
            if result:
                return result
    return None
