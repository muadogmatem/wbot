import os
import json
import time
import random
from zlapi.models import Message

def _get_name(bot, uid):
    try:
        return bot.style.get_name(uid)
    except Exception:
        return str(uid)


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    @property
    def reg(self):
        return self.bot.reg

    def handle(self, msg, mo, tid, tt, uid):
        from .sticker_utils import parse_stk_flags
        from .sticker_handler import StickerHandler
        
        flags = parse_stk_flags(msg)
        
        quote = getattr(mo, "quote", None)
        if not quote:
            self._show_usage(mo, tid, tt, uid)
            return
        
        attach = getattr(quote, "attach", None)
        if not attach:
            self.style.reply_warning(
                "vui long reply vao anh gif video hoac sticker",
                mo, tid, tt, uid, ttl=60000
            )
            return
        
        try:
            if isinstance(attach, str):
                attach_data = json.loads(attach)
            else:
                attach_data = attach
            
            handler = StickerHandler(self.bot, mo, tid, tt, uid)
            handler.process(attach_data, flags)
            
        except json.JSONDecodeError:
            self.style.reply_warning(
                "du lieu dinh kem khong hop le",
                mo, tid, tt, uid, ttl=60000
            )
        except Exception as e:
            self.style.reply_error(
                f"loi: {str(e)}",
                mo, tid, tt, uid, ttl=30000
            )

    def _show_usage(self, mo, tid, tt, uid):
        p = self.bot.prefix
        usage_text = (
            f"ban mun tao stk j"
        )
        self.style.reply_info(usage_text, mo, tid, tt, uid, ttl=120000)


def _ns():
    return {"cls": NS, "name": "sticker"}