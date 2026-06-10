# rapidapi_service.py

import aiohttp  # کتابخونه‌ای برای درخواست‌های HTTP به صورت async (غیر blocking)
import asyncio  # برای استفاده از asyncio.sleep در فاصله بین retry‌ها
from config import RAPIDAPI_KEY, RAPIDAPI_HOST  # کلید API و آدرس سرویس رو از فایل تنظیمات میخونه

MAX_RETRIES = 3   # حداکثر تعداد دفعاتی که دوباره امتحان میکنه
RETRY_DELAY = 1   # تاخیر اولیه به ثانیه — هر بار دو برابر میشه (1 → 2 → 4)


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

    try:
        # یه session HTTP باز میکنه — مثل باز کردن یه اتصال به اینترنت
        async with aiohttp.ClientSession() as session:

            # درخواست POST میزنه و منتظر جواب میمونه (بدون block کردن بقیه)
            async with session.post(
                api_url,                              # آدرس API
                json={"url": post_url},               # لینک اینستاگرام رو توی body میفرسته
                headers=headers,                      # هدرهای احراز هویت
                timeout=aiohttp.ClientTimeout(total=15),  # اگه تا ۱۵ ثانیه جواب نداد، timeout میده
            ) as response:
                response.raise_for_status()           # اگه کد خطا (4xx یا 5xx) برگشت، exception میندازه
                data = await response.json()          # جواب JSON رو به صورت async میخونه و parse میکنه

        # چک میکنه جواب API یه لیست باشه و خالی نباشه
        if not isinstance(data, list) or not data:
            return None  # اگه داده‌ای نبود، None برمیگردونه

        # کپشن رو از اولین آیتم لیست میخونه و یه پیشوند بهش اضافه میکنه
        raw_caption = "تق ✅\n\n" + data[0].get("meta", {}).get("title", "")

        # اگه کپشن از ۱۰۲۴ کاراکتر (حداکثر تلگرام) بیشتر بود، کوتاهش میکنه
        if len(raw_caption) > 1024:
            # تا کاراکتر ۱۰۲۰ میره و بعد از آخرین فاصله برش میده تا کلمه‌ای نصف نشه
            cut = raw_caption[:1020].rsplit(" ", 1)[0]
            caption = cut + " ..."  # سه نقطه اضافه میکنه که معلوم باشه ادامه داره
        else:
            caption = raw_caption  # اگه کوتاهه، همونطوری استفاده میکنه

        items = []  # لیست خالی برای نگه داشتن مدیاهایی که پیدا میکنیم

        # روی همه آیتم‌های جواب API حلقه میزنه (هر آیتم = یه اسلاید از پست)
        for item in data:
            urls = item.get("urls", [])          # لیست لینک‌های ویدیو (با کیفیت‌های مختلف)
            picture_url = item.get("pictureUrl") # لینک عکس (اگه ویدیو نباشه)

            if urls:
                # بهترین کیفیت ویدیو رو انتخاب میکنه (عدد quality بزرگتر = کیفیت بهتر)
                best = max(urls, key=lambda x: x.get("quality", 0))
                items.append({"type": "video", "url": best["url"]})  # به لیست اضافه میکنه
            elif picture_url:
                # اگه ویدیو نبود ولی عکس بود، عکس رو اضافه میکنه
                items.append({"type": "photo", "url": picture_url})

        # اگه چیزی پیدا شد dict برمیگردونه، وگرنه None
        return {"caption": caption, "items": items} if items else None

    except aiohttp.ClientResponseError as e:
        # وقتی سرور کد خطا (مثلاً ۴۰۳ یا ۵۰۰) برمیگردونه
        print(f"❌ HTTP Error از RapidAPI: {e.status} {e.message}")
        return None
    except TimeoutError:
        # وقتی API تا ۱۵ ثانیه جواب نداد
        print("⏱ RapidAPI timeout")
        return None
    except Exception as e:
        # هر خطای دیگه‌ای که پیش بیاد
        print(f"❌ خطا در RapidAPI: {e}")
        return None
