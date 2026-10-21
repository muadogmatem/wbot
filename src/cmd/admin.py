import os
import json

from zlapi.models import Message, ThreadType


ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "env.py")


def _get_admin_file(bot):
    if hasattr(bot, 'admin_file') and bot.admin_file:
        return bot.admin_file
    return None


def _load_env():
    env_data = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            exec(f.read(), env_data)
    return env_data


def _save_admin_env(admins):
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    skip_admin = False
    brace_count = 0
    
    for line in lines:
        if line.strip().startswith("ADMIN"):
            skip_admin = True
            brace_count = line.count("{") - line.count("}")
            if brace_count <= 0:
                skip_admin = False
            admin_str = json.dumps(admins, ensure_ascii=False, indent=4)
            new_lines.append(f"ADMIN = {admin_str}\n")
            continue
        
        if skip_admin:
            brace_count += line.count("{") - line.count("}")
            if brace_count <= 0:
                skip_admin = False
            continue
        
        new_lines.append(line)
    
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def _load_admin_json(admin_file):
    if os.path.exists(admin_file):
        try:
            with open(admin_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in ("4", "3"):
                if k not in data:
                    data[k] = []
            if "2" not in data:
                data["2"] = {}
            return data
        except:
            pass
    return {"4": [], "3": [], "2": {}}


def _save_admin_json(admin_file, admins):
    with open(admin_file, "w", encoding="utf-8") as f:
        json.dump(admins, f, indent=4, ensure_ascii=False)


def _get_admins_from_env():
    env_data = _load_env()
    admins = env_data.get("ADMIN", {})
    if isinstance(admins, list):
        return {"4": admins, "3": [], "2": {}}
    if not isinstance(admins, dict):
        return {"4": [], "3": [], "2": {}}
    if "4" not in admins:
        admins["4"] = []
    if "3" not in admins:
        admins["3"] = []
    if "2" not in admins:
        admins["2"] = {}
    return admins


def _get_admins(bot=None):
    if bot:
        admin_file = _get_admin_file(bot)
        if admin_file:
            return _load_admin_json(admin_file)
    return _get_admins_from_env()


def _save_admins(bot, admins):
    admin_file = _get_admin_file(bot)
    if admin_file:
        _save_admin_json(admin_file, admins)
    else:
        _save_admin_env(admins)


def _get_name(bot, uid):
    try:
        return bot.style.get_name(uid)
    except Exception:
        return str(uid)


def get_user_level(uid, tid=None, bot=None):
    admins = _get_admins(bot)
    uid = str(uid)
    
    if uid in admins.get("4", []):
        return 4
    
    if uid in admins.get("3", []):
        return 3
    
    if tid:
        tid = str(tid)
        group_admins = admins.get("2", {}).get(tid, [])
        if uid in group_admins:
            return 2
    
    return 1


def is_admin_level(uid, level, tid=None, bot=None):
    return get_user_level(uid, tid, bot) >= level


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    @property
    def reg(self):
        return self.bot.reg

    def _get_admins(self):
        return _get_admins(self.bot)

    def _save_admins(self, admins):
        _save_admins(self.bot, admins)

    def _get_user_level(self, uid, tid=None):
        return get_user_level(uid, tid, self.bot)

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            self._usage(mo, tid, tt, uid)
        elif args[0] == "-l" or args[0] == "list":
            self._list_admin(mo, tid, tt, uid)
        elif args[0] in ["2", "3", "4"]:
            self._toggle_admin(args[0], mo, tid, tt, uid)
        else:
            self._usage(mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        p = self.bot.prefix
        is_subbot = hasattr(self.bot, 'admin_file') and self.bot.admin_file
        
        self.style.reply_info(
            f"cach su dung admin:\n\n"
            f"{p}admin 2 @user: toggle admin\n"
            f"{p}admin 3 @user: toggle admin cap cao\n"
            f"{p}admin 4 @user: toggle owner\n"
            f"{p}admin -l: xem danh sach admin\n\n"
            f"cap quyen:\n"
            f"1 = thanh vien\n"
            f"2 = admin\n"
            f"3 = admin cap cao\n"
            f"4 = owner",
            mo, tid, tt, uid, ttl=20000,
        )

    def _check_permission(self, uid, target_level, mo, tid, tt):
        user_level = self._get_user_level(uid, tid)
        admins = self._get_admins()
        
        if target_level == 4:
            if not admins["4"] or str(uid) != str(admins["4"][0]):
                self.style.reply_denied(
                    "chi owner moi co quyen quan ly admin cap 4",
                    mo, tid, tt, uid, ttl=10000,
                )
                return False
        elif target_level == 3:
            if user_level < 4:
                self.style.reply_denied(
                    "chi owner moi co quyen quan ly admin cap cao",
                    mo, tid, tt, uid, ttl=10000,
                )
                return False
        elif target_level == 2:
            if user_level < 3:
                self.style.reply_denied(
                    "chi admin cap cao tro len moi co quyen quan ly admin",
                    mo, tid, tt, uid, ttl=10000,
                )
                return False
        
        return True

    def _extract_targets(self, mo):
        targets = []

        mentions = getattr(mo, "mentions", None)
        if mentions:
            if isinstance(mentions, list):
                for m in mentions:
                    uid = getattr(m, "uid", None)
                    if uid:
                        targets.append(str(uid))
            elif isinstance(mentions, dict):
                for uid in mentions:
                    targets.append(str(uid))

        if not targets:
            quote = getattr(mo, "quote", None)
            if quote:
                owner = getattr(quote, "ownerId", None)
                if owner:
                    targets.append(str(owner))

        return targets

    def _toggle_admin(self, level, mo, tid, tt, uid):
        level = str(level)
        
        if not self._check_permission(uid, int(level), mo, tid, tt):
            return

        targets = self._extract_targets(mo)
        
        if not targets:
            return self.style.reply_warning(
                "vui long tag hoac reply nguoi muon them/xoa admin",
                mo, tid, tt, uid, ttl=10000,
            )

        admins = self._get_admins()
        results = []

        for t in targets:
            name = _get_name(self.bot, t)
            
            if level == "4":
                if admins["4"] and t == str(admins["4"][0]):
                    results.append(f"khong the xoa owner")
                elif t in admins["4"]:
                    admins["4"].remove(t)
                    results.append(f"da xoa {name} khoi owner")
                else:
                    admins["4"].append(t)
                    results.append(f"da them {name} lam owner")
            
            elif level == "3":
                if t in admins["3"]:
                    admins["3"].remove(t)
                    results.append(f"da xoa {name} khoi admin cap cao")
                else:
                    admins["3"].append(t)
                    results.append(f"da them {name} lam admin cap cao")
            
            elif level == "2":
                tid_str = str(tid)
                if tid_str not in admins["2"]:
                    admins["2"][tid_str] = []
                
                if t in admins["2"][tid_str]:
                    admins["2"][tid_str].remove(t)
                    if not admins["2"][tid_str]:
                        del admins["2"][tid_str]
                    results.append(f"da xoa {name} khoi admin")
                else:
                    admins["2"][tid_str].append(t)
                    results.append(f"da them {name} lam admin")

        self._save_admins(admins)
        self._update_bot_admin_set(admins)

        self.style.reply_success(
            "\n\n".join(results),
            mo, tid, tt, uid, ttl=15000,
        )

    def _update_bot_admin_set(self, admins):
        admin_set = set()
        admin_set.update(admins.get("4", []))
        admin_set.update(admins.get("3", []))
        for group_admins in admins.get("2", {}).values():
            admin_set.update(group_admins)
        self.bot._admin_set = admin_set

    def _list_admin(self, mo, tid, tt, uid):
        user_level = self._get_user_level(uid, tid)
        if user_level < 3:
            return self.style.reply_denied(
                "ban khong co quyen xem danh sach admin",
                mo, tid, tt, uid, ttl=10000,
            )

        admins = self._get_admins()
        is_subbot = hasattr(self.bot, 'admin_file') and self.bot.admin_file
        
        lines = ["danh sach admin:", ""]
        
        if is_subbot:
            lines.append(f"(bot con - {getattr(self.bot, 'bot_id', 'N/A')})")
            lines.append("")
        
        lines.append("owner:")
        if admins["4"]:
            for i, admin_id in enumerate(admins["4"]):
                name = _get_name(self.bot, admin_id)
                if i == 0:
                    lines.append(f"  {i + 1}. {name} (owner)")
                else:
                    lines.append(f"  {i + 1}. {name}")
        else:
            lines.append("  (trong)")
        
        lines.append("")
        lines.append("admin cap cao:")
        if admins["3"]:
            for i, admin_id in enumerate(admins["3"]):
                name = _get_name(self.bot, admin_id)
                lines.append(f"  {i + 1}. {name}")
        else:
            lines.append("  (trong)")
        
        lines.append("")
        lines.append(f"admin (group nay - {tid}):")
        tid_str = str(tid)
        group_admins = admins["2"].get(tid_str, [])
        if group_admins:
            for i, admin_id in enumerate(group_admins):
                name = _get_name(self.bot, admin_id)
                lines.append(f"  {i + 1}. {name}")
        else:
            lines.append("  (trong)")

        total = len(admins["4"]) + len(admins["3"]) + len(group_admins)
        lines.append(f"\ntong: {total} admin")

        self.style.reply_info(
            "\n".join(lines),
            mo, tid, tt, uid, ttl=25000,
        )


def _ns():
    return {"cls": NS, "name": "admin"}