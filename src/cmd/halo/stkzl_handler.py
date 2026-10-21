import time
import threading

_pending_lock = threading.Lock()
_pending = {}

CACHE_TTL = 120


def save_sticker_search(tid, uid, stickers, cate_id, img_info=None):
    with _pending_lock:
        _pending[(tid, uid)] = {
            "stickers": stickers,
            "cate_id": cate_id,
            "img_info": img_info,
            "ts": time.time(),
        }


def get_sticker_search(tid, uid):
    with _pending_lock:
        data = _pending.get((tid, uid))
        if not data:
            return None
        if time.time() - data["ts"] > CACHE_TTL:
            _pending.pop((tid, uid), None)
            return None
        return data


def has_sticker_pending(tid, uid):
    return get_sticker_search(tid, uid) is not None


def clear_sticker_search(tid, uid):
    with _pending_lock:
        _pending.pop((tid, uid), None)


def get_msg_info(bot, tid, msg_id):
    if not msg_id:
        return None
    try:
        return {
            "msgId": msg_id,
            "cliMsgId": getattr(msg_id, "cliMsgId", str(int(time.time() * 1000))),
            "ownerId": str(bot.uid),
            "msgType": "chat.photo",
        }
    except:
        return None