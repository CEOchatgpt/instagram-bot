# rapidapi_service.py
import requests
from config import RAPIDAPI_KEY, RAPIDAPI_HOST


def get_instagram_media(post_url: str) -> dict | None:
    """
    media های پست + کپشن رو برمیگردونه.
    خروجی: {"caption": "...", "items": [{"type": "video"/"photo", "url": "..."}]}
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

        # کپشن از اولین آیتم
        raw_caption = "تق ✅\n" + data[0].get("meta", {}).get("title", "")
        # کوتاه کردن کپشن (تلگرام max 1024 کاراکتر برای caption)
        caption = raw_caption[:1020] + "..." if len(raw_caption) > 1024 else raw_caption

        items = []
        for item in data:
            urls = item.get("urls", [])
            picture_url = item.get("pictureUrl")

            if urls:
                best = max(urls, key=lambda x: x.get("quality", 0))
                items.append({"type": "video", "url": best["url"]})
            elif picture_url:
                items.append({"type": "photo", "url": picture_url})

        return {"caption": caption, "items": items} if items else None

    except requests.exceptions.Timeout:
        print("⏱ RapidAPI timeout")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error از RapidAPI: {e}")
        return None
    except Exception as e:
        print(f"❌ خطا در RapidAPI: {e}")
        return None
