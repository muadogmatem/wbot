import os
import re
import time
import json
import shutil
import subprocess
import threading

import requests
from bs4 import BeautifulSoup
from zlapi.models import Message, ThreadType

from src.core.reactions import REACTIONS, ReactionManager


_HERE = os.path.dirname(__file__)
CACHE_DIR = os.path.join(_HERE, "..", "..", "asset", "temp", "download")
AUTO_FILE = os.path.join(_HERE, "..", "..", "asset", "data", "download_auto.json")
os.makedirs(CACHE_DIR, exist_ok=True)

MAX_FILE_MB = 200
URL_RE = re.compile(r"https?://\S+", re.I)

_SUPPORTED_DOMAINS = (
    "tiktok.com", "vt.tiktok.com", "vm.tiktok.com",
    "douyin.com", "v.douyin.com",
    "facebook.com", "fb.watch", "fb.com",
    "youtube.com", "youtu.be",
    "instagram.com",
    "threads.net", "threads.com",
    "twitter.com", "x.com",
    "capcut.com",
    "pinterest.com", "pin.it",
)

_PIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
}

_DOUYIN_HEADERS = {
    "accept": "*/*",
    "accept-language": "vi-VN,vi;q=0.6",
    "cache-control": "no-cache",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "dnt": "1",
    "origin": "https://snaptiktok.to",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://snaptiktok.to/vi/douyin-downloader",
    "sec-ch-ua": '"Chromium";v="148", "Quetta";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36",
    "x-requested-with": "XMLHttpRequest",
}

_THREADS_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "vi-VN,vi;q=0.9",
    "cache-control": "no-cache",
    "dnt": "1",
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-platform": '"Android"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Mobile Safari/537.36"
}

_AUTO_COOLDOWN = {}


def _load_auto():
    try:
        with open(AUTO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"threads": []}


def _save_auto(data):
    os.makedirs(os.path.dirname(AUTO_FILE), exist_ok=True)
    with open(AUTO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_auto_on(tid):
    return str(tid) in _load_auto().get("threads", [])


def toggle_auto(tid):
    data = _load_auto()
    arr = data.setdefault("threads", [])
    tid = str(tid)
    if tid in arr:
        arr.remove(tid)
        enabled = False
    else:
        arr.append(tid)
        enabled = True
    _save_auto(data)
    return enabled


def get_platform_info(url):
    u = (url or "").lower()
    if "threads.net" in u or "threads.com" in u:
        return "Threads", "threads"
    if "douyin.com" in u:
        return "Douyin", "douyin"
    if "tiktok.com" in u:
        return "TikTok", "tiktok"
    if "facebook.com" in u or "fb.watch" in u or "fb.com" in u:
        return "Facebook", "facebook"
    if "youtube.com" in u or "youtu.be" in u:
        return "YouTube", "youtube"
    if "instagram.com" in u:
        return "Instagram", "instagram"
    if "twitter.com" in u or "x.com" in u:
        return "Twitter/X", "twitter"
    if "capcut.com" in u:
        return "CapCut", "capcut"
    if "pinterest.com" in u or "pin.it" in u:
        return "Pinterest", "pinterest"
    return "Video", "video"


def is_pinterest_url(url):
    u = (url or "").lower()
    return "pinterest.com" in u or "pin.it" in u


def is_douyin_url(url):
    u = (url or "").lower()
    return "douyin.com" in u


def is_threads_url(url):
    u = (url or "").lower()
    return "threads.net" in u or "threads.com" in u


def is_supported_link(url):
    u = (url or "").lower()
    return any(d in u for d in _SUPPORTED_DOMAINS)


def _extract_link(text):
    for u in URL_RE.findall(text or ""):
        if is_supported_link(u):
            return u
    return None


def _has_ffmpeg():
    return bool(shutil.which("ffmpeg"))


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def _fmt_duration_ms(seconds):
    try:
        return int(float(seconds or 0) * 1000)
    except Exception:
        return 0


def _get_video_metadata(file_path):
    if not _has_ffmpeg():
        return {"duration": 0, "width": 1080, "height": 1920}
    
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            file_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
        
        duration = 0
        if "format" in data and "duration" in data["format"]:
            duration = float(data["format"]["duration"])
        elif video_stream and "duration" in video_stream:
            duration = float(video_stream["duration"])
        
        width = 1080
        height = 1920
        if video_stream:
            width = int(video_stream.get("width", 1080))
            height = int(video_stream.get("height", 1920))
        
        return {
            "duration": duration,
            "width": width,
            "height": height
        }
        
    except Exception as e:
        print(f"[Download] ffprobe error: {e}")
        return {"duration": 0, "width": 1080, "height": 1920}


def _fetch_threads(url):
    try:
        session = requests.Session()
        response = session.get(url, headers=_THREADS_HEADERS, allow_redirects=True, timeout=15)
        response.raise_for_status()
        
        referer = response.url
        soup = BeautifulSoup(response.text, "html.parser")
        
        title_tag = soup.find("title")
        title = title_tag.text.strip() if title_tag else "Threads"
        
        images = soup.find_all("img", {"src": re.compile(r"https://instagram\..*\.fbcdn\.net/")})
        image_urls = []
        for img in images:
            src = img.get("src")
            if src and "fbcdn.net" in src and "/t51.82787-15/" in src:
                image_urls.append(src)
        
        image_urls = list(dict.fromkeys(image_urls))
        
        videos = soup.find_all("video")
        video_urls = []
        for video in videos:
            src = video.get("src")
            if src and "fbcdn.net" in src:
                video_urls.append(src)
        
        video_urls = list(dict.fromkeys(video_urls))
        
        if video_urls:
            return {
                "type": "video",
                "video_url": video_urls[0],
                "title": title,
                "referer": referer,
            }
        elif image_urls:
            return {
                "type": "image",
                "images": image_urls,
                "title": title,
                "referer": referer,
            }
        
        return None
        
    except Exception as e:
        print(f"[Download] threads error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _fetch_douyin(url):
    try:
        api_url = "https://snaptiktok.to/api/ajaxSearch"
        payload = {
            "q": url,
            "cursor": "0",
            "page": "0",
            "lang": "vi"
        }
        
        response = requests.post(api_url, headers=_DOUYIN_HEADERS, data=payload, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("status") != "ok":
            return None
        
        html_content = data.get("data", "")
        soup = BeautifulSoup(html_content, "html.parser")
        
        title_elem = soup.find("h3")
        title = title_elem.get_text(strip=True) if title_elem else "Douyin"
        
        thumbnail_elem = soup.find("img")
        thumbnail = thumbnail_elem.get("src") if thumbnail_elem else None
        
        links = soup.find_all("a", href=True)
        
        video_url = None
        hd_video_url = None
        audio_url = None
        
        for link in links:
            href = link.get("href", "")
            text = link.get_text(strip=True).lower()
            
            if not href or not text:
                continue
            
            if "mp4 hd" in text:
                hd_video_url = href
            elif ("mp4 [1]" in text or "mp4 [2]" in text) and not video_url:
                video_url = href
            elif "mp3" in text:
                audio_url = href
        
        final_video = hd_video_url or video_url
        
        if not final_video:
            return None
        
        return {
            "type": "video",
            "video_url": final_video,
            "audio_url": audio_url,
            "title": title,
            "author": "Unknown",
            "duration": 0,
            "thumbnail": thumbnail,
        }
        
    except Exception as e:
        print(f"[Download] douyin error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _fetch_tiktok(url):
    for attempt in range(3):
        try:
            r = requests.get("https://www.tikwm.com/api/", params={"url": url}, timeout=15)
            r.raise_for_status()
            j = r.json()
            if j.get("code") == 0 and j.get("data"):
                d = j["data"]
                
                images = d.get("images", [])
                if images and isinstance(images, list) and len(images) > 0:
                    return {
                        "type": "image",
                        "images": images,
                        "audio_url": (d.get("music_info") or {}).get("play") or d.get("music"),
                        "title": d.get("title") or "TikTok",
                        "author": (d.get("author") or {}).get("nickname") or "Unknown",
                        "duration": (d.get("music_info") or {}).get("duration") or 0,
                    }
                else:
                    return {
                        "type": "video",
                        "video_url": d.get("play"),
                        "audio_url": (d.get("music_info") or {}).get("play") or d.get("music"),
                        "title": d.get("title") or "TikTok",
                        "author": (d.get("author") or {}).get("nickname") or "Unknown",
                        "duration": d.get("duration") or 0,
                        "thumbnail": d.get("cover"),
                    }
        except Exception as e:
            print(f"[Download] tikwm error: {e}")
            time.sleep(1)
    return None


def _download_file(url, ext, referer=None):
    if not url:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        if referer:
            headers["Referer"] = referer
        
        r = requests.get(url, headers=headers, timeout=60, stream=True, allow_redirects=True)
        r.raise_for_status()
        path = os.path.join(CACHE_DIR, f"dl_{os.getpid()}_{int(time.time() * 1000)}.{ext}")
        size = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    size += len(chunk)
                    if size > MAX_FILE_MB * 1024 * 1024:
                        raise Exception(f"File vuot qua {MAX_FILE_MB}MB")
                    f.write(chunk)
        
        if os.path.getsize(path) <= 0:
            _cleanup(path)
            return None
        return path
    except Exception as e:
        print(f"[Download] file error: {e}")
        return None


def _fetch_pin_html(start_url):
    session = requests.Session()
    resp = session.get(start_url, headers=_PIN_HEADERS, allow_redirects=True, timeout=15)
    resp.raise_for_status()
    return resp.url, resp.text


def _extract_pin_image(html):
    soup = BeautifulSoup(html, "html.parser")

    preload = soup.find("link", id="pin-image-preload")
    if preload and preload.get("href"):
        return preload["href"]

    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]

    match = re.search(
        r"https://i\.pinimg\.com/(?:originals|736x)/[^\s\"'\\]+\.(?:jpg|jpeg|png|gif)", html
    )
    if match:
        return match.group(0)

    return None


def _extract_pin_title(html):
    soup = BeautifulSoup(html, "html.parser")
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return "Pinterest"


def _upgrade_pin_image(image_url):
    if "/736x/" in image_url:
        return image_url.replace("/736x/", "/originals/")
    return image_url


def _fetch_pinterest(url):
    try:
        final_url, html = _fetch_pin_html(url)
        image_url = _extract_pin_image(html)
        if not image_url:
            return None
        return {
            "image_url": _upgrade_pin_image(image_url),
            "title": _extract_pin_title(html),
        }
    except Exception as e:
        print(f"[Download] pinterest error: {e}")
        return None


def _download_ytdlp(url, is_audio):
    try:
        import yt_dlp
    except ImportError:
        raise Exception("yt-dlp chua duoc cai. Chay: pip install yt-dlp")

    out_tmpl = os.path.join(CACHE_DIR, f"yt_{os.getpid()}_{int(time.time() * 1000)}.%(ext)s")
    has_ff = _has_ffmpeg()

    if is_audio:
        fmt = "bestaudio/best"
        pps = [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}] if has_ff else []
    else:
        fmt = (
            "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best[height<=720]/best"
            if has_ff else
            "best[ext=mp4][height<=720]/best[height<=720]/best"
        )
        pps = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}] if has_ff else []

    opts = {
        "format": fmt,
        "outtmpl": out_tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "max_filesize": MAX_FILE_MB * 1024 * 1024,
        "postprocessors": pps,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
        if pps:
            base, _ = os.path.splitext(path)
            wanted_ext = "m4a" if is_audio else "mp4"
            cand = base + "." + wanted_ext
            if os.path.exists(cand):
                path = cand
        if not os.path.exists(path):
            stem = os.path.basename(out_tmpl).split(".")[0]
            for f in os.listdir(CACHE_DIR):
                if f.startswith(stem):
                    path = os.path.join(CACHE_DIR, f)
                    break
        return path, info


def _upload(bot, file_path, tid, tt):
    result = bot.uploadFile(file_path, tid, tt, timeout=90)
    if not result:
        return None
    if isinstance(result, dict):
        return result.get("fileUrl") or result.get("url")
    return getattr(result, "fileUrl", None) or getattr(result, "url", None)


def _send_media(bot, file_path, is_audio, info, tid, tt, uid, caption):
    file_url = _upload(bot, file_path, tid, tt)
    if not file_url:
        raise Exception("Upload len Zalo that bai")

    if is_audio:
        size = os.path.getsize(file_path)
        bot.sendRemoteVoice(file_url, tid, tt, fileSize=size)
        return

    metadata = _get_video_metadata(file_path)
    
    duration_ms = _fmt_duration_ms(metadata.get("duration") or info.get("duration") or 0)
    width = metadata.get("width") or int(info.get("width") or 1080)
    height = metadata.get("height") or int(info.get("height") or 1920)
    thumb = info.get("thumbnail") or ""
    
    bot.sendRemoteVideo(
        videoUrl=file_url,
        thumbnailUrl=thumb,
        duration=duration_ms,
        thread_id=tid,
        thread_type=tt,
        width=width,
        height=height,
        message=Message(text=caption),
    )


def process_link(bot, url, is_audio, mo, tid, tt, uid):
    style = bot.style
    platform_name, _ = get_platform_info(url)

    try:
        if is_threads_url(url):
            th = _fetch_threads(url)
            if not th:
                style.reply_warning("khong lay duoc du lieu threads, thu lai sau", mo, tid, tt, uid, ttl=10000)
                return

            if th.get("type") == "image":
                images = th.get("images", [])
                referer = th.get("referer")
                
                if not images:
                    style.reply_warning("link threads nay khong co anh de tai", mo, tid, tt, uid, ttl=10000)
                    return

                image_paths = []
                for idx, img_url in enumerate(images):
                    img_path = _download_file(img_url, "jpg", referer=referer)
                    if img_path:
                        image_paths.append(img_path)
                
                if not image_paths:
                    style.reply_warning("tai anh that bai", mo, tid, tt, uid, ttl=10000)
                    return

                try:
                    style.reply_success(
                        f"tai thanh cong tu {platform_name}: {th['title']}",
                        mo, tid, tt, uid, ttl=15000,
                    )
                    
                    if len(image_paths) == 1:
                        bot.sendLocalImage(
                            imagePath=image_paths[0],
                            thread_id=tid,
                            thread_type=tt,
                            message=Message(text=th["title"]),
                        )
                    else:
                        bot.sendMultiLocalImage(
                            imagePathList=image_paths,
                            thread_id=tid,
                            thread_type=tt,
                            message=Message(text=th["title"]),
                        )
                finally:
                    _cleanup(*image_paths)
                
                return

            video_url = th.get("video_url")
            referer = th.get("referer")
            
            if not video_url:
                style.reply_warning("link threads nay khong co video de tai", mo, tid, tt, uid, ttl=10000)
                return

            path = _download_file(video_url, "mp4", referer=referer)
            if not path:
                style.reply_warning("tai video that bai", mo, tid, tt, uid, ttl=10000)
                return

            try:
                info = {
                    "title": th["title"],
                    "duration": 0,
                    "thumbnail": "",
                    "width": 1080,
                    "height": 1920,
                }
                
                style.reply_success(
                    f"tai thanh cong tu {platform_name}: {info['title']}",
                    mo, tid, tt, uid, ttl=15000,
                )
                _send_media(bot, path, False, info, tid, tt, uid, info["title"])
            finally:
                _cleanup(path)

        elif is_douyin_url(url):
            dy = _fetch_douyin(url)
            if not dy:
                style.reply_warning("khong lay duoc du lieu douyin, thu lai sau", mo, tid, tt, uid, ttl=10000)
                return

            info = {
                "title": dy["title"], "uploader": dy["author"],
                "duration": dy["duration"], "thumbnail": dy["thumbnail"],
                "width": 1080, "height": 1920,
            }
            media_url = dy["audio_url"] if is_audio else dy["video_url"]
            
            if not media_url:
                style.reply_warning("link douyin nay khong co media de tai", mo, tid, tt, uid, ttl=10000)
                return

            path = _download_file(media_url, "m4a" if is_audio else "mp4")
            if not path:
                style.reply_warning("tai file that bai", mo, tid, tt, uid, ttl=10000)
                return

            try:
                style.reply_success(
                    f"tai thanh cong tu {platform_name}: {info['title']}",
                    mo, tid, tt, uid, ttl=15000,
                )
                _send_media(bot, path, is_audio, info, tid, tt, uid, info["title"])
            finally:
                _cleanup(path)

        elif "tiktok.com" in url.lower():
            tk = _fetch_tiktok(url)
            if not tk:
                style.reply_warning("khong lay duoc du lieu tiktok, thu lai sau", mo, tid, tt, uid, ttl=10000)
                return

            if tk.get("type") == "image":
                images = tk.get("images", [])
                audio_url = tk.get("audio_url")
                
                if not images:
                    style.reply_warning("link tiktok nay khong co anh de tai", mo, tid, tt, uid, ttl=10000)
                    return

                image_paths = []
                for idx, img_url in enumerate(images):
                    img_path = _download_file(img_url, "jpg")
                    if img_path:
                        image_paths.append(img_path)
                
                if not image_paths:
                    style.reply_warning("tai anh that bai", mo, tid, tt, uid, ttl=10000)
                    return

                try:
                    style.reply_success(
                        f"tai thanh cong tu {platform_name}: {tk['title']}",
                        mo, tid, tt, uid, ttl=15000,
                    )
                    
                    if len(image_paths) == 1:
                        bot.sendLocalImage(
                            imagePath=image_paths[0],
                            thread_id=tid,
                            thread_type=tt,
                            message=Message(text=tk["title"]),
                        )
                    else:
                        bot.sendMultiLocalImage(
                            imagePathList=image_paths,
                            thread_id=tid,
                            thread_type=tt,
                            message=Message(text=tk["title"]),
                        )
                    
                    if audio_url:
                        audio_path = _download_file(audio_url, "mp3")
                        if audio_path:
                            try:
                                audio_file_url = _upload(bot, audio_path, tid, tt)
                                if audio_file_url:
                                    size = os.path.getsize(audio_path)
                                    bot.sendRemoteVoice(audio_file_url, tid, tt, fileSize=size)
                            finally:
                                _cleanup(audio_path)
                    
                finally:
                    _cleanup(*image_paths)
                
                return

            info = {
                "title": tk["title"], "uploader": tk["author"],
                "duration": tk["duration"], "thumbnail": tk["thumbnail"],
                "width": 1080, "height": 1920,
            }
            media_url = tk["audio_url"] if is_audio else tk["video_url"]
            if not media_url:
                style.reply_warning("link tiktok nay khong co media de tai", mo, tid, tt, uid, ttl=10000)
                return

            path = _download_file(media_url, "m4a" if is_audio else "mp4")
            if not path:
                style.reply_warning("tai file that bai", mo, tid, tt, uid, ttl=10000)
                return

            try:
                style.reply_success(
                    f"tai thanh cong tu {platform_name}: {info['title']}",
                    mo, tid, tt, uid, ttl=15000,
                )
                _send_media(bot, path, is_audio, info, tid, tt, uid, info["title"])
            finally:
                _cleanup(path)

        elif is_pinterest_url(url):
            pin = _fetch_pinterest(url)
            if not pin:
                style.reply_warning("khong tim thay anh trong link pinterest nay", mo, tid, tt, uid, ttl=10000)
                return

            info = {"title": pin["title"]}
            try:
                style.reply_success(
                    f"tai thanh cong tu {platform_name}: {info['title']}",
                    mo, tid, tt, uid, ttl=15000,
                )
                
                bot.sendImage(
                    imageUrl=pin["image_url"],
                    thread_id=tid,
                    thread_type=tt,
                    caption=pin["title"],
                    message=Message(text=pin["title"]),
                )
            except Exception as e:
                print(f"[Download] pinterest sendImage fallback: {e}")
                path = _download_file(pin["image_url"], "jpg")
                if not path:
                    raise Exception("khong tai duoc anh pinterest")
                try:
                    bot.sendLocalImage(
                        imagePath=path, thread_id=tid, thread_type=tt,
                        message=Message(text=pin["title"]),
                    )
                finally:
                    _cleanup(path)

        else:
            path, ydl_info = _download_ytdlp(url, is_audio)
            if not path or not os.path.exists(path):
                style.reply_warning("tai video that bai (link khong ho tro hoac qua gioi han dung luong)", mo, tid, tt, uid, ttl=10000)
                return

            info = {
                "title": ydl_info.get("title") or platform_name,
                "uploader": ydl_info.get("uploader") or ydl_info.get("channel") or "Unknown",
                "duration": ydl_info.get("duration") or 0,
                "thumbnail": ydl_info.get("thumbnail"),
                "width": ydl_info.get("width") or 1080,
                "height": ydl_info.get("height") or 1920,
            }

            try:
                style.reply_success(
                    f"tai thanh cong tu {platform_name}: {info['title']}",
                    mo, tid, tt, uid, ttl=15000,
                )
                _send_media(bot, path, is_audio, info, tid, tt, uid, info["title"])
            finally:
                _cleanup(path)

    except Exception as e:
        print(f"[Download] process_link error: {e}")
        import traceback
        traceback.print_exc()
        style.reply_error(f"loi khi tai: {e}", mo, tid, tt, uid, ttl=10000)


def try_autolink(bot, msg, mo, tid, tt, uid):
    if not is_auto_on(tid):
        return False

    text = (msg or "").strip()
    if bot.prefix and text.startswith(bot.prefix):
        return False

    url = _extract_link(text)
    if not url:
        return False

    key = (str(tid), str(uid))
    now = int(time.time() * 1000)
    if now - _AUTO_COOLDOWN.get(key, 0) < 5000:
        return True
    _AUTO_COOLDOWN[key] = now

    try:
        reaction = ReactionManager(bot)
        reaction.react(mo, REACTIONS["received"], tid, tt)
    except Exception:
        pass

    threading.Thread(
        target=process_link, args=(bot, url, False, mo, tid, tt, uid), daemon=True
    ).start()
    return True


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        body = msg[len(self.bot.prefix):].strip().split(None, 1)
        args = body[1].strip() if len(body) > 1 else ""

        if not args:
            self._usage(mo, tid, tt, uid)
            return

        parts = args.split()
        sub = parts[0].lower()

        if sub in ("auto", "-a", "--auto"):
            enabled = toggle_auto(tid)
            if enabled:
                self.style.reply_success("da BAT tu dong tai link video trong nhom nay", mo, tid, tt, uid, ttl=10000)
            else:
                self.style.reply_warning("da TAT tu dong tai link video trong nhom nay", mo, tid, tt, uid, ttl=10000)
            return

        is_audio = "-a" in parts
        text_for_link = " ".join(p for p in parts if p != "-a")
        url = _extract_link(text_for_link)

        if not url:
            self.style.reply_warning(
                "link khong hop le hoac chua duoc ho tro\n"
                "ho tro: TikTok, Douyin, YouTube, Facebook, Instagram, Threads, Twitter/X, CapCut, Pinterest",
                mo, tid, tt, uid, ttl=10000,
            )
            return

        process_link(self.bot, url, is_audio, mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        p = self.bot.prefix
        self.style.reply_info(
            f"{p}download <link video>\n{p}download auto (toggle)",
            mo, tid, tt, uid, ttl=15000,
        )


def _ns():
    return {"cls": NS, "name": "download"}