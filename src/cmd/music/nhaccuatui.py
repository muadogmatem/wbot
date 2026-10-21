import os
import time
import requests
import hashlib
import tempfile

from PIL import Image

from .music_handler import save_search, register_platform, CACHE_TTL, get_msg_info, delete_message
from .card_renderer import draw_search_card, draw_detail_card
from .reaction_cooldown import start_cooldown_react_then_delete

_BASE = "https://graph.nhaccuatui.com/api"
_SEARCH = "/v3/search/all"
_LYRIC = "/v1/song/lyric/detail"
_AUTH = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJkdCI6IjE3NzA2Mjc0ODI3MzIiLCJuYmYiOjE3NzA2Mjc0ODIsImxvZ2lu"
    "TWV0aG9kIjoiNSIsImV4cGlyZWREYXRlIjoiMCIsImV4cCI6MTgwMjE2MzQ4MiwiZGV2aWNlaW5mbyI6IntcIkFkSURcIjpcIlwiL"
    "FwiQXBwTmFtZVwiOlwiV0VCXCIsXCJBcHBWZXJzaW9uXCI6XCIxXCIsXCJEZXZpY2VJRFwiOlwiMDk1NmJkNGY2MGU2ZjY4M1wiL"
    "FwiRGV2aWNlTmFtZVwiOlwiXCIsXCJOZXR3b3JrXCI6XCJcIixcIk9zTmFtZVwiOlwiV0VCXCIsXCJPc1ZlcnNpb25cIjpcIldFQl"
    "wiLFwiUHJvdmlkZXJcIjpcIk5DVENvcnBcIixcIlVzZXJOYW1lXCI6XCJcIixcImlzVk5cIjpmYWxzZX0iLCJidmVkIjoiMCIsImR"
    "ldmljZUlkIjoiMDk1NmJkNGY2MGU2ZjY4MyIsImlhdCI6MTc3MDYyNzQ4MiwidXQiOiIwIn0.pNaEDAVkGBRjmsxL-7HxelAgmuJZ"
    "7pkV6bS4l33NVLI"
)
_DEV = "0956bd4f60e6f683"
_PLATFORM = "nhaccuatui"

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
        except Exception:
            pass


def _search_headers():
    ts = str(int(time.time() * 1000))
    return {
        "accept": "*/*",
        "authorization": _AUTH,
        "origin": "https://www.nhaccuatui.com",
        "referer": "https://www.nhaccuatui.com/",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "content-type": "application/json",
        "x-nct-appid": "6",
        "x-nct-deviceid": _DEV,
        "x-nct-language": "vi",
        "x-nct-os": "web",
        "x-nct-version": "1",
        "x-nct-userid": "0",
        "x-nct-uuid": _DEV,
        "x-nct-token": _AUTH,
        "timestamp": ts,
        "x-nct-time": ts,
        "x-sign": hashlib.md5(ts.encode()).hexdigest() + ts,
    }


def _lyric_headers():
    ts = str(int(time.time() * 1000))
    return {
        "accept": "*/*",
        "authorization": _AUTH,
        "origin": "https://www.nhaccuatui.com",
        "referer": "https://www.nhaccuatui.com/",
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "x-nct-appid": "6",
        "x-nct-deviceid": _DEV,
        "x-nct-language": "vi",
        "x-nct-os": "web",
        "x-nct-time": ts,
        "x-nct-token": _AUTH,
        "x-nct-userid": "0",
        "x-nct-uuid": _DEV,
        "x-nct-version": "1",
    }


def _search(keyword, limit=20):
    try:
        ts = str(int(time.time() * 1000))
        enc = requests.utils.quote(keyword)
        url = f"{_BASE}{_SEARCH}?keyword={enc}&correct=true&timestamp={ts}"
        body = {"keyword": enc, "pageindex": 1, "pagesize": limit, "isShowLoading": True}
        r = requests.post(url, json=body, headers=_search_headers(), timeout=15)
        d = r.json()

        if not d.get("success"):
            return []

        result = []
        for s in d.get("data", {}).get("songs", []):
            su = None
            for q in ["320", "128"]:
                f = next((x for x in (s.get("streamURL") or []) if x.get("type") == q), None)
                if f:
                    su = f.get("stream")
                    break
            if not su and s.get("streamURL"):
                su = s["streamURL"][0].get("stream")
            if not su:
                continue

            art = s.get("artistName", "")
            if not art:
                art = ", ".join(a.get("name", "") for a in (s.get("artist") or []))

            result.append({
                "id": s.get("key", ""),
                "songKey": s.get("key", ""),
                "title": s.get("name", "khong ro"),
                "artist": art or "Unknown",
                "thumbnail": s.get("image", ""),
                "streamUrl": su,
                "duration": s.get("duration", 0),
                "isOfficial": "selected" in (s.get("flags") or []),
                "linkShare": s.get("linkShare", ""),
            })
        return result
    except Exception as e:
        print(f"[NCT] Search error: {e}")
        return []


def _get_lyric(song_key):
    try:
        ts = str(int(time.time() * 1000))
        url = f"{_BASE}{_LYRIC}?songKey={song_key}&timestamp={ts}"
        r = requests.get(url, headers=_lyric_headers(), timeout=10)
        d = r.json()
        if d.get("success") and d.get("data", {}).get("content"):
            return d["data"]["content"]
        return None
    except Exception as e:
        print(f"[NCT] Lyric error: {e}")
        return None


def _download(stream_url, path):
    try:
        r = requests.get(stream_url, stream=True, timeout=30, headers={
            "user-agent": "Mozilla/5.0",
            "referer": "https://www.nhaccuatui.com/",
        })
        r.raise_for_status()
        with open(path, "wb") as f:
            for c in r.iter_content(8192):
                if c:
                    f.write(c)
        return True
    except Exception as e:
        print(f"[NCT] Download error: {e}")
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
        print(f"[NCT] Upload error: {e}")
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
        print(f"[NCT] Send loading msg error: {e}")

    audio_path = os.path.join(TEMP_DIR, f"nct_{track['id']}_{int(time.time())}.mp3")
    detail_img_path = None

    try:
        if not _download(track["streamUrl"], audio_path):
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("khong tai duoc bai hat", mo, tid, tt, uid, ttl=10000)
            return

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("file audio bi loi", mo, tid, tt, uid, ttl=10000)
            return

        voice_url = _upload_file(bot, audio_path, tid, tt, url_suffix=".aac")
        if not voice_url:
            if loading_msg_info:
                delete_message(bot, tid, tt, loading_msg_info)
            style.reply_warning("khong upload duoc file", mo, tid, tt, uid, ttl=10000)
            return

        file_size = os.path.getsize(audio_path)

        if loading_msg_info:
            try:
                delete_message(bot, tid, tt, loading_msg_info)
                time.sleep(0.2)
            except Exception:
                pass

        detail_img = draw_detail_card(track, track.get("thumbnail", ""))
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
            print(f"[NCT] Send voice error: {e}")
            style.reply_warning(f"loi gui voice: {e}", mo, tid, tt, uid, ttl=10000)
            return

        if sub_cmd == "lyric":
            lyric = _get_lyric(track.get("songKey") or track["id"])
            if lyric:
                lt = f"loi bai hat: {track['title']}\n{track['artist']}\n\n"
                if len(lyric) > 4000:
                    lyric = lyric[:4000] + "\n\n... (da cat bot)"
                lt += lyric
                style.reply_success(lt, mo, tid, tt, uid, ttl=300000)
            else:
                style.reply_warning(
                    f"khong tim thay loi: {track['title']}",
                    mo, tid, tt, uid, ttl=10000
                )

    except Exception as e:
        print(f"[NCT] Error: {e}")
        if loading_msg_info:
            delete_message(bot, tid, tt, loading_msg_info)
        style.reply_warning(f"loi: {e}", mo, tid, tt, uid, ttl=10000)
    finally:
        _cleanup(audio_path, detail_img_path)


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
                f"vui long nhap tu khoa tim kiem\nVD: {p}nct lac troi",
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
            print(f"[NCT] Send image error: {e}")
            self.style.reply_warning(f"loi gui anh: {e}", mo, tid, tt, uid, ttl=10000)
        finally:
            _cleanup(img_path)

        save_search(tid, uid, songs, _PLATFORM, search_img_info)


def _ns():
    return {"cls": NS, "name": "nhaccuatui"}