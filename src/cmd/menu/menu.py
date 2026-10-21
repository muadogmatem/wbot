import os
import time
import random
from zlapi.models import Message

from .menu_handler import save_menu, get_msg_info, delete_message, clear_pending_menu, get_pending_menu, CACHE_TTL


PERM_TEXT = {
    1: "thanh vien",
    2: "admin",
    3: "admin cap cao",
    4: "owner",
    5: "server"
}


class NS:
    def __init__(self, bot):
        self.bot = bot
        self.PAGE_SIZE = 15
        self.BOT_NAME = "ConMeo"

    @property
    def style(self):
        return self.bot.style

    @property
    def reg(self):
        return self.bot.reg

    def _convert_perm(self, perm):
        if isinstance(perm, int):
            return perm
        if isinstance(perm, str):
            if perm == "admin":
                return 3
            elif perm == "all":
                return 1
            try:
                return int(perm)
            except ValueError:
                return 1
        return 1

    def _cleanup_file(self, file_path):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass

    def handle(self, msg, mo, tid, tt, uid):
        text = msg[len(self.bot.prefix):].strip()
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []

        if args and args[0].lower() == "all":
            self._send_menu_all(mo, tid, tt, uid)
        elif args and args[0].isdigit():
            self._send_menu_page(int(args[0]), mo, tid, tt, uid)
        else:
            self._send_menu_page(1, mo, tid, tt, uid)

    def _send_menu_page(self, page, mo, tid, tt, uid):
        from .menu_renderer import draw_menu_page, save_menu_image

        old_data = get_pending_menu(tid, uid)
        if old_data and old_data.get("menu_img_info"):
            try:
                delete_message(self.bot, tid, tt, old_data["menu_img_info"])
            except:
                pass
            clear_pending_menu(tid, uid)
        
        entries = list(self.reg.e.items())
        total = len(entries)
        total_pages = max(1, (total + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        
        if page < 1 or page > total_pages:
            self.style.reply_warning(
                f"trang {page} khong hop le. tong: {total_pages} trang.",
                mo, tid, tt, uid, ttl=10000
            )
            return
        
        start = (page - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        page_entries = entries[start:end]
        
        unique_id = f"{tid}_{int(time.time())}_{random.randint(1000, 9999)}"
        
        try:
            img = draw_menu_page(page_entries, page, total_pages, self.BOT_NAME)
            file_path = save_menu_image(img, unique_id)
            
            img_response = self.bot.sendLocalImage(
                file_path,
                thread_id=tid,
                thread_type=tt,
                width=img.width,
                height=img.height,
                message=Message(text=""),
                ttl=CACHE_TTL * 1000
            )
            
            self._cleanup_file(file_path)
            
            time.sleep(0.5)
            target_msg_id = getattr(img_response, "msgId", None)
            menu_img_info = get_msg_info(self.bot, tid, target_msg_id)
            
            save_menu(tid, uid, page, total_pages, menu_img_info)
            
        except Exception as e:
            self.style.reply_error(
                f"loi: {str(e)}",
                mo, tid, tt, uid, ttl=10000
            )

    def _send_menu_all(self, mo, tid, tt, uid):
        old_data = get_pending_menu(tid, uid)
        if old_data and old_data.get("menu_img_info"):
            try:
                delete_message(self.bot, tid, tt, old_data["menu_img_info"])
            except:
                pass
            clear_pending_menu(tid, uid)
        
        p = self.bot.prefix
        entries = []

        for name, entry in sorted(self.reg.e.items()):
            perm = self._convert_perm(entry.get("perm", 1))
            entries.append((name, entry, perm))

        if not entries:
            self.style.reply_warning(
                "khong tim thay lenh nao phu hop.",
                mo, tid, tt, uid, ttl=10000
            )
            return

        lines = ["toan bo danh sach lenh:", ""]
        current_level = None
        counter = 0
        sorted_entries = sorted(entries, key=lambda x: x[2])

        for name, entry, perm in sorted_entries:
            if perm != current_level:
                current_level = perm
                level_text = PERM_TEXT.get(perm, str(perm))
                
                if counter > 0:
                    lines.append("")
                
                lines.append(f"[{level_text}]")
                counter = 0

            counter += 1
            status = "+" if entry.get("on", True) else "-"
            desc = entry.get("desc", "chua co mo ta")
            lines.append(f"  {counter}. [{status}] {name}: {desc}")

        lines.append("")
        lines.append(f"{p}cmd info <lenh> -> xem chi tiet")

        self.style.reply_info(
            "\n".join(lines),
            mo, tid, tt, uid, ttl=120000
        )


def _ns():
    return {"cls": NS, "name": "menu"}