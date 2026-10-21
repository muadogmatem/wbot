import os
import traceback
from concurrent.futures import ThreadPoolExecutor

from .core import (
    ReactionManager, REACTIONS,
    CooldownManager,
)

_pool = ThreadPoolExecutor(16)


PERM_TEXT = {
    1: "thanh vien",
    2: "admin",
    3: "admin cap cao",
    4: "owner",
    5: "server",
    6: "hidden"
}

REPLY_CD_SECS = 10


class Engine:
    def __init__(self, bot, reg, admins=None):
        self.bot = bot
        self.reg = reg

        if isinstance(admins, str):
            self.admins = {admins}
        elif isinstance(admins, (list, tuple, set)):
            self.admins = set(str(a) for a in admins)
        else:
            self.admins = set()

        self.h = {}
        self.inline = {}
        self._locks = {}

        self.rm = ReactionManager(bot)
        self.cd = CooldownManager(self.rm)

        self._music = None
        self._music_loaded = False

    def _get_music(self):
        if self._music_loaded:
            return self._music
        self._music_loaded = True
        try:
            from src.cmd.music.music_handler import MusicHandler
            self._music = MusicHandler(self.bot)
        except ImportError:
            self._music = None
        return self._music

    def _get_user_level(self, uid, tid):
        try:
            from src.cmd.admin import get_user_level
            return get_user_level(uid, tid)
        except ImportError:
            if str(uid) in self.admins:
                return 4
            return 1

    def _is_server(self):
        return os.environ.get("BOT_IS_SERVER") == "1"

    def bind(self, name, fn, inline_config=None):
        if fn is not None and callable(fn):
            self.h[name.lower()] = fn
            if inline_config:
                self.inline[name.lower()] = inline_config

    def _get_entry(self, name):
        entry = self.reg.get(name)
        if entry:
            return entry
        return self.inline.get(name.lower())

    def _resolve(self, token):
        name = self.reg.resolve(token)
        if name:
            return name
        token = token.lower()
        if token in self.h:
            return token
        for n, cfg in self.inline.items():
            if token in [a.lower() for a in cfg.get("alias", [])]:
                return n
        return None

    def is_hidden(self, name):
        entry = self._get_entry(name)
        if not entry:
            return False
        if entry.get("hidden"):
            return True
        perm = entry.get("perm", 1)
        if isinstance(perm, str):
            if perm == "hidden":
                return True
            try:
                perm = int(perm)
            except ValueError:
                return False
        return perm == 6

    def visible_names(self):
        result = []
        all_names = set(self.reg.names()) | set(self.inline.keys())
        for n in all_names:
            if not self.is_hidden(n):
                result.append(n)
        return sorted(result)

    def _styled_reply(self, reply_type, text, name, mo, tid, tt, uid, ttl=10000, react_type=None):
        cd_key = f"reply:{name}:{uid}:{tid}"
        remain = self.cd.check(cd_key, uid, tid, REPLY_CD_SECS)

        if remain is not None:
            def _run_reply(fn, n, m, mo, tid, tt, uid):
                if hasattr(self.bot, "style"):
                    style_fn = getattr(self.bot.style, f"reply_{reply_type}", None)
                    if style_fn:
                        style_fn(text, mo, tid, tt, uid, ttl=ttl)
                    else:
                        self.rm.reply(text, mo, tid, tt)
                else:
                    self.rm.reply(text, mo, tid, tt)

            self.cd.countdown_then_run(
                remain, cd_key, None, None, mo, tid, tt, uid, _run_reply
            )
            return

        if react_type:
            self.rm.react(mo, REACTIONS[react_type], tid, tt)

        if hasattr(self.bot, "style"):
            style_fn = getattr(self.bot.style, f"reply_{reply_type}", None)
            if style_fn:
                style_fn(text, mo, tid, tt, uid, ttl=ttl)
            else:
                self.rm.reply(text, mo, tid, tt)
        else:
            self.rm.reply(text, mo, tid, tt)

    def _run_handler(self, fn, name, msg, mo, tid, tt, uid):
        try:
            self._locks[uid] = True
            fn(msg, mo, tid, tt, uid)
        except Exception as ex:
            traceback.print_exc()
            self._styled_reply("error", str(ex), name, mo, tid, tt, uid, ttl=10000, react_type="error")
        finally:
            self._locks[uid] = False

    def try_music_selection(self, msg, mo, tid, tt, uid):
        music = self._get_music()
        if not music:
            return

        def _exec():
            try:
                music.try_handle(msg, mo, tid, tt, uid)
            except Exception:
                traceback.print_exc()

        _pool.submit(_exec)

    def _check_perm(self, entry, name, mo, tid, tt, uid):
        if not entry:
            return True

        if not entry.get("on", True):
            self._styled_reply("warning", f"lenh '{name}' dang bi tat", name, mo, tid, tt, uid, react_type="disabled")
            return False

        perm = entry.get("perm", 1)

        if isinstance(perm, str):
            if perm == "admin":
                perm = 3
            elif perm == "all":
                perm = 1
            elif perm == "server":
                perm = 5
            elif perm == "hidden":
                perm = 6
            else:
                try:
                    perm = int(perm)
                except ValueError:
                    perm = 1

        if perm == 6:
            return True

        if perm == 5:
            if not self._is_server():
                self._styled_reply("denied", "lenh nay chi server moi dung duoc", name, mo, tid, tt, uid, react_type="denied")
                return False

            user_level = self._get_user_level(uid, tid)
            if user_level < 4:
                self._styled_reply("denied", "ban can quyen owner de dung lenh server", name, mo, tid, tt, uid, react_type="denied")
                return False
        else:
            user_level = self._get_user_level(uid, tid)

            if user_level < perm:
                perm_display = PERM_TEXT.get(perm, str(perm))
                self._styled_reply("denied", f"ban can quyen {perm_display} de dung lenh nay", name, mo, tid, tt, uid, react_type="denied")
                return False

        return True

    def _check_cooldown(self, entry, name, fn, msg, mo, tid, tt, uid):
        if not entry:
            return False

        cd_secs = entry.get("cd", 0)
        if cd_secs > 0:
            remain = self.cd.check(name, uid, tid, cd_secs)
            if remain is not None:
                self.cd.countdown_then_run(
                    remain, name, fn, msg, mo, tid, tt, uid,
                    self._run_handler,
                )
                return True

        return False

    def run_noprefix(self, name, msg, mo, tid, tt, uid):
        entry = self._get_entry(name)
        fn = self.h.get(name)

        if fn is None or not callable(fn):
            return False

        if not self._check_perm(entry, name, mo, tid, tt, uid):
            return True

        if self._check_cooldown(entry, name, fn, msg, mo, tid, tt, uid):
            return True

        if self._locks.get(uid):
            self._styled_reply("warning", "dang xu ly lenh truoc, vui long doi", name, mo, tid, tt, uid, react_type="processing")
            return True

        self.rm.react(mo, REACTIONS["received"], tid, tt)

        def _exec():
            self._run_handler(fn, name, msg, mo, tid, tt, uid)

        _pool.submit(_exec)
        return True

    def run(self, msg, mo, tid, tt, uid):
        p = self.bot.prefix
        if not isinstance(msg, str) or not msg.startswith(p):
            return

        body = msg[len(p):].strip()
        if not body:
            return

        token = body.split(None, 1)[0].lower()
        name = self._resolve(token)
        if not name:
            return

        entry = self._get_entry(name)

        if not self._check_perm(entry, name, mo, tid, tt, uid):
            return

        fn = self.h.get(name)
        if fn is None or not callable(fn):
            return

        if self._check_cooldown(entry, name, fn, msg, mo, tid, tt, uid):
            return

        if self._locks.get(uid):
            self._styled_reply("warning", "dang xu ly lenh truoc, vui long doi", name, mo, tid, tt, uid, react_type="processing")
            return

        self.rm.react(mo, REACTIONS["received"], tid, tt)

        def _exec():
            self._run_handler(fn, name, msg, mo, tid, tt, uid)

        _pool.submit(_exec)