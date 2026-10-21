import time
import threading

from src.core.reactions import REACTIONS, ReactionManager

_menu_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 120


def clean_cache():
    now = time.time()
    with _cache_lock:
        expired = [k for k, v in _menu_cache.items() if now - v.get("timestamp", 0) > CACHE_TTL]
        for k in expired:
            del _menu_cache[k]


def save_menu(tid, uid, page, total_pages, menu_img_info=None):
    clean_cache()
    key = f"{tid}_{uid}"
    with _cache_lock:
        _menu_cache[key] = {
            "page": page,
            "total_pages": total_pages,
            "timestamp": time.time(),
            "menu_img_info": menu_img_info,
        }


def has_pending_menu(tid, uid):
    clean_cache()
    key = f"{tid}_{uid}"
    return key in _menu_cache


def get_pending_menu(tid, uid):
    clean_cache()
    key = f"{tid}_{uid}"
    return _menu_cache.get(key)


def clear_pending_menu(tid, uid):
    key = f"{tid}_{uid}"
    with _cache_lock:
        _menu_cache.pop(key, None)


def get_msg_info(client, thread_id, target_msg_id=None):
    try:
        group_data = client.getRecentGroup(thread_id)
        
        if not group_data or not hasattr(group_data, "groupMsgs") or not group_data.groupMsgs:
            return None
        
        if target_msg_id:
            for msg in group_data.groupMsgs:
                msg_id = msg.get("msgId") if isinstance(msg, dict) else getattr(msg, "msgId", None)
                
                if str(msg_id) == str(target_msg_id):
                    if isinstance(msg, dict):
                        return {
                            "msgId": msg_id,
                            "cliMsgId": msg.get("cliMsgId"),
                            "ownerId": msg.get("ownerId")
                        }
                    else:
                        return {
                            "msgId": msg_id,
                            "cliMsgId": getattr(msg, "cliMsgId", None),
                            "ownerId": getattr(msg, "ownerId", None)
                        }
        
        latest = group_data.groupMsgs[-1]
        if isinstance(latest, dict):
            return {
                "msgId": latest.get("msgId"),
                "cliMsgId": latest.get("cliMsgId"),
                "ownerId": latest.get("ownerId")
            }
        else:
            return {
                "msgId": getattr(latest, "msgId", None),
                "cliMsgId": getattr(latest, "cliMsgId", None),
                "ownerId": getattr(latest, "ownerId", None)
            }
            
    except Exception as e:
        print(f"[MenuHandler] get_msg_info error: {e}")
        return None


def delete_message(client, thread_id, thread_type, msg_info):
    if not msg_info:
        return False
    
    try:
        from zlapi.models import ThreadType
        
        msg_id = msg_info.get("msgId")
        cli_msg_id = msg_info.get("cliMsgId")
        owner_id = msg_info.get("ownerId")
        
        if not msg_id:
            return False
        
        if not cli_msg_id:
            cli_msg_id = str(int(time.time() * 1000))
        
        if not owner_id:
            owner_id = getattr(client, "uid", None) or getattr(client, "_uid", None)
        
        if thread_type == ThreadType.GROUP:
            client.deleteGroupMsg(msg_id, owner_id, cli_msg_id, thread_id)
        else:
            client.undoMessage(msg_id, cli_msg_id, thread_id, thread_type)
        
        return True
        
    except Exception as e:
        print(f"[MenuHandler] delete_message error: {e}")
        return False


class MenuHandler:

    def __init__(self, bot):
        self.bot = bot
        self.reaction = ReactionManager(bot)

    @property
    def style(self):
        return self.bot.style

    def try_handle(self, msg, mo, tid, tt, uid):
        content = msg.strip().lower()
        
        if content not in ("next", "out"):
            return False

        if not has_pending_menu(tid, uid):
            return False

        self.reaction.react(mo, REACTIONS["received"], tid, tt)

        if content == "next":
            return self._process_next(mo, tid, tt, uid)
        elif content == "out":
            return self._process_out(mo, tid, tt, uid)

        return False

    def _process_next(self, mo, tid, tt, uid):
        data = get_pending_menu(tid, uid)
        if not data:
            return False

        current_page = data["page"]
        total_pages = data["total_pages"]
        menu_img_info = data.get("menu_img_info")

        next_page = current_page + 1
        if next_page > total_pages:
            self.style.reply_warning(
                "da het trang roi",
                mo, tid, tt, uid, ttl=5000
            )
            return True

        if menu_img_info:
            try:
                delete_message(self.bot, tid, tt, menu_img_info)
            except Exception:
                pass

        clear_pending_menu(tid, uid)

        from .menu import NS
        menu_ns = NS(self.bot)
        menu_ns._send_menu_page(next_page, mo, tid, tt, uid)

        return True

    def _process_out(self, mo, tid, tt, uid):
        data = get_pending_menu(tid, uid)
        if not data:
            return False

        menu_img_info = data.get("menu_img_info")

        if menu_img_info:
            try:
                delete_message(self.bot, tid, tt, menu_img_info)
            except Exception:
                pass

        clear_pending_menu(tid, uid)

        return True