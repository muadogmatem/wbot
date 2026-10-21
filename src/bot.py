import os
import json

from zlapi import ZaloAPI
from zlapi.models import *

from env import PREFIX, IMEI, COOKIES, ADMIN

from .engine import Engine
from .chat_style import ChatStyle
from .core import (
    C, log_info, log_warn,
    Registry,
    load_commands,
    MessageParser,
    ListenFilter,
    ListenerMixin,
    MessageHandlerMixin,
)

CMD_JSON = os.path.join(os.path.dirname(__file__), "..", "asset", "data", "cmd.json")
CMD_DIR = os.path.join(os.path.dirname(__file__), "cmd")
LISTEN_FILE = os.path.join(os.path.dirname(__file__), "..", "asset", "data", "listen.json")
RESTART_NOTIFY_FILE = os.path.join(os.path.dirname(__file__), "..", "asset", "temp", "restart_notify.json")


class Bot(ListenerMixin, MessageHandlerMixin, ZaloAPI):
    def __init__(self):
        super().__init__("</>", "</>", IMEI, COOKIES)
        self.prefix = PREFIX
        self.reg = Registry(CMD_JSON)
        self.engine = Engine(self, self.reg, self._build_admin_set())
        self.style = ChatStyle(self)

        self._admin_set = self._build_admin_set()
        self._listen = ListenFilter(LISTEN_FILE)
        self._seen_mids = {}
        self._seen_max = 500
        self._parser = MessageParser()

        self._boot()
        self._check_restart_notify()

    def _build_admin_set(self):
        admin_set = set()
        if isinstance(ADMIN, dict):
            admin_set.update(ADMIN.get("4", []))
            admin_set.update(ADMIN.get("3", []))
            for group_admins in ADMIN.get("2", {}).values():
                admin_set.update(group_admins)
        elif isinstance(ADMIN, list):
            admin_set.update(str(a) for a in ADMIN)
        elif isinstance(ADMIN, str):
            admin_set.add(ADMIN)
        return admin_set

    def _boot(self):
        count = load_commands(CMD_DIR, "src.cmd", self.reg, self.engine)
        
        is_server = os.environ.get("BOT_IS_SERVER") == "1"
        bot_type = "SERVER" if is_server else "CLIENT"
        
        log_info(
            f"type={C.BOLD}{bot_type}{C.D}  "
            f"prefix={C.BOLD}'{self.prefix}'{C.D}  "
            f"registered={C.BOLD}{len(self.reg.e)}{C.D}  "
            f"handlers={C.BOLD}{count}{C.D}"
        )
        for name in self.reg.names():
            if name not in self.engine.h:
                log_warn(f"  '{name}' in cmd.json but no handler file found")

    def _is_admin(self, uid):
        return str(uid) in self._admin_set

    def _check_restart_notify(self):
        if os.path.exists(RESTART_NOTIFY_FILE):
            try:
                with open(RESTART_NOTIFY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tid = data.get("tid")
                tt_val = data.get("tt")
                uid = data.get("uid")
                if tid and tt_val is not None:
                    tt = ThreadType(tt_val)
                    self.style.send_success("khoi dong lai bot thanh cong", tid, tt, uid, ttl=10000)
            except Exception as e:
                print(f"loi gui thong bao restart: {e}")
            finally:
                try:
                    os.remove(RESTART_NOTIFY_FILE)
                except Exception:
                    pass