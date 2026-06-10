# rapidapi_service.py

import re       # برای کار با عبارات منظم (پیدا کردن هشتگ‌ها و لینک‌ها)
import aiohttp  # کتابخونه‌ای برای درخواست‌های HTTP به صورت async (غیر blocking)
import asyncio  # برای استفاده از asyncio.sleep در فاصله بین retry‌ها
from config import RAPIDAPI_KEY, RAPIDAPI_HOST  # کلید API و آدرس سرویس رو از فایل تنظیمات میخونه

MAX_RETRIES = 3   # حداکثر تعداد دفعاتی که دوباره امتحان میکنه
RETRY_DELAY = 1   # تاخیر اولیه به ثانیه — هر بار دو برابر میشه (1 → 2 → 4)


import re

def format_caption(raw: str, username: str = None, post_url: str = None) -> str:
    """
    کپشن پیشرفته و زیبا — شبیه به استایل دلخواهت
    """
    if not raw:
        raw = ""

    # تمیز کردن متن
    text = re.sub(r'https?://\S+', '', raw)   # حذف لینک‌های داخل کپشن
    hashtags = re.findall(r'#\w+', text)
    text = re.sub(r'#\w+', '', text).strip()

    # ساخت کپشن نهایی با فرمت زیبا
    lines = []

    lines.append("📸 <b>پست اینستاگرام</b>")

    if username:
        lines.append(f"👤 <b>@{username}</b>")

    if text:
        # متن اصلی رو داخل یه بلاک نقل قول مثل قرار میدیم
        lines.append("")
        lines.append(f"<i>{text}</i>")   # ایتالیک برای زیبایی بیشتر

    if hashtags:
        hashtag_line = " ".join(hashtags)
        lines.append("")
        lines.append(f"<code>{hashtag_line}</code>")   # هشتگ‌ها رو تو کد بولد نشون بده

    # لینک منبع (Source)
    if post_url:
        lines.append("")
        lines.append(f"🔗 <a href='{post_url}'>Source</a>")

    caption = "\n".join(lines)

    # محدود کردن طول (تلگرام حداکثر ۱۰۲۴ کاراکتر)
    if len(caption) > 1024:
        caption = caption[:1010] + "\n\n..."

    return caption
    
# این تابع async هست، یعنی وقتی منتظر جواب API‌ه، بقیه کاربرا رو block نمیکنه
async def get_instagram_media(post_url: str) -> dict | None:
    """
    media های پست + کپشن رو برمیگردونه.
    خروجی: {"caption": "...", "items": [{"type": "video"/"photo", "url": "..."}]}
    """

    # آدرس کامل endpoint ای که باید بهش درخواست بزنیم رو میسازه
    api_url = f"https://{RAPIDAPI_HOST}/api/instagram/links"

    # هدرهایی که باید با هر درخواست بفرستیم تا RapidAPI بفهمه کی هستیم
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,       # کلید احراز هویت ما
        "X-RapidAPI-Host": RAPIDAPI_HOST,      # آدرس هاست API
        "Content-Type": "application/json",    # میگه که body درخواست JSON‌ه
    }

    data = None  # متغیر برای نگه داشتن جواب API — بیرون از حلقه تعریف میشه

    # حلقه retry — اگه خطا بخوره، تا MAX_RETRIES بار دوباره امتحان میکنه
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # یه session HTTP باز میکنه — مثل باز کردن یه اتصال به اینترنت
            async with aiohttp.ClientSession() as session:

                # درخواست POST میزنه و منتظر جواب میمونه (بدون block کردن بقیه)
                async with session.post(
                    api_url,                                   # آدرس API
                    json={"url": post_url},                    # لینک اینستاگرام رو توی body میفرسته
                    headers=headers,                           # هدرهای احراز هویت
                    timeout=aiohttp.ClientTimeout(total=15),   # اگه تا ۱۵ ثانیه جواب نداد، timeout میده
                ) as response:
                    response.raise_for_status()                # اگه کد خطا (4xx یا 5xx) برگشت، exception میندازه
                    data = await response.json()               # جواب JSON رو به صورت async میخونه و parse میکنه

            # اگه به اینجا رسیدیم یعنی درخواست موفق بود — از حلقه retry خارج میشیم
            break

        except aiohttp.ClientResponseError as e:
            # خطای 4xx (مثل 403 forbidden یا 404 not found) — retry فایده نداره، همین الان برمیگردیم
            if e.status < 500:
                print(f"❌ HTTP {e.status} از RapidAPI — retry نمیکنیم: {e.message}")
                return None

            # خطای 5xx (مثل 500 یا 503) — سرور مشکل داره، ارزش داره دوباره امتحان کنیم
            print(f"⚠️ HTTP {e.status} از RapidAPI — تلاش {attempt}/{MAX_RETRIES}")

        except (TimeoutError, aiohttp.ServerConnectionError):
            # timeout یا قطعی اتصال — ممکنه موقتی باشه، دوباره امتحان میکنیم
            print(f"⏱ خطای اتصال — تلاش {attempt}/{MAX_RETRIES}")

        except Exception as e:
            # هر خطای غیرمنتظره دیگه‌ای — retry فایده نداره
            print(f"❌ خطای ناشناخته: {e}")
            return None

        # اگه هنوز retry داریم، به اندازه delay صبر میکنیم (exponential backoff)
        if attempt < MAX_RETRIES:
            delay = RETRY_DELAY * (2 ** (attempt - 1))  # تلاش ۱: ۱s — تلاش ۲: ۲s — تلاش ۳: ۴s
            print(f"🔁 {delay} ثانیه صبر میکنیم...")
            await asyncio.sleep(delay)  # async sleep — بقیه کاربرا رو block نمیکنه
        else:
            # همه retry‌ها تموم شد و هنوز موفق نشدیم
            print("❌ همه تلاش‌ها ناموفق بود.")
            return None

    # چک میکنه جواب API یه لیست باشه و خالی نباشه
    if not isinstance(data, list) or not data:
        return None  # اگه داده‌ای نبود، None برمیگردونه

    # کپشن خام رو از اولین آیتم میخونه و به تابع format_caption میده تا تمیزش کنه
    raw_caption = data[0].get("meta", {}).get("title", "")
    caption = format_caption(raw_caption)

    items = []  # لیست خالی برای نگه داشتن مدیاهایی که پیدا میکنیم

    # روی همه آیتم‌های جواب API حلقه میزنه (هر آیتم = یه اسلاید از پست)
    for item in data:
        urls = item.get("urls", [])           # لیست لینک‌های ویدیو (با کیفیت‌های مختلف)
        picture_url = item.get("pictureUrl")  # لینک عکس (اگه ویدیو نباشه)

        if urls:
            # بهترین کیفیت ویدیو رو انتخاب میکنه (عدد quality بزرگتر = کیفیت بهتر)
            best = max(urls, key=lambda x: x.get("quality", 0))
            items.append({"type": "video", "url": best["url"]})  # به لیست اضافه میکنه
        elif picture_url:
            # اگه ویدیو نبود ولی عکس بود، عکس رو اضافه میکنه
            items.append({"type": "photo", "url": picture_url})

    # اگه چیزی پیدا شد dict برمیگردونه، وگرنه None
    return {"caption": caption, "items": items} if items else None
