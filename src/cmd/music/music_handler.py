import time
import threading

from src.core.reactions import REACTIONS, ReactionManager

_search_cache = {}
_cache_lock = threading.Lock()
CACHE_TTL = 120

_platform_senders = {}


def register_platform(name, send_fn):
    _platform_senders[name] = send_fn


def clean_cache():
    now = time.time()
    with _cache_lock:
        expired = [k for k, v in _search_cache.items() if now - v.get("timestamp", 0) > CACHE_TTL]
        for k in expired:
            del _search_cache[k]


def save_search(tid, uid, songs, platform, search_img_info=None):
    clean_cache()
    key = f"{tid}_{uid}"
    with _cache_lock:
        _search_cache[key] = {
            "songs": songs,
            "platform": platform,
            "timestamp": time.time(),
            "search_img_info": search_img_info,
        }


def has_pending(tid, uid):
    clean_cache()
    key = f"{tid}_{uid}"
    return key in _search_cache


def get_pending(tid, uid):
    clean_cache()
    key = f"{tid}_{uid}"
    return _search_cache.get(key)


def clear_pending(tid, uid):
    key = f"{tid}_{uid}"
    with _cache_lock:
        _search_cache.pop(key, None)


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
        print(f"[MusicHandler] get_msg_info error: {e}")
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
        print(f"[MusicHandler] delete_message error: {e}")
        return False


class MusicHandler:

    def __init__(self, bot):
        self.bot = bot
        self.reaction = ReactionManager(bot)

    @property
    def style(self):
        return self.bot.style

    def try_handle(self, msg, mo, tid, tt, uid):
        content = msg.strip()
        if not content:
            return False

        first = content.split()[0]
        if not first.isdigit():
            return False

        if not has_pending(tid, uid):
            return False

        self.reaction.react(mo, REACTIONS["cooldown"], tid, tt)

        return self._process_selection(content, mo, tid, tt, uid)

    def _process_selection(self, content, mo, tid, tt, uid):
        data = get_pending(tid, uid)
        if not data:
            return False

        songs = data["songs"]
        platform = data["platform"]
        search_img_info = data.get("search_img_info")

        parts = content.strip().split(maxsplit=1)
        try:
            index = int(parts[0]) - 1
        except (ValueError, IndexError):
            return False

        sub_cmd = None
        if len(parts) > 1:
            sub_cmd = parts[1].strip().lower()
            if sub_cmd in ("lrc", "lyrics"):
                sub_cmd = "lyric"

        if index < 0 or index >= len(songs):
            self.style.reply_warning(
                f"chon tu 1 den {len(songs)}",
                mo, tid, tt, uid, ttl=10000
            )
            return True

        track = songs[index]
        
        if search_img_info:
            try:
                delete_message(self.bot, tid, tt, search_img_info)
            except Exception:
                pass

        clear_pending(tid, uid)

        send_fn = _platform_senders.get(platform)
        if not send_fn:
            self.style.reply_warning(
                f"platform {platform} chua duoc ho tro",
                mo, tid, tt, uid, ttl=10000
            )
            return True

        try:
            send_fn(self.bot, track, sub_cmd, mo, tid, tt, uid)
            self.reaction.remove_react(mo, REACTIONS["cooldown"], tid, tt)
            self.reaction.react(mo, REACTIONS["received"], tid, tt)
        except Exception as e:
            self.reaction.remove_react(mo, REACTIONS["cooldown"], tid, tt)
            self.reaction.react(mo, REACTIONS["error"], tid, tt)
            self.style.reply_warning(f"loi: {e}", mo, tid, tt, uid, ttl=10000)

        return True