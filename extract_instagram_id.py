import re

def extract_instagram_id(url_or_text: str) -> dict:
    patterns = {
        'post': r'instagram\.com/p/([A-Za-z0-9_-]+)',
        'reel': r'instagram\.com/reel/([A-Za-z0-9_-]+)',
        'tv': r'instagram\.com/tv/([A-Za-z0-9_-]+)',
    }
    
    for media_type, pattern in patterns.items():
        match = re.search(pattern, url_or_text)
        if match:
            return {
                'type': media_type,
                'id': match.group(1),
                'full_id': f"{media_type}:{match.group(1)}"
            }
    return None
