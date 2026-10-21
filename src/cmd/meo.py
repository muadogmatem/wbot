from zlapi.models import Message
import requests
import threading

class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()

        if len(parts) < 2:
            self.style.reply_warning(
                "vui long nhap teamcode",
                mo, tid, tt, uid, ttl=12000
            )
            return

        teamcode = parts[1]
        mode = "full"
        if len(parts) > 2 and parts[2].lower() in ["ghost", "g"]:
            mode = "ghost"

        self.style.reply_success(
            "waiting...",
            mo, tid, tt, uid, ttl=86400000
        )

        threading.Thread(
            target=self._fire_api,
            args=(teamcode, mode, mo, tid, tt, uid),
            daemon=True
        ).start()

    def _fire_api(self, teamcode, mode, mo, tid, tt, uid):
        try:
            resp = requests.get(
                f"http://localhost:5000/wbot?teamcode={teamcode}&mode={mode}",
                timeout=25
            )
            data = resp.json()

            if resp.status_code == 404:
                self.style.reply_success(
                    "sai teamcode roi thg ngoo",
                    mo, tid, tt, uid, ttl=60000
                )
                return

            if "error" in data and "results" not in data:
                error_msg = data.get("error", "")
                detail = data.get("detail", "")

                if "offline" in error_msg.lower():
                    self.style.reply_warning(
                        "hong cs acc nao chay dc het",
                        mo, tid, tt, uid, ttl=30000
                    )
                elif "Đang có" in error_msg:
                    self.style.reply_warning(
                        "dung cs spam ma",
                        mo, tid, tt, uid, ttl=15000
                    )
                elif "Hết acc" in error_msg:
                    self.style.reply_warning(
                        "hong con acc nao het",
                        mo, tid, tt, uid, ttl=30000
                    )
                else:
                    self.style.reply_warning(
                        error_msg,
                        mo, tid, tt, uid, ttl=30000
                    )
                return

            ghost_sent = data.get("ghost_sent", 0)
            total = data.get("total", 0)

            if ghost_sent > 0:
                self.style.reply_success(
                    "quo tau",
                    mo, tid, tt, uid, ttl=60000
                )
            else:
                self.style.reply_warning(
                    "hong gui dc ghost",
                    mo, tid, tt, uid, ttl=30000
                )

        except requests.Timeout:
            self.style.reply_warning(
                "api timeout",
                mo, tid, tt, uid, ttl=15000
            )
        except Exception:
            self.style.reply_warning(
                "loi api",
                mo, tid, tt, uid, ttl=15000
            )

def _ns():
    return {"cls": NS, "name": "meo"}