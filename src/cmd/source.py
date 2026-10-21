from zlapi.models import Message
import json
import re

class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        if not mo.quote:
            return self.style.reply_warning(
                "reply tin nhan can lay thong tin",
                mo, tid, tt, uid, ttl=12000
            )

        try:
            quoted_message = mo.quote
            raw = quoted_message.__dict__.copy()

            for key in raw:
                raw[key] = self._parse_nested(raw[key])

            cateId = None
            stickerId = None

            attach = raw.get("attach")
            if isinstance(attach, dict) and attach.get("type") == 7:
                cateId = attach.get("catId")
                stickerId = attach.get("id")
            
            if not cateId:
                text_content = str(raw.get('content', '')) + str(raw.get('text', ''))
                match = re.search(r'\[\^(\d+)\.(\d+)\^\]', text_content)
                if match:
                    cateId = match.group(1)
                    stickerId = match.group(2)

            if cateId:
                try:
                    sticker_details = self.bot.getStickerDetail(cateId)
                    
                    detail_list = []
                    if isinstance(sticker_details, list):
                        detail_list = sticker_details
                    elif isinstance(sticker_details, dict):
                        detail_list = sticker_details.get("data", [])

                    if stickerId and detail_list:
                        specific_sticker = next((s for s in detail_list if str(s.get('id')) == str(stickerId)), None)
                        if specific_sticker:
                            raw['_sticker'] = specific_sticker
                        else:
                            raw['sticker_source'] = f"Không tìm thấy id {stickerId} trong bộ sticker {cateId}"
                    elif detail_list:
                        
                        raw['_sticker_cat'] = detail_list
                        
                except Exception as e:
                    raw['sticker_detail_error'] = f"Lỗi gọi API: {str(e)}"
            raw = self._reorder(raw)
            full_json = json.dumps(raw, indent=2, ensure_ascii=False)
            chunks = [full_json[i:i + 3000] for i in range(0, len(full_json), 3000)]

            for chunk in chunks:
                self.style.reply_success(
                    chunk,
                    mo, tid, tt, uid, ttl=86400000
                )

        except Exception as e:
            self.style.reply_error(
                f"loi:\n{str(e)}",
                mo, tid, tt, uid, ttl=10000
            )

    def _parse_nested(self, obj):
        if isinstance(obj, str):
            try:
                parsed = json.loads(obj)
                return self._parse_nested(parsed)
            except (json.JSONDecodeError, TypeError):
                return obj

        if isinstance(obj, dict):
            return {k: self._parse_nested(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._parse_nested(i) for i in obj]

        return obj

    def _reorder(self, data):
        if isinstance(data, dict):
            priority = ["_sticker", "_sticker_cat", "attach", "params", "content", "text"]
            new = {}

            for key in priority:
                if key in data:
                    new[key] = self._reorder(data[key])

            for k, v in data.items():
                if k not in priority:
                    new[k] = self._reorder(v)

            return new

        if isinstance(data, list):
            return [self._reorder(i) for i in data]

        return data


def _ns():
    return {"cls": NS, "name": "source"}