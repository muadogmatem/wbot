import json
import urllib.parse
from zlapi.models import Message


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        if mo.msgType == "chat.photo":
            try:
                img_url = mo.content.href.replace("\\/", "/")
                img_url = urllib.parse.unquote(img_url)
                self.style.reply_success(img_url, mo, tid, tt, uid, ttl=60000)
                return
            except Exception:
                pass

        if mo.quote:
            attach = mo.quote.attach
            if attach:
                try:
                    attach_data = json.loads(attach) if isinstance(attach, str) else attach
                    
                    if attach_data.get("type") == 7:
                        catId = attach_data.get("catId")
                        stickerId = attach_data.get("id")
                        
                        if catId and stickerId:
                            try:
                                sticker_details = self.bot.getStickerDetail(catId)
                                
                                detail_list = []
                                if isinstance(sticker_details, list):
                                    detail_list = sticker_details
                                elif isinstance(sticker_details, dict):
                                    detail_list = sticker_details.get("data", [])
                                
                                specific_sticker = next((s for s in detail_list if str(s.get('id')) == str(stickerId)), None)
                                
                                if specific_sticker:
                                    sticker_url = specific_sticker.get("stickerUrl") or specific_sticker.get("stickerSpriteUrl")
                                    if sticker_url:
                                        sticker_url = sticker_url.replace("\\/", "/")
                                        sticker_url = urllib.parse.unquote(sticker_url)
                                        self.style.reply_success(sticker_url, mo, tid, tt, uid, ttl=60000)
                                        return
                            except Exception:
                                pass
                    url = (
                        attach_data.get("hdUrl") or
                        attach_data.get("href") or
                        attach_data.get("oriUrl") or
                        attach_data.get("normalUrl") or
                        attach_data.get("thumbUrl")
                    )
                    
                    if url:
                        url = url.replace("\\/", "/")
                        url = urllib.parse.unquote(url)
                        self.style.reply_success(url, mo, tid, tt, uid, ttl=60000)
                        return
                        
                except json.JSONDecodeError:
                    pass

        self.style.reply_warning(
            "reply vao hinh anh, gif, file, video hoac sticker can getlink",
            mo, tid, tt, uid, ttl=10000
        )


def _ns():
    return {"cls": NS, "name": "getlink"}