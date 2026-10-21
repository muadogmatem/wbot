import os
import json
from zlapi.models import Message

DEFAULT_LISTEN_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "data", "listen.json")


def _get_listen_file(bot):
    if hasattr(bot, 'listen_file') and bot.listen_file:
        return bot.listen_file
    return DEFAULT_LISTEN_FILE


def _load(bot=None):
    listen_file = _get_listen_file(bot) if bot else DEFAULT_LISTEN_FILE
    try:
        with open(listen_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"groups": []}


def _save(data, bot=None):
    listen_file = _get_listen_file(bot) if bot else DEFAULT_LISTEN_FILE
    os.makedirs(os.path.dirname(listen_file), exist_ok=True)
    with open(listen_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_listening(thread_id, bot=None):
    data = _load(bot)
    return str(thread_id) in data.get("groups", [])


class NS:
    def __init__(self, bot):
        self.bot = bot

    def _is_server(self):
        if hasattr(self.bot, 'is_server'):
            return self.bot.is_server
        if hasattr(self.bot, 'bot_id') and self.bot.bot_id:
            return False
        return os.environ.get("BOT_IS_SERVER") == "1"

    def handle(self, msg, mo, tid, tt, uid):
        from src.chat_style import ChatStyle
        style = ChatStyle(self.bot)

        data = _load(self.bot)
        groups = data.get("groups", [])
        tid_str = str(tid)

        is_server = self._is_server()
        bot_type = "SERVER" if is_server else "CLIENT"
        bot_id = getattr(self.bot, 'bot_id', 'MAIN')

        if tid_str in groups:
            groups.remove(tid_str)
            data["groups"] = groups
            _save(data, self.bot)

            if hasattr(self.bot, "_listen_cache"):
                self.bot._listen_cache.discard(tid_str)
            
            if hasattr(self.bot, "_listen") and hasattr(self.bot._listen, "_cache"):
                self.bot._listen._cache.discard(tid_str)

            style.reply_warning(
                f"tao tat listen roi du me may",
                mo, tid, tt, uid, ttl=10000
            )
        else:
            groups.append(tid_str)
            data["groups"] = groups
            _save(data, self.bot)

            if hasattr(self.bot, "_listen_cache"):
                self.bot._listen_cache.add(tid_str)
            
            if hasattr(self.bot, "_listen") and hasattr(self.bot._listen, "_cache"):
                self.bot._listen._cache.add(tid_str)

            style.reply_success(
                f"tao bat listen roi ds thg ngoo",
                mo, tid, tt, uid, ttl=10000
            )


def _ns():
    return {"cls": NS, "name": "listen"}