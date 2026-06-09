# rapidapi_service.py
import requests
from config import RAPIDAPI_KEY, RAPIDAPI_HOST


def get_instagram_video_url(post_url: str) -> str | None:
    """
    لینک مستقیم ویدئوی اینستاگرام رو از RapidAPI میگیره.
    هیچ فایلی دانلود نمیشه — فقط URL برمیگرده.
    """
    api_url = f"https://{RAPIDAPI_HOST}/video-info"

    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": RAPIDAPI_HOST
    }

    params = {"url": post_url}

    try:
        response = requests.get(api_url, headers=headers, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()

        # لینک مستقیم ویدئو رو پیدا میکنیم
        # (ساختار response بستگی به API داره — اینجا رایج‌ترین حالت)
        video_url = (
            data.get("video_url") or
            data.get("url") or
            data.get("download_url") or
            (data.get("videos", [{}])[0].get("url") if data.get("videos") else None)
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
