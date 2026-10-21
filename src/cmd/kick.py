from zlapi.models import Message


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        
        if len(parts) > 1 and parts[1].lower() == "-a":
            self._kick_all(mo, tid, tt, uid)
        else:
            self._kick(mo, tid, tt, uid)

    def _check_admin(self, uid, mo, tid, tt):
        if not self.bot._is_admin(uid):
            self.style.reply_denied(
                "ban khong co quyen su dung lenh nay",
                mo, tid, tt, uid, ttl=10000,
            )
            return False
        return True

    def _get_bot_uid(self):
        return getattr(self.bot, "uid", None) or getattr(self.bot, "_uid", None)

    def _check_bot_permission(self, tid, mo, tt, uid):
        try:
            group_data = self.bot.fetchGroupInfo(tid).gridInfoMap[tid]
            admins = group_data.adminIds or []
            owner = group_data.creatorId
            bot_uid = self._get_bot_uid()

            if bot_uid not in admins and bot_uid != owner:
                self.style.reply_warning(
                    "bot can quyen quan tri vien de kick thanh vien",
                    mo, tid, tt, uid, ttl=10000
                )
                return None

            return group_data
        except Exception as e:
            self.style.reply_error(
                f"loi khi lay thong tin nhom: {str(e)}",
                mo, tid, tt, uid, ttl=10000
            )
            return None

    def _get_user_name(self, user_id):
        try:
            user_info = self.bot.fetchUserInfo(user_id)
            return user_info.changed_profiles[user_id].zaloName
        except Exception:
            return user_id

    def _can_kick(self, target_id, admins, owner, bot_uid):
        if target_id == owner:
            return False, "khong the kick chu nhom"

        if target_id == bot_uid:
            return False, "khong the tu kick"

        if bot_uid == owner:
            return True, None

        if target_id in admins:
            return False, "khong the kick quan tri vien"

        return True, None

    def _kick(self, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return

        user_ids_to_kick = []

        mentions = getattr(mo, "mentions", None)
        if mentions:
            if isinstance(mentions, list):
                for m in mentions:
                    mention_uid = getattr(m, "uid", None)
                    if mention_uid:
                        user_ids_to_kick.append(str(mention_uid))
            elif isinstance(mentions, dict):
                for mention_uid in mentions:
                    user_ids_to_kick.append(str(mention_uid))

        if not user_ids_to_kick and mo.quote:
            owner_id = getattr(mo.quote, "ownerId", None)
            if owner_id:
                user_ids_to_kick.append(str(owner_id))

        if not user_ids_to_kick:
            self.style.reply_info(
                "ban mun kick ai",
                mo, tid, tt, uid, ttl=15000
            )
            return

        group_data = self._check_bot_permission(tid, mo, tt, uid)
        if not group_data:
            return

        admins = group_data.adminIds or []
        owner = group_data.creatorId
        bot_uid = self._get_bot_uid()

        kicked_names = []
        skipped = []

        for user_id in user_ids_to_kick:
            can_kick, reason = self._can_kick(user_id, admins, owner, bot_uid)

            if not can_kick:
                skipped.append(reason)
                continue

            try:
                user_name = self._get_user_name(user_id)
                self.bot.kickUsersInGroup(user_id, tid)
                kicked_names.append(user_name)
            except Exception:
                pass

        if kicked_names:
            self.style.reply_success(
                f"da kick: {', '.join(kicked_names)}",
                mo, tid, tt, uid, ttl=15000
            )

        if skipped:
            self.style.reply_warning(
                "\n".join(set(skipped)),
                mo, tid, tt, uid, ttl=10000
            )

    def _kick_all(self, mo, tid, tt, uid):
        if not self._check_admin(uid, mo, tid, tt):
            return

        group_data = self._check_bot_permission(tid, mo, tt, uid)
        if not group_data:
            return

        admins = group_data.adminIds or []
        owner = group_data.creatorId
        bot_uid = self._get_bot_uid()

        protected_ids = set()
        protected_ids.add(owner)
        if bot_uid:
            protected_ids.add(bot_uid)

        if bot_uid != owner:
            protected_ids.update(admins)

        try:
            mem_list = group_data.get("memVerList", []) or getattr(group_data, "memVerList", []) or []
            all_members = set()

            for member in mem_list:
                if isinstance(member, str):
                    member_id = member.split('_')[0]
                    all_members.add(member_id)
                else:
                    all_members.add(str(member))

            members_to_kick = all_members - protected_ids

            if not members_to_kick:
                self.style.reply_warning(
                    "khong co thanh vien nao de kick",
                    mo, tid, tt, uid, ttl=10000
                )
                return

            self.style.reply_info(
                f"dang kick {len(members_to_kick)} thanh vien",
                mo, tid, tt, uid, ttl=10000
            )

            kicked_count = 0
            for member_id in members_to_kick:
                try:
                    self.bot.kickUsersInGroup(member_id, tid)
                    kicked_count += 1
                except Exception:
                    pass

            self.style.reply_success(
                f"da kick {kicked_count}/{len(members_to_kick)} thanh vien",
                mo, tid, tt, uid, ttl=15000
            )

        except Exception as e:
            self.style.reply_error(
                f"loi: {str(e)}",
                mo, tid, tt, uid, ttl=10000
            )


def _ns():
    return {"cls": NS, "name": "kick"}