# rapidapi_service.py
import requests
from config import RAPIDAPI_KEY, RAPIDAPI_HOST


def get_instagram_media(post_url: str) -> list | None:
    """
    لیست تمام media های یه پست اینستاگرام رو برمیگردونه.
    هر آیتم: {"type": "video"/"photo", "url": "..."}
    """
    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/links"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(api_url, json={"url": post_url}, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, list) or not data:
            return None

        result = []

        for item in data:
            urls = item.get("urls", [])
            picture_url = item.get("pictureUrl")

            if urls:
                # ویدئو — بهترین کیفیت
                best = max(urls, key=lambda x: x.get("quality", 0))
                result.append({
                    "type": "video",
                    "url": best["url"]
                })
            elif picture_url:
                # عکس
                result.append({
                    "type": "photo",
                    "url": picture_url
                })

        return result if result else None

    except requests.exceptions.Timeout:
        print("⏱ RapidAPI timeout")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error از RapidAPI: {e}")
        return None
    except Exception as e:
        print(f"❌ خطا در RapidAPI: {e}")
        return None
