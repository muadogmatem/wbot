class MessageParser:
    @staticmethod
    def extract_text(message):
        if message is None:
            return ""
        if isinstance(message, str):
            return message
        if hasattr(message, "text"):
            return message.text or ""
        try:
            return str(message)
        except Exception:
            return ""

    @staticmethod
    def parse(message, obj):
        msg = MessageParser.extract_text(message)

        msg_type = ""
        try:
            msg_type = getattr(obj, "msgType", "") or ""
        except Exception:
            pass

        if msg_type in ("chat.recommended", "chat.recommand"):
            try:
                content = getattr(obj, "content", None)
                if content is not None:
                    title = getattr(content, "title", None)
                    msg = title if title and isinstance(title, str) else ""
                else:
                    msg = ""
            except Exception:
                msg = ""

        try:
            mentions = getattr(obj, "mentions", None)
            if mentions and isinstance(mentions, (list, tuple)) and len(mentions) > 0:
                m = mentions[0]
                if isinstance(m, dict) and m.get("pos", -1) == 0:
                    length = m.get("len", 0)
                    if isinstance(msg, str) and len(msg) >= length:
                        msg = msg[length:]
        except Exception:
            pass

        if not isinstance(msg, str):
            msg = ""

        return msg.strip()