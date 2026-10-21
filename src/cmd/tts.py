import os
import time
import tempfile
import requests
from PIL import Image

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "temp")
os.makedirs(TEMP_DIR, exist_ok=True)


def _cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except:
            pass


def _get_tts_audio(text):
    try:
        url = "https://api.flowery.pw/v2/tts"
        headers = {
            'accept': 'audio/mp3',
            'accept-language': 'vi-VN',
            'content-type': 'application/ssml+xml',
            'origin': 'https://flowery.pw',
            'referer': 'https://flowery.pw/',
            'user-agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36'
        }
        
        data = f'<speak><voice name="58060710-7ab8-5843-819c-1f9cfd65935a">{text}</voice></speak>'
        
        response = requests.post(url, headers=headers, data=data.encode('utf-8'), timeout=30)
        response.raise_for_status()
        
        return response.content
    except Exception as e:
        print(f"[TTS] API error: {e}")
        return None


def _save_audio(audio_content):
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False, dir=TEMP_DIR) as tf:
            tf.write(audio_content)
            return tf.name
    except Exception as e:
        print(f"[TTS] Save error: {e}")
        return None


def _upload_file(bot, file_path, tid, tt):
    try:
        result = bot.uploadFile(file_path, tid, tt, timeout=60)
        if result:
            if isinstance(result, dict):
                file_url = result.get("fileUrl") or result.get("url")
            else:
                file_url = getattr(result, "fileUrl", None) or getattr(result, "url", None)
            
            if file_url:
                file_url = f"{file_url}.aac"
            
            return file_url
        return None
    except Exception as e:
        print(f"[TTS] Upload error: {e}")
        return None


def _extract_text_from_quote(quoted_message):
    try:
        text = getattr(quoted_message, 'msg', None) or getattr(quoted_message, 'content', None)
        
        if text:
            return text.strip()
        
        raw = quoted_message.__dict__.copy()
        text = raw.get('msg') or raw.get('content') or raw.get('text', '')
        
        if text:
            return str(text).strip()
        
        return None
    except Exception as e:
        print(f"[TTS] Extract text error: {e}")
        return None


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
        text = parts[1].strip() if len(parts) > 1 else ""

        if not text:
            if mo.quote:
                text = _extract_text_from_quote(mo.quote)
                if not text:
                    self.style.reply_warning(
                        "khong lay duoc noi dung tu tin nhan da reply",
                        mo, tid, tt, uid, ttl=10000
                    )
                    return
            else:
                self.style.reply_info(
                    f"vui long nhap noi dung can doc hoac reply tin nhan",
                    mo, tid, tt, uid, ttl=10000
                )
                return

        if len(text) > 2000:
            self.style.reply_warning(
                "noi dung qua dai, vui long nhap duoi 1000 ky tu",
                mo, tid, tt, uid, ttl=10000
            )
            return

        audio_path = None

        try:
            self.style.reply_success(
                f"dang tao voice",
                mo, tid, tt, uid, ttl=5000
            )

            audio_content = _get_tts_audio(text)
            if not audio_content:
                self.style.reply_warning(
                    "khong lay duoc audio tu API",
                    mo, tid, tt, uid, ttl=10000
                )
                return

            audio_path = _save_audio(audio_content)
            if not audio_path or not os.path.exists(audio_path):
                self.style.reply_warning(
                    "khong luu duoc file audio",
                    mo, tid, tt, uid, ttl=10000
                )
                return

            file_size = os.path.getsize(audio_path)
            if file_size < 100:
                self.style.reply_warning(
                    "file audio bi loi hoac qua nho",
                    mo, tid, tt, uid, ttl=10000
                )
                return

            voice_url = _upload_file(self.bot, audio_path, tid, tt)
            if not voice_url:
                self.style.reply_warning(
                    "khong upload duoc file",
                    mo, tid, tt, uid, ttl=10000
                )
                return

            try:
                self.bot.sendRemoteVoice(voice_url, tid, tt, fileSize=file_size)
            except Exception as e:
                print(f"[TTS] Send voice error: {e}")
                self.style.reply_warning(
                    f"loi gui voice: {e}",
                    mo, tid, tt, uid, ttl=10000
                )
                return

        except Exception as e:
            print(f"[TTS] Error: {e}")
            self.style.reply_warning(
                f"loi: {e}",
                mo, tid, tt, uid, ttl=10000
            )
        finally:
            _cleanup(audio_path)


def _ns():
    return {"cls": NS, "name": "tts"}