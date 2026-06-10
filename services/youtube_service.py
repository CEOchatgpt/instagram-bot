"""
سرویس دانلود ویدیو از یوتیوب برای ربات اینستاگرام
@author: CEOchatgpt
@date: June 2026
"""

import os
import re
import asyncio
from pathlib import Path
from typing import Optional, Dict, Tuple
import yt_dlp
from datetime import datetime

class YouTubeDownloader:
    """کلاس اصلی دانلودر یوتیوب"""
    
    def __init__(self, download_path: str = "downloads"):
        """
        راه‌اندازی دانلودر
        
        Args:
            download_path: مسیر ذخیره فایل‌های دانلود شده
        """
        self.download_path = Path(download_path)
        self.download_path.mkdir(exist_ok=True)
        
        # تنظیمات پایه yt-dlp
        self.base_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'force_generic_extractor': False,
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'logtostderr': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def is_youtube_url(self, url: str) -> bool:
        """بررسی معتبر بودن لینک یوتیوب"""
        youtube_patterns = [
            r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/',
            r'(https?://)?(www\.)?(m\.youtube\.com)/',
            r'(https?://)?(www\.)?(music\.youtube\.com)/'
        ]
        return any(re.match(pattern, url) for pattern in youtube_patterns)
    
    def get_video_info(self, url: str) -> Optional[Dict]:
        """
        دریافت اطلاعات ویدیو بدون دانلود
        
        Returns:
            دیکشنری شامل عنوان، مدت زمان، سایز، کیفیت‌های موجود
        """
        try:
            with yt_dlp.YoutubeDL(self.base_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'views': info.get('view_count', 0),
                    'uploader': info.get('uploader', 'Unknown'),
                    'upload_date': info.get('upload_date', 'Unknown'),
                    'thumbnail': info.get('thumbnail', ''),
                    'formats': [{
                        'quality': f.get('height', 'audio'),
                        'ext': f.get('ext', 'unknown'),
                        'filesize': f.get('filesize', 0),
                        'format_note': f.get('format_note', '')
                    } for f in info.get('formats', []) if f.get('height') or f.get('acodec') != 'none']
                }
        except Exception as e:
            print(f"خطا در دریافت اطلاعات: {e}")
            return None
    
    def download_video(
        self, 
        url: str, 
        quality: str = 'best',
        custom_name: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """
        دانلود ویدیو از یوتیوب
        
        Args:
            url: لینک ویدیو
            quality: کیفیت مورد نظر (best, 2160, 1440, 1080, 720, 480, 360, audio)
            custom_name: نام دلخواه برای فایل (بدون پسوند)
            
        Returns:
            (موفقیت, پیام, مسیر فایل)
        """
        try:
            # تنظیم نام فایل
            if custom_name:
                filename = f"{custom_name}_%(title)s.%(ext)s"
            else:
                filename = f"youtube_%(title)s_{datetime.now().strftime('%Y%m%d_%H%M%S')}.%(ext)s"
            
            # تنظیمات کیفیت
            quality_opts = self._get_quality_settings(quality)
            
            # ترکیب تنظیمات
            ydl_opts = {
                **self.base_opts,
                **quality_opts,
                'outtmpl': str(self.download_path / filename)
            }
            
            # دانلود
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                print(f"شروع دانلود: {url}")
                info = ydl.extract_info(url, download=True)
                
                # پیدا کردن مسیر فایل دانلود شده
                downloaded_file = ydl.prepare_filename(info)
                
                # اگر فایل با پسوند متفاوت ذخیره شده
                if not os.path.exists(downloaded_file):
                    for ext in ['.mp4', '.webm', '.mkv', '.m4a']:
                        test_path = downloaded_file + ext
                        if os.path.exists(test_path):
                            downloaded_file = test_path
                            break
                
                return True, f"✅ دانلود موفق: {info.get('title', 'ویدیو')}", downloaded_file
                
        except Exception as e:
            return False, f"❌ خطا در دانلود: {str(e)}", ""
    
    def _get_quality_settings(self, quality: str) -> Dict:
        """تنظیمات کیفیت بر اساس ورودی کاربر"""
        quality_map = {
            'best': {
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4'
            },
            '2160': {
                'format': 'bestvideo[height<=2160]+bestaudio/best[height<=2160]',
                'merge_output_format': 'mp4'
            },
            '1440': {
                'format': 'bestvideo[height<=1440]+bestaudio/best[height<=1440]',
                'merge_output_format': 'mp4'
            },
            '1080': {
                'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                'merge_output_format': 'mp4'
            },
            '720': {
                'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                'merge_output_format': 'mp4'
            },
            '480': {
                'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
                'merge_output_format': 'mp4'
            },
            '360': {
                'format': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
                'merge_output_format': 'mp4'
            },
            'audio': {
                'format': 'bestaudio/best',
                'extractaudio': True,
                'audioformat': 'mp3',
                'outtmpl': str(self.download_path / '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            }
        }
        
        return quality_map.get(quality, quality_map['best'])
    
    def download_playlist(self, url: str, max_videos: int = 10) -> List[Tuple[bool, str, str]]:
        """دانلود پلی‌لیست یوتیوب"""
        results = []
        
        ydl_opts = {
            **self.base_opts,
            'format': 'best[height<=720]',
            'outtmpl': str(self.download_path / '%(playlist_title)s/%(title)s.%(ext)s'),
            'playlistend': max_videos
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                results.append((True, f"پلی‌لیست {info.get('title', '')} دانلود شد", str(self.download_path)))
        except Exception as e:
            results.append((False, f"خطا: {e}", ""))
        
        return results
    
    def clean_old_files(self, hours: int = 24):
        """پاکسازی فایل‌های قدیمی"""
        import time
        now = time.time()
        
        for file in self.download_path.glob("*"):
            if file.is_file():
                file_age_hours = (now - file.stat().st_mtime) / 3600
                if file_age_hours > hours:
                    file.unlink()
                    print(f"فایل قدیمی حذف شد: {file.name}")


# تابع کمکی سریع برای استفاده در bot.py
def quick_download(url: str, quality: str = '720') -> Tuple[bool, str, str]:
    """دانلود سریع با تنظیمات پیش‌فرض"""
    downloader = YouTubeDownloader()
    return downloader.download_video(url, quality)
