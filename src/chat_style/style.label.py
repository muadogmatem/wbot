from zlapi.models import Message, MultiMsgStyle, MessageStyle, Mention

COLOR_RED = "#db342e"
COLOR_YELLOW = "#f7b503"
COLOR_GREEN = "#15a85f"

SIZE_30 = "30"
SIZE_18 = "18"
SIZE_16 = "16"
SIZE_14 = "14"

LABEL_SUCCESS = "SUCCESS"
LABEL_WARNING = "WARNING"
LABEL_DENIED = "DENIED"
LABEL_ERROR = "ERROR"
LABEL_INFO = "INFO"


class ChatStyle:
    def __init__(self, bot):
        self.bot = bot
        self._name_cache = {}

    def get_name(self, uid):
        uid = str(uid)
        if uid in self._name_cache:
            return self._name_cache[uid]
        try:
            info = self.bot.fetchUserInfo(uid)
            if info and hasattr(info, "changed_profiles") and info.changed_profiles:
                name = info.changed_profiles.get(uid, {}).get("zaloName")
                if name and name != "không xác định":
                    self._name_cache[uid] = name
                    return name
        except Exception:
            pass
        self._name_cache[uid] = uid
        return uid

    def _build(self, uid, label, label_color, text, ttl=0):
        name = self.get_name(uid)
        tag_line = f"@{name}"

        msg = f"{tag_line}\n{label}\n{text}"

        label_offset = len(tag_line) + 1
        styles = MultiMsgStyle([
            MessageStyle(
                offset=label_offset,
                length=len(label),
                style="color",
                color=label_color,
                auto_format=False
            ),
            MessageStyle(
                offset=label_offset,
                length=len(label),
                style="bold",
                auto_format=False
            ),
            MessageStyle(
                offset=label_offset,
                length=len(label),
                style="font",
                size=SIZE_14,
                auto_format=False
            ),
        ])

        mention = Mention(uid, length=len(tag_line), offset=0)

        return Message(text=msg, style=styles, mention=mention)

    def reply_success(self, text, mo, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_SUCCESS, COLOR_GREEN, text, ttl)
        self.bot.replyMessage(msg, mo, tid, tt, ttl=ttl)

    def reply_warning(self, text, mo, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_WARNING, COLOR_YELLOW, text, ttl)
        self.bot.replyMessage(msg, mo, tid, tt, ttl=ttl)

    def reply_denied(self, text, mo, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_DENIED, COLOR_RED, text, ttl)
        self.bot.replyMessage(msg, mo, tid, tt, ttl=ttl)

    def reply_error(self, text, mo, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_ERROR, COLOR_RED, text, ttl)
        self.bot.replyMessage(msg, mo, tid, tt, ttl=ttl)

    def reply_info(self, text, mo, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_INFO, COLOR_GREEN, text, ttl)
        self.bot.replyMessage(msg, mo, tid, tt, ttl=ttl)

    def send_success(self, text, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_SUCCESS, COLOR_GREEN, text, ttl)
        self.bot.sendMessage(msg, tid, tt, ttl=ttl)

    def send_warning(self, text, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_WARNING, COLOR_YELLOW, text, ttl)
        self.bot.sendMessage(msg, tid, tt, ttl=ttl)

    def send_denied(self, text, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_DENIED, COLOR_RED, text, ttl)
        self.bot.sendMessage(msg, tid, tt, ttl=ttl)

    def send_error(self, text, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_ERROR, COLOR_RED, text, ttl)
        self.bot.sendMessage(msg, tid, tt, ttl=ttl)

    def send_info(self, text, tid, tt, uid, ttl=0):
        msg = self._build(uid, LABEL_INFO, COLOR_GREEN, text, ttl)
        self.bot.sendMessage(msg, tid, tt, ttl=ttl)

    def reply_custom(self, label, color, text, mo, tid, tt, uid, ttl=0):
        msg = self._build(uid, label, color, text, ttl)
        self.bot.replyMessage(msg, mo, tid, tt, ttl=ttl)

    def send_custom(self, label, color, text, tid, tt, uid, ttl=0):
        msg = self._build(uid, label, color, text, ttl)
        self.bot.sendMessage(msg, tid, tt, ttl=ttl)

    def reply_simple(self, label, color, text, mo, tid, tt, ttl=0):
        msg_text = f"{label}\n{text}"
        styles = MultiMsgStyle([
            MessageStyle(offset=0, length=len(label), style="color", color=color, auto_format=False),
            MessageStyle(offset=0, length=len(label), style="bold", auto_format=False),
            MessageStyle(offset=0, length=len(label), style="font", size=SIZE_14, auto_format=False),
        ])
        self.bot.replyMessage(Message(text=msg_text, style=styles), mo, tid, tt, ttl=ttl)