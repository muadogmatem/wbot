import os
import json
import time
import urllib.parse

from zlapi._util import (
    now as _now,
    getHeader,
    zws_decode,
    getGroupEventType,
    dict_to_raw_cookies,
    HEADERS as _HEADERS,
)
from zlapi.models import MessageObject, EventObject, ThreadType

try:
    from websockets.sync.client import connect as ws_connect
except ImportError:
    from websocket import create_connection as ws_connect

from .logger import C, log_info, log_warn, log_error


class ListenerMixin:
    def _fix_recv(self):
        time.sleep(50 * 60)
        self._start_fix = True
        self._condition.set()

    def _listen_ws(self, thread=False, reconnect=5):
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor()

        self._condition.clear()
        self._start_fix = False

        params = {"zpw_ver": 645, "zpw_type": 30, "t": _now()}

        ws_urls = self._state._config.get("zpw_ws", [])
        if not ws_urls:
            log_error("WebSocket URL not found, falling back to requests mode")
            self._listen_req(1, thread, reconnect)
            return

        url = ws_urls[0] + "?" + urllib.parse.urlencode(params)

        user_agent = self._state._headers.get("User-Agent") or _HEADERS["User-Agent"]
        raw_cookies = dict_to_raw_cookies(self._state.get_cookies())

        if not raw_cookies:
            raise Exception("Unable to load cookies")

        headers = {
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "Upgrade",
            "Host": urllib.parse.urlparse(url).netloc,
            "Origin": "https://chat.zalo.me",
            "Pragma": "no-cache",
            "Sec-Websocket-Extensions": "permessage-deflate; client_max_window_bits",
            "Sec-Websocket-Version": "13",
            "Upgrade": "websocket",
            "User-Agent": user_agent,
            "Cookie": raw_cookies,
        }

        try:
            ws = ws_connect(url, additional_headers=headers)
        except TypeError:
            ws = ws_connect(url, header=headers)

        pool.submit(self._fix_recv)
        self.onListening()
        self._listening = True

        while not self._condition.is_set():
            try:
                data = ws.recv()
                if not isinstance(data, bytes):
                    continue

                encodedHeader = data[:4]
                n, cmd, s = getHeader(encodedHeader)

                dataToDecode = data[4:]
                decodedData = dataToDecode.decode("utf-8")
                if not decodedData:
                    continue

                parsed = json.loads(decodedData)

                if n == 1 and cmd == 1 and s == 1 and "key" in parsed:
                    self.ws_key = parsed["key"]
                    continue

                if not hasattr(self, "ws_key"):
                    log_error("Unable to decrypt data because key not found")
                    continue

                if n == 1 and cmd == 3000 and s == 0:
                    log_warn("Another connection is opened, closing this one")
                    ws.close()
                    break

                elif n == 1 and cmd == 501 and s == 0:
                    parsedData = zws_decode(parsed, self.ws_key)
                    userMsgs = parsedData["data"]["msgs"]

                    for message in userMsgs:
                        msgObj = MessageObject.fromDict(message, None)
                        uid_from = str(int(msgObj.uidFrom) or self.uid)
                        id_to = str(int(msgObj.uidFrom) or msgObj.idTo)
                        if thread:
                            pool.submit(self.onMessage, msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.USER)
                        else:
                            self.onMessage(msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.USER)

                elif n == 1 and cmd == 521 and s == 0:
                    parsedData = zws_decode(parsed, self.ws_key)
                    groupMsgs = parsedData["data"]["groupMsgs"]

                    seen_mids = set()
                    for message in groupMsgs:
                        mid = message.get("msgId")
                        if mid in seen_mids:
                            continue
                        seen_mids.add(mid)

                        msgObj = MessageObject.fromDict(message, None)
                        uid_from = str(int(msgObj.uidFrom) or self.uid)
                        id_to = str(int(msgObj.idTo) or self.uid)
                        if thread:
                            pool.submit(self.onMessage, msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.GROUP)
                        else:
                            self.onMessage(msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.GROUP)

                elif n == 1 and cmd == 612 and s == 0:
                    parsedData = zws_decode(parsed, self.ws_key)
                    reacts = parsedData["data"].get("reacts", [])
                    reactGroups = parsedData["data"].get("reactGroups", [])

                    for react in reacts:
                        react["content"] = json.loads(react["content"]) if isinstance(react["content"], str) else react["content"]
                        msgObj = MessageObject.fromDict(react, None)
                        uid_from = str(int(msgObj.uidFrom) or self.uid)
                        id_to = str(int(msgObj.uidFrom) or msgObj.idTo)
                        if thread:
                            pool.submit(self.onMessage, msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.USER)
                        else:
                            self.onMessage(msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.USER)

                    for reactGroup in reactGroups:
                        reactGroup["content"] = json.loads(reactGroup["content"]) if isinstance(reactGroup["content"], str) else reactGroup["content"]
                        msgObj = MessageObject.fromDict(reactGroup, None)
                        uid_from = str(int(msgObj.uidFrom) or self.uid)
                        id_to = str(int(msgObj.idTo) or self.uid)
                        if thread:
                            pool.submit(self.onMessage, msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.GROUP)
                        else:
                            self.onMessage(msgObj.msgId, uid_from, msgObj.content, msgObj, id_to, ThreadType.GROUP)

                elif n == 1 and cmd == 601 and s == 0:
                    parsedData = zws_decode(parsed, self.ws_key)
                    controls = parsedData["data"].get("controls", [])
                    for control in controls:
                        act_type = control.get("content", {}).get("act_type", "")
                        if act_type == "file_done":
                            pool.submit(self.fileEvent, control)
                        elif act_type == "group":
                            act = control["content"].get("act", "")
                            if act == "join_reject":
                                continue
                            groupEventData = control["content"].get("data", {})
                            if isinstance(groupEventData, str):
                                groupEventData = json.loads(groupEventData)
                            groupEventType = getGroupEventType(act)
                            event_data = EventObject.fromDict(groupEventData)
                            if thread:
                                pool.submit(self.onEvent, event_data, groupEventType)
                            else:
                                self.onEvent(event_data, groupEventType)

                elif cmd in (502, 522, 504, 524, 602):
                    continue

                else:
                    continue

            except KeyboardInterrupt:
                self._condition.set()
                ws.close()
                import signal
                log_warn("Stop Listen Because KeyboardInterrupt")
                os.kill(os.getpid(), signal.SIGTERM)

            except Exception as e:
                err_str = str(e)
                if "1000" in err_str and "OK" in err_str:
                    pass
                elif "ConnectionClosed" in type(e).__name__:
                    self._start_fix = True
                    self._condition.set()
                    try:
                        ws.close()
                    except Exception:
                        pass
                    break
                else:
                    self._listening = False
                    self._start_fix = False
                    self._condition.set()
                    try:
                        ws.close()
                    except Exception:
                        pass
                    self.onErrorCallBack(e)
                    if self.run_forever:
                        while not self._listening:
                            try:
                                log_info("Run forever mode, trying to reconnect...")
                                self._listen_ws(thread, reconnect)
                            except Exception:
                                pass
                            time.sleep(reconnect)
                    break

        self._listening = False

        if self._start_fix:
            log_info("Reconnecting websocket...")
            self._start_fix = False
            self._listen_ws(thread, reconnect)