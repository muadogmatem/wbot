import time
import threading
from zlapi.models import Message, ThreadType

_running = {}
WS_CONCURRENT_THREADS = 5

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

        if not args:
            self._run_ws(mo, tid, tt, uid)
        elif args[0].lower() == "stop":
            self._stop(mo, tid, tt, uid)

    def _check_admin(self, uid, mo, tid, tt):
        if not self.bot._is_admin(uid):
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )
            return False
        return True

    def _stop(self, mo, tid, tt, uid):
        global _running

        if not self._check_admin(uid, mo, tid, tt):
            return

        stid = str(tid)
        if stid in _running and _running[stid]:
            _running[stid] = False
            self.style.reply_success(
                "het iu roi a",
                mo, tid, tt, uid, ttl=12000,
            )
        else:
            self.style.reply_warning(
                "hong cs iu ai het",
                mo, tid, tt, uid, ttl=12000,
            )

    def _get_message_ids(self, response, tid):
        global_msg_id = getattr(response, 'msgId', None)
        if not global_msg_id:
            return None
            
        cli_msg_id = None
        owner_id = None
        
        try:
            group_data = self.bot.getRecentGroup(tid)
            
            if group_data and hasattr(group_data, 'groupMsgs') and group_data.groupMsgs:
                for msg in group_data.groupMsgs:
                    msg_id = msg.get('msgId') if isinstance(msg, dict) else getattr(msg, 'msgId', None)
                    
                    if str(msg_id) == str(global_msg_id):
                        if isinstance(msg, dict):
                            cli_msg_id = msg.get('cliMsgId')
                            owner_id = msg.get('ownerId')
                        else:
                            cli_msg_id = getattr(msg, 'cliMsgId', None)
                            owner_id = getattr(msg, 'ownerId', None)
                        break
                
                if not cli_msg_id:
                    latest = group_data.groupMsgs[-1]
                    if isinstance(latest, dict):
                        cli_msg_id = latest.get('cliMsgId')
                        owner_id = latest.get('ownerId')
                        global_msg_id = latest.get('msgId', global_msg_id)
                    else:
                        cli_msg_id = getattr(latest, 'cliMsgId', None)
                        owner_id = getattr(latest, 'ownerId', None)
                        global_msg_id = getattr(latest, 'msgId', global_msg_id)
        except Exception as e:
            print(f"[WS] getRecentGroup error: {e}")

        if not cli_msg_id:
            cli_msg_id = str(int(time.time() * 1000))
            
        if not owner_id:
            owner_id = getattr(self.bot, 'uid', None)

        return {
            "msgId": str(global_msg_id), 
            "cliMsgId": str(cli_msg_id), 
            "ownerId": str(owner_id)
        }

    def _run_ws(self, mo, tid, tt, uid):
        global _running

        if not self._check_admin(uid, mo, tid, tt):
            return

        stid = str(tid)
        if _running.get(stid):
            return self.style.reply_warning(
                "quo tau",
                mo, tid, tt, uid, ttl=10000,
            )

        _running[stid] = True
        self.style.reply_success(
            "ni hao la ma",
            mo, tid, tt, uid, ttl=5000,
        )

        msg_list = []
        for i in range(5):
            if not _running.get(stid, False): 
                break
                
            try:
                response = self.bot.replyMessage(
                    Message(text=f"alo"), 
                    mo, tid, tt, ttl=0
                )
                
                ids = self._get_message_ids(response, tid)
                if ids:
                    msg_list.append(ids)
                    
            except Exception as e:
                print(f"[WS] Error sending message: {e}")
                
            time.sleep(1)

        if not msg_list:
            _running[stid] = False
            return self.style.reply_warning(
                "gui tin nhan that bai, khong lay duoc ID",
                mo, tid, tt, uid, ttl=10000,
            )

        self.style.reply_success(
            f"oo chua oi",
            mo, tid, tt, uid, ttl=5000,
        )

        react_list_data = []
        for m in msg_list:
            react_list_data.append({
                "gMsgId": m['msgId'],
                "cMsgId": m['cliMsgId'],
                "uId": m['ownerId']
            })

        def _ws_worker():
            while _running.get(stid, False):
                for m in msg_list:
                    if not _running.get(stid, False): 
                        break
                    try:
                        self.bot.undoMessage(m['msgId'], m['cliMsgId'], tid, tt)
                        self.bot.deleteGroupMsg(m['msgId'], m['ownerId'], m['cliMsgId'], tid)
                        self.bot.undoMessage(m['msgId'], m['cliMsgId'], tid, tt)
                        self.bot.deleteGroupMsg(m['msgId'], m['ownerId'], m['cliMsgId'], tid)
                        self.bot.undoMessage(m['msgId'], m['cliMsgId'], tid, tt)
                        self.bot.deleteGroupMsg(m['msgId'], m['ownerId'], m['cliMsgId'], tid)
                        self.bot.undoMessage(m['msgId'], m['cliMsgId'], tid, tt)
                        self.bot.deleteGroupMsg(m['msgId'], m['ownerId'], m['cliMsgId'], tid)
                    except:
                        pass
                
                if _running.get(stid, False):
                    try:
                        self.bot.sendMultiReaction(react_list_data, "❤️", tid, tt, 75)
                    except:
                        pass
                
                time.sleep(0.01)
            
            _running[stid] = False

        for _ in range(WS_CONCURRENT_THREADS):
            t = threading.Thread(target=_ws_worker, daemon=True)
            t.start()


def _ns():
    return {"cls": NS, "name": "iu"}