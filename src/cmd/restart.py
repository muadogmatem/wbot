import os
import sys
import json
import time
import threading

TEMP_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "temp", "restart_notify.json")


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return
        self._restart(mo, tid, tt, uid)

    def _check_admin(self, uid, mo, tid, tt):
        if not self.bot._is_admin(uid):
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000
            )
            return False
        return True

    def _restart(self, mo, tid, tt, uid):
        self.style.reply_success(
            "dang khoi dong lai bot...",
            mo, tid, tt, uid, ttl=5000
        )

        def do_restart():
            time.sleep(2)
            try:
                os.makedirs(os.path.dirname(TEMP_FILE), exist_ok=True)
                tt_val = tt.value if hasattr(tt, "value") else int(tt)
                with open(TEMP_FILE, "w", encoding="utf-8") as f:
                    json.dump({"tid": tid, "tt": tt_val, "uid": uid}, f)
            except Exception:
                pass
            os.execv(sys.executable, [sys.executable] + sys.argv)

        threading.Thread(target=do_restart, daemon=True).start()


def _ns():
    return {"cls": NS, "name": "restart"}