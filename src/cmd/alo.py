import time
import shlex
from zlapi.models import Message


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        
        try:
            parts = shlex.split(text)
        except ValueError:
            parts = text.split()
        
        count = 5
        mode = "forward"
        idx = 1
        
        if len(parts) > idx and parts[idx].isdigit():
            count = int(parts[idx])
            idx += 1
            
        if len(parts) > idx and parts[idx].lower() in ['-l', '-c', '--link', '--card']:
            mode = "link"
            idx += 1
            
        message_text = " ".join(parts[idx:])
        
        if not message_text:
            self._usage(mo, tid, tt, uid)
        else:
            self._spam(count, mode, message_text, mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        self.style.reply_info(
            "alo con meo",
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

    def _spam(self, count, mode, message_text, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return

        if count > 100:
            self.style.reply_warning(
                "gioi han toi da 100 tin nhan moi lan spam de tranh bi khoa tai khoan",
                mo, tid, tt, uid, ttl=10000,
            )
            return

        self.style.reply_info(
            "ni hao la ma",
            mo, tid, tt, uid, ttl=5000,
        )

        success = 0
        fail = 0

        for i in range(count):
            try:
                if mode == "link":
                    if message_text.startswith("http"):
                        link_url = message_text
                    else:
                        link_url = message_text.replace(" ", "") + ".conMeo"
                    
                    self.bot.sendLinkCards(
                        thread_id=tid,
                        thread_type=tt,
                        link=link_url,
                        tw=512,
                        th=512,
                        title=message_text,
                        desc=message_text,
                        thumb="https://sf-static.upanhlaylink.com/img/image_202606271315768028e904fed2da7c18e505dad6.jpg",
                        message=message_text,
                        ttl=0
                    )
                else:
                    self.bot.sendMessageForward(
                        thread_id=tid,
                        thread_type=tt,
                        message=message_text,
                        ttl=0
                    )
                success += 1
                time.sleep(0.1)
            except Exception:
                fail += 1
                time.sleep(1)

        self.style.reply_success(
            "quo tau",
            mo, tid, tt, uid, ttl=10000,
        )


def _ns():
    return {"cls": NS, "name": "alo"}