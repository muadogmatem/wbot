import json
from zlapi.models import Message


REACTIONS = {
    "received": "/-ok",
    "processing": "⏳",
    "cooldown": "🕐",
    "denied": "😂✌",
    "disabled": "⛔",
    "error": "❌",
}


def _build_rMsg(message_object):
    try:
        from zlapi._util import getClientMessageType
        msg_type = getClientMessageType(message_object.msgType)
    except Exception:
        msg_type = 1
    return {
        "gMsgID": int(message_object.msgId),
        "cMsgID": int(message_object.cliMsgId),
        "msgType": msg_type,
    }


class ReactionManager:
    def __init__(self, bot):
        self.bot = bot

    def react(self, mo, icon, tid, tt):
        try:
            self.bot.sendReaction(
                messageObject=mo,
                reactionIcon=icon,
                thread_id=tid,
                thread_type=tt,
            )
        except Exception:
            pass

    def multi_react(self, mo, icon, count, tid, tt):
        try:
            r = _build_rMsg(mo)
            rMsg_list = [r.copy() for _ in range(count)]
            self.bot.sendMultiReaction(
                reactionObj=rMsg_list,
                reactionIcon=icon,
                thread_id=tid,
                thread_type=tt,
                reactionType=75,
            )
        except Exception:
            pass

    def remove_react(self, mo, icon, tid, tt):
        try:
            r = _build_rMsg(mo)
            self.bot.sendMultiReaction(
                reactionObj=[r],
                reactionIcon=icon,
                thread_id=tid,
                thread_type=tt,
                reactionType=-1,
            )
        except Exception:
            pass

    def reply(self, text, mo, tid, tt):
        try:
            self.bot.replyMessage(Message(text=str(text)), mo, tid, tt)
        except Exception:
            pass