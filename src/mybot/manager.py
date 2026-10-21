import os
import sys
import json
import time
import threading
import traceback


MYBOT_DIR = os.path.dirname(os.path.abspath(__file__))
BOTS_FILE = os.path.join(MYBOT_DIR, "bots.json")
ASSET_DIR = os.path.join(MYBOT_DIR, "asset")
DATA_DIR  = os.path.join(ASSET_DIR, "data")
TEMP_DIR  = os.path.join(ASSET_DIR, "temp")

try:
    import src as _src_pkg
    _SRC_DIR     = os.path.dirname(os.path.abspath(_src_pkg.__file__))
    PROJECT_ROOT = os.path.dirname(_SRC_DIR)
except ImportError:
    PROJECT_ROOT = os.path.dirname(os.path.dirname(MYBOT_DIR))
    _SRC_DIR     = os.path.join(PROJECT_ROOT, "src")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

SRC_CMD_DIR   = os.path.join(_SRC_DIR, "cmd")
MAIN_CMD_JSON = os.path.join(PROJECT_ROOT, "asset", "data", "cmd.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

print(f"[MYBOT] SRC_CMD_DIR  = {SRC_CMD_DIR}")
print(f"[MYBOT] MAIN_CMD_JSON = {MAIN_CMD_JSON}")
print(f"[MYBOT] DATA_DIR      = {DATA_DIR}")


def _load_bots():
    if os.path.exists(BOTS_FILE):
        with open(BOTS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def _save_bots(data):
    with open(BOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _update_admin_file(admin_file, bot_uid, owner_uid):
    admin_data = {"4": [], "3": [], "2": {}}
    if os.path.exists(admin_file):
        try:
            with open(admin_file, "r", encoding="utf-8") as f:
                admin_data = json.load(f)
        except Exception:
            pass
    for key in ("4", "3"):
        if key not in admin_data:
            admin_data[key] = []
    if "2" not in admin_data:
        admin_data["2"] = {}
    if bot_uid and str(bot_uid) not in admin_data["4"]:
        admin_data["4"].insert(0, str(bot_uid))
    if owner_uid and str(owner_uid) not in admin_data["4"]:
        admin_data["4"].append(str(owner_uid))
    with open(admin_file, "w", encoding="utf-8") as f:
        json.dump(admin_data, f, indent=4, ensure_ascii=False)
    print(f"[ADMIN] Updated: bot_uid={bot_uid}, owner_uid={owner_uid}")


def _load_admin_data(admin_file):
    data = {"4": [], "3": [], "2": {}}
    if os.path.exists(admin_file):
        try:
            with open(admin_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    for k in ("4", "3"):
        if k not in data:
            data[k] = []
    if "2" not in data:
        data["2"] = {}
    return data


class BotInstance:
    def __init__(self, bot_id, imei, cookies, prefix,
                 expire_at=None, owner_phone=None):
        self.bot_id     = bot_id
        self.imei       = imei
        self.cookies    = cookies
        self.prefix     = prefix
        self.expire_at  = expire_at
        self.owner_phone = owner_phone
        self.client     = None
        self.thread     = None
        self.running    = False
        self.start_time = None
        self.bot_uid    = None
        self.owner_uid  = None

    def start(self):
        if self.running:
            return False

        bot_id      = self.bot_id
        imei        = self.imei
        cookies     = self.cookies
        prefix      = self.prefix
        expire_at   = self.expire_at
        owner_phone = self.owner_phone
        instance    = self

        def _run():
            try:
                from zlapi import ZaloAPI
                from src.engine import Engine
                from src.chat_style import ChatStyle
                from src.core import (
                    C, log_info, log_warn,
                    Registry,
                    load_commands,
                    MessageParser,
                    ListenFilter,
                    ListenerMixin,
                    MessageHandlerMixin,
                )

                cmd_json    = os.path.join(DATA_DIR, f"cmd_{bot_id}.json")
                listen_json = os.path.join(DATA_DIR, f"listen_{bot_id}.json")
                admin_json  = os.path.join(DATA_DIR, f"admin_{bot_id}.json")

                class SubEngine(Engine):
                    def __init__(se, bot, reg, admins):
                        super().__init__(bot, reg, admins)
                        se.admin_file = admin_json

                    def _is_server(se):
                        return False

                    def _get_user_level(se, uid, tid):
                        a = _load_admin_data(se.admin_file)
                        uid_s = str(uid)
                        tid_s = str(tid)
                        if uid_s in a.get("4", []):
                            return 4
                        if uid_s in a.get("3", []):
                            return 3
                        if uid_s in a.get("2", {}).get(tid_s, []):
                            return 2
                        return 1

                class SubBot(ListenerMixin, MessageHandlerMixin, ZaloAPI):
                    def __init__(sb):
                        super().__init__("</>", "</>", imei, cookies)
                        sb.prefix      = prefix
                        sb.bot_id      = bot_id
                        sb.is_server   = False
                        sb.data_dir    = DATA_DIR
                        sb.temp_dir    = TEMP_DIR
                        sb.admin_file  = admin_json
                        sb.cmd_file    = cmd_json
                        sb.listen_file = listen_json
                        sb.owner_phone = owner_phone

                        sb._admin_set  = set()
                        sb.reg         = Registry(cmd_json)
                        sb.engine      = SubEngine(sb, sb.reg, sb._admin_set)
                        sb.style       = ChatStyle(sb)

                        sb._listen     = ListenFilter(listen_json)
                        sb._seen_mids  = {}
                        sb._seen_max   = 500
                        sb._parser     = MessageParser()

                    def _fetch_owner_uid(sb):
                        if not sb.owner_phone:
                            return None
                        try:
                            user_info = sb.fetchPhoneNumber(sb.owner_phone)
                            if user_info and hasattr(user_info, 'uid'):
                                owner_uid = str(user_info.uid)
                                print(f"[BOT {bot_id}] Owner UID fetched: {owner_uid} (Phone: {sb.owner_phone})")
                                return owner_uid
                        except Exception as e:
                            print(f"[BOT {bot_id}] Error fetching owner phone: {e}")
                        return None

                    def _setup_admin(sb):
                        bot_uid = str(sb.uid)
                        owner_uid = sb._fetch_owner_uid()
                        
                        _update_admin_file(admin_json, bot_uid, owner_uid)
                        
                        admin_data = _load_admin_data(admin_json)
                        sb._admin_set = set()
                        sb._admin_set.update(str(x) for x in admin_data.get("4", []))
                        sb._admin_set.update(str(x) for x in admin_data.get("3", []))
                        for ga in admin_data.get("2", {}).values():
                            sb._admin_set.update(str(x) for x in ga)
                        
                        sb.engine.admins = sb._admin_set
                        
                        instance.bot_uid = bot_uid
                        instance.owner_uid = owner_uid
                        
                        print(f"[BOT {bot_id}] Admin set: {sb._admin_set}")

                    def _boot(sb):
                        print(f"[SUB-BOT {bot_id}] Loading from: {SRC_CMD_DIR}")
                        count = load_commands(
                            SRC_CMD_DIR, "src.cmd",
                            sb.reg, sb.engine
                        )
                        log_info(
                            f"[SUB-BOT {bot_id}]  "
                            f"prefix={C.BOLD}'{sb.prefix}'{C.D}  "
                            f"registered={C.BOLD}{len(sb.reg.e)}{C.D}  "
                            f"handlers={C.BOLD}{count}{C.D}"
                        )
                        for nm in sb.reg.names():
                            if nm not in sb.engine.h:
                                log_warn(
                                    f"  [SUB-BOT {bot_id}] "
                                    f"'{nm}' in cmd.json but no handler"
                                )

                    def _is_admin(sb, uid):
                        return str(uid) in sb._admin_set

                client = SubBot()
                
                client._setup_admin()
                client._boot()

                instance.client     = client
                instance.running    = True
                instance.start_time = time.time()

                print(
                    f"[BOT {bot_id}] Started "
                    f"| UID: {instance.bot_uid} "
                    f"| Owner: {instance.owner_uid} "
                    f"| Prefix: {prefix}"
                )

                client.listen(run_forever=True, delay=0, thread=True)

                while instance.running:
                    if expire_at and time.time() >= expire_at:
                        print(f"[BOT {bot_id}] Expired, stopping...")
                        instance.stop()
                        break
                    time.sleep(1)

            except Exception as e:
                print(f"[BOT {bot_id}] Fatal error: {e}")
                traceback.print_exc()
                instance.running = False

        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()
        time.sleep(3)
        return True

    def stop(self):
        if not self.running:
            return False
        print(f"[BOT {self.bot_id}] Stopping...")
        self.running    = False
        self.start_time = None
        return True

    def restart(self):
        self.stop()
        time.sleep(2)
        return self.start()

    def get_status(self):
        if not self.running:
            return "stopped"
        if self.expire_at:
            remaining = self.expire_at - time.time()
            if remaining <= 0:
                return "expired"
            return f"running ({self._format_time(remaining)} left)"
        return "running (forever)"

    def get_uptime(self):
        if not self.start_time:
            return "N/A"
        return self._format_time(time.time() - self.start_time)

    def _format_time(self, seconds):
        d, rem = divmod(seconds, 86400)
        h, rem = divmod(rem, 3600)
        m, s   = divmod(rem, 60)
        parts = []
        if d > 0: parts.append(f"{int(d)}d")
        if h > 0: parts.append(f"{int(h)}h")
        if m > 0: parts.append(f"{int(m)}m")
        return " ".join(parts) or f"{int(s)}s"


class BotManager:
    def __init__(self):
        self.bots        = {}
        self.owner_phone = None
        self._load()

    def set_owner_phone(self, phone):
        self.owner_phone = str(phone)

    def _load(self):
        data = _load_bots()
        for bot_id, info in data.items():
            bot = BotInstance(
                bot_id,
                info["imei"],
                info["cookies"],
                info.get("prefix", "."),
                info.get("expire_at"),
                info.get("owner_phone"),
            )
            bot.bot_uid = info.get("bot_uid")
            bot.owner_uid = info.get("owner_uid")
            self.bots[bot_id] = bot

    def _save(self):
        data = {}
        for bot_id, bot in self.bots.items():
            data[bot_id] = {
                "imei":        bot.imei,
                "cookies":     bot.cookies,
                "prefix":      bot.prefix,
                "expire_at":   bot.expire_at,
                "auto_start":  bot.running,
                "owner_phone": bot.owner_phone,
                "bot_uid":     bot.bot_uid,
                "owner_uid":   bot.owner_uid,
            }
        _save_bots(data)

    def create_bot(self, imei, cookies, prefix="."):
        bot_id = str(int(time.time() * 1000))
        bot = BotInstance(bot_id, imei, cookies, prefix, owner_phone=self.owner_phone)
        self.bots[bot_id] = bot
        self._save()
        self._create_bot_files(bot_id)
        return bot_id

    def _create_bot_files(self, bot_id):
        cmd_file    = os.path.join(DATA_DIR, f"cmd_{bot_id}.json")
        listen_file = os.path.join(DATA_DIR, f"listen_{bot_id}.json")
        mute_file   = os.path.join(DATA_DIR, f"mute_{bot_id}.json")
        admin_file  = os.path.join(DATA_DIR, f"admin_{bot_id}.json")

        if not os.path.exists(cmd_file):
            if os.path.exists(MAIN_CMD_JSON):
                with open(MAIN_CMD_JSON, "r", encoding="utf-8") as f:
                    cmd_data = json.load(f)
                with open(cmd_file, "w", encoding="utf-8") as f:
                    json.dump(cmd_data, f, indent=4, ensure_ascii=False)
            else:
                fallback = {"commands": [
                    {"name":"test","alias":[],"desc":"lenh test",
                     "syntax":"{p}test","perm":1,"cd":5,"author":"System","on":True},
                ]}
                with open(cmd_file, "w", encoding="utf-8") as f:
                    json.dump(fallback, f, indent=4, ensure_ascii=False)

        if not os.path.exists(listen_file):
            with open(listen_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        if not os.path.exists(mute_file):
            with open(mute_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        if not os.path.exists(admin_file):
            with open(admin_file, "w", encoding="utf-8") as f:
                json.dump({"4": [], "3": [], "2": {}}, f, indent=4, ensure_ascii=False)

    def delete_bot(self, bot_id):
        if bot_id not in self.bots:
            return False
        bot = self.bots[bot_id]
        if bot.running:
            bot.stop()
        del self.bots[bot_id]
        self._save()
        for fname in (f"cmd_{bot_id}.json", f"listen_{bot_id}.json",
                       f"mute_{bot_id}.json", f"admin_{bot_id}.json"):
            fp = os.path.join(DATA_DIR, fname)
            if os.path.exists(fp):
                os.remove(fp)
        return True

    def get_bot(self, bot_id):
        return self.bots.get(bot_id)

    def list_bots(self):
        return list(self.bots.items())

    def start_bot(self, bot_id, duration=None):
        bot = self.bots.get(bot_id)
        if not bot:
            return False
        bot.expire_at = (time.time() + duration) if duration else None
        if self.owner_phone:
            bot.owner_phone = self.owner_phone
        result = bot.start()
        self._save()
        return result

    def stop_bot(self, bot_id):
        bot = self.bots.get(bot_id)
        if not bot:
            return False
        result = bot.stop()
        self._save()
        return result

    def restart_bot(self, bot_id):
        bot = self.bots.get(bot_id)
        if not bot:
            return False
        return bot.restart()

    def auto_start_all(self):
        data = _load_bots()
        started = []
        for bot_id, info in data.items():
            if info.get("auto_start"):
                bot = self.bots.get(bot_id)
                if bot and not bot.running:
                    if self.owner_phone:
                        bot.owner_phone = self.owner_phone
                    if self.start_bot(bot_id):
                        started.append(bot_id)
        if started:
            print(f"[MYBOT] Auto-started {len(started)} bots: {', '.join(started)}")
        else:
            print("[MYBOT] No bots to auto-start.")


_manager = None

def get_manager():
    global _manager
    if _manager is None:
        _manager = BotManager()
    return _manager