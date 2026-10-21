class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        p = self.bot.prefix
        
        try:
            self._send_custom_sticker(tid, tt)
        except Exception as e:
            print(f"Lỗi khi gửi sticker: {e}")
        
        self.style.reply_info(
            f"dung {p}menu de xem tat ca cac lenh",
            mo, tid, tt, uid, ttl=10000
        )
    
    def _send_custom_sticker(self, tid, tt):
        sticker_url = "https://f41-zfcloud.zdn.vn/9daa0867829c22c27b8d/1235296777538986957?stickerCreatedBy=LyHoangKhang.ConMeo"
        
        width = 498
        height = 498
        
        self.bot.sendCustomStickerAI(
            staticImgUrl=sticker_url,
            animationImgUrl=sticker_url,
            width=width,
            height=height,
            thread_id=tid,
            thread_type=tt,
            pStickerType=1
        )


def _ns():
    return {
        "cls": NS,
        "name": "prefixonly",
        "perm": 1,
        "cd": 30,
        "hidden": True,
        "on": True,
        "alias": []
    }