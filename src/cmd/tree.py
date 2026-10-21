import os
import sys
import platform
import time
from datetime import datetime

from zlapi.models import Message


def _format_uptime(seconds):
    d, rem = divmod(seconds, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d > 0:
        parts.append(f"{int(d)}d")
    if h > 0:
        parts.append(f"{int(h)}h")
    if m > 0:
        parts.append(f"{int(m)}m")
    if s > 0 or not parts:
        parts.append(f"{int(s)}s")
    return " ".join(parts)


class NS:
    def __init__(self, bot):
        self.bot = bot
        self._start_time = time.time()

    @property
    def style(self):
        return self.bot.style

    @property
    def reg(self):
        return self.bot.reg

    def _is_server(self):
        if hasattr(self.bot, 'is_server'):
            return self.bot.is_server
        if hasattr(self.bot, 'bot_id') and self.bot.bot_id:
            return False
        return os.environ.get("BOT_IS_SERVER") == "1"

    def _get_bot_info(self):
        is_server = self._is_server()
        bot_type = "SERVER" if is_server else "CLIENT"
        bot_id = getattr(self.bot, 'bot_id', 'MAIN')
        bot_uid = str(self.bot.uid)
        prefix = self.bot.prefix
        return bot_type, bot_id, bot_uid, prefix

    def _count_commands(self):
        total = len(self.reg.e)
        on = sum(1 for e in self.reg.e.values() if e.get("on", True))
        off = total - on
        return total, on, off

    def _count_handlers(self):
        return len(self.bot.engine.h)

    def _get_admin_count(self):
        admin_set = getattr(self.bot, '_admin_set', set())
        return len(admin_set)

    def _get_subbot_info(self):
        if not self._is_server():
            return None
        try:
            from src.mybot.manager import get_manager
            manager = get_manager()
            bots = manager.list_bots()
            total = len(bots)
            running = sum(1 for _, b in bots if b.running)
            stopped = total - running
            return total, running, stopped, bots
        except:
            return None

    def handle(self, msg, mo, tid, tt, uid):
        args = msg[len(self.bot.prefix):].strip().split()[1:]
        
        if args and args[0].lower() == "full":
            self._tree_full(mo, tid, tt, uid)
        else:
            self._tree_simple(mo, tid, tt, uid)

    def _tree_simple(self, mo, tid, tt, uid):
        bot_type, bot_id, bot_uid, prefix = self._get_bot_info()
        total_cmd, on_cmd, off_cmd = self._count_commands()
        handlers = self._count_handlers()
        admin_count = self._get_admin_count()
        
        lines = [
            f"{'═' * 30}",
            f"       BOT TREE INFO",
            f"{'═' * 30}",
            "",
            f"╭─ BOT INFO",
            f"│  ├─ Type: {bot_type}",
            f"│  ├─ ID: {bot_id}",
            f"│  ├─ UID: {bot_uid}",
            f"│  └─ Prefix: {prefix}",
            f"│",
            f"├─ COMMANDS",
            f"│  ├─ Total: {total_cmd}",
            f"│  ├─ On: {on_cmd}",
            f"│  ├─ Off: {off_cmd}",
            f"│  └─ Handlers: {handlers}",
            f"│",
            f"├─ ADMINS",
            f"│  └─ Total: {admin_count}",
        ]
        
        subbot_info = self._get_subbot_info()
        if subbot_info:
            total, running, stopped, bots = subbot_info
            lines.extend([
                f"│",
                f"├─ SUB BOTS",
                f"│  ├─ Total: {total}",
                f"│  ├─ Running: {running}",
                f"│  └─ Stopped: {stopped}",
            ])
        
        lines.extend([
            f"│",
            f"╰─ SYSTEM",
            f"   ├─ Python: {platform.python_version()}",
            f"   ├─ OS: {platform.system()}",
            f"   └─ Time: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            "",
            f"{'═' * 30}",
        ])
        
        self.style.reply_info(
            "\n".join(lines),
            mo, tid, tt, uid, ttl=30000
        )

    def _tree_full(self, mo, tid, tt, uid):
        bot_type, bot_id, bot_uid, prefix = self._get_bot_info()
        total_cmd, on_cmd, off_cmd = self._count_commands()
        handlers = self._count_handlers()
        admin_count = self._get_admin_count()
        
        lines = [
            f"{'═' * 35}",
            f"        BOT TREE INFO (FULL)",
            f"{'═' * 35}",
            "",
            f"╭─ BOT INFO",
            f"│  ├─ Type: {bot_type}",
            f"│  ├─ ID: {bot_id}",
            f"│  ├─ UID: {bot_uid}",
            f"│  └─ Prefix: {prefix}",
            f"│",
            f"├─ COMMANDS ({total_cmd})",
        ]
        
        cmd_items = list(self.reg.e.items())
        for i, (name, entry) in enumerate(cmd_items):
            status = "+" if entry.get("on", True) else "-"
            perm = entry.get("perm", 1)
            is_last = i == len(cmd_items) - 1
            connector = "└" if is_last else "├"
            lines.append(f"│  {connector}─ [{status}] {name} (p{perm})")
        
        lines.append(f"│")
        lines.append(f"├─ ADMINS ({admin_count})")
        
        admin_set = list(getattr(self.bot, '_admin_set', set()))
        admin_show = admin_set[:10]
        for i, admin_id in enumerate(admin_show):
            is_last = i == len(admin_show) - 1 and len(admin_set) <= 10
            connector = "└" if is_last else "├"
            try:
                name = self.bot.style.get_name(admin_id)
            except:
                name = admin_id
            lines.append(f"│  {connector}─ {name}")
        
        if len(admin_set) > 10:
            lines.append(f"│  └─ ... va {len(admin_set) - 10} admin khac")
        
        subbot_info = self._get_subbot_info()
        if subbot_info:
            total, running, stopped, bots = subbot_info
            lines.append(f"│")
            lines.append(f"├─ SUB BOTS ({total})")
            
            for i, (bid, bot) in enumerate(bots):
                status = "+" if bot.running else "-"
                is_last = i == len(bots) - 1
                connector = "└" if is_last else "├"
                bot_uid_sub = bot.bot_uid or "N/A"
                uptime = bot.get_uptime() if bot.running else "stopped"
                lines.append(f"│  {connector}─ [{status}] {bid}")
                pad = "   " if is_last else "│  "
                lines.append(f"│  {pad}  ├─ UID: {bot_uid_sub}")
                lines.append(f"│  {pad}  ├─ Prefix: {bot.prefix}")
                lines.append(f"│  {pad}  └─ Uptime: {uptime}")
        
        lines.extend([
            f"│",
            f"╰─ SYSTEM",
            f"   ├─ Python: {platform.python_version()}",
            f"   ├─ OS: {platform.system()} {platform.release()}",
            f"   ├─ Arch: {platform.machine()}",
            f"   └─ Time: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            "",
            f"{'═' * 35}",
        ])
        
        self.style.reply_info(
            "\n".join(lines),
            mo, tid, tt, uid, ttl=60000
        )


def _ns():
    return {"cls": NS, "name": "tree"}