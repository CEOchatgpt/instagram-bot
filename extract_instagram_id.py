# extract_instagram_id.py
import re

def extract_instagram_id(url_or_text: str) -> dict:
    """
    استخراج شناسه یکتا از لینک اینستاگرام
    """
    patterns = {
        'post': r'instagram\.com/p/([A-Za-z0-9_-]+)',
        'reel': r'instagram\.com/reel/([A-Za-z0-9_-]+)',
        'tv': r'instagram\.com/tv/([A-Za-z0-9_-]+)',
        'story': r'instagram\.com/stories/([^/]+)/(\d+)',
        'highlight': r'instagram\.com/stories/highlights/(\d+)',
    }
    
    # پست، ریل، tv
    for media_type, pattern in patterns.items():
        match = re.search(pattern, url_or_text)
        if match:
            if media_type in ['post', 'reel', 'tv']:
                return {
                    'type': media_type,
                    'id': match.group(1),
                    'full_id': f"{media_type}:{match.group(1)}"
                }
            elif media_type == 'story':
                return {
                    'type': 'story',
                    'username': match.group(1),
                    'story_id': match.group(2),
                    'full_id': f"story:{match.group(1)}:{match.group(2)}"
                }
            elif media_type == 'highlight':
                return {
                    'type': 'highlight',
                    'id': match.group(1),
                    'full_id': f"highlight:{match.group(1)}"
                }
    
    return None


def normalize_url(url: str) -> str:
    """
    نرمال‌سازی لینک برای ایجاد کلید یکسان
    """
    extracted = extract_instagram_id(url)
    if extracted:
        return extracted['full_id']
    
    # حذف پارامترهای اضافی
    clean_url = re.sub(r'\?.*$', '', url)
    clean_url = re.sub(r'/$', '', clean_url)
    return clean_url
