# rapidapi_service.py
import requests
from config import RAPIDAPI_KEY, RAPIDAPI_HOST


def get_instagram_video_url(post_url: str) -> str | None:
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

        # data یه list هست — اولین آیتم رو میگیریم
        if not isinstance(data, list) or not data:
            print("❌ Response خالی یا غیرمنتظره بود")
            return None

        item = data[0]

        # بهترین کیفیت رو پیدا میکنیم
        urls = item.get("urls", [])
        if not urls:
            print("❌ هیچ URL ویدئویی پیدا نشد")
            return None

        # بالاترین کیفیت رو انتخاب میکنیم
        best = max(urls, key=lambda x: x.get("quality", 0))
        return best.get("url")

    except requests.exceptions.Timeout:
        print("⏱ RapidAPI timeout")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP Error از RapidAPI: {e}")
        return None
    except Exception as e:
        print(f"❌ خطا در RapidAPI: {e}")
        return None
