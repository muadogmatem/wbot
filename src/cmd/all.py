import json
import time
import threading

from zlapi.models import Message

_running = {}


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def _get_client_id(self, mo):
        if hasattr(mo, "cliMsgId") and mo.cliMsgId:
            return mo.cliMsgId
        if hasattr(mo, "msgId") and mo.msgId:
            return mo.msgId
        if hasattr(mo, "clientId") and mo.clientId:
            return mo.clientId
        return int(time.time() * 1000)

    def _send_mention(self, tid, content, uid, client_id=None):
        mention_str = json.dumps([{"pos": 0, "len": len(content), "uid": str(uid), "type": 1}], ensure_ascii=False)
        style_str = json.dumps({"styles": [{"start": 0, "len": len(content), "st": "c_15a85f"}, {"start": 0, "len": len(content), "st": "t"}], "ver": 0}, ensure_ascii=False)
        
        params = {"zpw_ver": 645, "zpw_type": 30, "nretry": 0}
        
        if client_id is None:
            client_id = int(time.time() * 1000)
            
        payload_params = {
            "grid": str(tid),
            "message": content,
            "mentionInfo": mention_str,
            "clientId": str(client_id),
            "visibility": 0,
            "ttl": 0,
            "textProperties": style_str
        }
        
        payload = {"params": self.bot._encode(payload_params)}
        
        try:
            response = self.bot._post("https://tt-group-wpa.chat.zalo.me/api/group/mention", params=params, data=payload)
            data = response.json()
            if data.get("error_code") == 0:
                return True
            return False
        except:
            return False

    def handle(self, msg, mo, tid, tt, uid):
        global _running

        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            self._usage(mo, tid, tt, uid)
        elif args[0].lower() == "stop":
            self._stop(mo, tid, tt, uid)
        elif args[0].lower() == "-h":
            self._run_hide(args[1:], mo, tid, tt, uid)
        else:
            self._run_all(args, mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        self.style.reply_info(
            "alo ni hao la ma",
            mo, tid, tt, uid, ttl=15000,
        )

    def _stop(self, mo, tid, tt, uid):
        global _running

        if not self.bot._is_admin(uid):
            return self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )

        stid = str(tid)
        if stid in _running and _running[stid]:
            _running[stid] = False
            self.style.reply_success(
                "da dung all",
                mo, tid, tt, uid, ttl=12000,
            )
        else:
            self.style.reply_warning(
                "khong co all nao dang chay",
                mo, tid, tt, uid, ttl=12000,
            )

    def _run_all(self, args, mo, tid, tt, uid):
        if not self.bot._is_admin(uid):
            return self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )

        content = " ".join(args)
        if not content:
            return self.style.reply_warning(
                "nhap noi dung. vi du: .all alo",
                mo, tid, tt, uid, ttl=12000,
            )

        self._send_mention(tid, content, uid)

    def _run_hide(self, args, mo, tid, tt, uid):
        global _running

        if not self.bot._is_admin(uid):
            return self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )

        if len(args) < 2:
            return self.style.reply_warning(
                "nhap so lan va noi dung. vi du: .all -h 5 alo",
                mo, tid, tt, uid, ttl=12000,
            )

        try:
            count = int(args[0])
            content = " ".join(args[1:])
        except (ValueError, IndexError):
            return self.style.reply_warning(
                "sai dinh dang. vi du: .all -h 5 alo",
                mo, tid, tt, uid, ttl=12000,
            )

        if not content:
            return self.style.reply_warning(
                "noi dung khong duoc trong",
                mo, tid, tt, uid, ttl=10000,
            )

        if count <= 0:
            return self.style.reply_warning(
                "so lan phai lon hon 0",
                mo, tid, tt, uid, ttl=10000,
            )

        client_id = self._get_client_id(mo)
        stid = str(tid)
        _running[stid] = True

        def _loop():
            global _running
            for i in range(count):
                if not _running.get(stid, False):
                    break
                try:
                    self._send_mention(tid, content, uid, client_id=client_id)
                except:
                    pass
                time.sleep(1)
            _running[stid] = False

        t = threading.Thread(target=_loop, daemon=True)
        t.start()


def _ns():
    return {"cls": NS, "name": "all"}