import os
import json
from zlapi.models import Message
from src.cmd.admin import get_user_level


PERM_TEXT = {
    1: "thanh vien",
    2: "admin",
    3: "admin cap cao",
    4: "owner",
    5: "server"
}

MYBOT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "mybot", "asset", "data")


class NS:
    def __init__(self, bot):
        self.bot = bot

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

    def _get_user_level(self, uid, tid):
        return get_user_level(uid, tid, self.bot)

    def _get_subbot_cmd_files(self):
        files = []
        if os.path.exists(MYBOT_DATA_DIR):
            for f in os.listdir(MYBOT_DATA_DIR):
                if f.startswith("cmd_") and f.endswith(".json"):
                    files.append(os.path.join(MYBOT_DATA_DIR, f))
        return files

    def _get_running_subbots(self):
        try:
            from src.mybot.manager import get_manager
            manager = get_manager()
            return {bid: bot for bid, bot in manager.list_bots() if bot.running and bot.client}
        except:
            return {}

    def _sync_to_subbots(self, cmd_name, key, value):
        if not self._is_server():
            return 0
        
        count = 0
        running_bots = self._get_running_subbots()
        
        for cmd_file in self._get_subbot_cmd_files():
            try:
                bot_id = os.path.basename(cmd_file).replace("cmd_", "").replace(".json", "")
                
                with open(cmd_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                commands = data.get("commands", [])
                updated = False
                for cmd in commands:
                    if cmd.get("name") == cmd_name:
                        cmd[key] = value
                        updated = True
                        break
                
                if updated:
                    with open(cmd_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    count += 1
                    
                    if bot_id in running_bots:
                        subbot = running_bots[bot_id]
                        if subbot.client and hasattr(subbot.client, 'reg'):
                            subbot.client.reg.set(cmd_name, key, value)
            except:
                pass
        
        return count

    def _sync_full_to_subbots(self, cmd_name, entry):
        if not self._is_server():
            return 0
        
        count = 0
        running_bots = self._get_running_subbots()
        
        for cmd_file in self._get_subbot_cmd_files():
            try:
                bot_id = os.path.basename(cmd_file).replace("cmd_", "").replace(".json", "")
                
                with open(cmd_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                commands = data.get("commands", [])
                updated = False
                found = False
                
                for cmd in commands:
                    if cmd.get("name") == cmd_name:
                        for key in ["alias", "cd", "perm", "on", "desc", "syntax", "author"]:
                            if key in entry:
                                cmd[key] = entry[key]
                        updated = True
                        found = True
                        break
                
                if not found:
                    new_cmd = {"name": cmd_name}
                    for key in ["alias", "cd", "perm", "on", "desc", "syntax", "author"]:
                        if key in entry:
                            new_cmd[key] = entry[key]
                    commands.append(new_cmd)
                    data["commands"] = commands
                    updated = True
                
                if updated:
                    with open(cmd_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    count += 1
                    
                    if bot_id in running_bots:
                        subbot = running_bots[bot_id]
                        if subbot.client and hasattr(subbot.client, 'reg'):
                            if found:
                                for key in ["alias", "cd", "perm", "on", "desc", "syntax", "author"]:
                                    if key in entry:
                                        subbot.client.reg.set(cmd_name, key, entry[key])
                            else:
                                subbot.client.reg.e[cmd_name] = dict(entry)
            except:
                pass
        
        return count

    def _sync_full_all_to_subbots(self):
        if not self._is_server():
            return 0, 0, 0
        
        running_bots = self._get_running_subbots()
        server_cmds = dict(self.reg.e)
        
        total_files = 0
        total_updated = 0
        total_added = 0
        
        for cmd_file in self._get_subbot_cmd_files():
            try:
                bot_id = os.path.basename(cmd_file).replace("cmd_", "").replace(".json", "")
                
                with open(cmd_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                commands = data.get("commands", [])
                existing_names = {cmd.get("name") for cmd in commands}
                
                updated_count = 0
                added_count = 0
                
                for cmd in commands:
                    cmd_name = cmd.get("name")
                    if cmd_name in server_cmds:
                        entry = server_cmds[cmd_name]
                        for key in ["alias", "cd", "perm", "on", "desc", "syntax", "author"]:
                            if key in entry:
                                cmd[key] = entry[key]
                        updated_count += 1
                
                for cmd_name, entry in server_cmds.items():
                    if cmd_name not in existing_names:
                        new_cmd = {"name": cmd_name}
                        for key in ["alias", "cd", "perm", "on", "desc", "syntax", "author"]:
                            if key in entry:
                                new_cmd[key] = entry[key]
                        commands.append(new_cmd)
                        added_count += 1
                
                data["commands"] = commands
                
                with open(cmd_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                
                total_files += 1
                total_updated += updated_count
                total_added += added_count
                
                if bot_id in running_bots:
                    subbot = running_bots[bot_id]
                    if subbot.client and hasattr(subbot.client, 'reg'):
                        for cmd_name, entry in server_cmds.items():
                            if cmd_name in subbot.client.reg.e:
                                for key in ["alias", "cd", "perm", "on", "desc", "syntax", "author"]:
                                    if key in entry:
                                        subbot.client.reg.set(cmd_name, key, entry[key])
                            else:
                                subbot.client.reg.e[cmd_name] = dict(entry)
            except:
                pass
        
        return total_files, total_updated, total_added

    def handle(self, msg, mo, tid, tt, uid):
        args = msg[len(self.bot.prefix):].strip().split()[1:]
        if not args:
            return self._usage(mo, tid, tt, uid)

        act = args[0].lower()
        rest = args[1:]

        actions = {
            "info": self._info,
            "alias": self._alias,
            "cd": self._cd,
            "perm": self._perm,
            "toggle": self._toggle,
            "sync": self._sync,
        }

        fn = actions.get(act)
        if fn:
            fn(rest, mo, tid, tt, uid)
        else:
            self._usage(mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        p = self.bot.prefix
        is_server = self._is_server()
        
        perm_options = "1|2|3|4|5" if is_server else "1|2|3|4"
        perm_list = (
            f"1 = thanh vien\n"
            f"2 = admin\n"
            f"3 = admin cap cao\n"
            f"4 = owner"
        )
        if is_server:
            perm_list += f"\n5 = server"
        
        usage_text = (
            f"quan ly lenh bot\n\n"
            f"{p}cmd info <lenh>\n"
            f"{p}cmd alias <lenh> <a1,a2>\n"
            f"{p}cmd cd <lenh> <giay>\n"
            f"{p}cmd perm <lenh> <{perm_options}>\n"
            f"{p}cmd toggle <lenh>\n"
        )
        
        if is_server:
            usage_text += f"{p}cmd sync <lenh> - dong bo 1 lenh\n"
            usage_text += f"{p}cmd sync all - dong bo tat ca (cap nhat)\n"
            usage_text += f"{p}cmd sync full - dong bo tat ca (cap nhat + them moi)\n"
        
        usage_text += (
            f"\ncap quyen:\n"
            f"{perm_list}\n\n"
            f"dung {p}menu de xem danh sach lenh"
        )
        
        self.style.reply_info(usage_text, mo, tid, tt, uid, ttl=20000)

    def _check_admin(self, uid, tid, mo, tt):
        if self._get_user_level(uid, tid) < 3:
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000
            )
            return False
        return True

    def _info(self, a, mo, tid, tt, uid):
        if not a:
            return self.style.reply_warning(
                "thieu ten lenh.\ncu phap: cmd info <lenh>",
                mo, tid, tt, uid, ttl=10000
            )
        n = self.reg.resolve(a[0])
        if not n:
            return self.style.reply_error(
                f"lenh '{a[0]}' khong ton tai",
                mo, tid, tt, uid, ttl=10000
            )
        e = self.reg.get(n)
        p = self.bot.prefix
        status = "dang bat" if e.get("on", True) else "dang tat"
        alias_str = ", ".join(e.get("alias", [])) or "khong co"
        perm = e.get("perm", 1)
        perm_display = PERM_TEXT.get(perm, str(perm))
        self.style.reply_success(
            f"━━ {n.upper()} ━━\n\n"
            f"mo ta: {e.get('desc', '—')}\n"
            f"cu phap: {e.get('syntax', '—').replace('{p}', p)}\n"
            f"alias: {alias_str}\n"
            f"quyen: {perm_display} (cap {perm})\n"
            f"cooldown: {e.get('cd', 0)}s\n"
            f"author: {e.get('author', '—')}\n"
            f"trang thai: {status}",
            mo, tid, tt, uid, ttl=15000
        )

    def _alias(self, a, mo, tid, tt, uid):
        if not self._check_admin(uid, tid, mo, tt):
            return
        if len(a) < 2:
            return self.style.reply_warning(
                "cu phap: cmd alias <lenh> <a1,a2>",
                mo, tid, tt, uid, ttl=10000
            )
        n = self.reg.resolve(a[0])
        if not n:
            return self.style.reply_error(
                f"lenh '{a[0]}' khong ton tai",
                mo, tid, tt, uid, ttl=10000
            )
        als = [x.strip() for x in a[1].split(",") if x.strip()]
        for x in als:
            ex = self.reg.resolve(x)
            if ex and ex != n:
                return self.style.reply_error(
                    f"alias '{x}' da thuoc lenh '{ex}'",
                    mo, tid, tt, uid, ttl=10000
                )
        self.reg.set(n, "alias", als)
        
        sync_count = self._sync_to_subbots(n, "alias", als)
        
        result = f"da cap nhat alias cho '{n}':\n{', '.join(als)}"
        if sync_count > 0:
            result += f"\n\nda dong bo den {sync_count} bot con (realtime)"
        
        self.style.reply_success(result, mo, tid, tt, uid, ttl=10000)

    def _cd(self, a, mo, tid, tt, uid):
        if not self._check_admin(uid, tid, mo, tt):
            return
        if len(a) < 2:
            return self.style.reply_warning(
                "cu phap: cmd cd <lenh> <giay>",
                mo, tid, tt, uid, ttl=10000
            )
        n = self.reg.resolve(a[0])
        if not n:
            return self.style.reply_error(
                f"lenh '{a[0]}' khong ton tai",
                mo, tid, tt, uid, ttl=10000
            )
        try:
            s = float(a[1])
        except ValueError:
            return self.style.reply_error(
                "gia tri cooldown khong hop le",
                mo, tid, tt, uid, ttl=10000
            )
        self.reg.set(n, "cd", s)
        
        sync_count = self._sync_to_subbots(n, "cd", s)
        
        result = f"da dat cooldown cho '{n}' = {s}s"
        if sync_count > 0:
            result += f"\n\nda dong bo den {sync_count} bot con (realtime)"
        
        self.style.reply_success(result, mo, tid, tt, uid, ttl=10000)

    def _perm(self, a, mo, tid, tt, uid):
        if not self._check_admin(uid, tid, mo, tt):
            return
        
        is_server = self._is_server()
        perm_options = "1|2|3|4|5" if is_server else "1|2|3|4"
        
        if len(a) < 2:
            return self.style.reply_warning(
                f"cu phap: cmd perm <lenh> <{perm_options}>",
                mo, tid, tt, uid, ttl=10000
            )
        n = self.reg.resolve(a[0])
        if not n:
            return self.style.reply_error(
                f"lenh '{a[0]}' khong ton tai",
                mo, tid, tt, uid, ttl=10000
            )
        
        valid_perms = ("1", "2", "3", "4", "5") if is_server else ("1", "2", "3", "4")
        
        if a[1] not in valid_perms:
            valid_str = ", ".join(valid_perms)
            return self.style.reply_error(
                f"chi chap nhan: {valid_str}",
                mo, tid, tt, uid, ttl=10000
            )
        
        perm = int(a[1])
        perm_display = PERM_TEXT.get(perm, str(perm))
        self.reg.set(n, "perm", perm)
        
        sync_count = self._sync_to_subbots(n, "perm", perm)
        
        result = f"da dat quyen cho '{n}' = {perm_display} (cap {perm})"
        if sync_count > 0:
            result += f"\n\nda dong bo den {sync_count} bot con (realtime)"
        
        self.style.reply_success(result, mo, tid, tt, uid, ttl=10000)

    def _toggle(self, a, mo, tid, tt, uid):
        if not self._check_admin(uid, tid, mo, tt):
            return
        if not a:
            return self.style.reply_warning(
                "thieu ten lenh.\ncu phap: cmd toggle <lenh>",
                mo, tid, tt, uid, ttl=10000
            )
        n = self.reg.resolve(a[0])
        if not n:
            return self.style.reply_error(
                f"lenh '{a[0]}' khong ton tai",
                mo, tid, tt, uid, ttl=10000
            )
        cur = self.reg.get(n).get("on", True)
        new_state = not cur
        self.reg.set(n, "on", new_state)
        
        sync_count = self._sync_to_subbots(n, "on", new_state)
        
        if new_state:
            result = f"da BAT lenh '{n}'"
        else:
            result = f"da TAT lenh '{n}'"
        
        if sync_count > 0:
            result += f"\n\nda dong bo den {sync_count} bot con (realtime)"
        
        if new_state:
            self.style.reply_success(result, mo, tid, tt, uid, ttl=10000)
        else:
            self.style.reply_warning(result, mo, tid, tt, uid, ttl=10000)

    def _sync(self, a, mo, tid, tt, uid):
        if not self._check_admin(uid, tid, mo, tt):
            return
        
        if not self._is_server():
            return self.style.reply_denied(
                "lenh sync chi server moi dung duoc",
                mo, tid, tt, uid, ttl=10000
            )
        
        if not a:
            return self.style.reply_warning(
                "cu phap:\n"
                "cmd sync <lenh> - dong bo 1 lenh\n"
                "cmd sync all - dong bo tat ca (cap nhat)\n"
                "cmd sync full - dong bo tat ca (cap nhat + them moi)",
                mo, tid, tt, uid, ttl=10000
            )
        
        if a[0].lower() == "all":
            total_sync = 0
            cmd_count = 0
            
            for name, entry in self.reg.e.items():
                count = self._sync_full_to_subbots(name, entry)
                if count > 0:
                    total_sync = max(total_sync, count)
                cmd_count += 1
            
            return self.style.reply_success(
                f"da dong bo {cmd_count} lenh den {total_sync} bot con (realtime)\n\n"
                f"chi cap nhat lenh da co",
                mo, tid, tt, uid, ttl=10000
            )
        
        if a[0].lower() == "full":
            total_files, total_updated, total_added = self._sync_full_all_to_subbots()
            
            return self.style.reply_success(
                f"da dong bo den {total_files} bot con (realtime)\n\n"
                f"cap nhat: {total_updated} lenh\n"
                f"them moi: {total_added} lenh",
                mo, tid, tt, uid, ttl=10000
            )
        
        n = self.reg.resolve(a[0])
        if not n:
            return self.style.reply_error(
                f"lenh '{a[0]}' khong ton tai",
                mo, tid, tt, uid, ttl=10000
            )
        
        entry = self.reg.get(n)
        sync_count = self._sync_full_to_subbots(n, entry)
        
        self.style.reply_success(
            f"da dong bo lenh '{n}' den {sync_count} bot con (realtime)",
            mo, tid, tt, uid, ttl=10000
        )


def _ns():
    return {"cls": NS, "name": "cmd"}