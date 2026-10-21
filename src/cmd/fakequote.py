from zlapi.models import Message, ThreadType
import json
import time

try:
    from zlapi._utils import _util
except ImportError:
    _util = None


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []

        raw_args = " ".join(args)

        if "&" not in raw_args:
            self._usage(mo, tid, tt, uid)
            return

        content_parts = raw_args.split("&", 1)
        message_text = content_parts[0].strip() or " "
        fake_quote_content = content_parts[1].strip()

        if not fake_quote_content:
            self.style.reply_warning(
                "noi dung fake quote khong duoc trong!",
                mo, tid, tt, uid, ttl=15000,
            )
            return

        qmsgOwner = None
        qmsgId = None
        qmsgCliId = None
        qmsgTs = None

        quote = getattr(mo, "quote", None)
        mentions = getattr(mo, "mentions", None)

        if quote:
            ownerId = getattr(quote, "ownerId", None) or getattr(quote, "uidFrom", None)
            qmsgOwner = str(int(ownerId)) if ownerId else str(self.bot.uid)
            qmsgId = getattr(quote, "msgId", None)
            qmsgCliId = (
                getattr(quote, "cliMsgId", None) or getattr(quote, "cliId", None)
            )
            qmsgTs = getattr(quote, "ts", int(time.time() * 1000))

        elif mentions:
            first_uid = None
            if isinstance(mentions, list):
                for m in mentions:
                    if isinstance(m, dict):
                        first_uid = m.get("uid")
                    else:
                        first_uid = getattr(m, "uid", None)
                    if first_uid:
                        break
            elif isinstance(mentions, dict):
                keys = list(mentions.keys())
                if keys:
                    first_uid = keys[0]

            if first_uid:
                qmsgOwner = str(first_uid)
                now_ms = int(time.time() * 1000)
                qmsgId = now_ms
                qmsgCliId = now_ms
                qmsgTs = now_ms
            else:
                self.style.reply_warning(
                    "khong tim thay uid tu tag!",
                    mo, tid, tt, uid, ttl=15000,
                )
                return
        else:
            self.style.reply_warning(
                "hay reply tin nhan hoac tag nguoi muon fake quote!",
                mo, tid, tt, uid, ttl=15000,
            )
            return

        self._send_fake(
            message_text,
            fake_quote_content,
            qmsgOwner,
            qmsgId,
            qmsgCliId,
            qmsgTs,
            tid,
            tt,
            mo,
            uid,
        )

    def _usage(self, mo, tid, tt, uid):
        self.style.reply_info(
            "alo con meo",
            mo, tid, tt, uid, ttl=15000,
        )

    def _send_fake(
        self,
        message_text,
        fake_quote_content,
        qmsgOwner,
        qmsgId,
        qmsgCliId,
        qmsgTs,
        tid,
        tt,
        mo,
        uid,
    ):
        params_url = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0,
        }

        now_val = _util.now() if _util else int(time.time() * 1000)
        msg_type_val = _util.getClientMessageType(1) if _util else 1

        name = self.style.get_name(qmsgOwner)
        tag_line = f"@{name}"
        msg_content = f"{tag_line} {message_text}"

        mention_data = [{"pos": 0, "len": len(tag_line), "uid": str(qmsgOwner), "type": 0}]
        mention_json = json.dumps(mention_data, ensure_ascii=False)

        payload_params = {
            "message": msg_content,
            "clientId": now_val,
            "qmsgOwner": qmsgOwner,
            "qmsgId": qmsgId,
            "qmsgCliId": qmsgCliId,
            "qmsgType": msg_type_val,
            "qmsg": fake_quote_content,
            "qmsgTs": qmsgTs,
            "qmsgAttach": json.dumps({}),
            "qmsgTTL": 0,
            "ttl": 0,
            "mentionInfo": mention_json,
        }

        if tt == ThreadType.USER:
            url = "https://tt-chat2-wpa.chat.zalo.me/api/message/quote"
            payload_params["toid"] = str(tid)
        elif tt == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/quote"
            payload_params["visibility"] = 0
            payload_params["grid"] = str(tid)
        else:
            self.style.reply_error(
                "thread type khong hop le!",
                mo, tid, tt, uid, ttl=10000,
            )
            return

        payload = {"params": self.bot._encode(payload_params)}

        try:
            response = self.bot._post(url, params=params_url, data=payload)
            data = response.json()

            if data.get("error_code") == 0:
                self._delete_cmd_msg(mo, tid, tt, uid)
            else:
                error_code = data.get("error_code")
                error_message = (
                    data.get("error_message") or str(data.get("data", ""))
                )
                self.style.reply_error(
                    f"fake quote that bai #{error_code}: {error_message}",
                    mo, tid, tt, uid, ttl=10000,
                )
        except Exception as e:
            self.style.reply_error(
                f"loi gui fake quote: {str(e)}",
                mo, tid, tt, uid, ttl=10000,
            )

    def _delete_cmd_msg(self, mo, tid, tt, uid):
        try:
            cmd_msgId = getattr(mo, "msgId", None)
            cmd_cliMsgId = (
                getattr(mo, "cliMsgId", None)
                or getattr(mo, "clientId", None)
                or int(time.time() * 1000)
            )
            cmd_ownerId = uid

            if not cmd_msgId:
                return

            if tt == ThreadType.GROUP:
                self.bot.deleteGroupMsg(
                    cmd_msgId, cmd_ownerId, cmd_cliMsgId, tid
                )
            elif tt == ThreadType.USER:
                params = {"zpw_ver": 645, "zpw_type": 30}
                now_cli = _util.now() if _util else int(time.time() * 1000)
                payload = {
                    "params": self.bot._encode(
                        {
                            "toid": str(tid),
                            "cliMsgId": now_cli,
                            "msgs": [
                                {
                                    "cliMsgId": str(cmd_cliMsgId),
                                    "globalMsgId": str(cmd_msgId),
                                    "ownerId": str(cmd_ownerId),
                                    "destId": str(tid),
                                }
                            ],
                            "onlyMe": 0,
                        }
                    )
                }
                self.bot._post(
                    "https://tt-chat2-wpa.chat.zalo.me/api/message/deletemsg",
                    params=params,
                    data=payload,
                )
        except:
            pass


def _ns():
    return {"cls": NS, "name": "fakequote"}