import os
import json
import time
import threading

from zlapi.models import Message, ThreadType


def _get_mute_file(bot):
    if hasattr(bot, "bot_id") and bot.bot_id:
        base_dir = os.path.join(os.path.dirname(__file__), "..", "mybot", "asset", "data")
        return os.path.join(base_dir, f"mute_{bot.bot_id}.json")
    return os.path.join(os.path.dirname(__file__), "..", "..", "asset", "data", "mute.json")


def _load(bot=None):
    mute_file = _get_mute_file(bot) if bot else os.path.join(os.path.dirname(__file__), "..", "asset", "data", "mute.json")
    if os.path.exists(mute_file):
        with open(mute_file, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def _save(data, bot=None):
    mute_file = _get_mute_file(bot) if bot else os.path.join(os.path.dirname(__file__), "..", "asset", "data", "mute.json")
    os.makedirs(os.path.dirname(mute_file), exist_ok=True)
    with open(mute_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def _parse_duration(s):
    if not s:
        return None
    unit = s[-1].lower()
    try:
        val = int(s[:-1])
    except ValueError:
        return None
    if unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    return None


def _fmt_remaining(expires_at):
    if not expires_at:
        return "vinh vien"
    rem = expires_at - time.time()
    if rem <= 0:
        return "da het han"
    d, rem = divmod(rem, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if d > 0:
        parts.append(f"{int(d)} ngay")
    if h > 0:
        parts.append(f"{int(h)} gio")
    if m > 0:
        parts.append(f"{int(m)} phut")
    if not parts and s > 0:
        parts.append(f"{int(s)} giay")
    return " ".join(parts)


def _get_name(bot, uid):
    try:
        return bot.style.get_name(uid)
    except Exception:
        return str(uid)


def is_muted(thread_id, user_id, bot=None):
    data = _load(bot)
    tid = str(thread_id)
    uid = str(user_id)
    if tid in data and uid in data[tid]:
        exp = data[tid][uid].get("expires_at")
        if exp is None or exp > time.time():
            return True
        del data[tid][uid]
        if not data[tid]:
            del data[tid]
        _save(data, bot)
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
                notify = []

                for tid in list(data.keys()):
                    if isinstance(data[tid], list):
                        old_list = data[tid]
                        data[tid] = {}
                        for uid in old_list:
                            data[tid][uid] = {"expires_at": None}
                        changed = True

                    for uid in list(data[tid].keys()):
                        exp = data[tid][uid].get("expires_at")
                        if exp is not None and exp <= now:
                            notify.append((uid, tid))
                            del data[tid][uid]
                            changed = True

                    if not data[tid]:
                        del data[tid]
                        changed = True

                if changed:
                    _save(data, bot)

                for uid, tid in notify:
                    try:
                        name = _get_name(bot, uid)
                        bot.sendMessage(
                            Message(text=f"{name} m dc mo chat r kia thg ngoo"),
                            thread_id=tid,
                            thread_type=ThreadType.GROUP,
                            ttl=60000,
                        )
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(5)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


class NS:
    def __init__(self, bot):
        self.bot = bot
        _start_checker(bot)

    @property
    def style(self):
        return self.bot.style

    def _load(self):
        return _load(self.bot)

    def _save(self, data):
        _save(data, self.bot)

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []

        if not args:
            self._usage(mo, tid, tt, uid)
        elif args[0].lower() == "list":
            self._list(mo, tid, tt, uid)
        elif args[0].lower() in ("help", "menu"):
            self._usage(mo, tid, tt, uid)
        else:
            self._toggle(args, mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        self.style.reply_info(
            "muon silent ai noi me m di",
            mo, tid, tt, uid, ttl=15000,
        )

    def _check_admin(self, uid, mo, tid, tt):
        if not self.bot._is_admin(uid):
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )
            return False
        return True

    def _extract_targets(self, mo):
        targets = []

        mentions = getattr(mo, "mentions", None)
        if mentions:
            if isinstance(mentions, list):
                for m in mentions:
                    uid = getattr(m, "uid", None)
                    if uid:
                        targets.append(str(uid))
            elif isinstance(mentions, dict):
                for uid in mentions:
                    targets.append(str(uid))

        if not targets:
            quote = getattr(mo, "quote", None)
            if quote:
                owner = getattr(quote, "ownerId", None)
                if owner:
                    targets.append(str(owner))

        return targets

    def _toggle(self, args, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return

        duration = None
        if args:
            d = _parse_duration(args[0])
            if d is not None:
                duration = d

        targets = self._extract_targets(mo)
        if not targets:
            return self.style.reply_warning(
                "vui long tag hoac reply thg mun silent",
                mo, tid, tt, uid, ttl=10000,
            )

        for t in targets:
            if self.bot._is_admin(t):
                return self.style.reply_warning(
                    "ai cho m silent ae tao",
                    mo, tid, tt, uid, ttl=10000,
                )

        data = self._load()
        stid = str(tid)
        if stid not in data:
            data[stid] = {}
        elif isinstance(data[stid], list):
            old_list = data[stid]
            data[stid] = {}
            for u in old_list:
                data[stid][u] = {"expires_at": None}

        results = []

        for t in targets:
            name = _get_name(self.bot, t)

            if t in data.get(stid, {}):
                del data[stid][t]
                if not data[stid]:
                    del data[stid]
                results.append(
                    f"da mo silent cho thg ngoo {name}"
                )
            else:
                expires_at = None
                if duration is not None:
                    expires_at = time.time() + duration

                if stid not in data:
                    data[stid] = {}
                data[stid][t] = {"expires_at": expires_at}

                results.append(
                    f"da silent thg ngoo {name}"
                )

        self._save(data)

        self.style.reply_success(
            "\n\n".join(results),
            mo, tid, tt, uid, ttl=15000,
        )

    def _list(self, mo, tid, tt, uid):
        data = self._load()
        stid = str(tid)
        muted = data.get(stid, {})

        if isinstance(muted, list):
            old_list = muted
            muted = {}
            for u in old_list:
                muted[u] = {"expires_at": None}

        if not muted:
            return self.style.reply_info(
                "chua co thh ngoo nao bj silent",
                mo, tid, tt, uid, ttl=10000,
            )

        lines = [
            "danh sach bj silent",
            "-" * 30,
        ]

        for i, (user_id, info) in enumerate(muted.items(), 1):
            name = _get_name(self.bot, user_id)
            exp = info.get("expires_at")
            time_str = _fmt_remaining(exp)
            lines.append(
                f"{i}. {name}\n"
                f"   ID: {user_id}\n"
                f"   con: {time_str}"
            )
            lines.append("-" * 25)

        lines.append(f"\ntong: {len(muted)} nguoi bi cam chat")

        self.style.reply_info(
            "\n".join(lines),
            mo, tid, tt, uid, ttl=20000,
        )


def _ns():
    return {"cls": NS, "name": "silent"}