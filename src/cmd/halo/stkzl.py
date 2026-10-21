import os
import json
import re
import time

from .stkzl_handler import (
    save_sticker_search, get_sticker_search, has_sticker_pending,
    clear_sticker_search, get_msg_info, CACHE_TTL,
)
from .stkzl_renderer import draw_sticker_list_canvas, cleanup

TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "asset", "temp")
os.makedirs(TEMP_DIR, exist_ok=True)


class NS:
    def __init__(self, bot):
        self.bot = bot

    @property
    def style(self):
        return self.bot.style

    def handle(self, msg, mo, tid, tt, uid):
        args = msg.split()

        if len(args) < 2:
            return self.style.reply_info(
                "cu phap:\n"
                "stkzl install/uninstall\n"
                "stkzl info\n"
                "stkzl list",
                mo, tid, tt, uid, ttl=15000
            )

        action = args[1].lower()
        valid = ["install", "uninstall", "info", "list"]

        if action not in valid:
            return self.style.reply_warning(
                f"hanh dong khong hop le.\ndung: {', '.join(valid)}",
                mo, tid, tt, uid, ttl=12000
            )

        if action in ["install", "uninstall"]:
            return self._handle_install_uninstall(action, args, mo, tid, tt, uid)
        elif action == "info":
            return self._handle_info(args, mo, tid, tt, uid)
        elif action == "list":
            return self._handle_list(args, mo, tid, tt, uid)

    def handle_number_selection(self, msg, mo, tid, tt, uid):
        text = msg.strip()

        if text == "0":
            clear_sticker_search(tid, uid)
            return self.style.reply_info("da huy chon sticker", mo, tid, tt, uid, ttl=8000)

        if not text.isdigit():
            return False

        data = get_sticker_search(tid, uid)
        if not data:
            return False

        stickers = data["stickers"]
        cate_id = data["cate_id"]
        idx = int(text) - 1

        if idx < 0 or idx >= len(stickers):
            return self.style.reply_warning(
                f"so khong hop le. chon tu 1 den {len(stickers)}, hoac 0 de huy",
                mo, tid, tt, uid, ttl=8000
            )

        item = stickers[idx]
        sticker_id = item.get("id") or item.get("stickerId") or item.get("eid")
        sticker_type = item.get("type", 1)

        if not sticker_id:
            return self.style.reply_warning("khong lay duoc sticker id", mo, tid, tt, uid, ttl=8000)

        try:
            self.bot.sendSticker(
                int(sticker_type),
                int(sticker_id),
                int(cate_id),
                thread_id=tid,
                thread_type=tt
            )
        except Exception as e:
            return self.style.reply_error(f"loi gui sticker: {e}", mo, tid, tt, uid, ttl=10000)

        return True

    def _handle_install_uninstall(self, action, args, mo, tid, tt, uid):
        cate_id = None
        sticker_id = None

        if len(args) >= 3:
            try:
                cate_id = int(args[2])
            except ValueError:
                return self.style.reply_warning(
                    f"cate_id khong hop le: {args[2]}\nchi nhap so nguyen",
                    mo, tid, tt, uid, ttl=12000
                )

        if cate_id is None:
            if not mo.quote:
                return self.style.reply_warning(
                    "cu phap:\n"
                    "stkzl install/uninstall (reply vao sticker)\n"
                    "stkzl install/uninstall <cate_id>",
                    mo, tid, tt, uid, ttl=12000
                )
            cate_id, sticker_id = self._extract_sticker_info(mo.quote)
            if cate_id is None:
                return self.style.reply_warning(
                    "khong tim thay thong tin sticker trong tin nhan duoc reply",
                    mo, tid, tt, uid, ttl=12000
                )
            cate_id = int(cate_id)

        try:
            personalized_raw = self.bot.getPersonalizedStickers()
            personalized = self._unwrap(personalized_raw)

            if not personalized:
                return self.style.reply_error(
                    "khong doc duoc du lieu sticker hien tai",
                    mo, tid, tt, uid, ttl=15000
                )

            sticker_cates = list(personalized.get("sticker_cates") or [])
            version = personalized.get("version")

            if version is None:
                return self.style.reply_error(
                    "khong lay duoc version sticker hien tai",
                    mo, tid, tt, uid, ttl=12000
                )

            if action == "install":
                if cate_id in sticker_cates:
                    return self.style.reply_warning(
                        f"sticker pack {cate_id} da duoc cai dat roi",
                        mo, tid, tt, uid, ttl=12000
                    )
                sticker_cates.insert(0, cate_id)
                action_text = "cai dat"
            else:
                if cate_id not in sticker_cates:
                    return self.style.reply_warning(
                        f"sticker pack {cate_id} chua duoc cai dat",
                        mo, tid, tt, uid, ttl=12000
                    )
                sticker_cates = [x for x in sticker_cates if x != cate_id]
                action_text = "go bo"

            result_raw = self._update_with_retry(action, cate_id, sticker_cates, version)
            result_data = self._unwrap(result_raw)

            total_pack = len(result_data.get("sticker_cates") or sticker_cates)

            info = f"da {action_text} sticker pack {cate_id} thanh cong!\ntong so pack: {total_pack}"
            if sticker_id:
                info += f"\nsticker id: {sticker_id}"

            return self.style.reply_success(info, mo, tid, tt, uid, ttl=15000)

        except Exception as e:
            return self.style.reply_error(f"loi:\n{str(e)}", mo, tid, tt, uid, ttl=12000)

    def _handle_info(self, args, mo, tid, tt, uid):
        cate_id = None
        sticker_id = None

        if len(args) >= 3:
            try:
                cate_id = int(args[2])
            except ValueError:
                return self.style.reply_warning(
                    f"cate_id khong hop le: {args[2]}",
                    mo, tid, tt, uid, ttl=12000
                )

        if cate_id is None:
            if not mo.quote:
                return self.style.reply_warning(
                    "cu phap:\n"
                    "stkzl info (reply vao sticker)\n"
                    "stkzl info <cate_id>",
                    mo, tid, tt, uid, ttl=12000
                )
            cate_id, sticker_id = self._extract_sticker_info(mo.quote)
            if cate_id is None:
                return self.style.reply_warning(
                    "khong tim thay thong tin sticker trong tin nhan duoc reply",
                    mo, tid, tt, uid, ttl=12000
                )
            cate_id = int(cate_id)
            if sticker_id:
                sticker_id = str(sticker_id)

        try:
            detail = self.bot.getStickerDetail(cate_id)
            stickers = self._extract_sticker_list(detail)

            if not stickers:
                return self.style.reply_warning(
                    f"khong tim thay sticker nao trong pack {cate_id}",
                    mo, tid, tt, uid, ttl=12000
                )

            if sticker_id:
                sticker = next((s for s in stickers if str(s.get("id")) == sticker_id), None)
                if sticker:
                    return self._send_sticker_detail(sticker, cate_id, mo, tid, tt, uid)
                else:
                    return self._send_pack_info(stickers, cate_id, sticker_id, mo, tid, tt, uid)
            else:
                return self._send_pack_info(stickers, cate_id, None, mo, tid, tt, uid)

        except Exception as e:
            return self.style.reply_error(f"loi:\n{str(e)}", mo, tid, tt, uid, ttl=12000)

    def _send_sticker_detail(self, sticker, cate_id, mo, tid, tt, uid):
        sid = sticker.get("id", "N/A")
        stype = sticker.get("type", "N/A")
        duration = sticker.get("duration", "N/A")
        sticker_url = sticker.get("stickerUrl") or f"https://zalo-api.zadn.vn/api/emoticon/sticker/webpc?eid={sid}&size=130"
        sprite_url = sticker.get("stickerSpriteUrl") or f"https://zalo-api.zadn.vn/api/emoticon/sprite?eid={sid}&size=130"
        total_frames = sticker.get("totalFrames", "N/A")
        effect_id = sticker.get("effectId", "N/A")
        ext = sticker.get("ext", "N/A")

        text = (
            f"Sticker Details\n"
            f"ID: {sid}\n"
            f"Category ID: {cate_id}\n"
            f"Type: {stype}\n"
            f"Duration: {duration} ms\n"
            f"Total Frames: {total_frames}\n"
            f"Effect ID: {effect_id}\n"
            f"Ext: {ext}\n"
            f"Sticker URL: {sticker_url}\n"
            f"Sprite URL: {sprite_url}"
        )

        return self.style.reply_success(text, mo, tid, tt, uid, ttl=60000)

    def _send_pack_info(self, stickers, cate_id, not_found_id, mo, tid, tt, uid):
        total = len(stickers)
        ids_preview = [str(s.get("id", "?")) for s in stickers[:10]]
        ids_text = ", ".join(ids_preview)
        if total > 10:
            ids_text += f" ... (+{total - 10})"

        types_set = set()
        for s in stickers:
            t = s.get("type")
            if t is not None:
                types_set.add(str(t))
        types_text = ", ".join(sorted(types_set)) if types_set else "N/A"

        text = f"Sticker Pack Info\n"
        text += f"Category ID: {cate_id}\n"
        text += f"Total Stickers: {total}\n"
        text += f"Types: {types_text}\n"
        text += f"Sticker IDs: {ids_text}"

        if not_found_id:
            text += f"\n\nSticker ID {not_found_id} khong tim thay trong pack nay"

        return self.style.reply_success(text, mo, tid, tt, uid, ttl=60000)

    def _handle_list(self, args, mo, tid, tt, uid):
        cate_id = self._resolve_cate_id(args, mo, tid, tt, uid)
        if cate_id is None:
            return

        img_path = None
        try:
            loading_resp = self.style.reply_info(
                f"dang tai sticker pack {cate_id}...",
                mo, tid, tt, uid, ttl=0
            )
            time.sleep(0.3)
            loading_msg_id = getattr(loading_resp, "msgId", None)

            detail = self.bot.getStickerDetail(cate_id)
            stickers = self._extract_sticker_list(detail)

            if not stickers:
                self._try_delete_msg(tid, loading_msg_id)
                return self.style.reply_warning(
                    f"khong tim thay sticker nao trong pack {cate_id}",
                    mo, tid, tt, uid, ttl=12000
                )

            img_path = os.path.join(TEMP_DIR, f"stklist_{cate_id}_{int(time.time())}.png")
            width, height = draw_sticker_list_canvas(stickers, cate_id, img_path)

            self._try_delete_msg(tid, loading_msg_id)

            img_response = self.bot.sendLocalImage(
                img_path,
                thread_id=tid,
                thread_type=tt,
                width=width,
                height=height,
                message=None,
                ttl=CACHE_TTL * 1000
            )

            time.sleep(0.3)
            target_msg_id = getattr(img_response, "msgId", None)
            img_info = get_msg_info(self.bot, tid, target_msg_id)

            save_sticker_search(tid, uid, stickers, cate_id, img_info)

            try:
                from src.cmd.music.reaction_cooldown import start_cooldown_react_then_delete
                start_cooldown_react_then_delete(
                    self.bot, img_info, tid, tt, CACHE_TTL,
                    icon="🕐", msg_type="chat.photo"
                )
            except ImportError:
                pass

        except Exception as e:
            return self.style.reply_error(f"loi:\n{str(e)}", mo, tid, tt, uid, ttl=12000)
        finally:
            cleanup(img_path)

    def _resolve_cate_id(self, args, mo, tid, tt, uid):
        cate_id = None

        if len(args) >= 3:
            try:
                cate_id = int(args[2])
            except ValueError:
                self.style.reply_warning(
                    f"cate_id khong hop le: {args[2]}",
                    mo, tid, tt, uid, ttl=12000
                )
                return None

        if cate_id is None:
            if not mo.quote:
                self.style.reply_warning(
                    "cu phap:\n"
                    "stkzl <action> (reply vao sticker)\n"
                    "stkzl <action> <cate_id>",
                    mo, tid, tt, uid, ttl=12000
                )
                return None
            cate_id, _ = self._extract_sticker_info(mo.quote)
            if cate_id is None:
                self.style.reply_warning(
                    "khong tim thay thong tin sticker trong tin nhan duoc reply",
                    mo, tid, tt, uid, ttl=12000
                )
                return None
            cate_id = int(cate_id)

        return cate_id

    def _try_delete_msg(self, tid, msg_id):
        if not msg_id:
            return
        try:
            cli = str(int(time.time() * 1000))
            self.bot.deleteGroupMsg(msg_id, str(self.bot.uid), cli, tid)
        except:
            pass

    def _extract_sticker_list(self, detail):
        if isinstance(detail, list):
            return detail
        if isinstance(detail, dict):
            if "data" in detail:
                d = detail["data"]
                if isinstance(d, list):
                    return d
                if isinstance(d, dict):
                    if "data" in d and isinstance(d["data"], list):
                        return d["data"]
                    for key in ["stickers", "items", "list"]:
                        if key in d and isinstance(d[key], list):
                            return d[key]
            for key in ["stickers", "items", "list"]:
                if key in detail and isinstance(detail[key], list):
                    return detail[key]
        return []

    def _update_with_retry(self, action, cate_id, sticker_cates, version):
        try:
            return self.bot.updatePersonalizedStickers(sticker_cates, version)
        except Exception as e:
            if "Outdated input" not in str(e):
                raise

        personalized_raw = self.bot.getPersonalizedStickers()
        personalized = self._unwrap(personalized_raw)

        if not personalized:
            raise Exception("Outdated input va khong lay duoc du lieu moi")

        fresh_cates = list(personalized.get("sticker_cates") or [])
        fresh_version = personalized.get("version")

        if fresh_version is None:
            raise Exception("Outdated input va khong lay duoc version moi")

        if action == "install":
            if cate_id not in fresh_cates:
                fresh_cates.insert(0, cate_id)
        else:
            fresh_cates = [x for x in fresh_cates if x != cate_id]

        return self.bot.updatePersonalizedStickers(fresh_cates, fresh_version)

    def _unwrap(self, data):
        if not isinstance(data, dict):
            return {}
        if "sticker_cates" in data:
            return data
        lvl1 = data.get("data")
        if isinstance(lvl1, dict):
            if "sticker_cates" in lvl1:
                return lvl1
            lvl2 = lvl1.get("data")
            if isinstance(lvl2, dict) and "sticker_cates" in lvl2:
                return lvl2
        return {}

    def _extract_sticker_info(self, quoted_message):
        raw = quoted_message.__dict__.copy()
        for key in list(raw.keys()):
            raw[key] = self._parse_nested(raw[key])

        attach = raw.get("attach")
        if isinstance(attach, dict):
            if str(attach.get("type")) == "7":
                cate_id = attach.get("catId") or attach.get("cateId") or attach.get("cate_id")
                sticker_id = attach.get("id") or attach.get("stickerId") or attach.get("sticker_id")
                if cate_id:
                    return cate_id, sticker_id

        text_content = str(raw.get("content", "")) + str(raw.get("text", ""))
        match = re.search(r'\[\^(\d+)\.(\d+)\^\]', text_content)
        if match:
            return match.group(1), match.group(2)

        try:
            raw_text = json.dumps(raw, ensure_ascii=False)
        except:
            raw_text = str(raw)

        cate_match = re.search(r'"(?:catId|cateId|cate_id)"\s*:\s*"?(\d+)"?', raw_text)
        id_match = re.search(r'"(?:id|stickerId|sticker_id)"\s*:\s*"?(\d+)"?', raw_text)

        if cate_match:
            return cate_match.group(1), id_match.group(1) if id_match else None

        return None, None

    def _parse_nested(self, obj):
        if isinstance(obj, str):
            try:
                return self._parse_nested(json.loads(obj))
            except (json.JSONDecodeError, TypeError):
                return obj
        if isinstance(obj, dict):
            return {k: self._parse_nested(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._parse_nested(i) for i in obj]
        return obj


def _ns():
    return {"cls": NS, "name": "stkzl"}