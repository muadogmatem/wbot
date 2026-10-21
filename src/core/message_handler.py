import json
import time
import traceback

from zlapi.models import ThreadType

from .logger import C, log_error, log_cmd, log_msg
from .reactions import REACTIONS


NOPREFIX_COMMANDS = ["prefix", "prefixonly"]


class MessageHandlerMixin:
    def _is_duplicate(self, mid):
        if not mid:
            return False
        now = time.time()
        if mid in self._seen_mids:
            return True
        if len(self._seen_mids) > self._seen_max:
            cutoff = now - 60
            self._seen_mids = {k: v for k, v in self._seen_mids.items() if v > cutoff}
        self._seen_mids[mid] = now
        return False

    def _try_delete_muted_msg(self, mid, author_id, message_object, thread_id):
        try:
            cli_msg_id = getattr(message_object, "cliMsgId", None)
            if cli_msg_id:
                self.deleteGroupMsg(mid, author_id, cli_msg_id, thread_id)
            else:
                self.deleteGroupMsg(mid, author_id, thread_id)
        except Exception:
            try:
                self.deleteGroupMsg(mid, author_id, thread_id)
            except Exception:
                pass

    def _dump_obj(self, obj):
        result = {}
        try:
            if hasattr(obj, "__dict__"):
                for key, val in obj.__dict__.items():
                    try:
                        if hasattr(val, "__dict__"):
                            result[key] = val.__dict__
                        else:
                            json.dumps(val)
                            result[key] = val
                    except (TypeError, ValueError):
                        result[key] = str(val)
            else:
                result = str(obj)
        except Exception:
            result = {"error": "cannot dump"}
        return result

    def _log_full(self, mid, msg, msg_type, author_id, thread_id, thread_type, mo, is_admin, is_cmd):
        thread_label = "Group" if thread_type == ThreadType.GROUP else "User"
        admin_tag = f" {C.Y}[ADMIN]{C.D}" if is_admin else ""
        author_name = self.style.get_name(author_id)

        mentions_data = "None"
        try:
            mentions = getattr(mo, "mentions", None)
            if mentions:
                mentions_data = json.dumps(mentions, ensure_ascii=False, indent=2)
        except Exception:
            pass

        content_raw = "None"
        try:
            content = getattr(mo, "content", None)
            if content is not None:
                if hasattr(content, "__dict__"):
                    content_raw = json.dumps(content.__dict__, ensure_ascii=False, indent=2)
                elif isinstance(content, str):
                    content_raw = content
                else:
                    content_raw = json.dumps(content, ensure_ascii=False, indent=2)
        except Exception as e:
            content_raw = str(e)

        full_dump = "{}"
        try:
            dumped = self._dump_obj(mo)
            full_dump = json.dumps(dumped, ensure_ascii=False, indent=2)
        except Exception:
            full_dump = str(mo)

        log_text = (
            f"\n"
            f"{'━' * 50}\n"
            f"  {C.W}Thread:{C.D}      {thread_label} ({C.DIM}{thread_id}{C.D})\n"
            f"  {C.W}Author:{C.D}      {C.CY}{author_name}{C.D} ({C.DIM}{author_id}{C.D}){admin_tag}\n"
            f"  {C.W}Message ID:{C.D}  {C.DIM}{mid}{C.D}\n"
            f"  {C.W}Msg Type:{C.D}    {C.M}{msg_type}{C.D}\n"
            f"  {C.W}Text:{C.D}        {C.G}{msg}{C.D}\n"
            f"  {C.W}Mentions:{C.D}    {C.Y}{mentions_data}{C.D}\n"
            f"  {C.W}Content:{C.D}     {C.DIM}{content_raw[:300]}{C.D}\n"
            f"  {C.W}Full JSON:{C.D}\n{C.DIM}{full_dump[:800]}{C.D}\n"
            f"{'━' * 50}"
        )

        if is_cmd:
            log_cmd(log_text)
        else:
            log_msg(log_text)

    def _handle_noprefix(self, msg, mo, tid, tt, uid):
        text = msg.strip()
        first_word = text.split()[0].lower() if text.split() else ""

        if first_word in NOPREFIX_COMMANDS:
            return self.engine.run_noprefix(first_word, msg, mo, tid, tt, uid)

        return False

    def _handle_prefix_only(self, msg, mo, tid, tt, uid):
        p = self.prefix
        if msg.strip() == p.strip():
            return self.engine.run_noprefix("prefixonly", msg, mo, tid, tt, uid)
        return False

    def _handle_menu_navigation(self, msg, mo, tid, tt, uid):
        content_lower = msg.strip().lower()

        if content_lower not in ("next", "out"):
            return False

        try:
            from src.cmd.menu.menu_handler import has_pending_menu, MenuHandler
            if has_pending_menu(tid, uid):
                menu_handler = MenuHandler(self)
                return menu_handler.try_handle(msg, mo, tid, tt, uid)
        except ImportError:
            pass

        return False

    def _handle_sticker_selection(self, msg, mo, tid, tt, uid):
        first_word = msg.strip().split()[0] if msg.strip() else ""

        if not first_word.isdigit():
            return False

        try:
            from src.cmd.halo.stkzl_handler import has_sticker_pending
            if not has_sticker_pending(tid, uid):
                return False
        except ImportError:
            return False

        try:
            from src.cmd.halo.stkzl import NS as StkzlNS
            handler = StkzlNS(self)
            result = handler.handle_number_selection(msg, mo, tid, tt, uid)
            return bool(result)
        except Exception:
            traceback.print_exc()
            return False

    def _handle_music_selection(self, msg, mo, tid, tt, uid):
        first_word = msg.strip().split()[0] if msg.strip() else ""

        if not first_word.isdigit():
            return False

        music = self.engine._get_music()
        if music:
            try:
                from src.cmd.music.music_handler import has_pending
                if has_pending(tid, uid):
                    self.engine.try_music_selection(msg, mo, tid, tt, uid)
                    return True
            except ImportError:
                pass

        return False

    def _handle_animehay_selection(self, msg, mo, tid, tt, uid):
        first_word = msg.strip().split()[0] if msg.strip() else ""

        if not first_word.isdigit():
            return False

        try:
            from src.cmd.animehay.animehay_handler import has_pending, AnimeHayHandler
            if has_pending(tid, uid):
                handler = AnimeHayHandler(self)
                return handler.try_handle(msg, mo, tid, tt, uid)
        except ImportError:
            pass
        except Exception:
            traceback.print_exc()

        return False

    def _handle_auto_download(self, msg, mo, tid, tt, uid):
        try:
            from src.cmd.download import try_autolink
            return try_autolink(self, msg, mo, tid, tt, uid)
        except ImportError:
            pass
        except Exception:
            traceback.print_exc()

        return False

    def _handle_group_anti(self, mid, author_id, message_object, thread_id, thread_type):
        try:
            from src.cmd.group import check_and_handle, check_spam
            
            if check_spam(self, author_id, message_object, thread_id, thread_type):
                return True
            
            anti_types = [
                "antilink", "antivoice", "antiphoto", "antivideo", "antisticker",
                "antilocation", "antigif", "antifile", "anticard", "antisdt", "antiforward"
            ]
            for anti_type in anti_types:
                if check_and_handle(self, anti_type, message_object, thread_id, thread_type, author_id, mid):
                    return True
            
            return False
        except ImportError:
            return False
        except Exception as e:
            log_error(f"_handle_group_anti: {e}")
            traceback.print_exc()
            return False

    def onMessage(self, mid, author_id, message, message_object, thread_id, thread_type):
        try:
            if self._is_duplicate(mid):
                return

            msg_type = getattr(message_object, "msgType", "") or ""
            is_group = thread_type == ThreadType.GROUP
            is_admin = self._is_admin(author_id)

            if is_group and not is_admin:
                if msg_type not in ("chat.undo", "chat.delete", "chat.reaction"):
                    from src.cmd.silent import is_muted
                    if is_muted(thread_id, author_id, self):
                        self._try_delete_muted_msg(mid, author_id, message_object, thread_id)
                        return
                    
                    if self._handle_group_anti(mid, author_id, message_object, thread_id, thread_type):
                        return

            if msg_type in ("chat.undo", "chat.delete", "chat.reaction"):
                return

            msg = self._parser.parse(message, message_object)
            if not msg:
                return

            is_cmd = msg.startswith(self.prefix)
            is_listening = self._listen.is_listening(thread_id) if is_group else True
            can_interact = is_admin or is_listening or not is_group

            if not can_interact:
                return

            self._log_full(
                mid, msg, msg_type, author_id,
                thread_id, thread_type, message_object,
                is_admin, is_cmd,
            )

            if is_cmd:
                if is_admin or is_listening or not is_group:
                    if self._handle_prefix_only(msg, message_object, thread_id, thread_type, author_id):
                        return
                    self.engine.run(msg, message_object, thread_id, thread_type, author_id)
                return

            if is_admin or is_listening:
                if self._handle_noprefix(msg, message_object, thread_id, thread_type, author_id):
                    return

            if self._handle_menu_navigation(msg, message_object, thread_id, thread_type, author_id):
                return

            if self._handle_sticker_selection(msg, message_object, thread_id, thread_type, author_id):
                return

            if self._handle_music_selection(msg, message_object, thread_id, thread_type, author_id):
                return

            if self._handle_animehay_selection(msg, message_object, thread_id, thread_type, author_id):
                return

            if self._handle_auto_download(msg, message_object, thread_id, thread_type, author_id):
                return

        except Exception as e:
            log_error(f"onMessage: {e}")
            traceback.print_exc()

    def onEvent(self, event_data, event_type):
        try:
            from src.core.event_handler import handle_group_event
            handle_group_event(self, event_data, event_type)
        except ImportError:
            pass
        except Exception as e:
            log_error(f"onEvent: {e}")
            traceback.print_exc()