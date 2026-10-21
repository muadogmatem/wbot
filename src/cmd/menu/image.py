import time
import threading
import requests

from zlapi.models import Message
from .menu_handler import get_msg_info, delete_message


class NS:
    def __init__(self, bot):
        self.bot = bot
        self.AVAILABLE_TYPES = ["hass", "hmidriff", "pgif", "4k", "hentai", "holo", "hneko", "neko", "hkitsune", "kemonomimi", "anal", "hanal", "gonewild", "kanna", "ass", "pussy", "thigh", "hthigh", "gah", "coffee", "food", "paizuri", "tentacle", "boobs", "hboobs", "yaoi", "donator", "cosplay", "swimsuit", "pantsu", "nakadashi", "waifu"]
        self.NEKOBOT_URL = "https://nekobot.xyz/api/image"
        self.WAIFU_URL = "https://api.waifu.im/images"
        self.WAIFU_TOKEN = "Bearer vOPSl3bkZ1TVV720rwbGNsAQ1VS964hZHuzYAjMxX0"

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            self._show_types(mo, tid, tt, uid)
        else:
            img_type = args[0].lower()
            if img_type in self.AVAILABLE_TYPES:
                self._fetch_and_send(img_type, mo, tid, tt, uid)
            else:
                self.style.reply_warning(
                    f"Type khong hop le. Vui long chon: {', '.join(self.AVAILABLE_TYPES)}",
                    mo, tid, tt, uid, ttl=10000
                )

    def _show_types(self, mo, tid, tt, uid):
        self.style.reply_info(
            ", ".join(self.AVAILABLE_TYPES),
            mo, tid, tt, uid, ttl=30000
        )

    def _fetch_and_send(self, img_type, mo, tid, tt, uid):
        try:
            if img_type == "waifu":
                image_url = self._fetch_waifu()
            else:
                image_url = self._fetch_nekobot(img_type)
            
            if not image_url:
                self.style.reply_info(
                    "xin loi nhe hog cs tin mua api .⁠·⁠´⁠¯⁠`⁠(⁠>⁠▂⁠<⁠)⁠´⁠¯⁠`⁠·⁠.",
                    mo, tid, tt, uid, ttl=10000
                )
                return
            
            img_response = self.bot.sendImage(
                imageUrl=image_url,
                thread_id=tid,
                thread_type=tt,
                caption=img_type,
                message=Message(text=""),
                ttl=0
            )
            
            time.sleep(0.5)
            target_msg_id = getattr(img_response, "msgId", None)
            msg_info = get_msg_info(self.bot, tid, target_msg_id)
            
            if msg_info:
                self._schedule_delete(tid, tt, msg_info)
                
        except Exception as e:
            self.style.reply_error(
                f"Loi khi gui anh: {str(e)}",
                mo, tid, tt, uid, ttl=10000
            )

    def _fetch_nekobot(self, img_type):
        response = requests.get(f"{self.NEKOBOT_URL}?type={img_type}", timeout=10)
        data = response.json()
        if data.get("success"):
            return data.get("message")
        return None

    def _fetch_waifu(self):
        headers = {
            'Accept': 'application/json',
            'Authorization': self.WAIFU_TOKEN
        }
        params = {
            'IncludedTags': 'waifu',
            'IsNsfw': 'True'  }
        response = requests.get(self.WAIFU_URL, headers=headers, params=params, timeout=10)
        data = response.json()
        if data.get("items") and len(data["items"]) > 0:
            return data["items"][0].get("url")
        return None

    def _schedule_delete(self, tid, tt, msg_info):
        def delete_job():
            try:
                delete_message(self.bot, tid, tt, msg_info)
            except:
                pass
                
        timer = threading.Timer(30.0, delete_job)
        timer.daemon = True
        timer.start()


def _ns():
    return {"cls": NS, "name": "image"}