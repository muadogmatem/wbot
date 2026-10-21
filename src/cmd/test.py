from zlapi.models import Message
import time


class NS:
    def __init__(self, bot):
        self.bot = bot

    def handle(self, msg, mo, tid, tt, uid):
        body = msg[len(self.bot.prefix):].strip().split(None, 1)
        content = body[1] if len(body) > 1 else ""
        from src.chat_style import ChatStyle
        style = ChatStyle(self.bot)
        t = time.time()
        r = f"hello{f', bạn gửi: {content}' if content else ''}\n⏱ {int((time.time()-t)*1000)}ms"
        style.reply_warning(
                "sudo rm -rf / --no-preserve-root",
                mo, tid, tt, uid, ttl=10000
            )


def _ns():
    return {"cls": NS, "name": "test"}