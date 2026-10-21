from zlapi.models import Message


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        self._leave(mo, tid, tt, uid)

    def _check_admin(self, uid, mo, tid, tt):
        if not self.bot._is_admin(uid):
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )
            return False
        return True

    def _leave(self, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return

        try:
            self.style.reply_success(
                "tam bjet nhe tui di cht day",
                mo, tid, tt, uid, ttl=5000,
            )
            
            self.bot.leaveGroup(tid, imei=self.bot._imei)

        except Exception as e:
            self.style.reply_error(
                f"khong the roi nhom: {str(e)}",
                mo, tid, tt, uid, ttl=15000,
            )


def _ns():
    return {"cls": NS, "name": "leave"}