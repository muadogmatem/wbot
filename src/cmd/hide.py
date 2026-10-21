import json
import time
import threading

from zlapi.models import ThreadType

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

    def _send_glitch(self, tid, tt, content, client_id):
        try:
            params = {
                "zpw_ver": 686,
                "zpw_type": 30,
                "nretry": 0
            }
            
            msg_ref_data = {
                "id": "f21b78443cfaab4d3e382603b1cc68d3",
                "ts": 1782940694364,
                "logSrcType": 2,
                "fwLvl": 1,
                "rootMsgRef": {
                    "id": "f21b78443cfaab4d3e382603b1cc68d3",
                    "ts": 1782940694364,
                    "logSrcType": 2
                }
            }
            
            reference = {
                "type": 3,
                "data": json.dumps(msg_ref_data, ensure_ascii=False)
            }
            
            msg_info = {
                "message": content,
                "reference": json.dumps(reference, ensure_ascii=False)
            }
            
            decor_log = {
                "fw": {
                    "pmsg": {"st": 2, "ts": 1782940694364, "id": "f21b78443cfaab4d3e382603b1cc68d3"},
                    "rmsg": {"st": 2, "ts": 1782940694364, "id": "f21b78443cfaab4d3e382603b1cc68d3"},
                    "fwLvl": 1
                }
            }
            
            payload_params = {
                "ttl": 0,
                "msgType": 1,
                "totalIds": 1,
                "msgInfo": json.dumps(msg_info, ensure_ascii=False),
                "decorLog": json.dumps(decor_log, ensure_ascii=False)
            }
            
            if tt == ThreadType.USER or tt == 0:
                url = "https://tt-files-wpa.chat.zalo.me/api/message/mforward"
                payload_params["tids"] = [{"clientId": str(client_id), "uid": str(tid), "ttl": 0}]
            else:
                url = "https://tt-files-wpa.chat.zalo.me/api/group/mforward"
                payload_params["grids"] = [{"clientId": str(client_id), "grid": str(tid), "ttl": 0}]
            
            payload = {
                "params": self.bot._encode(payload_params)
            }
            
            response = self.bot._post(url, params=params, data=payload)
            data = response.json()
            return data.get("error_code") == 0
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
        else:
            self._run(args, mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        self.style.reply_info(
            "alo quo tau",
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
                "da dung hide",
                mo, tid, tt, uid, ttl=12000,
            )
        else:
            self.style.reply_warning(
                "khong co hide nao dang chay",
                mo, tid, tt, uid, ttl=12000,
            )

    def _run(self, args, mo, tid, tt, uid):
        global _running

        if not self.bot._is_admin(uid):
            return self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )

        if len(args) < 2:
            return self.style.reply_warning(
                "nhap so lan va noi dung. vi du: hide 100 alo",
                mo, tid, tt, uid, ttl=12000,
            )

        try:
            count = int(args[0])
            content = " ".join(args[1:])
        except (ValueError, IndexError):
            return self.style.reply_warning(
                "sai dinh dang. vi du: hide 100 alo",
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
                    self._send_glitch(tid, tt, content, client_id)
                except:
                    pass
            _running[stid] = False

        t = threading.Thread(target=_loop, daemon=True)
        t.start()


def _ns():
    return {"cls": NS, "name": "hide"}