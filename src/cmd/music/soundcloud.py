import os
import re
import time
import tempfile
import subprocess
import requests
from bs4 import BeautifulSoup
from PIL import Image

from .music_handler import save_search, register_platform, CACHE_TTL, get_msg_info, delete_message
from .card_renderer import draw_search_card, draw_detail_card
from .reaction_cooldown import start_cooldown_react_then_delete

_PLATFORM = "soundcloud"
_CLIENT_ID_CACHE = None

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "asset", "temp")
os.makedirs(TEMP_DIR, exist_ok=True)


def _autosave(img, quality=92):
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, dir=TEMP_DIR) as tf:
        img.convert("RGB").save(tf.name, "JPEG", quality=quality, optimize=True)
        return tf.name


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except:
            pass


def _get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/97.0.4692.71 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://soundcloud.com/",
    }


def _get_client_id():
    global _CLIENT_ID_CACHE
    if _CLIENT_ID_CACHE:
        return _CLIENT_ID_CACHE
    try:
        res = requests.get("https://soundcloud.com/", headers=_get_headers(), timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        script_tags = soup.find_all("script", {"crossorigin": True})
        urls = [tag.get("src") for tag in script_tags if tag.get("src") and tag.get("src").startswith("https")]
        if not urls:
            return None
        res = requests.get(urls[-1], headers=_get_headers(), timeout=10)
        res.raise_for_status()
        match = re.search(r'client_id:"(.*?)"', res.text)
        if match:
            _CLIENT_ID_CACHE = match.group(1)
            return _CLIENT_ID_CACHE
        return None
    except Exception as e:
        print(f"[SCL] get_client_id error: {e}")
        return None


def _wait_for_client_id():
    client_id = _get_client_id()
    retries = 5
    while not client_id and retries > 0:
        time.sleep(2)
        client_id = _get_client_id()
        retries -= 1
    return client_id


def _ms_to_seconds(ms):
    try:
        return ms // 1000
    except:
        return 0


def _get_song_details(link):
    try:
        client_id = _wait_for_client_id()
        if not client_id:
            return None
        api_url = f"https://api-v2.soundcloud.com/resolve?url={link}&client_id={client_id}"
        response = requests.get(api_url, headers=_get_headers(), timeout=10)
        response.raise_for_status()
        data = response.json()
        return {
            "duration": _ms_to_seconds(data.get("duration", 0)),
            "duration_ms": data.get("duration", 0),
            "playback_count": data.get("playback_count", 0),
            "likes_count": data.get("likes_count", 0),
            "artist": data.get("user", {}).get("username", "Unknown"),
            "artwork_url": data.get("artwork_url", ""),
        }
    except Exception as e:
        print(f"[SCL] get_song_details error: {e}")
        return None


def _search(keyword, limit=10):
    try:
        base_url = "https://soundcloud.com"
        search_url = f"https://m.soundcloud.com/search?q={requests.utils.quote(keyword)}"
        response = requests.get(search_url, headers=_get_headers(), timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        songs = []
        url_pattern = re.compile(r"^/[^/]+/[^/]+$")

        for element in soup.select("li > div"):
            a_tag = element.select_one("a")
            if a_tag and a_tag.has_attr("href"):
                relative_url = a_tag["href"]
                if url_pattern.match(relative_url):
                    title = a_tag.get("aria-label", "").strip()
                    link = base_url + relative_url
                    img_tag = element.select_one("img")
                    cover_url = img_tag["src"] if img_tag and img_tag.has_attr("src") else ""

                    detail = _get_song_details(link)
                    if detail:
                        songs.append({
                            "id": link,
                            "title": title or "Unknown",
                            "artist": detail.get("artist", "Unknown"),
                            "thumbnail": cover_url or detail.get("artwork_url", ""),
                            "streamUrl": link,
                            "duration": detail.get("duration", 0),
                            "duration_ms": detail.get("duration_ms", 0),
                            "playback_count": detail.get("playback_count", 0),
                            "likes_count": detail.get("likes_count", 0),
                        })

            if len(songs) >= limit:
                break

        return songs
    except Exception as e:
        print(f"[SCL] search error: {e}")
        return []


def _get_stream_url(link):
    try:
        client_id = _wait_for_client_id()
        if not client_id:
            return None
        api_url = f"https://api-v2.soundcloud.com/resolve?url={link}&client_id={client_id}"
        response = requests.get(api_url, headers=_get_headers(), timeout=10)
        response.raise_for_status()
        data = response.json()

        for transcode in data.get("media", {}).get("transcodings", []):
            if transcode.get("format", {}).get("protocol") == "progressive":
                stream_url_req = requests.get(
                    f"{transcode['url']}?client_id={client_id}",
                    headers=_get_headers(),
                    timeout=10
                )
                stream_url_req.raise_for_status()
                return stream_url_req.json().get("url")
        return None
    except Exception as e:
        print(f"[SCL] get_stream_url error: {e}")
        return None


def _get_cover_url(link):
    try:
        client_id = _wait_for_client_id()
        if not client_id:
            return None
        api_url = f"https://api-v2.soundcloud.com/resolve?url={link}&client_id={client_id}"
        response = requests.get(api_url, headers=_get_headers(), timeout=10)
        response.raise_for_status()
        data = response.json()
        cover_url = data.get("artwork_url")
        if cover_url:
            cover_url = cover_url.replace("-large", "-t500x500")
        else:
            cover_url = data.get("user", {}).get("avatar_url", "")
            if cover_url:
                cover_url = cover_url.replace("-large", "-t500x500")
        return cover_url
    except Exception as e:
        print(f"[SCL] get_cover_url error: {e}")
        return None


def _download(stream_url, path):
    try:
        r = requests.get(stream_url, stream=True, timeout=60, headers=_get_headers())
        r.raise_for_status()
        with open(path, "wb") as f:
            for c in r.iter_content(8192):
                if c:
                    f.write(c)
        return True
    except Exception as e:
        print(f"[SCL] download error: {e}")
        return False


def _convert_audio(input_path, output_path):
    try:
        command = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-c:a", "aac", "-b:a", "128k",
            output_path
        ]
        subprocess.run(command, check=True, capture_output=True, timeout=300)
        return True
    except subprocess.TimeoutExpired:
        print("[SCL] FFmpeg timeout")
        return False
    except FileNotFoundError:
        print("[SCL] FFmpeg not found")
        return False
    except Exception as e:
        print(f"[SCL] convert_audio error: {e}")
        return False


def _upload_file(bot, file_path, tid, tt, url_suffix=None):
    try:
        result = bot.uploadFile(file_path, tid, tt, timeout=60)
        if result:
            if isinstance(result, dict):
                file_url = result.get("fileUrl") or result.get("url")
            else:
                file_url = getattr(result, "fileUrl", None) or getattr(result, "url", None)

            if file_url and url_suffix:
                file_url = f"{file_url}{url_suffix}"

            return file_url
        return None
    except Exception as e:
        print(f"[SCL] Upload error: {e}")
        return None


def send_track(bot, track, sub_cmd, mo, tid, tt, uid):
    style = bot.style
    loading_msg_info = None

    try:
        loading_text = f"dang tai: {track['title']} - {track['artist']}"
        response = style.reply_info(loading_text, mo, tid, tt, uid, ttl=0)
        time.sleep(0.5)
        target_msg_id = getattr(response, "msgId", None)
        loading_msg_info = get_msg_info(bot, tid, target_msg_id)
    except Exception as e:
        print(f"[SCL] send loading msg error: {e}")

    original_path = os.path.join(TEMP_DIR, f"scl_{int(time.time())}_original.mp3")
    converted_path = os.path.join(TEMP_DIR, f"scl_{int(time.time())}_converted.aac")
    detail_img_path = None

    try:
        duration_ms = track.get("duration_ms", 0)
        if duration_ms > 5400000:
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("khong ho tro bai hat tren 90 phut", mo, tid, tt, uid, ttl=10000)
            return

        stream_url = _get_stream_url(track["streamUrl"])
        if not stream_url:
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("khong lay duoc stream url", mo, tid, tt, uid, ttl=10000)
            return

        if not _download(stream_url, original_path):
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("khong tai duoc bai hat", mo, tid, tt, uid, ttl=10000)
            return

        if not os.path.exists(original_path) or os.path.getsize(original_path) < 1000:
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("file audio bi loi", mo, tid, tt, uid, ttl=10000)
            return

        if not _convert_audio(original_path, converted_path):
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("loi khi xu ly audio", mo, tid, tt, uid, ttl=10000)
            return

        _cleanup(original_path)

        voice_url = _upload_file(bot, converted_path, tid, tt, url_suffix=".aac")
        if not voice_url:
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("khong upload duoc file", mo, tid, tt, uid, ttl=10000)
            return

        file_size = os.path.getsize(converted_path)

        if loading_msg_info:
            try:
                delete_message(bot, tid, tt, loading_msg_info)
                time.sleep(0.2)
            except:
                pass

        cover_url = _get_cover_url(track["streamUrl"]) or track.get("thumbnail", "")
        detail_img = draw_detail_card(track, cover_url)
        detail_img_path = _autosave(detail_img)

        with Image.open(detail_img_path) as im:
            width, height = im.size

        bot.sendLocalImage(
            detail_img_path,
            thread_id=tid,
            thread_type=tt,
            width=width,
            height=height,
            message=None,
            ttl=120000
        )

        try:
            bot.sendRemoteVoice(voice_url, tid, tt, fileSize=file_size)
        except Exception as e:
            print(f"[SCL] send voice error: {e}")
            style.reply_warning(f"loi gui voice: {e}", mo, tid, tt, uid, ttl=10000)
            return

    except Exception as e:
        print(f"[SCL] error: {e}")
        if loading_msg_info:
            delete_message(bot, tid, tt, loading_msg_info)
        style.reply_warning(f"loi: {e}", mo, tid, tt, uid, ttl=10000)
    finally:
        _cleanup(original_path, converted_path, detail_img_path)


register_platform(_PLATFORM, send_track)


class NS:

    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        p = self.bot.prefix

        content = msg[len(p):].strip()
        parts = content.split(maxsplit=1)
        keyword = parts[1].strip() if len(parts) > 1 else ""

        if not keyword:
            self.style.reply_warning(
                f"vui long nhap tu khoa tim kiem\nVD: {p}scl shape of you",
                mo, tid, tt, uid, ttl=10000
            )
            return

        songs = _search(keyword, 10)

        if not songs:
            self.style.reply_warning(
                f"khong tim thay ket qua cho: {keyword}",
                mo, tid, tt, uid, ttl=10000
            )
            return

        search_img = draw_search_card(songs, keyword, CACHE_TTL)
        img_path = _autosave(search_img)

        search_img_info = None

        try:
            with Image.open(img_path) as im:
                width, height = im.size

            img_response = self.bot.sendLocalImage(
                img_path,
                thread_id=tid,
                thread_type=tt,
                width=width,
                height=height,
                message=None,
                ttl=CACHE_TTL * 1000
            )

            time.sleep(0.5)
            target_msg_id = getattr(img_response, "msgId", None)
            search_img_info = get_msg_info(self.bot, tid, target_msg_id)

            start_cooldown_react_then_delete(
                self.bot,
                search_img_info,
                tid,
                tt,
                CACHE_TTL,
                icon="🕐",
                msg_type="chat.photo"
            )

        except Exception as e:
            print(f"[SCL] send image error: {e}")
            self.style.reply_warning(f"loi gui anh: {e}", mo, tid, tt, uid, ttl=10000)
        finally:
            _cleanup(img_path)

        save_search(tid, uid, songs, _PLATFORM, search_img_info)


def _ns():
    return {"cls": NS, "name": "soundcloud"}