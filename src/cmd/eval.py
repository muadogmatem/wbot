import os
import math
import json
import requests
from zlapi.models import Message, ThreadType


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
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split(maxsplit=1)
        
        code = parts[1] if len(parts) > 1 else None
        
        if not code and mo.quote:
            quoted_text = getattr(mo.quote, "msg", None) or getattr(mo.quote, "msg", None)
            if quoted_text:
                code = str(quoted_text).strip()
        
        if not code:
            self._usage(mo, tid, tt, uid)
        else:
            self._eval(code, mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        self.style.reply_info(
            "ban mun chay cai j",
            mo, tid, tt, uid, ttl=15000,
        )

    def _check_admin(self, uid, mo, tid, tt):
        if not self.bot._is_admin(uid):
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )
            return False
        return True

    def _eval(self, code, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return

        local_vars = {
            "client": self.bot,
            "bot": self.bot,
            "api": self.bot,
            "this": self.bot,
            "message_object": mo,
            "mo": mo,
            "data": mo,
            "msg": mo,
            "thread_id": tid,
            "tid": tid,
            "thread_type": tt,
            "tt": tt,
            "author_id": uid,
            "uid": uid,
            "math": math,
            "json": json,
            "requests": requests,
            "os": os,
            "Message": Message,
            "ThreadType": ThreadType
        }

        try:
            result = eval(code, globals(), local_vars)
            
            if result is None:
                response_text = "Null"
            else:
                response_text = str(result)

            self.style.reply_success(
                f"{response_text}",
                mo, tid, tt, uid, ttl=30000,
            )

        except Exception as e:
            self.style.reply_error(
                f"{str(e)}",
                mo, tid, tt, uid, ttl=15000,
            )


def _ns():
    return {"cls": NS, "name": "eval"}