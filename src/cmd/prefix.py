import os
from zlapi.models import Message
from src.cmd.admin import get_user_level


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def _get_user_level(self, uid, tid):
        return get_user_level(uid, tid, self.bot)

    def _is_server(self):
        if hasattr(self.bot, 'is_server'):
            return self.bot.is_server
        if hasattr(self.bot, 'bot_id') and self.bot.bot_id:
            return False
        return os.environ.get("BOT_IS_SERVER") == "1"

    def handle(self, msg, mo, tid, tt, uid):
        text = msg.strip()
        parts = text.split()
        
        if len(parts) == 1 and parts[0].lower() == "prefix":
            self._show_prefix(mo, tid, tt, uid)
        elif len(parts) >= 2 and parts[0].lower() == "prefix":
            self._set_prefix(parts[1], mo, tid, tt, uid)

    def _show_prefix(self, mo, tid, tt, uid):
        is_server = self._is_server()
        bot_type = "SERVER" if is_server else "CLIENT"
        bot_id = getattr(self.bot, 'bot_id', 'MAIN')

        self.style.reply_info(
            f"prefix hien tai: {self.bot.prefix}\n\n"
            f"[{bot_type}] ID: {bot_id}",
            mo, tid, tt, uid, ttl=15000
        )

    def _set_prefix(self, new_prefix, mo, tid, tt, uid):
        if self._get_user_level(uid, tid) < 4:
            return self.style.reply_denied(
                "ban can quyen admin cap cao de doi prefix",
                mo, tid, tt, uid, ttl=10000
            )

        old_prefix = self.bot.prefix
        self.bot.prefix = new_prefix

        is_server = self._is_server()

        if is_server:
            self._save_to_env(new_prefix)
        else:
            self._save_to_bots_json(new_prefix)

        bot_type = "SERVER" if is_server else "CLIENT"
        bot_id = getattr(self.bot, 'bot_id', 'MAIN')

        self.style.reply_success(
            f"da doi prefix thanh cong!\n\n"
            f"cu: {old_prefix}\n"
            f"moi: {new_prefix}\n\n"
            f"[{bot_type}] ID: {bot_id}",
            mo, tid, tt, uid, ttl=15000
        )

    def _save_to_env(self, new_prefix):
        try:
            env_file = os.path.join(os.path.dirname(__file__), "..", "..", "env.py")
            
            with open(env_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                if line.strip().startswith("PREFIX"):
                    new_lines.append(f'PREFIX = "{new_prefix}"\n')
                else:
                    new_lines.append(line)

            with open(env_file, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            print(f"[PREFIX] Error saving to env.py: {e}")

    def _save_to_bots_json(self, new_prefix):
        try:
            bot_id = getattr(self.bot, 'bot_id', None)
            if not bot_id:
                return

            from src.mybot.manager import get_manager
            manager = get_manager()
            bot = manager.get_bot(bot_id)
            if bot:
                bot.prefix = new_prefix
                manager._save()
        except Exception as e:
            print(f"[PREFIX] Error saving to bots.json: {e}")


def _ns():
    return {"cls": NS, "name": "prefix"}