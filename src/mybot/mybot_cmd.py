import os
import time
import json
import threading
import traceback

from zlapi import ZaloAPI
from zlapi.models import Message, ThreadType
from zlapi._exception import ZaloLoginError

from .manager import get_manager


MAIN_PHONE = "878080202"


def _parse_duration(s):
    if not s:
        return None
    s = s.lower()
    unit = s[-1]
    try:
        val = int(s[:-1])
    except ValueError:
        return None
    if unit == "d":
        return val * 86400
    elif unit == "h":
        return val * 3600
    elif unit == "m":
        return val * 60
    return None


class NS:
    def __init__(self, bot):
        self.bot = bot
        self.manager = get_manager()
        self.manager.set_owner_phone(MAIN_PHONE)
        print(f"[MYBOT] Owner phone set: {MAIN_PHONE}")

    @property
    def style(self):
        return self.bot.style

    @property
    def reg(self):
        return self.bot.reg

    def _resolve_targets(self, target):
        if target.lower() == "all":
            return list(self.manager.bots.keys())
        try:
            idx = int(target) - 1
            keys = list(self.manager.bots.keys())
            if 0 <= idx < len(keys):
                return [keys[idx]]
            return []
        except ValueError:
            if target in self.manager.bots:
                return [target]
            return []

    def handle(self, msg, mo, tid, tt, uid):
        args = msg[len(self.bot.prefix):].strip().split()[1:]
        if not args:
            return self._usage(mo, tid, tt, uid)

        action = args[0].lower()

        if action == "create":
            if len(args) < 2:
                return self._usage(mo, tid, tt, uid)
            if args[1].lower() == "qr":
                self._create_qr(mo, tid, tt, uid)
            else:
                self._create_manual(args[1:], mo, tid, tt, uid)
        elif action == "list":
            self._list(mo, tid, tt, uid)
        elif action == "execute":
            if len(args) < 2:
                return self._usage(mo, tid, tt, uid)
            
            target_str = "all"
            command = args[1].lower()
            cmd_args = []
            
            if command.isdigit() or command == "all":
                if len(args) < 3:
                    return self._usage(mo, tid, tt, uid)
                target_str = command
                command = args[2].lower()
                cmd_args = args[3:]
            
            self._execute(target_str, command, cmd_args, mo, tid, tt, uid)
        elif action in ("start", "stop", "restart", "delete", "run", "info"):
            if len(args) < 2:
                return self._usage(mo, tid, tt, uid)
            
            targets = self._resolve_targets(args[1])
            if not targets:
                return self.style.reply_error(
                    f"khong tim thay bot (stt/id: {args[1]})",
                    mo, tid, tt, uid, ttl=10000
                )
            
            results = []
            for bot_id in targets:
                if action == "start":
                    results.append(self._start(bot_id, args[2:]))
                elif action == "stop":
                    results.append(self._stop(bot_id))
                elif action == "restart":
                    results.append(self._restart(bot_id))
                elif action == "delete":
                    results.append(self._delete(bot_id))
                elif action == "run":
                    results.append(self._run(bot_id, args[2:]))
                elif action == "info":
                    results.append(self._info(bot_id))
            
            self.style.reply_info(
                "\n".join(results),
                mo, tid, tt, uid, ttl=20000
            )
        elif action == "server":
            self._show_server_info(mo, tid, tt, uid)
        else:
            self._usage(mo, tid, tt, uid)

    def _usage(self, mo, tid, tt, uid):
        p = self.bot.prefix
        self.style.reply_info(
            f"quan ly multi bot:\n\n"
            f"{p}mybot create qr - tao bot bang qr\n"
            f"{p}mybot create <imei> <cookie> - tao bot thu cong\n"
            f"{p}mybot list - xem danh sach bot\n"
            f"{p}mybot info <stt/all> - xem thong tin bot\n"
            f"{p}mybot server - xem thong tin server\n"
            f"{p}mybot start <stt/all> - bat bot\n"
            f"{p}mybot stop <stt/all> - tat bot\n"
            f"{p}mybot restart <stt/all> - khoi dong lai bot\n"
            f"{p}mybot delete <stt/all> - xoa bot\n"
            f"{p}mybot run <stt/all> [30d/12h/...] - chay bot\n"
            f"{p}mybot execute [stt/all] join - bot con join nhom hien tai",
            mo, tid, tt, uid, ttl=20000
        )

    def _show_server_info(self, mo, tid, tt, uid):
        try:
            user_info = self.bot.fetchPhoneNumber(MAIN_PHONE)
            if user_info and hasattr(user_info, 'uid'):
                info_text = (
                    f"thong tin server:\n\n"
                    f"uid: {user_info.uid}\n"
                    f"name: {user_info.zalo_name or user_info.display_name}\n"
                    f"gender: {user_info.gender}\n"
                    f"dob: {user_info.sdob}\n\n"
                    f"luu y: moi bot con se tu fetch uid rieng"
                )
                self.style.reply_info(info_text, mo, tid, tt, uid, ttl=15000)
            else:
                self.style.reply_error(
                    "khong lay duoc thong tin server",
                    mo, tid, tt, uid, ttl=10000
                )
        except Exception as e:
            self.style.reply_error(
                f"loi: {e}",
                mo, tid, tt, uid, ttl=10000
            )

    def _create_qr(self, mo, tid, tt, uid):
        qr_file = f"qr_mybot_{tid}_{int(time.time())}.png"

        def _process():
            temp_client = None
            try:
                self.style.reply_info(
                    "dang tao ma qr, vui long cho...",
                    mo, tid, tt, uid, ttl=10000
                )

                temp_client = ZaloAPI(phone=None, password=None, imei=None, auto_login=False)

                def send_qr(path):
                    if os.path.exists(path):
                        msg = Message(text="quet ma qr trong vong 100 giay de tao bot")
                        self.bot.sendLocalImage(
                            imagePath=path,
                            thread_id=tid,
                            thread_type=tt,
                            message=msg,
                            ttl=100000
                        )

                temp_client.loginWithQR(
                    qr_path=qr_file,
                    on_qr_generated=send_qr
                )

                if temp_client.isLoggedIn():
                    imei = temp_client._state.user_imei
                    cookies = temp_client.getSession()

                    bot_id = self.manager.create_bot(imei, cookies, ".")

                    self.style.reply_success(
                        f"tao bot thanh cong!\n\n"
                        f"id: {bot_id}\n"
                        f"imei: {imei}\n\n"
                        f"dung {self.bot.prefix}mybot run {bot_id} de chay bot",
                        mo, tid, tt, uid, ttl=30000
                    )

            except ZaloLoginError as e:
                if "Het thoi gian cho quet ma qr" in str(e):
                    self.style.reply_error(
                        "het thoi gian cho quet ma qr",
                        mo, tid, tt, uid, ttl=10000
                    )
                else:
                    self.style.reply_error(
                        f"loi dang nhap qr: {e}",
                        mo, tid, tt, uid, ttl=10000
                    )
            except Exception as e:
                self.style.reply_error(
                    f"loi: {e}",
                    mo, tid, tt, uid, ttl=10000
                )
                traceback.print_exc()
            finally:
                if os.path.exists(qr_file):
                    try:
                        os.remove(qr_file)
                    except:
                        pass

        threading.Thread(target=_process, daemon=True).start()

    def _create_manual(self, args, mo, tid, tt, uid):
        if len(args) < 2:
            return self.style.reply_warning(
                f"cu phap: {self.bot.prefix}mybot create <imei> <cookie>",
                mo, tid, tt, uid, ttl=10000
            )

        imei = args[0]
        cookie_str = " ".join(args[1:])

        try:
            cookies = json.loads(cookie_str)
        except json.JSONDecodeError:
            return self.style.reply_error(
                "cookie khong hop le (phai la json)",
                mo, tid, tt, uid, ttl=10000
            )

        bot_id = self.manager.create_bot(imei, cookies, ".")

        self.style.reply_success(
            f"tao bot thanh cong!\n\n"
            f"id: {bot_id}\n"
            f"imei: {imei}\n\n"
            f"dung {self.bot.prefix}mybot run {bot_id} de chay bot",
            mo, tid, tt, uid, ttl=20000
        )

    def _list(self, mo, tid, tt, uid):
        bots = self.manager.list_bots()

        if not bots:
            return self.style.reply_info(
                "chua co bot con nao",
                mo, tid, tt, uid, ttl=10000
            )

        lines = ["danh sach bot con:", ""]

        for i, (bot_id, bot) in enumerate(bots, 1):
            status = bot.get_status()
            uptime = bot.get_uptime()
            bot_uid = bot.bot_uid or "N/A"
            owner_uid = bot.owner_uid or "N/A"
            lines.append(
                f"{i}. id: {bot_id}\n"
                f"   bot uid: {bot_uid}\n"
                f"   owner uid: {owner_uid}\n"
                f"   trang thai: {status}\n"
                f"   uptime: {uptime}\n"
                f"   prefix: {bot.prefix}"
            )
            lines.append("")

        lines.append(f"tong: {len(bots)} bot")

        self.style.reply_info(
            "\n".join(lines),
            mo, tid, tt, uid, ttl=30000
        )

    def _info(self, bot_id):
        bot = self.manager.get_bot(bot_id)
        if not bot:
            return f"khong tim thay bot {bot_id}"

        status = bot.get_status()
        uptime = bot.get_uptime()
        bot_uid = bot.bot_uid or "N/A"
        owner_uid = bot.owner_uid or "N/A"

        return (
            f"thong tin bot {bot_id}:\n"
            f"bot uid: {bot_uid}\n"
            f"owner uid: {owner_uid}\n"
            f"prefix: {bot.prefix}\n"
            f"trang thai: {status}\n"
            f"uptime: {uptime}"
        )

    def _start(self, bot_id, args):
        bot = self.manager.get_bot(bot_id)
        if not bot:
            return f"khong tim thay bot {bot_id}"
        if self.manager.start_bot(bot_id):
            return f"da bat bot {bot_id}"
        return f"bot {bot_id} da chay roi"

    def _stop(self, bot_id):
        bot = self.manager.get_bot(bot_id)
        if not bot:
            return f"khong tim thay bot {bot_id}"
        if self.manager.stop_bot(bot_id):
            return f"da tat bot {bot_id}"
        return f"bot {bot_id} chua chay"

    def _restart(self, bot_id):
        bot = self.manager.get_bot(bot_id)
        if not bot:
            return f"khong tim thay bot {bot_id}"
        if self.manager.restart_bot(bot_id):
            return f"da khoi dong lai bot {bot_id}"
        return f"loi khi khoi dong lai bot {bot_id}"

    def _delete(self, bot_id):
        if self.manager.delete_bot(bot_id):
            return f"da xoa bot {bot_id}"
        return f"khong tim thay bot {bot_id}"

    def _run(self, bot_id, args):
        bot = self.manager.get_bot(bot_id)
        if not bot:
            return f"khong tim thay bot {bot_id}"

        duration = None
        duration_text = "vinh vien"

        if args:
            duration = _parse_duration(args[0])
            if duration:
                duration_text = args[0]

        if self.manager.start_bot(bot_id, duration):
            return f"da chay bot {bot_id} ({duration_text})"
        return f"bot {bot_id} da chay roi"

    def _execute(self, target_str, command, args, mo, tid, tt, uid):
        if command == "join":
            if tt != ThreadType.GROUP:
                return self.style.reply_error(
                    "lenh nay chi dung trong nhom",
                    mo, tid, tt, uid, ttl=10000
                )
            
            targets = self._resolve_targets(target_str)
            if not targets:
                return self.style.reply_error(
                    f"khong tim thay bot (stt/id: {target_str})",
                    mo, tid, tt, uid, ttl=10000
                )

            try:
                link_res = self.bot.getGroupLink(tid)
                
                if not isinstance(link_res, dict) or link_res.get('error_code') != 0:
                    return self.style.reply_error(
                        f"loi lay link nhom: {link_res.get('error_message', 'unknown')}",
                        mo, tid, tt, uid, ttl=10000
                    )
                
                group_link = link_res.get('data', {}).get('link')
                
                if not group_link:
                    return self.style.reply_error(
                        "khong tim thay link nhom trong response",
                        mo, tid, tt, uid, ttl=10000
                    )
            except Exception as e:
                return self.style.reply_error(
                    f"loi lay link nhom: {e}",
                    mo, tid, tt, uid, ttl=10000
                )

            success = []
            failed = []
            
            for bot_id in targets:
                bot_instance = self.manager.get_bot(bot_id)
                if not bot_instance:
                    failed.append(f"{bot_id} (khong ton tai)")
                    continue
                    
                if bot_instance.running and bot_instance.client:
                    try:
                        bot_instance.client.joinGroup(group_link)
                        success.append(bot_id)
                    except Exception as e:
                        failed.append(f"{bot_id} ({e})")
                else:
                    failed.append(f"{bot_id} (offline)")
            
            msg = f"thuc thi lenh join cho bot:\n\n"
            if success:
                msg += f"thanh cong ({len(success)}): {', '.join(success)}\n"
            if failed:
                msg += f"that bai ({len(failed)}): {', '.join(failed)}"
            
            self.style.reply_success(msg, mo, tid, tt, uid, ttl=15000)
        else:
            self._usage(mo, tid, tt, uid)


def _ns():
    return {"cls": NS, "name": "mybot"}