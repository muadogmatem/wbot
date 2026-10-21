from zlapi.models import Message, ThreadType


def _get_name(bot, uid):
    try:
        return bot.style.get_name(uid)
    except Exception:
        return str(uid)


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
            self._usage(mo, tid, tt, uid)
        elif args[0] in ["-a", "-a:m"]:
            self._add_key(mo, tid, tt, uid, args[0])
        elif args[0] in ["-r", "-r:m"]:
            self._remove_key(mo, tid, tt, uid, args[0])
        else:
            self._usage(mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        p = self.bot.prefix
        self.style.reply_info(
            f"cach su dung keysilver:\n\n"
            f"{p}keysilver -a @user: them key bac cho nguoi duoc tag/reply\n"
            f"{p}keysilver -a:m: them key bac cho chinh ban\n"
            f"{p}keysilver -r @user: xoa key bac cua nguoi duoc tag/reply\n"
            f"{p}keysilver -r:m: xoa key bac cua chinh ban",
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

    def _add_key(self, mo, tid, tt, uid, flag):
        if not self._check_admin(uid, mo, tid, tt):
            return

        if flag == "-a:m":
            targets = [str(uid)]
        else:
            targets = self._extract_targets(mo)
            if not targets:
                targets = [str(uid)]

        results = []

        for t in targets:
            name = _get_name(self.bot, t)
            
            try:
                self.bot.addGroupAdmins(t, tid)
                results.append(f"da them key bac cho {name}")
            except Exception as e:
                results.append(f"loi khi them key bac cho {name}: {str(e)}")

        self.style.reply_success(
            "\n\n".join(results),
            mo, tid, tt, uid, ttl=15000,
        )

    def _remove_key(self, mo, tid, tt, uid, flag):
        if not self._check_admin(uid, mo, tid, tt):
            return

        if flag == "-r:m":
            targets = [str(uid)]
        else:
            targets = self._extract_targets(mo)
            if not targets:
                targets = [str(uid)]

        results = []

        for t in targets:
            name = _get_name(self.bot, t)
            
            try:
                self.bot.removeGroupAdmins(t, tid)
                results.append(f"da xoa key bac cua {name}")
            except Exception as e:
                results.append(f"loi khi xoa key bac cua {name}: {str(e)}")

        self.style.reply_success(
            "\n\n".join(results),
            mo, tid, tt, uid, ttl=15000,
        )


def _ns():
    return {"cls": NS, "name": "keysilver"}