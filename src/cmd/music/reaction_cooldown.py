import time
import threading

from .music_handler import delete_message


def _reaction_obj(msg_id, cli_id, msg_type="chat.photo"):
    return type("M", (), {
        "msgId": msg_id,
        "cliMsgId": cli_id,
        "msgType": msg_type
    })()


def _build_rmsg(mo):
    msg_type = getattr(mo, "msgType", 1)
    try:
        from zlapi._util import getClientMessageType
        msg_type = getClientMessageType(msg_type)
    except Exception:
        pass
    return {
        "gMsgID": int(mo.msgId),
        "cMsgID": int(mo.cliMsgId),
        "msgType": msg_type,
    }


def multi_react(client, mo, icon, count, tid, tt):
    try:
        if count <= 0:
            return
        r = _build_rmsg(mo)
        client.sendMultiReaction(
            reactionObj=[r.copy() for _ in range(count)],
            reactionIcon=icon,
            thread_id=tid,
            thread_type=tt,
            reactionType=75,
        )
    except Exception:
        pass


def remove_multi_react(client, mo, icon, count, tid, tt):
    try:
        if count <= 0:
            return
        r = _build_rmsg(mo)
        client.sendMultiReaction(
            reactionObj=[r.copy() for _ in range(count)],
            reactionIcon=icon,
            thread_id=tid,
            thread_type=tt,
            reactionType=-1,
        )
    except Exception:
        pass


def cooldown_react_then_delete(client, msg_id, cli_id, tid, tt, seconds, icon="🕐", msg_type="chat.photo"):
    try:
        mo = _reaction_obj(msg_id, cli_id, msg_type)
        secs = max(1, int(seconds))

        current = secs
        multi_react(client, mo, icon, current, tid, tt)

        while current > 0:
            time.sleep(1)
            remove_multi_react(client, mo, icon, current, tid, tt)
            current -= 1
            if current > 0:
                time.sleep(0.05)
                multi_react(client, mo, icon, current, tid, tt)

        time.sleep(0.05)

        try:
            delete_message(client, tid, tt, {
                "msgId": msg_id,
                "cliMsgId": cli_id,
                "msgType": msg_type
            })
        except Exception:
            pass

        time.sleep(0.05)

        try:
            client.sendReaction(mo, "", tid, tt, reactionType=-1)
        except Exception:
            pass
    except Exception:
        pass


def start_cooldown_react_then_delete(client, msg_info, tid, tt, seconds, icon="🕐", msg_type="chat.photo"):
    try:
        if not msg_info:
            return
        msg_id = msg_info.get("msgId")
        cli_id = msg_info.get("cliMsgId")
        if not msg_id or not cli_id:
            return
        threading.Thread(
            target=cooldown_react_then_delete,
            args=(client, msg_id, cli_id, tid, tt, seconds, icon, msg_type),
            daemon=True
        ).start()
    except Exception:
        pass