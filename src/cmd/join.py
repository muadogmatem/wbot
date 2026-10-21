from zlapi.models import Message


MSG_ERR = {
    0: "da tham gia nhom thanh cong",
    240: "da gui yeu cau tham gia, cho duyet",
    178: "bot da la thanh vien nhom nay",
    221: "khong tim thay nhom hoac ma nhom khong hop le",
    227: "link nhom khong ton tai hoac bi chan",
    175: "bot bi chan trong nhom nay",
    1003: "nhom da day thanh vien",
    1004: "gioi han thanh vien nhom",
    1022: "yeu cau tham gia da duoc gui truoc do"
}


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split(maxsplit=1)
        
        link = parts[1].strip() if len(parts) > 1 else None
        
        if not link and mo.quote:
            quoted_text = getattr(mo.quote, "content", None) or getattr(mo.quote, "text", None)
            if quoted_text:
                link = str(quoted_text).strip()
        
        if not link:
            self._usage(mo, tid, tt, uid)
        else:
            self._join(link, mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        self.style.reply_info(
            "ban mun join nhom nao",
            mo, tid, tt, uid, ttl=15000,
        )

    def _check_admin(self, uid, mo, tid, tt):
        if not self.bot._is_admin(uid):
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )
            return False
        return True

    def _join(self, link, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return

        if "zalo.me/g/" not in link:
            self.style.reply_warning(
                "link nhom khong hop le\nvi du: https://zalo.me/g/xxxxxx",
                mo, tid, tt, uid, ttl=10000,
            )
            return

        try:
            result = self.bot.joinGroup(link)
            
            error_code = None
            if hasattr(result, "error_code"):
                error_code = result.error_code
            elif isinstance(result, dict):
                error_code = result.get("error_code") or result.get("errorCode")
            
            if error_code is None:
                error_code = 0
            
            error_code = int(error_code)
            message = MSG_ERR.get(error_code, f"loi khong xac dinh (code: {error_code})")
            
            if error_code in [0, 240]:
                self.style.reply_success(message, mo, tid, tt, uid, ttl=15000)
            elif error_code == 178:
                self.style.reply_info(message, mo, tid, tt, uid, ttl=15000)
            else:
                self.style.reply_warning(message, mo, tid, tt, uid, ttl=15000)

        except Exception as e:
            self.style.reply_error(
                f"loi: {str(e)}",
                mo, tid, tt, uid, ttl=15000,
            )


def _ns():
    return {"cls": NS, "name": "join"}