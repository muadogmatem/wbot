import os
import json
import time
import re
import threading

from zlapi.models import Message, ThreadType, GroupEventType


GROUP_ANTI_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "data", "group-anti.json")
EVENT_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "data", "group-event.json")

_spam_action_locks = {}
_lock_timeout = 5  


def _get_group_anti_file(bot):
    if hasattr(bot, "bot_id") and bot.bot_id:
        base_dir = os.path.join(os.path.dirname(__file__), "..", "mybot", "asset", "data")
        return os.path.join(base_dir, f"group-anti_{bot.bot_id}.json")
    return GROUP_ANTI_FILE


def _load(bot=None):
    file_path = _get_group_anti_file(bot)
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return _get_default_config()
    return _get_default_config()


def _get_default_config():
    return {
        "antilink": {},
        "antivoice": {},
        "antiphoto": {},
        "antivideo": {},
        "antisticker": {},
        "antilocation": {},
        "antigif": {},
        "antifile": {},
        "anticard": {},
        "antisdt": {},
        "antiforward": {},
        "antispam": {},
        "auto_approve": {},
        "violations": {},
        "permanent_violations": {},
        "spam_tracking": {},
        "spam_warned": {},
        "spam_notified": {},
        "spam_action_time": {},
        "forward_count": {},
        "config": {}
    }


def _save(data, bot=None):
    file_path = _get_group_anti_file(bot)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _load_event_settings(bot=None):
    if os.path.exists(EVENT_SETTINGS_FILE):
        try:
            with open(EVENT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"enabled_groups": []}
    return {"enabled_groups": []}


def _save_event_settings(data, bot=None):
    os.makedirs(os.path.dirname(EVENT_SETTINGS_FILE), exist_ok=True)
    with open(EVENT_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _get_name(bot, uid):
    try:
        return bot.style.get_name(uid)
    except Exception:
        return str(uid)


def _is_group_admin(bot, group_id, user_id):
    try:
        group_details = bot.fetchGroupInfo(group_id)
        if not group_details or not hasattr(group_details, 'gridInfoMap'):
            return False

        group_info = group_details.gridInfoMap.get(str(group_id))
        if not group_info:
            return False

        creator_id = group_info.get('creatorId')
        admin_ids = group_info.get('adminIds', [])

        user_id_str = str(user_id)
        
        if user_id_str == str(creator_id):
            return True
        
        if user_id_str in [str(admin) for admin in admin_ids]:
            return True
        
        return False
    except Exception as e:
        print(f"[Group] Loi kiem tra group admin: {e}")
        return False


def _get_group_config(thread_id, bot=None):
    data = _load(bot)
    tid = str(thread_id)
    
    if "config" not in data:
        data["config"] = {}
    
    if tid not in data["config"]:
        data["config"][tid] = {
            "max_violations": 3,
            "punishment_method": "ban"
        }
        _save(data, bot)
    
    return data["config"][tid]


def is_enabled(anti_type, thread_id, bot=None):
    data = _load(bot)
    return data.get(anti_type, {}).get(str(thread_id), False)


def is_auto_approve_enabled(thread_id, bot=None):
    return is_enabled("auto_approve", thread_id, bot)


def handle_join_request(bot, event_data):
    group_id = event_data.get("groupId")
    if not group_id:
        return
    
    if not is_auto_approve_enabled(group_id, bot):
        return
    
    members = event_data.get("updateMembers", [])
    if not members:
        return
    
    member_ids = [member.get("id") for member in members if member.get("id")]
    if not member_ids:
        return
    
    try:
        print(f"[AutoApprove] Approving {len(member_ids)} members in group {group_id}")
        result = bot.handleGroupPending(member_ids, group_id, isApprove=True)
        print(f"[AutoApprove] Approved successfully: {result}")
    except Exception as e:
        print(f"[AutoApprove] Error approving members: {e}")
        import traceback
        traceback.print_exc()


def _is_forward_message(message_object):
    try:
        ref = getattr(message_object, "reference", None)
        if not ref:
            return False

        if isinstance(ref, dict):
            raw = ref.get("data")
        else:
            raw = getattr(ref, "data", None)
        
        if not raw:
            return False

        if isinstance(raw, str):
            ref_data = json.loads(raw)
        else:
            ref_data = raw
        
        return bool(ref_data.get("fwLvl"))
    except:
        return False


def _is_url_in_message(message_object):
    msg_type = getattr(message_object, "msgType", "") or ""
    
    url_regex = re.compile(
        r'(?:(?:https?://)|(?:www\.))[\w.-]+\.(?:[a-zA-Z]{2,})[\w\/?=&%.-]*|(?<!\w)[\w-]+\.(com|vn|net|org|info|xyz|me|link|top|site|io|tv|cc|biz|us|uk|au|ca)(?:\.[\w-]+)*[\w\/?=&%.-]*(?!\w)',
        re.IGNORECASE
    )
    
    if msg_type.startswith("chat.photo") or msg_type == "chat.photo":
        content = getattr(message_object, "content", None)
        attach = getattr(message_object, "attach", None)
        
        if isinstance(content, dict):
            title = content.get("title", "")
            if title and url_regex.search(str(title)):
                print(f"[AntiLink] Found URL in photo title: {title}")
                return True
        
        if isinstance(attach, dict):
            title = attach.get("title", "")
            if title and url_regex.search(str(title)):
                print(f"[AntiLink] Found URL in photo attach title: {title}")
                return True
        elif attach:
            title = getattr(attach, "title", "")
            if title and url_regex.search(str(title)):
                print(f"[AntiLink] Found URL in photo attach title: {title}")
                return True
        
        return False
    
    ignored_types = [
        "chat.video", 
        "chat.voice",
        "chat.gif",
        "share.file",
        "chat.sticker",
        "chat.location.new"
    ]
    
    for ignored in ignored_types:
        if msg_type.startswith(ignored) or msg_type == ignored:
            return False
    
    if msg_type == "chat.recommended":
        content = getattr(message_object, "content", None)
        attach = getattr(message_object, "attach", None)
        
        action = ""
        href = ""
        
        if isinstance(content, dict):
            action = content.get("action", "")
            href = content.get("href", "")
        
        if not action and isinstance(attach, dict):
            action = attach.get("action", "")
        elif not action and attach:
            action = getattr(attach, "action", "")
        
        if not href and isinstance(attach, dict):
            params = attach.get("params", {})
            if isinstance(params, dict):
                href = params.get("href", "")
            if not href:
                href = attach.get("href", "")
        elif not href and attach:
            params = getattr(attach, "params", None)
            if isinstance(params, dict):
                href = params.get("href", "")
            if not href:
                href = getattr(attach, "href", "")
        
        if action in ["recommened.user", "recommened.group"]:
            print(f"[AntiLink] Skipping card (action: {action}) - handled by anticard")
            return False
        
        if action == "recommened.link":
            if href and url_regex.search(str(href)):
                print(f"[AntiLink] Blocked recommened.link with URL: {href}")
                return True
        
        if href and url_regex.search(str(href)):
            print(f"[AntiLink] Found URL in recommended (action: {action}): {href}")
            return True
        
        if isinstance(content, dict):
            title = content.get("title", "")
            if title and url_regex.search(str(title)):
                print(f"[AntiLink] Found URL in recommended title: {title}")
                return True
        
        return False
    
    content = getattr(message_object, "content", None)
    
    if content:
        if hasattr(content, "title"):
            title = getattr(content, "title", "")
            if title and url_regex.search(str(title)):
                print(f"[AntiLink] Found URL in content.title: {title[:100]}")
                return True
        
        if hasattr(content, "text"):
            text = getattr(content, "text", "")
            if text and url_regex.search(str(text)):
                print(f"[AntiLink] Found URL in content.text: {text[:100]}")
                return True
        
        if hasattr(content, "msg"):
            msg = getattr(content, "msg", "")
            if msg and url_regex.search(str(msg)):
                print(f"[AntiLink] Found URL in content.msg: {msg[:100]}")
                return True
        
        if isinstance(content, dict):
            text_content = content.get("text", "") or content.get("msg", "") or content.get("title", "")
            if text_content and url_regex.search(str(text_content)):
                print(f"[AntiLink] Found URL in content dict: {str(text_content)[:100]}")
                return True
            
            href = content.get("href", "")
            if href and url_regex.search(str(href)):
                print(f"[AntiLink] Found URL in content.href: {href}")
                return True
        elif isinstance(content, str):
            if url_regex.search(content):
                print(f"[AntiLink] Found URL in content string: {content[:100]}")
                return True
    
    msg_text = getattr(message_object, "msg", None) or getattr(message_object, "text", None)
    if msg_text and url_regex.search(str(msg_text)):
        print(f"[AntiLink] Found URL in msg/text field: {str(msg_text)[:100]}")
        return True
    
    return False


def _has_phone_number(message_object):
    msg_type = getattr(message_object, "msgType", "") or ""
    
    ignored_types = [
        "chat.photo",
        "chat.video", 
        "chat.voice",
        "chat.gif",
        "share.file",
        "chat.sticker",
        "chat.location.new",
        "chat.recommended"
    ]
    
    for ignored in ignored_types:
        if msg_type.startswith(ignored) or msg_type == ignored:
            return False
    
    text = getattr(message_object, "content", None) or ""
    
    if isinstance(text, dict):
        text = text.get("text", "") or text.get("msg", "")
    
    if not text:
        return False
    
    phone_patterns = [
        r'(\+84|84|0)(3|5|7|8|9)\d{8}',  
        r'\b0\d{9}\b',  
        r'\b\d{10}\b',  
    ]
    
    text_str = str(text)
    for pattern in phone_patterns:
        if re.search(pattern, text_str):
            return True
    
    return False


def _check_msg_type(anti_type, message_object):
    msg_type = getattr(message_object, "msgType", "") or ""
    
    type_map = {
        "antilink": lambda: _is_url_in_message(message_object),
        "antivoice": lambda: msg_type == "chat.voice",
        "antiphoto": lambda: msg_type.startswith("chat.photo"),
        "antivideo": lambda: msg_type == "chat.video.msg",
        "antisticker": lambda: msg_type == "chat.sticker",
        "antilocation": lambda: msg_type == "chat.location.new",
        "antigif": lambda: msg_type == "chat.gif",
        "antifile": lambda: msg_type == "share.file",
        "anticard": lambda: msg_type == "chat.recommended" and not _is_url_in_message(message_object),
        "antisdt": lambda: _has_phone_number(message_object),
        "antiforward": lambda: _is_forward_message(message_object),
    }
    
    checker = type_map.get(anti_type)
    if checker:
        return checker()
    return False


_checker_started = {}


def _start_checker(bot):
    global _checker_started
    bot_key = getattr(bot, "bot_id", "main") or "main"
    if bot_key in _checker_started:
        return
    _checker_started[bot_key] = True

    def _loop():
        while True:
            try:
                data = _load(bot)
                now = time.time()
                changed = False
                
                
                spam_tracking = data.get("spam_tracking", {})
                for tid in list(spam_tracking.keys()):
                    for uid in list(spam_tracking[tid].keys()):
                        timestamps = spam_tracking[tid][uid]
                        cleaned = [t for t in timestamps if now - t <= 3]
                        if cleaned:
                            spam_tracking[tid][uid] = cleaned
                        else:
                            del spam_tracking[tid][uid]
                            changed = True
                    
                    if not spam_tracking[tid]:
                        del spam_tracking[tid]
                        changed = True

                
                spam_action_time = data.get("spam_action_time", {})
                for tid in list(spam_action_time.keys()):
                    for uid in list(spam_action_time[tid].keys()):
                        for action_type in list(spam_action_time[tid][uid].keys()):
                            last_time = spam_action_time[tid][uid][action_type]
                            if now - last_time > 10:  
                                del spam_action_time[tid][uid][action_type]
                                changed = True
                        
                        if not spam_action_time[tid][uid]:
                            del spam_action_time[tid][uid]
                            changed = True
                    
                    if not spam_action_time[tid]:
                        del spam_action_time[tid]
                        changed = True

                
                spam_warned = data.get("spam_warned", {})
                for tid in list(spam_warned.keys()):
                    for uid in list(spam_warned[tid].keys()):
                        warned_time = spam_warned[tid][uid]
                        if isinstance(warned_time, bool):
                            
                            spam_warned[tid][uid] = now
                            changed = True
                        elif now - warned_time > 30:
                            del spam_warned[tid][uid]
                            changed = True
                    
                    if not spam_warned[tid]:
                        del spam_warned[tid]
                        changed = True

                if changed:
                    data["spam_tracking"] = spam_tracking
                    data["spam_action_time"] = spam_action_time
                    data["spam_warned"] = spam_warned
                    _save(data, bot)

                global _spam_action_locks
                for key in list(_spam_action_locks.keys()):
                    if now - _spam_action_locks[key] > _lock_timeout:
                        del _spam_action_locks[key]

            except Exception as e:
                print(f"[Checker] Error: {e}")
            time.sleep(2)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def _can_send_action(thread_id, user_id, action_type):
    global _spam_action_locks
    key = f"{thread_id}_{user_id}_{action_type}"
    now = time.time()
    
    if key in _spam_action_locks:
        last_time = _spam_action_locks[key]
        if now - last_time < _lock_timeout:
            return False
    
    _spam_action_locks[key] = now
    return True


def check_spam(bot, author_id, message_object, thread_id, thread_type):
    if thread_type != ThreadType.GROUP:
        return False
    
    msg_type = getattr(message_object, "msgType", "") or ""
    if msg_type == "chat.reaction":
        return False
    
    if not is_enabled("antispam", thread_id, bot):
        return False
    
    if bot._is_admin(author_id):
        return False
    
    if _is_group_admin(bot, thread_id, author_id):
        return False
    
    data = _load(bot)
    spam_tracking = data.get("spam_tracking", {})
    spam_warned = data.get("spam_warned", {})
    spam_notified = data.get("spam_notified", {})
    spam_action_time = data.get("spam_action_time", {})
    config = _get_group_config(thread_id, bot)
    
    tid = str(thread_id)
    uid = str(author_id)
    
    if tid not in spam_tracking:
        spam_tracking[tid] = {}
    if uid not in spam_tracking[tid]:
        spam_tracking[tid][uid] = []
    
    now = time.time()
    timestamps = spam_tracking[tid][uid]
    timestamps.append(now)
    timestamps = [t for t in timestamps if now - t <= 3]
    spam_tracking[tid][uid] = timestamps
    
    data["spam_tracking"] = spam_tracking
    _save(data, bot)
    
    spam_threshold = 5  
    kick_threshold = 8  
    
    count = len(timestamps)
    name = _get_name(bot, author_id)
    
    if count >= kick_threshold:
        if tid not in spam_notified:
            spam_notified[tid] = {}
        
        if uid not in spam_notified.get(tid, {}):
            if not _can_send_action(tid, uid, "kiss"):
                return True
            
            try:
                method = config.get("punishment_method", "ban")
                action_text = "kiss" if method == "kiss" else "ban"
                
                spam_notified[tid][uid] = now
                
                if tid not in spam_action_time:
                    spam_action_time[tid] = {}
                if uid not in spam_action_time[tid]:
                    spam_action_time[tid][uid] = {}
                spam_action_time[tid][uid]["kiss"] = now
                
                data["spam_notified"] = spam_notified
                data["spam_action_time"] = spam_action_time
                _save(data, bot)
                
                bot.style.send_warning(
                    f"{name} da bi {action_text} khoi nhom do spam tin nhan",
                    thread_id, thread_type, author_id, ttl=10000
                )
                
                time.sleep(0.5)
                
                if method == "kiss":
                    bot.kickUsersInGroup(author_id, thread_id)
                else:
                    bot.blockUsersInGroup(author_id, thread_id)
                
                if tid in spam_tracking and uid in spam_tracking[tid]:
                    del spam_tracking[tid][uid]
                    if not spam_tracking[tid]:
                        del spam_tracking[tid]
                
                if tid in spam_warned and uid in spam_warned.get(tid, {}):
                    del spam_warned[tid][uid]
                    if not spam_warned[tid]:
                        del spam_warned[tid]
                
                if tid in spam_notified and uid in spam_notified.get(tid, {}):
                    del spam_notified[tid][uid]
                    if not spam_notified[tid]:
                        del spam_notified[tid]
                
                data["spam_tracking"] = spam_tracking
                data["spam_warned"] = spam_warned
                data["spam_notified"] = spam_notified
                _save(data, bot)
                
                print(f"[AntiSpam] Kicked {name} and cleaned up data")
                
            except Exception as e:
                print(f"[AntiSpam] Loi xu ly: {e}")
                import traceback
                traceback.print_exc()
        
        return True
    
    elif count >= spam_threshold:
        if tid not in spam_warned:
            spam_warned[tid] = {}
        
        if uid not in spam_warned.get(tid, {}):
            if not _can_send_action(tid, uid, "warn"):
                return False
            
            bot.style.send_warning(
                f"{name} dang gui tin nhan qua nhanh\nVui long giam toc do de tranh bi kiss",
                thread_id, thread_type, author_id, ttl=10000
            )
            
            spam_warned[tid][uid] = now
            
            if tid not in spam_action_time:
                spam_action_time[tid] = {}
            if uid not in spam_action_time[tid]:
                spam_action_time[tid][uid] = {}
            spam_action_time[tid][uid]["warn"] = now
            
            data["spam_warned"] = spam_warned
            data["spam_action_time"] = spam_action_time
            _save(data, bot)
    
    elif count < spam_threshold and uid in spam_warned.get(tid, {}):
        del spam_warned[tid][uid]
        if not spam_warned[tid]:
            del spam_warned[tid]
        data["spam_warned"] = spam_warned
        _save(data, bot)
    
    return False


def check_and_handle(bot, anti_type, message_object, thread_id, thread_type, author_id, mid):
    if thread_type != ThreadType.GROUP:
        return False
    
    if not is_enabled(anti_type, thread_id, bot):
        return False
    
    if not _check_msg_type(anti_type, message_object):
        return False
    
    if bot._is_admin(author_id):
        return False
    
    if _is_group_admin(bot, thread_id, author_id):
        return False
    
    try:
        data = _load(bot)
        permanent_violations = data.get("permanent_violations", {})
        forward_count = data.get("forward_count", {})
        config = _get_group_config(thread_id, bot)
        max_violations = config.get("max_violations", 3)
        
        tid = str(thread_id)
        uid = str(author_id)
        
        if anti_type == "antiforward":
            if tid not in forward_count:
                forward_count[tid] = {}
            
            if uid not in forward_count[tid]:
                forward_count[tid][uid] = 0
            
            forward_count[tid][uid] += 1
            count = forward_count[tid][uid]
            
            data["forward_count"] = forward_count
            _save(data, bot)
            
            try:
                cli_msg_id = getattr(message_object, "cliMsgId", None)
                if cli_msg_id:
                    bot.deleteGroupMsg(mid, author_id, cli_msg_id, thread_id)
                else:
                    bot.deleteGroupMsg(mid, author_id, thread_id)
            except Exception as e:
                print(f"[AntiForward] Loi xoa tin nhan: {e}")
            
            name = _get_name(bot, author_id)
            
            if count >= 5:
                if not _can_send_action(tid, uid, f"forward_kick"):
                    return True
                
                try:
                    method = config.get("punishment_method", "ban")
                    action_text = "kiss" if method == "kiss" else "ban"
                    
                    bot.style.send_warning(
                        f"{name} da bi {action_text} khoi nhom do forward tin nhan qua nhieu lan",
                        thread_id, thread_type, author_id, ttl=120000
                    )
                    
                    time.sleep(1)
                    
                    if method == "kiss":
                        bot.kickUsersInGroup(author_id, thread_id)
                    else:
                        bot.blockUsersInGroup(author_id, thread_id)
                    
                    if tid in forward_count and uid in forward_count[tid]:
                        del forward_count[tid][uid]
                        if not forward_count[tid]:
                            del forward_count[tid]
                        data["forward_count"] = forward_count
                        _save(data, bot)
                        
                except Exception as e:
                    bot.style.send_error(
                        f"khong the xu ly {name}, loi: {e}",
                        thread_id, thread_type, author_id, ttl=60000
                    )
            else:
                if _can_send_action(tid, uid, f"forward_warn_{count}"):
                    bot.style.send_warning(
                        f"{name} tin nhan forward bi xoa\ncon {5 - count} lan nua se bi xu ly",
                        thread_id, thread_type, author_id, ttl=120000
                    )
            
            return True
        
        if tid not in permanent_violations:
            permanent_violations[tid] = {}
        
        if uid not in permanent_violations[tid]:
            permanent_violations[tid][uid] = {}
        
        if anti_type not in permanent_violations[tid][uid]:
            permanent_violations[tid][uid][anti_type] = 0
        
        permanent_violations[tid][uid][anti_type] += 1
        count = permanent_violations[tid][uid][anti_type]
        
        data["permanent_violations"] = permanent_violations
        _save(data, bot)
        
        try:
            cli_msg_id = getattr(message_object, "cliMsgId", None)
            if cli_msg_id:
                bot.deleteGroupMsg(mid, author_id, cli_msg_id, thread_id)
            else:
                bot.deleteGroupMsg(mid, author_id, thread_id)
        except Exception as e:
            print(f"[Anti{anti_type.title()}] Loi xoa tin nhan: {e}")
        
        name = _get_name(bot, author_id)
        type_name_map = {
            "antilink": "link",
            "antivoice": "voice",
            "antiphoto": "anh",
            "antivideo": "video",
            "antisticker": "sticker",
            "antilocation": "vi tri",
            "antigif": "gif",
            "antifile": "file",
            "anticard": "card",
            "antisdt": "so dien thoai",
        }
        type_name = type_name_map.get(anti_type, anti_type)
        
        if count >= max_violations:
            if not _can_send_action(tid, uid, f"{anti_type}_kick"):
                return True
            
            try:
                method = config.get("punishment_method", "ban")
                action_text = "kiss" if method == "kiss" else "ban"
                
                bot.style.send_warning(
                    f"{name} da bi {action_text} khoi nhom do gui {type_name} qua nhieu lan ({count}/{max_violations})",
                    thread_id, thread_type, author_id, ttl=120000
                )
                
                time.sleep(1)
                
                if method == "kiss":
                    bot.kickUsersInGroup(author_id, thread_id)
                else:
                    bot.blockUsersInGroup(author_id, thread_id)
                
                if tid in permanent_violations and uid in permanent_violations[tid]:
                    if anti_type in permanent_violations[tid][uid]:
                        del permanent_violations[tid][uid][anti_type]
                    
                    if not permanent_violations[tid][uid]:
                        del permanent_violations[tid][uid]
                    
                    if not permanent_violations[tid]:
                        del permanent_violations[tid]
                    
                    data["permanent_violations"] = permanent_violations
                    _save(data, bot)
            except Exception as e:
                bot.style.send_error(
                    f"khong the xu ly {name}, loi: {e}",
                    thread_id, thread_type, author_id, ttl=60000
                )
        elif count >= max_violations - 1:
            if _can_send_action(tid, uid, f"{anti_type}_warn_final"):
                bot.style.send_warning(
                    f"{name} canh bao cuoi cung day ({count}/{max_violations})\ncon {max_violations - count} lan nua se bi xu ly",
                    thread_id, thread_type, author_id, ttl=120000
                )
        else:
            if _can_send_action(tid, uid, f"{anti_type}_info_{count}"):
                bot.style.send_info(
                    f"{name} nhom khong cho phep gui {type_name}\nday la lan vi pham thu {count}/{max_violations}",
                    thread_id, thread_type, author_id, ttl=120000
                )
        
        return True
        
    except Exception as e:
        print(f"[Anti{anti_type.title()}] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


class NS:
    def __init__(self, bot):
        self.bot = bot
        _start_checker(bot)

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        if tt != ThreadType.GROUP:
            return self.style.send_warning(
                "chi su dung duoc trong nhom",
                tid, tt, uid, ttl=10000
            )
        
        if not self.bot._is_admin(uid):
            return self.style.send_denied(
                "ban khong co quyen su dung lenh nay",
                tid, tt, uid, ttl=10000
            )

        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        
        if len(parts) < 2:
            return self._show_help(mo, tid, tt, uid)
        
        subcommand = parts[1].lower()

        if subcommand == "config":
            return self._handle_config(parts, mo, tid, tt, uid)
        
        if subcommand == "event":
            return self._toggle_event(mo, tid, tt, uid)
        
        if subcommand == "approve":
            return self._toggle_approve(mo, tid, tt, uid)

        anti_types = [
            "antilink", "antivoice", "antiphoto", "antivideo", "antisticker",
            "antilocation", "antigif", "antifile", "anticard",
            "antisdt", "antiforward", "antispam"
        ]

        if subcommand not in anti_types:
            return self._show_help(mo, tid, tt, uid)

        return self._toggle(subcommand, mo, tid, tt, uid)

    def _show_help(self, mo, tid, tt, uid):
        help_text = f"""cac lenh nhom (toggle):
{self.bot.prefix}group antilink
{self.bot.prefix}group antivoice
{self.bot.prefix}group antiphoto
{self.bot.prefix}group antivideo
{self.bot.prefix}group antisticker
{self.bot.prefix}group antilocation
{self.bot.prefix}group antigif
{self.bot.prefix}group antifile
{self.bot.prefix}group anticard
{self.bot.prefix}group antisdt
{self.bot.prefix}group antiforward
{self.bot.prefix}group antispam
{self.bot.prefix}group event
{self.bot.prefix}group approve

cau hinh:
{self.bot.prefix}group config maxviolations <so>
{self.bot.prefix}group config method <kiss/ban>
{self.bot.prefix}group config show"""
        
        return self.style.send_info(help_text, tid, tt, uid, ttl=60000)

    def _handle_config(self, parts, mo, tid, tt, uid):
        if len(parts) < 3:
            return self._show_config(mo, tid, tt, uid)
        
        config_type = parts[2].lower()
        
        if config_type == "show":
            return self._show_config(mo, tid, tt, uid)
        
        if config_type == "maxviolations":
            if len(parts) < 4:
                return self.style.send_warning(
                    f"vui long nhap so lan vi pham\nVD: {self.bot.prefix}group config maxviolations 5",
                    tid, tt, uid, ttl=10000
                )
            
            try:
                max_viol = int(parts[3])
                if max_viol < 1 or max_viol > 1000:
                    return self.style.send_warning(
                        "so lan vi pham phai tu 1 den 10",
                        tid, tt, uid, ttl=10000
                    )
                
                data = _load(self.bot)
                tid_str = str(tid)
                
                if "config" not in data:
                    data["config"] = {}
                
                if tid_str not in data["config"]:
                    data["config"][tid_str] = {}
                
                data["config"][tid_str]["max_violations"] = max_viol
                _save(data, self.bot)
                
                return self.style.send_success(
                    f"da dat so lan vi pham toi da: {max_viol}",
                    tid, tt, uid, ttl=60000
                )
            except ValueError:
                return self.style.send_warning(
                    "vui long nhap so hop le",
                    tid, tt, uid, ttl=10000
                )
        
        elif config_type == "method":
            if len(parts) < 4:
                return self.style.send_warning(
                    f"vui long chon phuong thuc xu ly\nVD: {self.bot.prefix}group config method ban",
                    tid, tt, uid, ttl=10000
                )
            
            method = parts[3].lower()
            if method not in ["kiss", "ban"]:
                return self.style.send_warning(
                    "phuong thuc chi co the la 'kiss' hoac 'ban'",
                    tid, tt, uid, ttl=10000
                )
            
            data = _load(self.bot)
            tid_str = str(tid)
            
            if "config" not in data:
                data["config"] = {}
            
            if tid_str not in data["config"]:
                data["config"][tid_str] = {}
            
            data["config"][tid_str]["punishment_method"] = method
            _save(data, self.bot)
            
            return self.style.send_success(
                f"da dat phuong thuc xu ly: {method}",
                tid, tt, uid, ttl=60000
            )
        
        return self._show_config(mo, tid, tt, uid)

    def _show_config(self, mo, tid, tt, uid):
        config = _get_group_config(tid, self.bot)
        max_viol = config.get("max_violations", 3)
        method = config.get("punishment_method", "ban")
        
        data = _load(self.bot)
        event_data = _load_event_settings(self.bot)
        tid_str = str(tid)
        
        anti_types = [
            ("antilink", "Link"),
            ("antivoice", "Voice"),
            ("antiphoto", "Photo"),
            ("antivideo", "Video"),
            ("antisticker", "Sticker"),
            ("antilocation", "Location"),
            ("antigif", "GIF"),
            ("antifile", "File"),
            ("anticard", "Card"),
            ("antisdt", "SDT"),
            ("antiforward", "Forward"),
            ("antispam", "Spam")
        ]
        
        enabled_features = []
        disabled_features = []
        
        for anti_key, anti_name in anti_types:
            if data.get(anti_key, {}).get(tid_str, False):
                enabled_features.append(anti_name)
            else:
                disabled_features.append(anti_name)
        
        event_status = "Bat" if tid_str in event_data.get("enabled_groups", []) else "Tat"
        approve_status = "Bat" if data.get("auto_approve", {}).get(tid_str, False) else "Tat"
        
        enabled_text = ", ".join(enabled_features) if enabled_features else "khong co"
        disabled_text = ", ".join(disabled_features) if disabled_features else "khong co"
        
        config_text = f"""cau hinh hien tai:
so lan vi pham toi da: {max_viol}
phuong thuc xu ly: {method}
su kien nhom: {event_status}
tu dong duyet: {approve_status}

tinh nang da bat:
{enabled_text}

tinh nang da tat:
{disabled_text}"""
        
        return self.style.send_info(config_text, tid, tt, uid, ttl=60000)

    def _toggle(self, anti_type, mo, tid, tt, uid):
        data = _load(self.bot)
        
        if anti_type not in data:
            data[anti_type] = {}
        
        tid_str = str(tid)
        current_status = data[anti_type].get(tid_str, False)
        
        new_status = not current_status
        data[anti_type][tid_str] = new_status
        _save(data, self.bot)
        
        status_text = "bat" if new_status else "tat"
        
        return self.style.send_success(
            f"da {status_text} {anti_type}",
            tid, tt, uid, ttl=60000
        )

    def _toggle_event(self, mo, tid, tt, uid):
        data = _load_event_settings(self.bot)
        enabled_groups = data.get("enabled_groups", [])
        tid_str = str(tid)
        
        if tid_str in enabled_groups:
            enabled_groups.remove(tid_str)
            status = "tat"
        else:
            enabled_groups.append(tid_str)
            status = "bat"
        
        data["enabled_groups"] = enabled_groups
        _save_event_settings(data, self.bot)
        
        return self.style.send_success(
            f"da {status} thong bao su kien nhom",
            tid, tt, uid, ttl=60000
        )

    def _toggle_approve(self, mo, tid, tt, uid):
        data = _load(self.bot)
        
        if "auto_approve" not in data:
            data["auto_approve"] = {}
        
        tid_str = str(tid)
        current_status = data["auto_approve"].get(tid_str, False)
        
        new_status = not current_status
        data["auto_approve"][tid_str] = new_status
        _save(data, self.bot)
        
        status_text = "bat" if new_status else "tat"
        
        return self.style.send_success(
            f"da {status_text} tu dong duyet thanh vien",
            tid, tt, uid, ttl=60000
        )


def _ns():
    return {"cls": NS, "name": "group"}