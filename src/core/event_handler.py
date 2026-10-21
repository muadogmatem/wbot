import os
import time
import threading
from PIL import Image
from zlapi.models import GroupEventType, ThreadType, Message, Mention

try:
    from .event_renderer import (
        render_welcome,
        render_leave,
        render_kick,
        render_add_admin,
        render_remove_admin,
        render_block
    )
    RENDERER_AVAILABLE = True
except ImportError as e:
    print(f"[EventHandler] Cannot import renderer: {e}")
    RENDERER_AVAILABLE = False

EVENT_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "data", "group-event.json")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "temp")
os.makedirs(CACHE_DIR, exist_ok=True)

_processed_events = {}
_pending_kicks = {}
_block_received = {}
_event_lock = threading.Lock()
_EVENT_TIMEOUT = 3
_KICK_DELAY = 0.5


def _mark_event_processed(group_id, user_id, event_category):
    with _event_lock:
        key = f"{group_id}_{user_id}_{event_category}"
        current_time = time.time()
        
        expired_keys = [k for k, v in _processed_events.items() if current_time - v > _EVENT_TIMEOUT]
        for k in expired_keys:
            del _processed_events[k]
        
        _processed_events[key] = current_time
        print(f"[EventHandler] Marked {event_category} as processed for user {user_id}")


def _is_event_processed(group_id, user_id, event_category):
    with _event_lock:
        key = f"{group_id}_{user_id}_{event_category}"
        current_time = time.time()
        
        expired_keys = [k for k, v in _processed_events.items() if current_time - v > _EVENT_TIMEOUT]
        for k in expired_keys:
            del _processed_events[k]
        
        if key in _processed_events:
            print(f"[EventHandler] Event {event_category} already processed for user {user_id}")
            return True
        
        return False


def _mark_block_received(group_id, user_id):
    with _event_lock:
        key = f"{group_id}_{user_id}"
        _block_received[key] = time.time()
        print(f"[EventHandler] Marked BLOCK received for user {user_id}")


def _is_block_received(group_id, user_id):
    with _event_lock:
        key = f"{group_id}_{user_id}"
        current_time = time.time()
        
        expired_keys = [k for k, v in _block_received.items() if current_time - v > _EVENT_TIMEOUT]
        for k in expired_keys:
            del _block_received[k]
        
        return key in _block_received


def _mark_kick_pending(group_id, user_id, event_data):
    with _event_lock:
        key = f"{group_id}_{user_id}"
        _pending_kicks[key] = {
            'time': time.time(),
            'data': event_data
        }
        print(f"[EventHandler] Marked KICK as pending for user {user_id}")


def _cancel_pending_kick(group_id, user_id):
    with _event_lock:
        key = f"{group_id}_{user_id}"
        if key in _pending_kicks:
            print(f"[EventHandler] Canceling pending KICK for {user_id} (BLOCK event received)")
            del _pending_kicks[key]
            return True
        return False


def _process_pending_kick(bot, group_id, user_id, group_name):
    time.sleep(_KICK_DELAY)
    
    if _is_block_received(group_id, user_id):
        print(f"[EventHandler] BLOCK was received, canceling KICK for {user_id}")
        with _event_lock:
            key = f"{group_id}_{user_id}"
            if key in _pending_kicks:
                del _pending_kicks[key]
        return
    
    with _event_lock:
        key = f"{group_id}_{user_id}"
        if key not in _pending_kicks:
            print(f"[EventHandler] Pending KICK was canceled for {user_id}")
            return
        
        event_data = _pending_kicks[key]['data']
        del _pending_kicks[key]
    
    if _is_event_processed(group_id, user_id, "removal"):
        print(f"[EventHandler] Removal already processed, skipping delayed KICK for {user_id}")
        return
    
    print(f"[EventHandler] Processing delayed KICK event for {user_id}")
    source_id = event_data.get("sourceId")
    
    user_info = _get_user_info(bot, user_id)
    kicker_info = _get_user_info(bot, source_id)
    
    img = render_kick(
        user_info["name"],
        user_info["avatar"],
        user_info["cover"],
        group_name,
        kicker_info["name"]
    )
    
    _mark_event_processed(group_id, user_id, "removal")
    _send_event_image(bot, img, group_id, user_id)


def _load_event_settings():
    if os.path.exists(EVENT_SETTINGS_FILE):
        try:
            import json
            with open(EVENT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("enabled_groups", [])
        except Exception as e:
            print(f"[EventHandler] Load settings error: {e}")
            return []
    return []


def _get_user_info(bot, uid):
    try:
        info = bot.fetchUserInfo(uid)
        profile = info.get("changed_profiles", {}).get(str(uid), {})
        return {
            "name": profile.get("displayName", "User"),
            "avatar": profile.get("avatar", ""),
            "cover": profile.get("cover", "")
        }
    except Exception as e:
        print(f"[EventHandler] Get user info error: {e}")
        return {
            "name": "User",
            "avatar": "",
            "cover": ""
        }


def _get_group_name(bot, gid):
    try:
        info = bot.fetchGroupInfo(gid)
        group_data = info.gridInfoMap.get(str(gid), {})
        return group_data.get("name", "Group")
    except Exception as e:
        print(f"[EventHandler] Get group name error: {e}")
        return "Group"


def _handle_join_request_event(bot, event_data):
    try:
        from src.cmd.group import is_auto_approve_enabled
        
        group_id = event_data.get("groupId")
        if not group_id:
            print("[EventHandler] JOIN_REQUEST: No group_id")
            return
        
        print(f"[EventHandler] JOIN_REQUEST: Checking group {group_id}")
        print(f"[EventHandler] JOIN_REQUEST: event_data type: {type(event_data)}")
        print(f"[EventHandler] JOIN_REQUEST: event_data keys: {list(event_data.keys()) if isinstance(event_data, dict) else 'not dict'}")
        
        if not is_auto_approve_enabled(group_id, bot):
            print(f"[EventHandler] JOIN_REQUEST: Auto approve not enabled for group {group_id}")
            return
        
        members = None
        if isinstance(event_data, dict):
            members = event_data.get("updateMembers") or event_data.get("members")
        else:
            members = getattr(event_data, "updateMembers", None) or getattr(event_data, "members", None)
        
        print(f"[EventHandler] JOIN_REQUEST: members type: {type(members)}")
        print(f"[EventHandler] JOIN_REQUEST: members value: {members}")
        
        if not members:
            print(f"[EventHandler] JOIN_REQUEST: No members found, trying viewGroupPending")
            try:
                pending_result = bot.viewGroupPending(group_id)
                print(f"[EventHandler] viewGroupPending result type: {type(pending_result)}")
                print(f"[EventHandler] viewGroupPending result: {pending_result}")
                
                if hasattr(pending_result, "__dict__"):
                    pending_dict = pending_result.__dict__
                elif isinstance(pending_result, dict):
                    pending_dict = pending_result
                else:
                    pending_dict = {}
                
                print(f"[EventHandler] pending_dict keys: {list(pending_dict.keys())}")
                
                users_raw = pending_dict.get("users") or pending_dict.get("members") or []
                print(f"[EventHandler] users_raw: {users_raw}")
                
                member_ids = []
                if isinstance(users_raw, list):
                    for m in users_raw:
                        if isinstance(m, dict):
                            uid = str(m.get("uid") or m.get("id") or "")
                        else:
                            uid = str(getattr(m, "uid", "") or getattr(m, "id", "") or "")
                        
                        if uid:
                            member_ids.append(uid)
                
                if not member_ids:
                    print(f"[EventHandler] JOIN_REQUEST: No pending members found")
                    return
                
                print(f"[EventHandler] JOIN_REQUEST: Found {len(member_ids)} pending members: {member_ids}")
                
                result = bot.handleGroupPending(member_ids, group_id, isApprove=True)
                print(f"[EventHandler] JOIN_REQUEST: Approval result: {result}")
                return
                
            except Exception as e:
                print(f"[EventHandler] viewGroupPending error: {e}")
                import traceback
                traceback.print_exc()
                return
        
        member_ids = []
        if isinstance(members, list):
            for member in members:
                if isinstance(member, dict):
                    uid = member.get("id") or member.get("uid")
                else:
                    uid = getattr(member, "id", None) or getattr(member, "uid", None)
                
                if uid:
                    member_ids.append(str(uid))
        
        if not member_ids:
            print(f"[EventHandler] JOIN_REQUEST: No valid member IDs")
            return
        
        print(f"[EventHandler] JOIN_REQUEST: Approving {len(member_ids)} members for group {group_id}")
        print(f"[EventHandler] Member IDs: {member_ids}")
        
        result = bot.handleGroupPending(member_ids, group_id, isApprove=True)
        print(f"[EventHandler] JOIN_REQUEST: Approval result: {result}")
        
    except Exception as e:
        print(f"[EventHandler] JOIN_REQUEST error: {e}")
        import traceback
        traceback.print_exc()


def handle_group_event(bot, event_data, event_type):
    print(f"[EventHandler] Received event: {event_type}")
    
    if event_type == GroupEventType.JOIN_REQUEST:
        _handle_join_request_event(bot, event_data)
        return
    
    if not RENDERER_AVAILABLE:
        print("[EventHandler] Renderer not available, skipping...")
        return
    
    group_id = event_data.get("groupId")
    if not group_id:
        print("[EventHandler] No group_id in event")
        return
    
    enabled_groups = _load_event_settings()
    print(f"[EventHandler] Enabled groups: {enabled_groups}")
    print(f"[EventHandler] Current group: {group_id}")
    
    if str(group_id) not in enabled_groups:
        print(f"[EventHandler] Group {group_id} not enabled for events")
        return
    
    print(f"[EventHandler] Processing event for group {group_id}")
    
    group_name = _get_group_name(bot, group_id)
    
    if event_type == GroupEventType.JOIN:
        members = event_data.get("updateMembers", [])
        source_id = event_data.get("sourceId")
        
        print(f"[EventHandler] JOIN event - Members: {len(members)}")
        
        for member in members:
            uid = member.get("id")
            
            if _is_event_processed(group_id, uid, "join"):
                continue
            
            user_info = _get_user_info(bot, uid)
            
            adder_name = None
            if source_id and source_id != uid:
                adder_info = _get_user_info(bot, source_id)
                adder_name = adder_info["name"]
            
            img = render_welcome(
                user_info["name"],
                user_info["avatar"],
                user_info["cover"],
                group_name,
                adder_name
            )
            
            _mark_event_processed(group_id, uid, "join")
            _send_event_image(bot, img, group_id, uid, mention=True)
    
    elif event_type == GroupEventType.LEAVE:
        members = event_data.get("updateMembers", [])
        print(f"[EventHandler] LEAVE event - Members: {len(members)}")
        
        if members:
            uid = members[0].get("id")
            
            if _is_event_processed(group_id, uid, "leave"):
                return
            
            user_info = _get_user_info(bot, uid)
            
            img = render_leave(
                user_info["name"],
                user_info["avatar"],
                user_info["cover"],
                group_name
            )
            
            _mark_event_processed(group_id, uid, "leave")
            _send_event_image(bot, img, group_id, uid)
    
    elif event_type == GroupEventType.BLOCK_MEMBER:
        members = event_data.get("updateMembers", [])
        source_id = event_data.get("sourceId")
        
        print(f"[EventHandler] BLOCK event - Members: {len(members)}")
        
        if members:
            uid = members[0].get("id")
            
            _mark_block_received(group_id, uid)
            _cancel_pending_kick(group_id, uid)
            
            if _is_event_processed(group_id, uid, "removal"):
                print(f"[EventHandler] Removal already processed, skipping BLOCK")
                return
            
            user_info = _get_user_info(bot, uid)
            blocker_info = _get_user_info(bot, source_id)
            
            img = render_block(
                user_info["name"],
                user_info["avatar"],
                user_info["cover"],
                group_name,
                blocker_info["name"]
            )
            
            _mark_event_processed(group_id, uid, "removal")
            _send_event_image(bot, img, group_id, uid)
    
    elif event_type == GroupEventType.REMOVE_MEMBER:
        members = event_data.get("updateMembers", [])
        
        print(f"[EventHandler] KICK event - Members: {len(members)}")
        
        if members:
            uid = members[0].get("id")
            
            if _is_event_processed(group_id, uid, "removal"):
                print(f"[EventHandler] Removal already processed, skipping KICK")
                return
            
            if _is_block_received(group_id, uid):
                print(f"[EventHandler] BLOCK already received, skipping KICK for {uid}")
                return
            
            _mark_kick_pending(group_id, uid, event_data)
            
            threading.Thread(
                target=_process_pending_kick,
                args=(bot, group_id, uid, group_name),
                daemon=True
            ).start()
    
    elif event_type == GroupEventType.ADD_ADMIN:
        members = event_data.get("updateMembers", [])
        source_id = event_data.get("sourceId")
        
        print(f"[EventHandler] ADD_ADMIN event - Members: {len(members)}")
        
        if members:
            uid = members[0].get("id")
            
            if _is_event_processed(group_id, uid, "add_admin"):
                return
            
            user_info = _get_user_info(bot, uid)
            adder_info = _get_user_info(bot, source_id)
            
            img = render_add_admin(
                user_info["name"],
                user_info["avatar"],
                user_info["cover"],
                group_name,
                adder_info["name"]
            )
            
            _mark_event_processed(group_id, uid, "add_admin")
            _send_event_image(bot, img, group_id, uid, mention=True)
    
    elif event_type == GroupEventType.REMOVE_ADMIN:
        members = event_data.get("updateMembers", [])
        source_id = event_data.get("sourceId")
        
        print(f"[EventHandler] REMOVE_ADMIN event - Members: {len(members)}")
        
        if members:
            uid = members[0].get("id")
            
            if _is_event_processed(group_id, uid, "remove_admin"):
                return
            
            user_info = _get_user_info(bot, uid)
            remover_info = _get_user_info(bot, source_id)
            
            img = render_remove_admin(
                user_info["name"],
                user_info["avatar"],
                user_info["cover"],
                group_name,
                remover_info["name"]
            )
            
            _mark_event_processed(group_id, uid, "remove_admin")
            _send_event_image(bot, img, group_id, uid, mention=True)


def _send_event_image(bot, img, group_id, user_id, mention=False):
    filepath = None
    try:
        filepath = os.path.join(CACHE_DIR, f"event_{user_id}_{int(time.time())}.png")
        
        img.save(filepath, "PNG")
        
        with Image.open(filepath) as pil_img:
            width, height = pil_img.size
        
        print(f"[EventHandler] Image size: {width}x{height}")
        print(f"[EventHandler] Sending event image to {group_id}")
        
        if mention:
            bot.sendLocalImage(
                filepath,
                thread_id=group_id,
                thread_type=ThreadType.GROUP,
                width=width,
                height=height,
                message=Message(
                    text="@Member",
                    mention=Mention(user_id, length=len("@Member"), offset=0)
                ),
                ttl=300000
            )
        else:
            bot.sendLocalImage(
                filepath,
                thread_id=group_id,
                thread_type=ThreadType.GROUP,
                width=width,
                height=height,
                ttl=300000
            )
        
        print(f"[EventHandler] Image sent successfully")
        
    except Exception as e:
        print(f"[EventHandler] Send image error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if filepath:
            try:
                time.sleep(0.5)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"[EventHandler] Cleaned up: {filepath}")
            except Exception as e:
                print(f"[EventHandler] Cleanup error: {e}")