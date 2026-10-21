# -*- coding: UTF-8 -*-
import uuid
import base64
import re
import random
import websockets
import requests, json

from .models import *
from ._package import *
from . import _util, _state
from .logging import Logging
from websockets.sync.client import connect
from concurrent.futures import ThreadPoolExecutor, Future

pool = ThreadPoolExecutor(max_workers=9999)
logger = Logging(theme="catppuccin-mocha", log_text_color="black")

class ZaloAPI(object):
    def __init__(self, phone, password, imei, session_cookies=None, user_agent=None, auto_login=True):
        """Initialize and log in the client.
        
        Args:
            imei (str): The device imei is logged into Zalo
            phone (str): Zalo account phone number
            password (str): Zalo account password
            auto_login (bool): Automatically log in when initializing ZaloAPI (Default: True)
            user_agent (str): Custom user agent to use when sending requests. If `None`, user agent will be chosen from a premade list
            session_cookies (dict): Cookies from a previous session (Required if logging in with cookies)
            
        Raises:
            ZaloLoginError: On failed login
            LoginMethodNotSupport: If method login not support
        """
        self._ws = None
        self._state = _state.State()
        self._condition = threading.Event()
        self._listening = False
        self._start_fix = False
        self._up_id = {}
        
        
    
        if auto_login:
            if (
                not session_cookies 
                or not self.setSession(session_cookies) 
                or not self.isLoggedIn()
            ):
                self.login(phone, password, imei, user_agent)
        
    def loginWithQR(self, user_agent=None, qr_path="zalo_qr.png", on_qr_generated=None):
        """Khởi tạo quá trình đăng nhập bằng mã QR.

        Tham số:
            user_agent (str, tùy chọn): User agent tùy chỉnh cho phiên đăng nhập.
            qr_path (str, tùy chọn): Đường dẫn tệp để lưu ảnh mã QR được tạo.
            on_qr_generated (callable, tùy chọn): Một hàm callback sẽ được thực thi
                                                 ngay sau khi mã QR được lưu.
                                                 Hàm này nhận 'qr_path' làm tham số duy nhất.
        Lỗi có thể xảy ra:
            ZaloLoginError: Nếu bất kỳ bước nào của quá trình đăng nhập QR thất bại.
        """
        logger.info("Bắt đầu đăng nhập bằng mã QR...")
        
        session = self._state._session
        
        _user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        self._state._headers["User-Agent"] = _user_agent

        try:
            login_version = self._qr_load_login_page(session, _user_agent)
            if not login_version:
                raise ZaloLoginError("Không thể xác định phiên bản đăng nhập Zalo.")
            logger.info(f"Đã lấy phiên bản đăng nhập: {login_version}")

            self._qr_get_login_info(session, _user_agent, login_version)
            self._qr_verify_client(session, _user_agent, login_version)

            qr_data = self._qr_generate(session, _user_agent, login_version)
            qr_code = qr_data.get("code")
            qr_image_b64 = qr_data.get("image", "").replace("data:image/png;base64,", "")

            if not (qr_code and qr_image_b64):
                raise ZaloLoginError(f"Tạo mã QR thất bại. Phản hồi: {qr_data}")

            with open(qr_path, "wb") as f:
                f.write(base64.b64decode(qr_image_b64))
            
            if on_qr_generated:
                try:
                    on_qr_generated(qr_path)
                except Exception as cb_exc:
                    logger.error(f"Lỗi khi thực thi callback 'on_qr_generated': {cb_exc}")

            scan_info = self._qr_wait_for_scan(session, _user_agent, login_version, qr_code)
            display_name = scan_info.get("display_name", "Người dùng không xác định")
            logger.info(f"Mã QR đã được quét bởi: {display_name}. Vui lòng xác nhận đăng nhập trên điện thoại của bạn.")

            confirm_result = self._qr_wait_for_confirm(session, _user_agent, login_version, qr_code)
            if confirm_result.get("error_code") == -13:
                raise ZaloLoginError("Đăng nhập đã bị từ chối trên điện thoại.")
            elif confirm_result.get("error_code") != 0:
                 raise ZaloLoginError(f"Xác nhận đăng nhập thất bại. Phản hồi: {confirm_result}")

            self._qr_check_session(session, _user_agent)
            
            user_info = self._qr_get_user_info(session, _user_agent)
            if not user_info.get("data", {}).get("logged"):
                raise ZaloLoginError("Kiểm tra phiên đăng nhập cuối cùng thất bại. Phiên không hợp lệ.")
            
            logger.login(f"Đăng nhập thành công với tư cách {user_info['data']['info']['name']}")
            
            self._finalize_login_session(session.cookies.get_dict(), _user_agent)
            
            self.onLoggedIn(self._state._config.get("phone_number"))

            return {"status": "success", "userInfo": user_info['data']['info']}

        except requests.exceptions.RequestException as e:
            raise ZaloLoginError(f"Đã xảy ra lỗi mạng trong quá trình đăng nhập QR: {e}")
        except ZaloLoginError as e:
            logger.error(f"Lỗi Đăng nhập QR: {e}")
            raise e
        except Exception as e:
            logger.error(f"Đã xảy ra lỗi không mong muốn trong quá trình đăng nhập QR: {e}")
            traceback.print_exc()
            raise ZaloLoginError(f"Đã xảy ra một lỗi không mong muốn: {e}")


    def _qr_load_login_page(self, session, user_agent):
        url = "https://id.zalo.me/account?continue=https%3A%2F%2Fchat.zalo.me%2F"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://chat.zalo.me/",
            "User-Agent": user_agent,
        }
        response = session.get(url, headers=headers)
        response.raise_for_status()
        
        html = response.text
        match = re.search(r"https:\/\/stc-zlogin\.zdn\.vn\/main-([\d.]+)\.js", html)
        return match.group(1) if match else None

    def _qr_get_login_info(self, session, user_agent, version):
        url = "https://id.zalo.me/account/logininfo"
        headers = self._get_qr_post_headers(user_agent)
        data = {"continue": "https://zalo.me/pc", "v": version}
        response = session.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()

    def _qr_verify_client(self, session, user_agent, version):
        url = "https://id.zalo.me/account/verify-client"
        headers = self._get_qr_post_headers(user_agent)
        data = {"type": "device", "continue": "https://zalo.me/pc", "v": version}
        response = session.post(url, headers=headers, data=data)
        response.raise_for_status()
        return response.json()

    def _qr_generate(self, session, user_agent, version):
        url = "https://id.zalo.me/account/authen/qr/generate"
        headers = self._get_qr_post_headers(user_agent)
        data = {"continue": "https://zalo.me/pc", "v": version}
        response = session.post(url, headers=headers, data=data)
        response.raise_for_status()
        result = response.json()
        if result.get("error_code") != 0:
            raise ZaloLoginError(f"Tạo QR thất bại: {result.get('error_message')}")
        return result.get("data")

    def _qr_wait_for_scan(self, session, user_agent, version, code, timeout=100):
        url = "https://id.zalo.me/account/authen/qr/waiting-scan"
        headers = self._get_qr_post_headers(user_agent)
        data = {"code": code, "continue": "https://chat.zalo.me/", "v": version}
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = session.post(url, headers=headers, data=data)
            response.raise_for_status()
            result = response.json()
            
            if result.get("error_code") == 0 and result.get("data"):
                return result["data"]
            elif result.get("error_code") != 8:
                raise ZaloLoginError(f"Lỗi trong khi chờ quét mã: {result.get('error_message')}")
            
            time.sleep(1)
        
        raise ZaloLoginError("Hết thời gian chờ quét mã QR.")

    def _qr_wait_for_confirm(self, session, user_agent, version, code, timeout=100):
        url = "https://id.zalo.me/account/authen/qr/waiting-confirm"
        headers = self._get_qr_post_headers(user_agent)
        data = {
            "code": code, "gToken": "", "gAction": "CONFIRM_QR", 
            "continue": "https://chat.zalo.me/", "v": version
        }
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = session.post(url, headers=headers, data=data)
            response.raise_for_status()
            result = response.json()
            
            if result.get("error_code") != 8:
                return result
            
            time.sleep(1)
        
        raise ZaloLoginError("Hết thời gian chờ xác nhận đăng nhập.")

    def _qr_check_session(self, session, user_agent):
        url = "https://id.zalo.me/account/checksession?continue=https%3A%2F%2Fchat.zalo.me%2Findex.html"
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Referer": "https://id.zalo.me/account?continue=https%3A%2F%2Fchat.zalo.me%2F",
            "User-Agent": user_agent,
        }
        response = session.get(url, headers=headers)
        response.raise_for_status()
        return response

    def _qr_get_user_info(self, session, user_agent):
        url = "https://jr.chat.zalo.me/jr/userinfo"
        headers = {
            "Accept": "*/*",
            "Referer": "https://chat.zalo.me/",
            "User-Agent": user_agent,
        }
        response = session.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def _finalize_login_session(self, session_cookies, user_agent):
        self._state.set_cookies(session_cookies)
        
        imei_uuid = str(uuid.uuid4())
        imei_hash = hashlib.md5(user_agent.encode()).hexdigest()
        imei = f"{imei_uuid}-{imei_hash}"

        self._imei = imei
        self._state.user_imei = imei

        url = f"https://wpa.chat.zalo.me/api/login/getLoginInfo?imei={imei}&type=30&client_version=650&ts={_util.now()}"
        
        response = self._state._get(url)
        response.raise_for_status()
        data = response.json()

        if data.get("error_code") == 0 and "data" in data:
            login_data = data["data"]
            self._state._config = {
                "phone_number": login_data.get("phone_number"),
                "secret_key": login_data.get("zpw_enk"),
                "send2me_id": str(login_data.get("uid")),
                "zpw_ws": login_data.get("zpw_ws"),
            }
            self.uid = self._state._config.get("send2me_id")
            self._state.user_id = self.uid
            self._state._loggedin = True
        else:
            raise ZaloLoginError(f"Không thể lấy thông tin phiên cuối cùng: {data.get('error_message')}")
            
    def _get_qr_post_headers(self, user_agent):
        return {
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://id.zalo.me/account?continue=https%3A%2F%2Fzalo.me%2Fpc",
            "User-Agent": user_agent,
        }
        
    def uid(self):
        """The ID of the client."""
        return self.uid
    
    """
    INTERNAL REQUEST METHODS
    """
    
    def _get(self, *args, **kwargs):
        return self._state._get(*args, **kwargs)
        
    def _post(self, *args, **kwargs):
        return self._state._post(*args, **kwargs)
    
    """
    END INTERNAL REQUEST METHODS
    """
    
    """
    EXTENSIONS METHODS
    """
    
    def _encode(self, params):
        return _util.zalo_encode(params, self._state._config.get("secret_key"))
        
    def _decode(self, params):
        return _util.zalo_decode(params, self._state._config.get("secret_key")) 
        
    """
    END EXTENSIONS METHODS
    """
    
    """
    LOGIN METHODS
    """
    
    def isLoggedIn(self):
        """Get data from config to check the login status.

        Returns:
            bool: True if the client is still logged in
        """
        return self._state.is_logged_in()
        
    def getSession(self):
        """Retrieve session cookies.
            
        Returns:
            dict: A dictionary containing session cookies
        """
        return self._state.get_cookies()
        
    def setSession(self, session_cookies):
        """Load session cookies.
        
        Warning:
            Error sending requests if session cookie is wrong
            
        Args:
            session_cookies (dict): A dictionary containing session cookies
            
        Returns:
            Bool: False if ``session_cookies`` does not contain proper cookies
        """
        try:
            if not isinstance(session_cookies, dict):
                return False
            # Load cookies into current session
            self._state.set_cookies(session_cookies)
            self.uid = self._state.user_id
        except Exception as e:
            print("Failed loading session")
            return False
        return True
    
    def getSecretKey(self):
        """Retrieve secret key to encode/decode payload.
            
        Returns:
            str: A secret key string with base64 encode
        """
        return self._state.get_secret_key()
        
    def setSecretKey(self, secret_key):
        """Load secret key.
        
        Warning:
            Error (enc/de)code payload if secret key is wrong
            
        Args:
            secret_key (str): A secret key string with base64 encode
            
        Returns:
            bool: False if ``secret_key`` not correct to (en/de)code the payload
        """
        try:
            self._state.set_secret_key(secret_key)
            
            return True
        except:
            return False
    
    def login(self, phone, password, imei, user_agent=None):
        """Login the user, using ``phone`` and ``password``.
            
        If the user is already logged in, this will do a re-login.
                
        Args:
            imei (str): The device imei is logged into Zalo
            phone (str): Zalo account phone number
            password (str): Zalo account password
            user_agent (str): Custom user agent to use when sending requests. If `None`, user agent will be chosen from a premade list
            
        Raises:
            ZaloLoginError: On failed login
            LoginMethodNotSupport: If method login not support
        """
        if not (phone and password):
            raise ZaloUserError("Phone and password not set")
        
        self.onLoggingIn()
        
        self._state.login(
            phone,
            password,
            imei,
            user_agent=user_agent
        )
        try:
            self._imei = self._state.user_imei
            self.uid = self.fetchAccountInfo().profile.get("userId", self._state.user_id)
        except:
            self._imei = None
            self.uid = self._state.user_id
        
        self.onLoggedIn(self._state._config.get("phone_number"))
        
    """
    END LOGIN METHODS
    """
    
    """
    ATTACHMENTS METHODS
    """

    def upload(self, filepath: str, toid: str):
        filesize = os.path.getsize(filepath)
        max_chunk = 2 * 1024 * 1024 # 2mb
        client_id = _util.now()
        filename = os.path.basename(filepath)
        chunk_id = 1
        url = "https://tt-files-wpa.chat.zalo.me/api/message/asyncfile/upload"
        with open(filepath, "rb") as f:
            while chunk := f.read(max_chunk):
                chunk_file = __import__("io").BytesIO(chunk)
                chunk_file.name = filename
                files = {"chunkContent": chunk_file}
                raw_params = {
                    "zpw_ver": 655,
                    "zpw_type": 24,
                    "params": {
                        "totalChunk": (filesize // max_chunk) + (1 if filesize % max_chunk > 0 else 0),
                        "fileName": filename,
                        "clientId": client_id,
                        "totalSize": filesize,
                        "imei": self._imei,
                        "chunkId": chunk_id,
                        "toid": toid
                    },
                    "type": 2
                }
                raw_params["params"] = self._encode(raw_params["params"])
                resp = self._post(url, params=raw_params, files=files).json()
                if resp.get("error_code") != 0:
                    raise Exception(f"Bug rồi cưng: {resp.get('error_message')}")
                upload_data = self._decode(resp["data"])
                chunk_id += 1
                data = upload_data.get("data")
                
                if data and data.get("fileId") and data.get("fileId") != "-1":
                    def cb(res):
                        if not future.done():
                            future.set_result(res)
                    self._up_id[data.get("fileId")] = cb
                    return future.result(timeout=30)
                chunk_id += 1

    def fileEvent(self, data):
        data = data.get("content", {})
        if data.get("act_type") == "file_done":
            file_id = str(data.get("fileId"))
            file_url = data.get("data", {}).get("url")
            if file_id in self._up_id:
                cb = self._up_id.pop(file_id)
                cb({"fileId": file_id, "fileUrl": file_url})
            if hasattr(self, "hkhang"):
                try:
                    self.hkhang("uploadFile", {"fileId": file_id, "fileUrl": file_url})
                except Exception:
                    pass

    def uploadFile(self, filepath: str, thread_id: str, thread_type: ThreadType, timeout: int = 30):
        """
        Upload async file (USER hoặc GROUP)
        """
        import os
        from io import BytesIO
        from concurrent.futures import Future

        if not os.path.exists(filepath):
            raise ZaloUserError(f"{filepath} not found")

        filesize = os.path.getsize(filepath)
        max_chunk = 2 * 1024 * 1024
        client_id = _util.now()
        filename = os.path.basename(filepath)

        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/asyncfile/upload"
            toid_key = "toid"
            type_val = 2
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/asyncfile/upload"
            toid_key = "grid"
            type_val = 11
        else:
            raise ZaloUserError("Thread type is invalid")

        future = Future()

        with open(filepath, "rb") as f:
            chunk_id = 1
            while chunk := f.read(max_chunk):
                chunk_file = BytesIO(chunk)
                chunk_file.name = filename
                files = [("chunkContent", chunk_file)]
                raw_params = {
                    "zpw_ver": 655,
                    "zpw_type": 24,
                    "params": {
                        "totalChunk": (filesize // max_chunk) + (1 if filesize % max_chunk > 0 else 0),
                        "fileName": filename,
                        "clientId": client_id,
                        "totalSize": filesize,
                        "imei": self._imei,
                        "chunkId": chunk_id,
                        toid_key: str(thread_id),
                        "isE2EE": 0,
                        "jxl": 0
                    },
                    "type": type_val
                }
                encoded_params = self._encode(raw_params["params"])
                raw_params["params"] = encoded_params
                response = self._post(url, params=raw_params, files=files)
                resp_json = response.json()
                if resp_json.get("error_code") != 0:
                    raise Exception(f"Upload file lỗi: {resp_json.get('error_message')}")
                upload_data = self._decode(resp_json["data"])
                data = upload_data.get("data", {})
                if data and data.get("fileId") and data.get("fileId") != "-1":
                    file_id = str(data["fileId"])
                    def cb(res):
                        if not future.done():
                            future.set_result(res)
                    self._up_id[file_id] = cb
                    return future.result(timeout=timeout)
                chunk_id += 1

        raise Exception("Upload fail: Không có fileId")

    def _uploadImage(self, filePath, thread_id, thread_type):
        """Upload images to Zalo.
            
        Args:
            filePath (str): Image path to upload
            thread_id (int | str): User/Group ID to upload to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            dict: A dictionary containing the image info just uploaded
            dict: A dictionary containing error_code, response if failed
            
        Raises:
            ZaloAPIException: If request failed
        """
        if not os.path.exists(filePath):
            raise ZaloUserError(f"{filePath} not found")
            
        files = [("chunkContent", open(filePath, "rb"))]
        fileSize = len(open(filePath, "rb").read())
        fileName = filePath if "/" not in filePath else filePath.rstrip("/")[1]
        
        params = {
            "params": {
                "totalChunk": 1,
                "fileName": fileName,
                "clientId": _util.now(),
                "totalSize": fileSize,
                "imei": self._imei,
                "isE2EE": 0,
                "jxl": 0,
                "chunkId": 1
            },
            "zpw_ver": 645,
            "zpw_type": 30,
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/photo_original/upload"
            params["type"] = 2
            params["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/photo_original/upload"
            params["type"] = 11
            params["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        params["params"] = self._encode(params["params"])
        
        response = self._post(url, params=params, files=files)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(data["data"])
            results = results.get("data") if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            return results
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    """
    END ATTACHMENTS METHODS
    """
    
    """
    FETCH METHODS
    """
    
    def fetchAccountInfo(self):
        """fetch account information of the client 
        
        Returns:
            object: `User` client info
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "params": self._encode({
                "avatar_size": 120,
                "imei": self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30,
            "os": 8,
            "browser": 0
        }
        
        response = self._get("https://tt-profile-wpa.chat.zalo.me/api/social/profile/me-v2", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def getGroupLink(self, chatID):
        if not chatID:
            raise ValueError("chatID is required")

        payload = {
            'params': {
                'grid': chatID,
                'imei': self._imei,
            }
        }
        payload['params'] = self._encode(payload['params'])

        try:
            response = self._get(
                'https://tt-group-wpa.chat.zalo.me/api/group/link/detail?zpw_ver=645&zpw_type=30',
                params=payload
            )
            data = response.json()

            if data.get("error_code") == 0:
                data = data.get("data")
            else:
                data = None

            if isinstance(data, str):
                try:
                    data = self._decode(data)
                    if isinstance(data, str):
                        data = json.loads(data)
                except json.JSONDecodeError:
                    return {'error': 'Could not decode data'}

            if isinstance(data, dict):
                return data
            else:
                return {'error': 'Invalid response format'}

        except ZaloAPIException as e:
            return {'error': str(e)}
        except Exception as e:
            return {'error': f'An unexpected error occurred: {str(e)}'}
                
    def fetchPhoneNumber(self, phoneNumber, language="vi"):
        """Fetch user info by Phone Number.
        
        Not available with hidden phone numbers
        
        Args:
            phoneNumber (int | str): Phone number to fetch information
            language (str): Language for response (not sure | Default: vi)
        
        Returns:
            object: `User` user(s) info
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        
        phone = "84" + str(phoneNumber) if str(phoneNumber)[:1] != "0" else "84" + str(phoneNumber)[1:]
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "params": self._encode({
                "phone": phone,
                "avatar_size": 240,
                "language": language,
                "imei": self._imei,
                "reqSrc": 85
            })
        }
        
        response = self._get("https://tt-friend-wpa.chat.zalo.me/api/friend/profile/get", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def getQrUser(self, userId):
        params = {
            "zpw_ver": 650,
            "zpw_type": 30
        }

        payload = {
            "params": self._encode({
                "fids": [str(userId)]
            })
        }

        response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/mget-qr", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}

            return User.fromDict(results, None)

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def fetchUserInfo(self, userId):
        """Fetch user info by ID.
        
        Args:
            userId (int | str | list): User(s) ID to get info
        
        Returns:
            object: `User` user(s) info
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 641,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "phonebook_version": int(_util.now() / 1000),
                "friend_pversion_map": [],
                "avatar_size": 120,
                "language": "vi",
                "show_online_status": 1,
                "imei": self._imei
            }
        }
        
        if isinstance(userId, list):
            for i in range(len(userId)):
                userId[i] = str(userId[i]) + "_0"
            payload["params"]["friend_pversion_map"] = userId
            
        else:
            payload["params"]["friend_pversion_map"].append(str(userId) + "_0")
            
        payload["params"] = self._encode(payload["params"])
        
        response = self._post("https://tt-profile-wpa.chat.zalo.me/api/social/friend/getprofiles/v2", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def sendBankCard(self, thread_id, thread_type, bin_bank, account_number, account_name, ttl=0):
        """Send bank card information to a conversation.
        
        Args:
            thread_id (int | str): The User/Group ID to send the bank card to.
            thread_type (ThreadType): The type of thread (ThreadType.USER or ThreadType.GROUP).
            bin_bank (int | str): The bank BIN code.
            account_number (str): The bank account number.
            account_name (str): The account holder's name.
            ttl (int): Time to live for the message (default: 0).
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
            
        Raises:
            ZaloAPIException: If the API request fails.
            ZaloUserError: If required parameters are missing or thread type is invalid.
        """
        
        if not bin_bank:
            raise ZaloUserError("Missing bin_bank")
        if not account_number:
            raise ZaloUserError("Missing account_number")
        if not account_name:
            raise ZaloUserError("Missing account_name")
        
        url = "https://zimsg.chat.zalo.me/api/transfer/card"
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        client_id = _util.now() * 60
        ts_msg = _util.now()
        
        if thread_type == ThreadType.USER:
            dest_type = 0
        elif thread_type == ThreadType.GROUP:
            dest_type = 1
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload = {
            "params": {
                "binBank": int(bin_bank),
                "numAccBank": str(account_number),
                "nameAccBank": str(account_name),
                "cliMsgId": str(client_id),
                "tsMsg": ts_msg,
                "destUid": str(thread_id),
                "destType": dest_type,
                "imei": self._imei,
                "ttl": ttl
            }
        }
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
        
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending bank card: {error_message}")

    def callGroupRequest(self, groupId, userId, callId):
        params = {
            "zpw_ver": 667,
            "zpw_type": 24
        }

        payload = {
            "params": self._encode({
                "groupId": str(groupId),
                "callId": callId,
                "typeRequest": 1,
                "data": json.dumps({
                    "extraData": "",
                    "groupAvatar": "",
                    "groupId": str(groupId),
                    "groupName": "Xuan Bach Cte",
                    "maxUsers": 8,
                    "noiseId": [userId]
                }),
                "partners": [userId]
            })
        }

        response = self._post(
            "https://voicecall-wpa.chat.zalo.me/api/voicecall/group/requestcall",
            params=params, data=payload
        )
        try:
            data = response.json()
        except json.JSONDecodeError:
            raise ZaloAPIException("Invalid JSON response from server.")

        if data.get("error_code") != 0:
            raise ZaloAPIException(
                f"Error #{data.get('error_code')} when sending call request: {data.get('error_message', 'Unknown error')}"
            )

        results = data.get("data")
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    raise ZaloAPIException("Invalid results string.")
            return results

        raise ZaloAPIException(
            f"Error #{data.get('error_code')} when sending requests: {data.get('error_message')}"
        )
    def callGroup(self, groupId, userId, callId=None):
        if not callId:
            callId = int(time.time())

        params = {
            "zpw_ver": 667,
            "zpw_type": 24
        }
        request_data = self.callGroupRequest(groupId, userId, callId)

        try:
            params_data = json.loads(request_data.get("params", "{}"))
        except Exception:
            params_data = {}

        call_setting = params_data.get("callSetting", {})
        servers = call_setting.get("servers", [])
        session = call_setting.get("session", "")
        rtpaddr, rtcpaddr, rtpaddrIPv6, rtcpaddrIPv6 = "", "", "", ""
        partner_ids = request_data.get("partnerIds", [])
        idcal = partner_ids[0] if isinstance(partner_ids, list) and partner_ids else None
        if servers:
            srv = servers[0]
            rtpaddr = srv.get("rtpaddr", "")
            rtcpaddr = srv.get("rtcpaddr", "")
            rtpaddrIPv6 = srv.get("rtpaddrIPv6", "")
            rtcpaddrIPv6 = srv.get("rtcpaddrIPv6", "")

        inner_data = f'\n{{\n\t"groupAvatar" : "",\n\t"groupName" : "Xuan Bach Cte",\n\t"hostCall" : {params_data.get("hostCall")},\n\t"maxUsers" : {params_data.get("maxUsers",8)},\n\t"noiseId" : ["{idcal}"]\n}}\n'

        outer_data = f'\n{{\n\t"codec" : "",\n\t"data" : "{inner_data.replace("\\", "\\\\").replace("\"", "\\\"")}",\n\t"extendData" : "",\n\t"rtcpAddress" : "{rtcpaddr}",\n\t"rtcpAddressIPv6" : "{rtcpaddrIPv6}",\n\t"rtpAddress" : "{rtpaddr}",\n\t"rtpAddressIPv6" : "{rtpaddrIPv6}"\n}}\n'

        payload = {
            "params": self._encode({
                "callId": params_data.get("callId", callId),
                "callType": 1,
                "data": outer_data,
                "session": session,
                "partners": f'[ "{idcal}" ]\n',
                "groupId": str(groupId)
            })
        }

        response = self._post(
            "https://voicecall-wpa.chat.zalo.me/api/voicecall/group/request",
            params=params, data=payload
        )

        try:
            data = response.json()
        except json.JSONDecodeError:
            raise ZaloAPIException("Invalid JSON response from server.")

        if data.get("error_code") != 0:
            raise ZaloAPIException(
                f"Error #{data.get('error_code')} when sending call: {data.get('error_message', 'Unknown error')}"
            )

        results = data.get("data")
        if results:
            results = self._decode(results)
            return results

        raise ZaloAPIException("Empty response data in callGroup.")

    def setMute(self, thread_id, thread_type, duration=-1, is_mute=True):
        """Mute/Unmute a conversation thread.
        
        Args:
            thread_id (int | str): The User/Group ID to mute/unmute.
            thread_type (ThreadType): The type of thread (ThreadType.USER or ThreadType.GROUP).
            duration (int or str): The duration in seconds to mute for.
                - Use -1 for "Forever".
                - Use "until8am" to mute until 8 AM the next day.
                - Any other integer for a specific duration in seconds.
                This parameter is ignored when `is_mute` is False.
            is_mute (bool): True to mute the thread, False to unmute it.
            
        Returns:
            dict: A dictionary containing the API response on success.
            
        Raises:
            ZaloAPIException: If the API request fails.
            ZaloUserError: If the duration format is invalid.
        """
        
        url = "https://tt-profile-wpa.chat.zalo.me/api/social/profile/setmute"
        
        params = {
            "zpw_ver": 677,
            "zpw_type": 30
        }

        action = 1 if is_mute else 3
        mute_duration = -1

        if is_mute:
            if isinstance(duration, str) and duration.lower() == "until8am":
                now = datetime.now()
                next_8am = now.replace(hour=8, minute=0, second=0, microsecond=0)
                if now >= next_8am:
                    next_8am += timedelta(days=1)
                mute_duration = int((next_8am - now).total_seconds())
            else:
                try:
                    mute_duration = int(duration)
                except (ValueError, TypeError):
                    raise ZaloUserError("Invalid duration format. Must be an integer or 'until8am'.")
        
        params_to_encode = {
            "toid": str(thread_id),
            "duration": mute_duration,
            "action": action,
            "startTime": int(time.time()),
            "muteType": 1 if thread_type == ThreadType.USER else 2,
            "imei": self._imei,
        }

        payload = {
            "params": self._encode(params_to_encode)
        }
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None

        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results is None:
                return {"status": "success", "message": "Mute status updated successfully."}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except json.JSONDecodeError:
                    results = {"status": "success", "raw_data": results}
            
            return results
        
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when setting mute status: {error_message}")

    def upgradeCommunity(self, groupId, language="vi"):
        """Upgrade group to community.

        Args:
            groupId (int | str): Group ID to upgrade
            language (str): Language code (default: vi)

        Returns:
            dict: Upgrade result data if success

        Raises:
            ZaloAPIException: If request failed
        """

        params = {
            "zpw_ver": 674,
            "zpw_type": 30
        }

        payload = {
            "params": {
                "grId": str(groupId),
                "language": language
            }
        }

        payload["params"] = self._encode(payload["params"])

        response = self._post(
            "https://tt-group-wpa.chat.zalo.me/api/group/upgrade/community",
            params=params,
            data=payload
        )

        data = response.json()

        if data.get("error_code") != 0:
            error_code = data.get("error_code")
            error_message = data.get("error_message") or data.get("data")
            raise ZaloAPIException(
                f"Error #{error_code} when sending requests: {error_message}"
            )

        results = data.get("data")
        if results is None:
            raise ZaloAPIException(
                "Error #1337 when sending requests: Data is None"
            )

        results = self._decode(results)

        if isinstance(results, dict) and results.get("error_code", 0) != 0:
            return results

        if isinstance(results, str):
            try:
                results = json.loads(results)
            except:
                return {
                    "error_code": 1337,
                    "error_message": results
                }

        return results

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def sendCustomStickerAI(
        self,
        staticImgUrl,
        animationImgUrl,
        thread_id,
        thread_type,
        pStickerType,
        reply=None,
        width=None,
        height=None,
        ttl=0
    ):
        width = int(width) if width else 498
        height = int(height) if height else 332

        params = {
            "zpw_ver": 641,
            "zpw_type": 30,
            "nretry": 0
        }

        payload = {
            "params": {
                "clientId": _util.now() * 6000,
                "title": "",
                "oriUrl": staticImgUrl,
                "thumbUrl": staticImgUrl,
                "hdUrl": staticImgUrl,
                "width": width,
                "height": height,

                "properties": json.dumps({
                    "subType": 0,
                    "color": -1,
                    "size": -1,
                    "type": 3,  
                    "is_original": 0,
                    "ext": json.dumps({
                        "sSrcStr": "@LyHoangKhang",
                        "sSrcType": 0
                    })
                }),

                "contentId": _util.now(),
                "thumb_width": width,
                "thumb_height": height,

                "webp": json.dumps({
                    "width": width,
                    "height": height,
                    "url": animationImgUrl
                }),

                "msgBubbleLayoutType": 3,
                "is_group_layout": 0,
                "zsource": -1,
                "jcp": json.dumps({
                      "pStickerType": pStickerType
                  }),
                "ttl": ttl
            }
        }

        if reply:
            payload["params"]["refMessage"] = str(reply)

        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/photo_url"
            payload["params"]["toId"] = str(thread_id)

        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/photo_url"
            payload["params"]["grid"] = str(thread_id)
            payload["params"]["visibility"] = 0

        else:
            raise ZaloUserError("Thread type is invalid")

        payload["params"] = self._encode(payload["params"])

        response = self._post(url, params=params, data=payload)
        data = response.json()

        if data.get("error_code") == 0:
            results = self._decode(data.get("data"))
            results = results.get("data") if isinstance(results, dict) else results

            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    pass

            return (
                Group.fromDict(results, None)
                if thread_type == ThreadType.GROUP
                else User.fromDict(results, None)
            )

        raise ZaloAPIException(
            f"Error #{data.get('error_code')} when sending sticker: {data.get('error_message') or data.get('data')}"
        )
    
    def fetchGroupInfo(self, groupId):
        """Fetch group info by ID.
        
        Args:
            groupId (int | str | dict): Group(s) ID to get info
        
        Returns:
            object: `Group` group info
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "gridVerMap": {}
            }
        }
        
        if isinstance(groupId, dict):
            for i in groupId:
                payload["params"]["gridVerMap"][str(i)] = 0
        else:
            payload["params"]["gridVerMap"][str(groupId)] = 0
            
        payload["params"]["gridVerMap"] = json.dumps(payload["params"]["gridVerMap"])
        payload["params"] = self._encode(payload["params"])
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/getmg-v2", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
        
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def fetchAllFriends(self):
        """Fetch all users the client is currently chatting with (only friends).
        
        Returns:
            object: `User` all friend IDs
            any: If response is not list friends
            
        Raises:
            ZaloAPIException: If request failed
        """
        
        params = {
            "params": self._encode({
                "incInvalid": 0,
                "page": 1,
                "count": 20000,
                "avatar_size": 120,
                "actiontime": 0
            }),
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        response = self._get("https://profile-wpa.chat.zalo.me/api/social/friend/getfriends", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            datas = []
            if results.get("data"):
                for data in results.get("data"):
                    datas.append(User(**data))
            
            return datas
                    
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
        
    def fetchAllGroups(self):
        """Fetch all group IDs are joining and chatting.
        
        Returns:
            object: `Group` all group IDs
            any: If response is not all group IDs
        
        Raises:
            ZaloAPIException: If request failed
        """
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/getlg/v4", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
        
    """
    END FETCH METHODS
    """
    
    """
    GET METHODS
    """
    
    def getLastMsgs(self):
        """Get last message the client's friends/group chat room.
            
        Returns:
            object: `User` last msg data
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": "645",
            "zpw_type": "30",
            "params": self._encode({
                "threadIdLocalMsgId": json.dumps({}),
                "imei": self._imei
            })
        }
        
        response = self._get("https://tt-convers-wpa.chat.zalo.me/api/preloadconvers/get-last-msgs", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def getRecentGroup(self, groupId):
        """Get recent messages in group by ID.
            
        Args:
            groupId (int | str): Group ID to get recent msgs
            
        Returns:
            object: `Group` List msg data in groupMsgs
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "params": self._encode({
                "groupId": str(groupId),
                "globalMsgId": 110560011931056001193,
                "count": 50,
                "msgIds": [],
                "imei": self._imei,
                "src": 1
            }),
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0,
        }
        
        response = self._get("https://tt-group-cm.chat.zalo.me/api/cm/getrecentv2", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = json.loads(results.get("data")) if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def _getGroupBoardList(self, board_type, page, count, last_id, last_type, groupId):
        params = {
            "params": self._encode({
                "group_id": str(groupId),
                "board_type": board_type,
                "page": page,
                "count": count,
                "last_id": last_id,
                "last_type": last_type,
                "imei": self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://groupboard-wpa.chat.zalo.me/api/board/list", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = Group.fromDict(results.get("data"), None)
            
            return results
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def getGroupBoardList(self, groupId, page=1, count=20, last_id=0, last_type=0):
        """Get group board list (pinmsg, note, poll) by ID.
            
        Args:
            groupId (int | str): Group ID to get board list
            page (int): Number of pages to retrieve data from
            count (int): Amount of data to retrieve per page (5 poll, ..)
            last_id (int): Default (no description)
            last_type (int): Default (no description)
            
        Returns:
            object: `Group` board data in group
            dict: A dictionary containing error_code, response if failed
            
        Raises:
            ZaloAPIException: If request failed
        """
        response = self._getGroupBoardList(0, page, count, last_id, last_type, groupId)
        
        return response
    
    def getGroupPinMsg(self, groupId, page=1, count=20, last_id=0, last_type=0):
        """Get group pinned messages by ID.
            
        Args:
            groupId (int | str): Group ID to get pinned messages
            page (int): Number of pages to retrieve data from
            count (int): Amount of data to retrieve per page (5 message, ..)
            last_id (int): Default (no description)
            last_type (int): Default (no description)
            
        Returns:
            object: `Group` pinned messages in group
            dict: A dictionary containing error_code, response if failed
            
        Raises:
            ZaloAPIException: If request failed
        """
        response = self._getGroupBoardList(2, page, count, last_id, last_type, groupId)
        
        return response
    
    def getGroupNote(self, groupId, page=1, count=20, last_id=0, last_type=0):
        """Get group notes by ID.
            
        Args:
            groupId (int | str): Group ID to get notes
            page (int): Number of pages to retrieve data from
            count (int): Amount of data to retrieve per page (5 notes, ..)
            last_id (int): Default (no description)
            last_type (int): Default (no description)
            
        Returns:
            object: `Group` notes in group
            dict: A dictionary containing error_code, response if failed
            
        Raises:
            ZaloAPIException: If request failed
        """
        response = self._getGroupBoardList(1, page, count, last_id, last_type, groupId)
        
        return response
    
    def getGroupPoll(self, groupId, page=1, count=20, last_id=0, last_type=0):
        """Get group polls by ID.
            
        Args:
            groupId (int | str): Group ID to get polls
            page (int): Number of pages to retrieve data from
            count (int): Amount of data to retrieve per page (5 poll, ..)
            last_id (int): Default (no description)
            last_type (int): Default (no description)
            
        Returns:
            object: `Group` polls in group
            dict: A dictionary containing error_code, response if failed
            
        Raises:
            ZaloAPIException: If request failed
        """
        response = self._getGroupBoardList(3, page, count, last_id, last_type, groupId)
        
        return response
    
    """
    END GET METHODS
    """
    
    """
    ACCOUNT ACTION METHODS
    """
    
    def changeAccountSetting(self, name, dob, gender, biz={}, language="vi"):
        """Change account information.
        
        Args:
            name (str): The new account name
            dob (str): Date of birth wants to change (format: year-month-day)
            gender (int | str): Gender wants to change (0 = Male, 1 = Female)
            biz (unknown): idk this
            language (str): Zalo language wants to change (default = vn)
        
        Returns:
            object: `User` change account setting status
            dict: A dictionary containing error_code, response if failed
            
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "profile": json.dumps({
                    "name": name,
                    "dob": dob,
                    "gender": int(gender)
                }),
                "biz": json.dumps(biz),
                "language": language
            })
        }
        
        response = self._post("https://tt-profile-wpa.chat.zalo.me/api/social/profile/update", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def changeAccountAvatar(self, filePath, width=500, height=500, language="vn", size=None):
        """Upload/Change account avatar.
        
        Args:
            filePath (str): A path to the image to upload/change avatar
            size (int): Avatar image size (default = auto)
            width (int): Width of avatar image
            height (int): height of avatar image
            language (int | str): Zalo Website language ? (idk)
            
        Returns:
            object: `User` Account avatar change status
            None: If requet success/failed depending on the case
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if not os.path.exists(filePath):
            raise ZaloUserError(f"{filePath} not found")
        
        size = os.stat(filePath).st_size if not size else size
        files = [("fileContent", open(filePath, "rb"))]
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "params": self._encode({
                "avatarSize": 120,
                "clientId": str(self.uid) + _util.formatTime("%H:%M %d/%m/%Y"),
                "language": language,
                "metaData": json.dumps({
                    "origin": {
                        "width": width,
                        "height": height
                    },
                    "processed": {
                        "width": width,
                        "height": height,
                        "size": size
                    }
                })
            })
        }
        
        response = self._post("https://tt-files-wpa.chat.zalo.me/api/profile/upavatar", params=params, files=files)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    """
    END ACCOUNT ACTION METHODS
    """
    
    """
    USER ACTION METHODS
    """
    
    def sendFriendRequest(self, userId, msg, language="vi"):
        """Send friend request to a user by ID.
            
        Args:
            userId (int | str): User ID to send friend request
            msg (str): Friend request message
            language (str): Response language or Zalo interface language

        Returns:
            object: `User` Friend requet response
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "toid": str(userId),
                "msg": msg,
                "reqsrc": 30,
                "imei": self._imei,
                "language": language,
                "srcParams": json.dumps({
                    "uidTo": str(userId)
                })
            })
        }
        
        response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/sendreq", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def acceptFriendRequest(self, userId, language="vi"):
        """Accept friend request from user by ID.
            
        Args:
            userId (int | str): User ID to accept friend request
            language (str): Response language or Zalo interface language

        Returns:
            object: `User` Friend accept requet response
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "fid": str(userId),
                "language": language
            })
        }
        
        response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/accept", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def blockViewFeed(self, userId, isBlockFeed):
        """Block/Unblock friend view feed by ID.
            
        Args:
            userId (int | str): User ID to block/unblock view feed
            isBlockFeed (int): Block/Unblock friend view feed (1 = True | 0 = False)
        
        Returns:
            object: `User` Friend requet response
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "fid": str(userId),
                "isBlockFeed": isBlockFeed,
                "imei": self._imei
            })
        }
        
        response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/feed/block", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def blockUser(self, userId):
        """Block user by ID.
            
        Args:
            userId (int | str): User ID to block
        
        Returns:
            object: `User` Block response
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "fid": str(userId),
                "imei": self._imei
            })
        }
        
        response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/block", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def unblockUser(self, userId):
        """Unblock user by ID.
            
        Args:
            userId (int | str): User ID to unblock
        
        Returns:
            object: `User` Unblock response
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "fid": str(userId),
                "imei": self._imei
            })
        }
        
        response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/unblock", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return User.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    """
    END USER ACTION METHODS
    """
    
    """
    GROUP ACTION METHODS
    """
    
    def createGroup(self, name=None, description=None, members=[], nameChanged=1, createLink=1):
        """Create a new group.
            
        Args:
            name (str): The new group name
            description (str): Description of the new group
            members (str | list): List/String member IDs add to new group
            nameChanged (int - auto): Will use default name if disabled (0), else (1)
            createLink (int - default): Create a group link? Default = 1 (True)
            
        Returns:
            object: `Group` new group response
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        memberTypes = []
        nameChanged = 1 if name else 0
        name = name or "Default Group Name"
        
        if members and isinstance(members, list):
            members = [str(member) for member in members]
        else:
            members = [str(members)]
            
        if members:
            for i in members:
                memberTypes.append(-1)
            
        params = {
            "params": self._encode({
                "clientId": _util.now(),
                "gname": name,
                "gdesc": description,
                "members": members,
                "memberTypes": memberTypes,
                "nameChanged": nameChanged,
                "createLink": createLink,
                "clientLang": "vi",
                "imei": self._imei,
                "zsource": 601
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/create/v2", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return results
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def changeGroupAvatar(self, filePath, groupId):
        """Upload/Change group avatar by ID.
        
        Client must be the Owner of the group
        (If the group does not allow members to upload/change)
            
        Args:
            filePath (str): A path to the image to upload/change avatar
            groupId (int | str): Group ID to upload/change avatar
            
        Returns:
            object: `Group` Group avatar change status
            None: If requet success/failed depending on the case
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if not os.path.exists(filePath):
            raise ZaloUserError(f"{filePath} not found")
            
            
        files = [("fileContent", open(filePath, "rb"))]
        
        params = {
            "params": self._encode({
                "grid": str(groupId),
                "avatarSize": 120,
                "clientId": "g" + str(groupId) + _util.formatTime("%H:%M %d/%m/%Y"),
                "originWidth": 640,
                "originHeight": 640,
                "imei": self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._post("https://tt-files-wpa.chat.zalo.me/api/group/upavatar", params=params, files=files)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def changeGroupName(self, groupName, groupId):
        """Set/Change group name by ID.
        
        Client must be the Owner of the group
        (If the group does not allow members to change group name)
            
        Args:
            groupName (str): Group name to change
            groupId (int | str): Group ID to change name
            
        Returns:
            object: `Group` Group name change status
            None: If requet success/failed depending on the case
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "gname": groupName,
                "grid": str(groupId)
            })
        }
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/updateinfo", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def changeGroupDesc(self, groupDesc, groupId):
        """Not Available Yet"""
    
    def changeGroupSetting(self, groupId, defaultMode="default", **kwargs):
        """Update group settings by ID.
        
        Client must be the Owner/Admin of the group.
        
        Warning:
            Other settings will default value if not set. See `defaultMode`
        
        Args:
            groupId (int | str): Group ID to update settings
            defaultMode (str): Default mode of settings
            
                default: Group default settings
                anti-raid: Group default settings for anti-raid
            
            **kwargs: Group settings kwargs, Value: (1 = True, 0 = False)
            
                blockName: Không cho phép user đổi tên & ảnh đại diện nhóm
                signAdminMsg: Đánh dấu tin nhắn từ chủ/phó nhóm
                addMemberOnly: Chỉ thêm members (Khi tắt link tham gia nhóm)
                setTopicOnly: Cho phép members ghim (tin nhắn, ghi chú, bình chọn)
                enableMsgHistory: Cho phép new members đọc tin nhắn gần nhất
                lockCreatePost: Không cho phép members tạo ghi chú, nhắc hẹn
                lockCreatePoll: Không cho phép members tạo bình chọn
                joinAppr: Chế độ phê duyệt thành viên
                bannFeature: Default (No description)
                dirtyMedia: Default (No description)
                banDuration: Default (No description)
                lockSendMsg: Không cho phép members gửi tin nhắn
                lockViewMember: Không cho phép members xem thành viên nhóm
                blocked_members: Danh sách members bị chặn
        
        Returns:
            object: `Group` Group settings change status
            None: If requet success/failed depending on the case
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if defaultMode == "anti-raid":
            defSetting = {
                "blockName": 1,
                "signAdminMsg": 1,
                "addMemberOnly": 0,
                "setTopicOnly": 1,
                "enableMsgHistory": 1,
                "lockCreatePost": 1,
                "lockCreatePoll": 1,
                "joinAppr": 1,
                "bannFeature": 0,
                "dirtyMedia": 0,
                "banDuration": 0,
                "lockSendMsg": 0,
                "lockViewMember": 0,
            }
        else:
            defSetting = self.fetchGroupInfo(groupId).gridInfoMap
            defSetting = defSetting[str(groupId)]["setting"]
            
        blockName = kwargs.get("blockName", defSetting.get("blockName", 1))
        signAdminMsg = kwargs.get("signAdminMsg", defSetting.get("signAdminMsg", 1))
        addMemberOnly = kwargs.get("addMemberOnly", defSetting.get("addMemberOnly", 0))
        setTopicOnly = kwargs.get("setTopicOnly", defSetting.get("setTopicOnly", 1))
        enableMsgHistory = kwargs.get("enableMsgHistory", defSetting.get("enableMsgHistory", 1))
        lockCreatePost = kwargs.get("lockCreatePost", defSetting.get("lockCreatePost", 1))
        lockCreatePoll = kwargs.get("lockCreatePoll", defSetting.get("lockCreatePoll", 1))
        joinAppr = kwargs.get("joinAppr", defSetting.get("joinAppr", 1))
        bannFeature = kwargs.get("bannFeature", defSetting.get("bannFeature", 0))
        dirtyMedia = kwargs.get("dirtyMedia", defSetting.get("dirtyMedia", 0))
        banDuration = kwargs.get("banDuration", defSetting.get("banDuration", 0))
        lockSendMsg = kwargs.get("lockSendMsg", defSetting.get("lockSendMsg", 0))
        lockViewMember = kwargs.get("lockViewMember", defSetting.get("lockViewMember", 0))
        blocked_members = kwargs.get("blocked_members", [])
        
        params = {
            "params": self._encode({
                "blockName": blockName,
                "signAdminMsg": signAdminMsg,
                "addMemberOnly": addMemberOnly,
                "setTopicOnly": setTopicOnly,
                "enableMsgHistory": enableMsgHistory,
                "lockCreatePost": lockCreatePost,
                "lockCreatePoll": lockCreatePoll,
                "joinAppr": joinAppr,
                "bannFeature": bannFeature,
                "dirtyMedia": dirtyMedia,
                "banDuration": banDuration,
                "lockSendMsg": lockSendMsg,
                "lockViewMember": lockViewMember,
                "blocked_members": blocked_members,
                "grid": str(groupId),
                "imei":self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/setting/update", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def changeGroupOwner(self, newAdminId, groupId):
        """Change group owner (yellow key) by ID.
        
        Client must be the Owner of the group.
            
        Args:
            newAdminId (int | str): members ID to changer owner
            groupId (int | str): ID of the group to changer owner
            
        Returns:
            object: `Group` Group owner change status
            None: If requet success/failed depending on the case
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "params": self._encode({
                "grid": str(groupId),
                "newAdminId": str(newAdminId),
                "imei": self._imei,
                "language": "vi"
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/change-owner", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def addUsersToGroup(self, user_ids, groupId):
        """Add friends/users to a group.
            
        Args:
            user_ids (str | list): One or more friend/user IDs to add
            groupId (int | str): Group ID to add friend/user to
        
        Returns:
            object: `Group` add friend/user data
            dict: A dictionary containing error_code, response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        memberTypes = []
        
        if user_ids and isinstance(user_ids, list):
            members = [str(user) for user in user_ids]
        else:
            members = [str(user_ids)]
            
        if members:
            for i in members:
                memberTypes.append(-1)
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "grid": str(groupId),
                "members": members,
                "memberTypes": memberTypes,
                "imei": self._imei,
                "clientLang": "vi"
            })
        }
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/invite/v2", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def kickUsersInGroup(self, members, groupId):
        """Kickout members in group by ID.
        
        Client must be the Owner of the group.
        
        Args:
            members (str | list): One or More member IDs to kickout
            groupId (int | str): Group ID to kick member from
            
        Returns:
            object: `Group` kick data
            dict: A dictionary/object containing error responses
            
        Raises:
            ZaloAPIException: If request failed
        """
        if isinstance(members, list):
            members = [str(member) for member in members]
        else:
            members = [str(members)]
            
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "grid": str(groupId),
                "members": members
            })
        }
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/kickout", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def blockUsersInGroup(self, members, groupId):
        """Blocked members in group by ID.
        
        Client must be the Owner of the group.
        
        Args:
            members (str | list): One or More member IDs to block
            groupId (int | str): Group ID to block member from
            
        Returns:
            object: `Group` block members response
            dict: A dictionary/object containing error responses
            
        Raises:
            ZaloAPIException: If request failed
        """
        if isinstance(members, list):
            members = [str(member) for member in members]
        else:
            members = [str(members)]
            
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "params": self._encode({
                "grid": str(groupId),
                "members": members
            })
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/blockedmems/add", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def unblockUsersInGroup(self, members, groupId):
        """unblock members in group by ID.
        
        Client must be the Owner of the group.
        
        Args:
            members (str | list): One or More member IDs to unblock
            groupId (int | str): Group ID to unblock member from
            
        Returns:
            object: `Group` unblock members response
            dict: A dictionary/object containing error responses
            
        Raises:
            ZaloAPIException: If request failed
        """
        if isinstance(members, list):
            members = [str(member) for member in members]
        else:
            members = [str(members)]
            
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "params": self._encode({
                "grid": str(groupId),
                "members": members
            })
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/blockedmems/remove", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def addGroupAdmins(self, members, groupId):
        """Add admins to the group (white key).
        
        Client must be the Owner of the group.
            
        Args:
            members (str | list): One or More member IDs to add
            groupId (int | str): Group ID to add admins
            
        Returns:
            object: `Group` Group admins add status
            None: If requet success/failed depending on the case
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if isinstance(members, list):
            members = [str(member) for member in members]
        else:
            members = [str(members)]
            
        params = {
            "params": self._encode({
                "grid": str(groupId),
                "members": members,
                "imei": self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/admins/add", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
        
    def removeGroupAdmins(self, members, groupId):
        """Remove admins in the group (white key) by ID.
        
        Client must be the Owner of the group.
            
        Args:
            members (str | list): One or More admin IDs to remove
            groupId (int | str): Group ID to remove admins
            
        Returns:
            object: `Group` Group admins remove status
            None: If requet success/failed depending on the case
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if isinstance(members, list):
            members = [str(member) for member in members]
        else:
            members = [str(members)]
            
        params = {
            "params": self._encode({
                "grid": str(groupId),
                "members": members,
                "imei": self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/admins/remove", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def pinGroupMsg(self, pinMsg, groupId):
        """Pin message in group by ID.
        
        Args:
            pinMsg (Message): Message Object to pin
            groupId (int | str): Group ID to pin message
        
        Returns:
            object: `Group` pin message status
            dict: A dictionary containing error_code & responses if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "grid": str(groupId),
                "type": 2,
                "color": -14540254,
                "emoji": "📌",
                "startTime": -1,
                "duration": -1,
                "repeat": 0,
                "src": -1,
                "imei": self._imei,
                "pinAct": 1
            }
        }
        
        if pinMsg.msgType == "webchat":
            
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "title": pinMsg.content,
                "msg_type": _util.getClientMessageType(pinMsg.msgType)
            })
        
        elif pinMsg.msgType == "chat.voice":
            
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "msg_type": _util.getClientMessageType(pinMsg.msgType)
            })
        
        elif pinMsg.msgType in ["chat.photo", "chat.video.msg"]:
            
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "thumb": pinMsg.content.thumb,
                "title": pinMsg.content.description,
                "msg_type": _util.getClientMessageType(pinMsg.msgType)
            })
        
        elif pinMsg.msgType == "chat.sticker":
            
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "extra": json.dumps({
                    "id": pinMsg.content.id,
                    "catId": pinMsg.content.catId,
                    "type": pinMsg.content.type
                }),
                "msg_type": _util.getClientMessageType(pinMsg.msgType)
            })
        
        elif pinMsg.msgType in ["chat.recommended", "chat.link"]:
            
            extra = json.loads(pinMsg.content.params)
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "href": pinMsg.content.href,
                "thumb": pinMsg.content.thumb or "",
                "title": pinMsg.content.title,
                "linkCaption": "https://vrxx1337.vercel.app",
                "redirect_url": extra.get("redirect_url", ""),
                "streamUrl": extra.get("streamUrl", ""),
                "artist": extra.get("artist", ""),
                "stream_icon": extra.get("stream_icon", ""),
                "type": 2,
                "extra": json.dumps({
                    "action": pinMsg.content.action,
                    "params": json.dumps({
                        "mediaTitle": extra.get("mediaTitle", ""),
                        "artist": extra.get("artist", ""),
                        "src": extra.get("src", ""),
                        "stream_icon": extra.get("stream_icon", ""),
                        "streamUrl": extra.get("streamUrl", ""),
                        "type": 2
                    })
                }),
                "msg_type": _util.getClientMessageType(pinMsg.msgType)
            })
        
        elif pinMsg.msgType == "chat.location.new":
            
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "msg_type": _util.getClientMessageType(pinMsg.msgType),
                "title": pinMsg.content.title or pinMsg.content.description
            })
        
        elif pinMsg.msgType == "share.file":
            
            extra = json.loads(pinMsg.content.params)
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "title": pinMsg.content.title,
                "extra": json.dumps({
                    "fileSize": "7295",
                    "checksum": extra.get("checksum", ""),
                    "fileExt": extra.get("fileExt", ""),
                    "tWidth": extra.get("tWidth", 0),
                    "tHeight": extra.get("tHeight", 0),
                    "duration": extra.get("duration", 0),
                    "fType": extra.get("fType", 0),
                    "fdata": extra.get("fdata", ""),
                }),
                "msg_type": _util.getClientMessageType(pinMsg.msgType)
            })
        
        elif pinMsg.msgType == "chat.gif":
            
            payload["params"]["params"] = json.dumps({
                "client_msg_id": pinMsg.cliMsgId,
                "global_msg_id": pinMsg.msgId,
                "senderUid": str(int(pinMsg.uidFrom) or self.uid),
                "senderName": pinMsg.dName,
                "thumb": pinMsg.content.thumb,
                "msg_type": _util.getClientMessageType(pinMsg.msgType)
            })
        
        payload["params"] = self._encode(payload["params"])
        response = self._post("https://groupboard-wpa.chat.zalo.me/api/board/topic/createv2", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def unpinGroupMsg(self, pinId, pinTime, groupId):
        """Unpin message in group by ID.
        
        Args:
            pinId (int | str): Pin ID to unpin
            pinTime (int): Pin start time
            groupId (int | str): Group ID to unpin message
        
        Returns:
            object: `Group` unpin message status
            dict: A dictionary containing error_code & responses if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "params": self._encode({
                "grid": str(groupId),
                "imei": self._imei,
                "topic": {
                    "topicId": str(pinId),
                    "topicType": 2
                },
                "boardVersion": int(pinTime)
            })
        }
        
        response = self._get("https://groupboard-wpa.chat.zalo.me/api/board/unpinv2", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def deleteGroupMsg(self, msgId, ownerId, clientMsgId, groupId):
        """Delete message in group by ID.
        
        Args:
            groupId (int | str): Group ID to delete message
            msgId (int | str): Message ID to delete
            ownerId (int | str): Owner ID of the message to delete
            clientMsgId (int | str): Client message ID to delete message
        
        Returns:
            object: `Group` delete message status
            dict: A dictionary containing error_code & responses if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "grid": str(groupId),
                "cliMsgId": _util.now(),
                "msgs": [{
                    "cliMsgId": str(clientMsgId),
                    "globalMsgId": str(msgId),
                    "ownerId": str(ownerId),
                    "destId": str(groupId)
                }],
                "onlyMe": 0
            })
        }
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/deletemsg", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def viewGroupPending(self, groupId):
        """See list of people pending approval in group by ID.
        
        Args:
            groupId (int | str): Group ID to view pending members
            
        Returns:
            object: `Group` pending responses
            dict: A dictionary containing error_code & responses if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "params": self._encode({
                "grid": str(groupId),
                "imei": self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/pending-mems/list", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def handleGroupPending(self, members, groupId, isApprove=True):
        """Approve/Deny pending users to the group from the group's approval.
        
        Client must be the Owner of the group.
        
        Args:
            members (str | list): One or More member IDs to handle
            groupId (int | str): ID of the group to handle pending members
            isApprove (bool): Approve/Reject pending members (True | False)
            
        Returns:
            object: `Group` handle pending responses
            dict: A dictionary/object containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if isinstance(members, list):
            members = [str(member) for member in members]
        else:
            members = [str(members)]
        
        params = {
            "params": self._encode({
                "grid": str(groupId),
                "members": members,
                "isApprove": 1 if isApprove else 0
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/pending-mems/review", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
                
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def viewPollDetail(self, pollId):
        """View poll data by ID.
        
        Args:
            pollId (int | str): Poll ID to view detail
            
        Returns:
            object: `Group` poll data
            dict: A dictionary containing error_code & response if failed
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "params": self._encode({
                "poll_id": int(pollId),
                "imei":self._imei
            }),
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/poll/detail", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def createPoll(
        self,
        question,
        options,
        groupId,
        expiredTime=0,
        pinAct=False,
        multiChoices=True,
        allowAddNewOption=True,
        hideVotePreview=False,
        isAnonymous=False
    ):
        """Create poll in group by ID.
        
        Client must be the Owner of the group.
        
        Args:
            question (str): Question for poll
            options (str | list): List options for poll
            groupId (int | str): Group ID to create poll from
            expiredTime (int): Poll expiration time (0 = no expiration)
            pinAct (bool): Pin action (pin poll)
            multiChoices (bool): Allows multiple poll choices
            allowAddNewOption (bool): Allow members to add new options
            hideVotePreview (bool): Hide voting results when haven't voted
            isAnonymous (bool): Hide poll voters
            
        Returns:
            object: `Group` poll create data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "group_id": str(groupId),
                "question": question,
                "options": [],
                "expired_time": expiredTime,
                "pinAct": pinAct,
                "allow_multi_choices": multiChoices,
                "allow_add_new_option": allowAddNewOption,
                "is_hide_vote_preview": hideVotePreview,
                "is_anonymous": isAnonymous,
                "poll_type": 0,
                "src": 1,
                "imei": self._imei
            }
        }
        
        if isinstance(options, list):
            payload["params"]["options"] = options
        else:
            payload["params"]["options"].append(str(options))
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/poll/create", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def sharePoll(self, pollId):
        """Share poll in group.
        
        Args:
            pollId (int | str): Poll ID to share
            
        Returns:
            object: `Group` poll share data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 689,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "poll_id": int(pollId),
                "imei": self._imei
            })
        }
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/poll/share", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def fetchGroupBoard(
        self,
        groupId,
        boardType=0,
        page=1,
        count=20,
        lastId=0,
        lastType=0
    ):
        """Fetch group board list.
        
        Args:
            groupId (int | str): Group ID to fetch board from
            boardType (int): Board type (default: 1)
            page (int): Page number (default: 1)
            count (int): Number of items to fetch (default: 20)
            lastId (int): Last item ID for pagination (default: 0)
            lastType (int): Last item type for pagination (default: 0)
            
        Returns:
            object: `Group` board list data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 689,
            "zpw_type": 30,
            "params": self._encode({
                "group_id": str(groupId),
                "board_type": boardType,
                "page": page,
                "count": count,
                "last_id": lastId,
                "last_type": lastType,
                "imei": self._imei
            })
        }
        
        response = self._get("https://groupboard-wpa.chat.zalo.me/api/board/list", params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def createTopic(
        self,
        title,
        groupId,
        emoji="⏰",
        color=-16245706,
        startTime=None,
        duration=-1,
        repeat=1,
        topicType=0,
        pinAct=False
    ):
        """Create topic/event in group by ID.
        
        Args:
            title (str): Title of the topic/event
            groupId (int | str): Group ID to create topic in
            emoji (str): Emoji icon for the topic (default: "⏰")
            color (int): Color code for the topic (default: -16245706)
            startTime (int): Start time in milliseconds timestamp (default: current time)
            duration (int): Duration in milliseconds (-1 = no end time)
            repeat (int): Repeat mode (0 = no repeat, 1 = daily, etc.)
            topicType (int): Type of topic (default: 0)
            pinAct (bool): Pin action (pin topic)
            
        Returns:
            object: `Group` topic create data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 678,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "grid": str(groupId),
                "type": topicType,
                "color": color,
                "emoji": emoji,
                "startTime": startTime if startTime is not None else int(time.time() * 1000),
                "duration": duration,
                "params": json.dumps({"title": title}),
                "repeat": repeat,
                "src": 1,
                "imei": self._imei,
                "pinAct": int(pinAct)
            }
        }
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(
            "https://groupboard-wpa.chat.zalo.me/api/board/topic/createv2",
            params=params,
            data=payload
        )
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
        
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def getTopics(
        self,
        groupId,
        page=1,
        count=20,
        lastId=0,
        lastType=0,
        boardType=1
    ):
        params = {
            "zpw_ver": 678,
            "zpw_type": 30,
            "params": self._encode({
                "objectData": json.dumps({
                    "group_id": str(groupId),
                    "board_type": boardType,
                    "page": page,
                    "count": count,
                    "last_id": lastId,
                    "last_type": lastType
                }),
                "imei": self._imei
            })
        }

        response = self._get(
            "https://groupboard-wpa.chat.zalo.me/api/board/listReminder",
            params=params
        )
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results

            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}

            return Group.fromDict(results, None)

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def deleteTopic(
        self,
        topicId,
        groupId
    ):
        params = {
            "zpw_ver": 678,
            "zpw_type": 30
        }

        payload = {
            "params": self._encode({
                "grid": str(groupId),
                "topicId": str(topicId),
                "imei": self._imei
            })
        }

        response = self._post(
            "https://groupboard-wpa.chat.zalo.me/api/board/topic/remove",
            params=params,
            data=payload
        )
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results is not None:
            if results:
                results = self._decode(results)
                results = results.get("data") if results.get("data") else results

                if isinstance(results, str):
                    try:
                        results = json.loads(results)
                    except:
                        results = {"error_code": 1337, "error_message": results}
            else:
                results = {"error_code": 0, "error_message": "Successful."}

            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            return Group.fromDict(results, None)

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def sendMessageForward(self, thread_id, thread_type, message="", ttl=0):
        """Send a message with hardcoded forward reference and decorLog.
            
        Args:
            thread_id (int | str): User/Group ID to send the message to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP.
            message (str): Text message to send.
            ttl (int): Time to live for the message.
        
        Returns:
            object: `User/Group` send message response.
        
        Raises:
            ZaloAPIException: If request failed.
        """
        params = {
            "zpw_ver": 686,
            "zpw_type": 30,
            "nretry": 0
        }
        
        client_id = str(_util.now())
        
        msg_ref_data = {
            "id": "f21b78443cfaab4d3e382603b1cc68d3",
            "ts": 1782940694364,
            "logSrcType": 2,
            "fwLvl": 1,
            "rootMsgRef": {
                "id": "f21b78443cfaab4d3e382603b1cc68d3",
                "ts": 1782940694364,
                "logSrcType": 2
            }
        }
        
        reference = {
            "type": 3,
            "data": json.dumps(msg_ref_data, ensure_ascii=False)
        }
        
        msg_info = {
            "message": message,
            "reference": json.dumps(reference, ensure_ascii=False)
        }
        
        decor_log = {
            "fw": {
                "pmsg": {"st": 2, "ts": 1782940694364, "id": "f21b78443cfaab4d3e382603b1cc68d3"},
                "rmsg": {"st": 2, "ts": 1782940694364, "id": "f21b78443cfaab4d3e382603b1cc68d3"},
                "fwLvl": 1
            }
        }
        
        payload_params = {
            "ttl": ttl,
            "msgType": 1,
            "totalIds": 1,
            "msgInfo": json.dumps(msg_info, ensure_ascii=False),
            "decorLog": json.dumps(decor_log, ensure_ascii=False)
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/mforward"
            payload_params["tids"] = [{"clientId": client_id, "uid": str(thread_id), "ttl": ttl}]
        else:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/mforward"
            payload_params["grids"] = [{"clientId": client_id, "grid": str(thread_id), "ttl": ttl}]
        
        payload = {
            "params": self._encode(payload_params)
        }
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"msgId": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending message: {error_message}")

    def sendMention(self, message, groupId, refId=None, refTs=None, ttl=0):
        """Send message with mention and quote/forward a message.
            
        Args:
            message (Message): Message to send (contains text, style, mention).
            groupId: Group ID to send to.
            refId: ID of the message being quoted/forwarded.
            refTs: Timestamp of the message being quoted/forwarded.
            ttl (int): Time to live.
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload_params = {
            "grid": str(groupId),
            "message": message.text,
            "mentionInfo": message.mention,
            "clientId": _util.now() * 60,
            "visibility": 0,
            "ttl": ttl
        }
        
        # Thêm Style (rtfProps / textProperties)
        if message.style:
            if isinstance(message.style, str):
                payload_params["textProperties"] = message.style
            else:
                payload_params["textProperties"] = json.dumps(message.style)
        
        # Thêm Reference (Để quote/forward tin nhắn cũ)
        if refId and refTs:
            ref_data = {
                "id": str(refId),
                "ts": int(refTs),
                "logSrcType": 2,
                "fwLvl": 1,
                "rootMsgRef": {
                    "id": str(refId),
                    "ts": int(refTs),
                    "logSrcType": 2
                }
            }
            payload_params["reference"] = json.dumps({
                "type": 3,
                "data": json.dumps(ref_data)
            })
        
        payload = {
            "params": self._encode(payload_params)
        }
        
        # Đổi lại endpoint về api/group/mention (không dùng mforward nữa)
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/mention", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def sendLinkCard(self, thread_id, thread_type, link, tw, th, title="", desc="", thumb="", message="", ttl=0):
        """Send a link card message to a conversation.
            
        Args:
            thread_id (int | str): User/Group ID to send the link card to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP.
            link (str): URL of the link.
            title (str): Title for the link card.
            desc (str): Description for the link card.
            thumb (str): Thumbnail image URL for the link card.
            message (str): Text message accompanied with the link (default is the link itself).
            ttl (int): Time to live for the message.
        
        Returns:
            object: `User/Group` send link card response.
        
        Raises:
            ZaloAPIException: If request failed.
        """
        params = {
            "zpw_ver": 686,
            "zpw_type": 30,
            "nretry": 0
        }
        
        client_id = str(_util.now())
        
        ext_data = {
            "redirect_url": "",
            "src": title,
            "mediaTitle": title,
            "streamUrl": "",
            "type": 12,
            "linkType": 12,
            "artist": title,
            "count": "",
            "stream_icon": "",
            "mediaId": "",
            "video_duration": 0,
            "arid": 0,
            "href": link,
            "owner": {"id": 0, "avt": title, "dispname": title},
            "params": {"autoplay": 0},
            "dimen": {
                "width": 0, "height": 0, "latitude": 0, "longitude": 0,
                "created_time": 0, "file_name": title, "file_size": 0, "has_device_info": False
            },
            "tType": 1,
            "tWidth": tw,
            "tHeight": th,
            "brand_name": title,
            "errorMap": "{}",
            "avatar": thumb,
            "thumb_renew": thumb,
            "thumb_src_type": 0,
            "link_sub_type": 1
        }
        
        msg_info = {
            "link": link,
            "linkTitle": title or link,
            "linkDesc": desc,
            "linkThumb": thumb,
            "linkType": "",
            "extData": json.dumps(ext_data, ensure_ascii=False),
            "message": message or link,
            "reference": ""
        }
        
        payload_params = {
            "ttl": ttl,
            "msgType": 3,
            "totalIds": 1,
            "msgInfo": json.dumps(msg_info, ensure_ascii=False),
            "decorLog": "{}"
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/mforward"
            payload_params["tids"] = [{"clientId": client_id, "uid": str(thread_id), "ttl": ttl}]
        else:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/mforward"
            payload_params["grids"] = [{"clientId": client_id, "grid": str(thread_id), "ttl": ttl}]
        
        payload = {
            "params": self._encode(payload_params)
        }
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"msgId": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending link card: {error_message}")

    def sendLinkCards(self, thread_id, thread_type, link, tw, th, title="", desc="", thumb="", message="", ttl=0):
        """Send a link card message to a conversation.
            
        Args:
            thread_id (int | str): User/Group ID to send the link card to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP.
            link (str): URL of the link.
            tw (int): Thumbnail width.
            th (int): Thumbnail height.
            title (str): Title for the link card.
            desc (str): Description for the link card.
            thumb (str): Thumbnail image URL for the link card.
            message (str): Text message accompanied with the link (default is the link itself).
            ttl (int): Time to live for the message.
        
        Returns:
            object: `User/Group` send link card response.
        
        Raises:
            ZaloAPIException: If request failed.
        """
        params = {
            "zpw_ver": 686,
            "zpw_type": 30,
            "nretry": 0
        }
        
        client_id = str(_util.now())
        
        ext_data = {
            "streamUrl": "",
            "video_duration": 0,
            "arid": 0,
            "stream_icon": "",
            "tType": 1,
            "artist": "",
            "src": title,
            "thumb_src_type": 1,
            "count": "",
            "tHeight": th,
            "avatar": thumb,
            "type": 0,
            "title": title,
            "mediaId": "",
            "link_sub_type": 1,
            "mediaTitle": title,
            "thumb_renew": thumb,
            "width": tw,
            "linkType": 12,
            "href": link,
            "redirect_url": "",
            "desc": desc,
            "tWidth": tw,
            "height": th
        }
        
        msg_info = {
            "link": link,
            "linkTitle": title or link,
            "linkDesc": desc,
            "linkThumb": thumb,
            "linkType": "",
            "extData": json.dumps(ext_data, ensure_ascii=False),
            "message": message or link,
            "reference": ""
        }
        
        payload_params = {
            "ttl": ttl,
            "msgType": 3,
            "totalIds": 1,
            "msgInfo": json.dumps(msg_info, ensure_ascii=False),
            "decorLog": "{}"
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/mforward"
            payload_params["tids"] = [{"clientId": client_id, "uid": str(thread_id), "ttl": ttl}]
        else:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/mforward"
            payload_params["grids"] = [{"clientId": client_id, "grid": str(thread_id), "ttl": ttl}]
        
        payload = {
            "params": self._encode(payload_params)
        }
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"msgId": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending link card: {error_message}")

    def sendCatalogLinkCard(self, thread_id, thread_type, link, tw, th, title="", desc="", thumb="",
                             message="", ttl=0, src="", media_title="", owner_id=0, owner_name="",
                             seller_id="", catalog_id=0, product_id=0, link_type=7, type_=0,
                             local_path_thumb_link=""):
        """Send a catalog product link card message to a conversation.

        Args:
            thread_id (int | str): User/Group ID to send the link card to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP.
            link (str): URL of the catalog product link.
            tw (int): Thumbnail width.
            th (int): Thumbnail height.
            title (str): Title for the link card.
            desc (str): Description for the link card.
            thumb (str): Thumbnail image URL for the link card.
            message (str): Text message accompanied with the link (default is empty).
            ttl (int): Time to live for the message.
            src (str): Source domain shown on the card (e.g. "catalog.zalo.me").
            media_title (str): Media title shown on the card.
            owner_id (int | str): Owner/seller ID.
            owner_name (str): Owner/seller display name.
            seller_id (str): Seller ID for productCatalogInfo.
            catalog_id (int): Catalog ID for productCatalogInfo.
            product_id (int): Product ID for productCatalogInfo.
            link_type (int): extData linkType (default 7 for catalog).
            type_ (int): extData type (default 0 for catalog).
            local_path_thumb_link (str): Local cached thumbnail path (optional).

        Returns:
            object: `User/Group` send link card response.

        Raises:
            ZaloAPIException: If request failed.
        """
        params = {
            "zpw_ver": 690,
            "zpw_type": 30,
            "nretry": 0
        }

        client_id = str(_util.now())

        ext_data = {
            "redirect_url": "",
            "src": src,
            "mediaTitle": media_title,
            "streamUrl": "",
            "type": type_,
            "linkType": link_type,
            "artist": "",
            "count": "",
            "stream_icon": "",
            "mediaId": "",
            "video_duration": 0,
            "arid": 0,
            "href": link,
            "owner": {"id": owner_id, "avt": "", "dispname": owner_name},
            "params": {"autoplay": 0},
            "dimen": {
                "width": 0, "height": 0, "latitude": 0, "longitude": 0,
                "created_time": 0, "file_name": "", "file_size": 0, "has_device_info": False
            },
            "productCatalogInfo": {
                "sellerId": str(seller_id),
                "catalogId": catalog_id,
                "productId": product_id
            },
            "tType": 1,
            "tWidth": tw,
            "tHeight": th,
            "errorMap": "{}",
            "local_path_thumb_link": local_path_thumb_link,
            "thumb_src_type": 0
        }

        msg_info = {
            "link": link,
            "linkTitle": title or link,
            "linkDesc": desc,
            "linkThumb": thumb,
            "linkType": "",
            "extData": json.dumps(ext_data, ensure_ascii=False),
            "message": message or "",
            "reference": ""
        }

        payload_params = {
            "ttl": ttl,
            "msgType": 3,
            "totalIds": 1,
            "msgInfo": json.dumps(msg_info, ensure_ascii=False),
            "decorLog": "{}"
        }

        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/mforward"
            payload_params["tids"] = [{"clientId": client_id, "uid": str(thread_id), "ttl": ttl}]
        else:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/mforward"
            payload_params["grids"] = [{"clientId": client_id, "grid": str(thread_id), "ttl": ttl}]

        payload = {
            "params": self._encode(payload_params)
        }

        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None

        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"msgId": results}

            return (
                Group.fromDict(results, None)
                if thread_type == ThreadType.GROUP else
                User.fromDict(results, None)
            )

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending catalog link card: {error_message}")

    def sendLocation(self, thread_id, thread_type, lat, lon, desc="", title="", ttl=0):
        """Send a location message to a conversation.
            
        Args:
            thread_id (int | str): User/Group ID to send the location to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP.
            lat (float): Latitude of the location.
            lon (float): Longitude of the location.
            desc (str): Address description or details.
            title (str): Title for the location.
            ttl (int): Time to live for the message.
        
        Returns:
            object: `User/Group` send location response.
        
        Raises:
            ZaloAPIException: If request failed.
        """
        params = {
            "zpw_ver": 686,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "ttl": ttl,
                "msgType": 7,
                "zsource": -1,
                "clientId": str(_util.now()),
                "msgInfo": {
                    "title": str(title),
                    "desc": str(desc),
                    "appId": "",
                    "lat": float(lat),
                    "lon": float(lon),
                    "placeId": "",
                    "isUserLocation": 1,
                    "reference": ""
                }
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/forward"
            payload["params"]["toId"] = str(thread_id)
            payload["params"]["imei"] = self._imei
        else:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/forward"
            payload["params"]["visibility"] = 0
            payload["params"]["grid"] = str(thread_id)
        
        payload["params"]["msgInfo"] = json.dumps(payload["params"]["msgInfo"], ensure_ascii=False)
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"msgId": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending location: {error_message}")

    def getRequestedFriendList(self):
        """Get list of received friend requests.
        
        Returns:
            object: Friend request list data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 679,
            "zpw_type": 30,
            "params": self._encode({
                "imei": self._imei
            })
        }

        response = self._get(
            "https://tt-friend-wpa.chat.zalo.me/api/friend/requested/list",
            params=params
        )
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results

            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}

            return Group.fromDict(results, None)

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def acceptFriendRequest(self, userId, language="vi"):
        """Accept a friend request by user ID.
        
        Args:
            userId (int | str): User ID of the person whose friend request to accept
            language (str): Language code (default: "vi")
            
        Returns:
            object: Accept friend request result data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 679,
            "zpw_type": 30
        }

        payload = {
            "params": self._encode({
                "fid": str(userId),
                "language": language
            })
        }

        response = self._post(
            "https://tt-friend-wpa.chat.zalo.me/api/friend/accept",
            params=params,
            data=payload
        )
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results is not None:
            if results:
                results = self._decode(results)
                results = results.get("data") if results.get("data") else results

                if isinstance(results, str):
                    try:
                        results = json.loads(results)
                    except:
                        results = {"error_code": 1337, "error_message": results}
            else:
                results = {"error_code": 0, "error_message": "Successful."}

            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            return Group.fromDict(results, None)

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def undoFriendRequest(self, userId):
        """Decline/undo a friend request by user ID.
        
        Args:
            userId (int | str): User ID of the person whose friend request to decline/undo
            
        Returns:
            object: Undo friend request result data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 679,
            "zpw_type": 30
        }

        payload = {
            "params": self._encode({
                "fid": str(userId)
            })
        }

        response = self._post(
            "https://tt-friend-wpa.chat.zalo.me/api/friend/undo",
            params=params,
            data=payload
        )
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results is not None:
            if results:
                results = self._decode(results)
                results = results.get("data") if results.get("data") else results

                if isinstance(results, str):
                    try:
                        results = json.loads(results)
                    except:
                        results = {"error_code": 1337, "error_message": results}
            else:
                results = {"error_code": 0, "error_message": "Successful."}

            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            return Group.fromDict(results, None)

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def getRecommendedFriendList(self):
        """Get list of recommended/suggested friends.
        
        Returns:
            object: Recommended friends list data including suggested users and received friend requests
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 679,
            "zpw_type": 30,
            "params": self._encode({
                "imei": self._imei
            })
        }

        response = self._get(
            "https://tt-friend-wpa.chat.zalo.me/api/friend/recommendsv2/list",
            params=params
        )
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results

            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}

            return Group.fromDict(results, None)

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def extractUids(self, data):
        uids = []
        
        mentions = getattr(data, "mentions", None)
        if mentions:
            if isinstance(mentions, list):
                for m in mentions:
                    uid = getattr(m, "uid", None)
                    if uid:
                        uids.append(str(uid))
            elif isinstance(mentions, dict):
                for uid in mentions:
                    uids.append(str(uid))
        
        if not uids:
            quote = getattr(data, "quote", None)
            if quote:
                owner = getattr(quote, "ownerId", None)
                if owner:
                    uids.append(str(owner))
        
        return uids

    def extractUid(self, data):
        uids = self.extractUids(data)
        return uids[0] if uids else None
    
    def lockPoll(self, pollId):
        """Lock/end poll in group by ID.
        
        Client must be the Owner of the group.
        
        Args:
            pollId (int | str): Poll ID to lock
            
        Returns:
            None: If requet success
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "poll_id": int(pollId),
                "imei": self._imei
            })
        }
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/poll/end", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def is_group_admin(self, group_id, user_id):
        try:
            group_details = self.fetchGroupInfo(group_id)
            if not group_details or not hasattr(group_details, 'gridInfoMap'):
                logger.warning(f"Không thể lấy thông tin chi tiết cho nhóm {group_id} để kiểm tra admin.")
                return False

            group_info = group_details.gridInfoMap.get(str(group_id))
            if not group_info:
                logger.warning(f"Không tìm thấy dữ liệu cho nhóm {group_id} trong response.")
                return False

            creator_id = group_info.get('creatorId')
            admin_ids = group_info.get('adminIds', [])

            user_id_str = str(user_id)
            
            if user_id_str == str(creator_id):
                return True
            
            if user_id_str in [str(admin) for admin in admin_ids]:
                return True
            
            return False
        except Exception as e:
            logger.error(f"Lỗi khi kiểm tra quyền admin của user {user_id} trong nhóm {group_id}: {e}")
            return False

    def leaveReadOnlyGroups(self, dry_run=False, whitelist_ids=None):
        if whitelist_ids is None:
            whitelist_ids = []
            
        summary = {
            "left_groups": [],
            "kept_groups": [],
            "failed_to_leave": [],
            "whitelisted_groups": [],
            "bot_is_admin_groups": []
        }
        action_prefix = "[DRY RUN] " if dry_run else ""

        logger.info(f"{action_prefix}Starting process to find and leave read-only groups...")

        try:
            all_groups_obj = self.fetchAllGroups()
            if not all_groups_obj or not hasattr(all_groups_obj, 'gridInfoMap') or all_groups_obj.gridVerMap is None:
                logger.info("Account is not a member of any groups. Process finished.")
                return summary
            
            group_ids = list(all_groups_obj.gridVerMap.keys())
            if not group_ids:
                logger.info("Account has no groups to process. Process finished.")
                return summary
            logger.info(f"Found {len(group_ids)} total groups. Checking permissions...")

        except ZaloAPIException as e:
            logger.error(f"Fatal error: Could not fetch the group list. Aborting. Error: {e}")
            return summary

        bot_uid = self.uid

        for group_id in group_ids:
            try:
                group_details = self.fetchGroupInfo(group_id)
                if not group_details or not hasattr(group_details, 'gridInfoMap'):
                    logger.warning(f"Could not retrieve valid details for group ID {group_id}. Skipping.")
                    continue
                    
                group_info = group_details.gridInfoMap.get(str(group_id))
                if not group_info:
                    logger.warning(f"Details for group ID {group_id} not found in response. Skipping.")
                    continue

                group_name = group_info.get("name", f"Unknown Group (ID: {group_id})")
                settings = group_info.get("setting", {})
                is_read_only = settings.get("lockSendMsg") == 1

                if str(group_id) in whitelist_ids:
                    logger.info(f"Skipping group '{group_name}' as it is in the whitelist.")
                    summary["whitelisted_groups"].append({"id": group_id, "name": group_name})
                    summary["kept_groups"].append({"id": group_id, "name": group_name})
                    continue

                if is_read_only:
                    creator_id = group_info.get('creatorId')
                    admin_ids = group_info.get('adminIds', [])
                    bot_is_admin_or_creator = (str(bot_uid) == str(creator_id)) or (str(bot_uid) in [str(admin) for admin in admin_ids])

                    if bot_is_admin_or_creator:
                        logger.info(f"Skipping read-only group '{group_name}' because bot is an admin/creator.")
                        summary["bot_is_admin_groups"].append({"id": group_id, "name": group_name})
                        summary["kept_groups"].append({"id": group_id, "name": group_name})
                        continue

                    logger.warning(f"{action_prefix}Group '{group_name}' is read-only and bot is not admin. Preparing to leave.")
                    if not dry_run:
                        try:
                            self.leaveGroup(grid=group_id, imei=self._imei)
                            logger.info(f"Successfully left group '{group_name}'.")
                            summary["left_groups"].append({"id": group_id, "name": group_name})
                        except ZaloAPIException as leave_error:
                            logger.error(f"Failed to leave group '{group_name}': {leave_error}")
                            summary["failed_to_leave"].append({"id": group_id, "name": group_name, "error": str(leave_error)})
                    else:
                        summary["left_groups"].append({"id": group_id, "name": group_name})
                else:
                    summary["kept_groups"].append({"id": group_id, "name": group_name})
                
                time.sleep(0.2)

            except ZaloAPIException as e:
                logger.error(f"An error occurred while processing group {group_id}: {e}")
                summary["failed_to_leave"].append({"id": group_id, "name": "Unknown (fetch failed)", "error": str(e)})

        logger.info("--- Process Complete ---")
        return summary
        
    def disperseGroup(self, groupId):
        """Disperse group by ID.
        
        Client must be the Owner of the group.
            
        Args:
            groupId (int | str): Group ID to disperse
            
        Returns:
            None: If requet success
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "grid": str(groupId),
                "imei": self._imei
            })
        }
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/disperse", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("error_code") == 0 else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
        
    """
    END GROUP ACTION METHODS
    """
    
    """
    SEND METHODS
    """
    
    def send(self, message, thread_id, thread_type=ThreadType.USER, mark_message=None, ttl=0):
        """Send message to a thread.
            
        Args:
            message (Message): Message to send
            thread_id (int | str): User/Group ID to send to
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        thread_id = str(int(thread_id) or self.uid)
        if message.mention:
            return self.sendMentionMessage(message, thread_id, ttl)
        else:
            return self.sendMessage(message, thread_id, thread_type, mark_message, ttl)
    
    def sendMessage(self, message, thread_id, thread_type, mark_message=None, ttl=0):
        """Send message to a thread (user/group).
            
        Args:
            message (Message): Message to send
            thread_id (int | str): User/Group ID to send to
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            mark_message (str): Send messages as `Urgent` or `Important` mark
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "message": message.text,
                "clientId": _util.now() * 60,
                "imei": self._imei,
                "ttl": ttl
            }
        }
        
        if mark_message and mark_message.lower() in ["important", "urgent"]:
            markType = 1 if mark_message.lower() == "important" else 2
            payload["params"]["metaData"] = {"urgency": markType}
        
        if message.style:
            payload["params"]["textProperties"] = message.style
            
        if thread_type == ThreadType.USER:
            url = "https://tt-chat2-wpa.chat.zalo.me/api/message/sms"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/sendmsg"
            payload["params"]["visibility"] = 0
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendbug(self, message, thread_id, thread_type, mark_message=None, ttl=0):
        """Send message to a thread (user/group).
            
        Args:
            message (Message): Message to send
            thread_id (int | str): User/Group ID to send to
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            mark_message (str): Send messages as `Urgent` or `Important` mark
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "message": message.text,
                "clientId": _util.now() * 60,
                "imei": self._imei,
                "ttl": ttl
            }
        }
        
        if mark_message and mark_message.lower() in ["important", "urgent"]:
            markType = 1 if mark_message.lower() == "important" else 2
            payload["params"]["metaData"] = {"urgency": markType}
        
        if message.style:
            payload["params"]["textProperties"] = message.style
            
        if thread_type == ThreadType.USER:
            url = "https://tt-chat2-wpa.chat.zalo.me/api/message/sms"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/sendmsg"
            payload["params"]["visibility"] = 0
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
        
    def replyMessage(self, message, replyMsg, thread_id, thread_type, ttl=0):
        """Reply message in group by ID.
            
        Args:
            message (Message): Message Object to send
            replyMsg (Message): Message Object to reply
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "message": message.text,
                "clientId": _util.now(),
                "qmsgOwner": str(int(replyMsg.uidFrom) or self.uid),
                "qmsgId": replyMsg.msgId,
                "qmsgCliId": replyMsg.cliMsgId,
                "qmsgType": _util.getClientMessageType(replyMsg.msgType),
                "qmsg": replyMsg.content,
                "qmsgTs": replyMsg.ts,
                "qmsgAttach": json.dumps({}),
                "qmsgTTL": 0,
                "ttl": ttl,
            }
        }
        
        if not isinstance(replyMsg.content, str):
            payload["params"]["qmsg"] = ""
            payload["params"]["qmsgAttach"] = json.dumps(replyMsg.content.toDict())
        
        if message.style:
            payload["params"]["textProperties"] = message.style
            
        if message.mention:
            payload["params"]["mentionInfo"] = message.mention
        
        if thread_type == ThreadType.USER:
            url = "https://tt-chat2-wpa.chat.zalo.me/api/message/quote"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/quote"
            payload["params"]["visibility"] = 0
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendMentionMessage(self, message, groupId, ttl=0):
        """Send message to a group with mention by ID.
            
        Args:
            mention (str): Mention format data to send
            message (Message): Message to send
            groupId: Group ID to send to.
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "grid": str(groupId),
                "message": message.text,
                "mentionInfo": message.mention,
                "clientId": _util.now() * 60,
                "visibility": 0,
                "ttl": ttl
            }
        }
        
        if message.style:
            payload["params"]["textProperties"] = message.style
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/mention", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return Group.fromDict(results, None)
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def undoMessage(self, msgId, cliMsgId, thread_id, thread_type):
        """Undo message from the client by ID.
            
        Args:
            msgId (int | str): Message ID to undo
            cliMsgId (int | str): Client Msg ID to undo
            thread_id (int | str): User/Group ID to undo message
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            object: `User/Group` undo message status
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "msgId": str(msgId),
                "cliMsgIdUndo": str(cliMsgId),
                "clientId": _util.now()
            } 
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-chat3-wpa.chat.zalo.me/api/message/undo"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/undomsg"
            payload["params"]["grid"] = str(thread_id)
            payload["params"]["visibility"] = 0
            payload["params"]["imei"] = self._imei
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendReaction(self, messageObject, reactionIcon, thread_id, thread_type, reactionType=75):
        """Reaction message by ID.
            
        Args:
            messageObject (Message): Message Object to reaction
            reactionIcon (str): Icon/Text to reaction
            thread_id (int | str): Group/User ID contain message to reaction
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            object: `User/Group` message reaction data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "react_list": [{
                    "message": json.dumps({
                        "rMsg": [{
                            "gMsgID": int(messageObject.msgId),
                            "cMsgID": int(messageObject.cliMsgId),
                            "msgType": _util.getClientMessageType(messageObject.msgType)
                        }],
                        "rIcon": reactionIcon,
                        "rType": reactionType,
                        "source": 6
                    }),
                    "clientId": _util.now()
                }],
                "imei": self._imei
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://reaction.chat.zalo.me/api/message/reaction"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://reaction.chat.zalo.me/api/group/reaction"
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendMultiReaction(self, reactionObj, reactionIcon, thread_id, thread_type, reactionType=75):
        """Reaction message by ID.
            
        Args:
            reactionObj (MessageReaction): Message(s) data to reaction
            reactionIcon (str): Icon/Text to reaction
            thread_id (int | str): Group/User ID contain message to reaction
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            object: `User/Group` message reaction data
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "react_list": [{
                    "message": {
                        "rMsg": [],        
                        "rIcon": reactionIcon,
                        "rType": reactionType,
                        "source": 6
                    },
                    "clientId": _util.now()
                }],
                "imei": self._imei
            }
        }
        
        if isinstance(reactionObj, dict):
            payload["params"]["react_list"][0]["message"]["rMsg"].append(reactionObj)
        elif isinstance(reactionObj, list):
            payload["params"]["react_list"][0]["message"]["rMsg"] = reactionObj
        else:
            raise ZaloUserError("Reaction type is invalid")
        
        if thread_type == ThreadType.USER:
            url = "https://reaction.chat.zalo.me/api/message/reaction"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://reaction.chat.zalo.me/api/group/reaction"
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"]["react_list"][0]["message"] = json.dumps(payload["params"]["react_list"][0]["message"])
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendRemoteFile(self, fileUrl, thread_id, thread_type, fileName="default", fileSize=None, extension="vrxx", ttl=0):
        """Send File to a User/Group with url.
            
        Args:
            fileUrl (str): File url to send
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            fileName (str): File name to send
            fileSize (int): File size to send
            extension (str): type of file to send (py, txt, mp4, ...)
            
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if not fileSize:
            try:
                with self._state._session.get(fileUrl) as response:
                    if response.status_code == 200:
                        fileSize = int(response.headers.get("Content-Length", len(response.content)))
                    else:
                        fileSize = 0
                    
                    fileChecksum = hashlib.md5(response.content).hexdigest()
            
            except:
                raise ZaloAPIException("Unable to get url content")
        
        has_extension = fileName.rsplit(".")
        extension = has_extension[-1:][0] if len(has_extension) >= 2 else extension
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "fileId": str(int(_util.now() * 2)),
                "checksum": fileChecksum,
                "checksumSha": "",
                "extension": extension,
                "totalSize": fileSize,
                "fileName": fileName,
                "clientId": _util.now(),
                "fType": 1,
                "fileCount": 0,
                "fdata": "{}",
                "fileUrl": fileUrl,
                "zsource": 401,
                "ttl": ttl
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/asyncfile/msg"
            payload["params"]["toid"] = str(thread_id)
            payload["params"]["imei"] = self._imei
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/asyncfile/msg"
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendRemoteVideo(self, videoUrl, thumbnailUrl, duration, thread_id, thread_type, width=1280, height=720, message=None, ttl=0):
        """Send (Forward) video to a User/Group with url using forward API.
        
        Warning:
            This is a feature created through the forward function.
            Because Zalo Web does not allow viewing videos.
        
        Args:
            videoUrl (str): Video link to send
            thumbnailUrl (str): Thumbnail link for video
            duration (int | str): Time for video (ms)
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            width (int): Width of the video
            height (int): Height of the video
            message (Message): Message to send with video
            ttl (int): Time to live for the message
        
        Returns:
            object: `User/Group` (Returns msg ID just sent)
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        try:
            with self._state._session.head(videoUrl) as response:
                if response.status_code == 200:
                    fileSize = int(response.headers.get("Content-Length", len(response.content)))
                else:
                    fileSize = 0
                
        except Exception as e:
            raise ZaloAPIException(f"Unable to get url content: {e}")
            
        params = {
            "zpw_ver": 689,
            "zpw_type": 30,
            "nretry": 0
        }
        
        msg_info = {
            "videoUrl": str(videoUrl),
            "thumbUrl": str(thumbnailUrl),
            "duration": int(duration),
            "width": int(width),
            "height": int(height),
            "fileSize": fileSize,
            "isHD": 2,
            "isOriginal": 1,
            "title": message.text if message else "",
            "videoRotation": 0,
            "properties": None,
            "hdUrl": str(videoUrl),
            "normalUrl": str(videoUrl),
            "oriUrl": str(videoUrl),
            "rawUrl": str(videoUrl),
            "url": str(videoUrl),
            "hdSize": str(fileSize),
            "thumbSize": "0",
            "previewThumb": "",
            "jcp": json.dumps({
                "is_original": 1,
                "isOriginal": 1,
                "sendSource": 1,
                "convertible": "jxl",
                "quality": "original"
            })
        }
        
        payload = {
            "params": {
                "clientId": str(int(_util.now() * 1000)),
                "msgType": 5,
                "visibility": 0,
                "ttl": ttl,
                "zsource": 704,
                "msgInfo": json.dumps(msg_info),
                "imei": self._imei,
                "photoId": int(_util.now()),
                "videoId": int(_util.now()),
                "desc": message.text if message else ""
            }
        }
        
        if message and message.mention:
            payload["params"]["mentionInfo"] = message.mention
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/forward"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/forward"
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendRemoteVoice(self, voiceUrl, thread_id, thread_type, fileSize=None, ttl=0):
        """Send voice by url.
            
        Args:
            voiceUrl (str): Voice link to send
            thread_id (int | str): User/Group ID to change status in
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            fileSize (int | str): Voice content length (size) to send
        
        Returns:
            object: `User/Group` response
        
        Raises:
            ZaloAPIException: If request failed
        """
        with self._state._session.get(voiceUrl) as response:
            if response.status_code == 200:
                fileSize = fileSize if fileSize else int(response.headers.get("Content-Length", len(response.content)))
            else:
                fileSize = fileSize if fileSize else 0
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "ttl": ttl,
                "zsource": -1,
                "msgType": 3,
                "clientId": str(_util.now()),
                "msgInfo": json.dumps({
                    "voiceUrl": str(voiceUrl),
                    "m4aUrl": str(voiceUrl),
                    "fileSize": int(fileSize)
                })
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/forward"
            payload["params"]["toId"] = str(thread_id)
            payload["params"]["imei"] = self._imei
        else:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/forward"
            payload["params"]["visibility"] = 0
            payload["params"]["grid"] = str(thread_id)
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def sendImage(self, imageUrl, thread_id, thread_type, caption="", message=None, ttl=0):
        """Send Image to a User/Group with image URL using forward API.
        
        Args:
            imageUrl (str): Image URL to send
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            caption (str): Image caption/description
            message (Message): Message object with text and mentions
            ttl (int): Time to live for the message
            
        Returns:
            object: `User/Group` objects response
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        image_info = self._getImageInfoFromUrl(imageUrl)
        if not image_info:
            raise ZaloAPIException("Failed to get image info from URL")
        
        if image_info.get("totalSize") and image_info["totalSize"] < 1024:
            raise ZaloAPIException("Image is too small (size < 1024 bytes)")
        
        width = image_info.get("width", 500)
        height = image_info.get("height", 500)
        
        params = {
            "zpw_ver": 689,
            "zpw_type": 30,
            "nretry": 0
        }
        
        msg_info = {
            "title": caption or (message.text if message else ""),
            "oriUrl": imageUrl,
            "thumbUrl": imageUrl,
            "hdUrl": imageUrl,
            "width": width,
            "height": height,
            "url": imageUrl,
            "normalUrl": "",
            "jcp": json.dumps({"is_original": 1})
        }
        
        payload = {
            "params": {
                "clientId": str(int(_util.now() * 1000)),
                "msgType": 2,
                "visibility": 0,
                "ttl": ttl,
                "zsource": 704,
                "msgInfo": json.dumps(msg_info),
                "imei": self._imei
            }
        }
        
        if message and message.mention:
            payload["params"]["mentionInfo"] = message.mention
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/forward"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/forward"
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def _getImageInfoFromUrl(self, imageUrl):
        """Get image information from URL.
        
        Args:
            imageUrl (str): Image URL
            
        Returns:
            dict: Image info including width, height, totalSize
            None: If failed to get info
        """
        try:
            import requests as req
            from io import BytesIO
            from PIL import Image
            
            response = req.get(imageUrl, timeout=15, stream=True)
            totalSize = int(response.headers.get("content-length", len(response.content)))
            img = Image.open(BytesIO(response.content))
            return {
                "width": img.width,
                "height": img.height,
                "totalSize": totalSize
            }
        except ImportError:
            try:
                import requests as req
                response = req.head(imageUrl, timeout=10)
                totalSize = int(response.headers.get("content-length", 0))
                return {
                    "width": 500,
                    "height": 500,
                    "totalSize": totalSize
                }
            except Exception:
                return None
        except Exception:
            return None
 
    def sendLocalImage(self, imagePath, thread_id, thread_type, width=2560, height=2560, message=None, custom_payload=None, ttl=0):
        """Send Image to a User/Group with local file using forward API.
            
        Args:
            imagePath (str): Image directory to send
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            width (int): Image width to send
            height (int): Image height to send
            message (Message): Message to send with image
            custom_payload (dict): Custom payload to override default
            ttl (int): Time to live for the message
            
        Returns:
            object: `User/Group` objects response
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 689,
            "zpw_type": 30,
            "nretry": 0
        }
        
        if custom_payload:
            if thread_type == ThreadType.USER:
                url = "https://tt-files-wpa.chat.zalo.me/api/message/forward"
            elif thread_type == ThreadType.GROUP:
                url = "https://tt-files-wpa.chat.zalo.me/api/group/forward"
            else:
                raise ZaloUserError("Thread type is invalid")
            
            payload = custom_payload
        
        else:
            uploadImage = self._uploadImage(imagePath, thread_id, thread_type)
            
            msg_info = {
                "title": message.text if message else "",
                "oriUrl": uploadImage["normalUrl"],
                "thumbUrl": uploadImage["thumbUrl"],
                "hdUrl": uploadImage["hdUrl"],
                "width": width,
                "height": height,
                "url": uploadImage["normalUrl"],
                "normalUrl": "",
                "jcp": json.dumps({"is_original": 1})
            }
            
            payload = {
                "params": {
                    "clientId": uploadImage.get("clientFileId", str(int(_util.now() * 1000))),
                    "msgType": 2,
                    "visibility": 0,
                    "ttl": ttl,
                    "zsource": 704,
                    "msgInfo": json.dumps(msg_info),
                    "imei": self._imei
                }
            }
        
            if message and message.mention:
                payload["params"]["mentionInfo"] = message.mention
            
            if thread_type == ThreadType.USER:
                url = "https://tt-files-wpa.chat.zalo.me/api/message/forward"
                payload["params"]["toid"] = str(thread_id)
            elif thread_type == ThreadType.GROUP:
                url = "https://tt-files-wpa.chat.zalo.me/api/group/forward"
                payload["params"]["grid"] = str(thread_id)
            else:
                raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendMultiLocalImage(self, imagePathList, thread_id, thread_type, width=2560, height=2560, message=None, ttl=0):
        """Send Multiple Image to a User/Group with local file using forward API.
            
        Args:
            imagePathList (list): List image directory to send
            width (int): Image width to send
            height (int): Image height to send
            message (Message): Message to send with image
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            ttl (int): Time to live for the message
            
        Returns:
            object: `User/Group` objects
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        uploadData = []
        
        if not isinstance(imagePathList, list) or len(imagePathList) < 1:
            raise ZaloUserError("image path must be a list to be able to send multiple at once.")
        
        groupLayoutId = str(_util.now())
        
        for i, imagePath in enumerate(imagePathList):
            uploadImage = self._uploadImage(imagePath, thread_id, thread_type)
        
            msg_info = {
                "title": message.text if message else "",
                "oriUrl": uploadImage["normalUrl"],
                "thumbUrl": uploadImage["thumbUrl"],
                "hdUrl": uploadImage["hdUrl"],
                "width": width,
                "height": height,
                "url": uploadImage["normalUrl"],
                "normalUrl": "",
                "groupLayoutId": groupLayoutId,
                "totalItemInGroup": len(imagePathList),
                "isGroupLayout": 1,
                "idInGroup": i,
                "jcp": json.dumps({"is_original": 1})
            }
            
            payload = {
                "params": {
                    "clientId": uploadImage.get("clientFileId", str(int(_util.now() * 1000))),
                    "msgType": 2,
                    "visibility": 0,
                    "ttl": ttl,
                    "zsource": 704,
                    "msgInfo": json.dumps(msg_info),
                    "imei": self._imei
                }
            }
        
            if message and message.mention:
                payload["params"]["mentionInfo"] = message.mention
            
            if thread_type == ThreadType.USER:
                payload["params"]["toid"] = str(thread_id)
            elif thread_type == ThreadType.GROUP:
                payload["params"]["grid"] = str(thread_id)
            else:
                raise ZaloUserError("Thread type is invalid")
            
            data = self.sendLocalImage(imagePath, thread_id, thread_type, width, height, message, custom_payload=payload, ttl=ttl)
            uploadData.append(data.toDict())
        
        return (
            Group.fromDict(uploadData, None) 
            if thread_type == ThreadType.GROUP else 
            User.fromDict(uploadData, None)
        )
    
    def sendLocalGif(self, gifPath, thumbnailUrl, thread_id, thread_type, gifName="vrxx.gif", width=500, height=500, ttl=0):
        """Send Gif to a User/Group with local file.
            
        Args:
            gifPath (str): Gif path to send
            thumbnailUrl (str): Thumbnail of gif to send
            gifName (str): Gif name to send
            width (int): Gif width to send
            height (int): Gif height to send
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            object: `User/Group` objects
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        if not os.path.exists(gifPath):
            raise ZaloUserError(f"{gifPath} not found")
            
        files = [("chunkContent", open(gifPath, "rb"))]
        gifSize = len(open(gifPath, "rb").read())
        gifName = gifName if gifName else gifPath if "/" not in gifPath else gifPath.rstrip("/")[1]
        fileChecksum = hashlib.md5(open(gifPath, "rb").read()).hexdigest()
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "type": 1,
            "params": {
                "clientId": str(_util.now()),
                "fileName": gifName,
                "totalSize": gifSize,
                "width": width,
                "height": height,
                "msg": "",
                "type": 1,
                "ttl": ttl,
                "thumb": thumbnailUrl,
                "checksum": fileChecksum,
                "totalChunk": 1,
                "chunkId": 1
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/gif"
            params["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/gif"
            params["params"]["visibility"] = 0
            params["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        params["params"] = self._encode(params["params"])
        
        response = self._post(url, params=params, files=files)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def getStickerDetail(self, cateId):
        """Get Sticker Detail by Category ID.
            
        Args:
            cateId (int | str): Sticker category ID to get details
            
        Returns:
            list: List of sticker objects with details
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 688,
            "zpw_type": 30,
            "params": self._encode({"cid": str(cateId)})
        }
        
        url = "https://tt-sticker-wpa.chat.zalo.me/api/message/sticker/category/sticker_detail"
        
        response = self._get(url, params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return results
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
 
    def getPersonalizedStickers(self):
        """Get Personalized Stickers List.
            
        Returns:
            dict: Dictionary containing personalized stickers data with:
                - sticker_cates (list): List of sticker category IDs
                - expired_time (int): Expiration time in seconds
                - version (int): Current version number
                - removeSticker (list): List of removed stickers with sticker_id and cate_id
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 688,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "imei": self._imei
            }
        }
        
        payload["params"] = self._encode(payload["params"])
        params["params"] = payload["params"]
        
        url = "https://tt-sticker-wpa.chat.zalo.me/api/message/sticker/personalized/list"
        
        response = self._get(url, params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return results
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
 
    def updatePersonalizedStickers(self, stickerCates, version=None):
        """Update Personalized Stickers.
            
        Args:
            stickerCates (list): List of sticker category IDs
            version (int, optional): Version number. Defaults to current timestamp.
            
        Returns:
            dict: Dictionary containing update results with removed stickers info
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 688,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "version": version or _util.now(),
                "sticker_cates": stickerCates,
                "imei": self._imei
            }
        }
        
        payload["params"] = self._encode(payload["params"])
        params["params"] = payload["params"]
        
        url = "https://tt-sticker-wpa.chat.zalo.me/api/message/sticker/personalized/update"
        
        response = self._get(url, params=params)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return results
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendSticker(self, stickerType, stickerId, cateId, thread_id, thread_type, ttl=0):
        """Send Sticker to a User/Group.
            
        Args:
            stickerType (int | str): Sticker type to send
            stickerId (int | str): Sticker id to send
            cateId (int | str): Sticker category id to send
            thread_id (int | str): User/Group ID to send to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            object: `User/Group` objects
            dict: A dictionary containing error responses
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "stickerId": int(stickerId),
                "cateId": int(cateId),
                "type": int(stickerType),
                "clientId": _util.now(),
                "imei": self._imei,
                "ttl": ttl,
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-chat2-wpa.chat.zalo.me/api/message/sticker"
            payload["params"]["zsource"] = 106
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/sticker"
            payload["params"]["zsource"] = 103
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
        
    def sendCustomSticker(
        self,
        staticImgUrl,
        animationImgUrl,
        thread_id,
        thread_type,
        reply=None,
        width=None,
        height=None,
        ttl=0
    ):
        """Send custom (static/animation) sticker to a User/Group with url.
            
        Args:
            staticImgUrl (str): Image url (png, jpg, jpeg) format to create sticker
            animationImgUrl (str): Static/Animation image url (webp) format to create sticker
            thread_id (int | str): User/Group ID to send sticker to.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            reply (int | str): Message ID to send stickers with quote
            width (int | str): Width of photo/sticker
            height (int | str): Height of photo/sticker
            
        Returns:
            object: `User/Group` sticker data
            dict: A dictionary containing error responses
            
        Raises:
            ZaloAPIException: If request failed
        """
        width = int(width) if width else 0
        height = int(height) if height else 0
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "clientId": _util.now(),
                "title": "",
                "oriUrl": staticImgUrl,
                "thumbUrl": staticImgUrl,
                "hdUrl": staticImgUrl,
                "width": width,
                "height": height,
                "properties": json.dumps({
                    "subType": 0,
                    "color": -1,
                    "size": -1,
                    "type": 3,
                    "ext": json.dumps({
                        "sSrcStr": "@STICKER",
                        "sSrcType": 0
                    })
                }),
                "contentId": _util.now(),
                "thumb_height": width,
                "thumb_width": height,
                "webp": json.dumps({
                    "width": width,
                    "height": height,
                    "url": animationImgUrl
                }),
                "zsource": -1,
                "ttl": ttl
            }
        }
        
        if reply:
            payload["params"]["refMessage"] = str(reply)
            
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/photo_url"
            payload["params"]["toId"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/photo_url"
            payload["params"]["visibility"] = 0
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendLink(self, linkUrl, title, thread_id, thread_type, thumbnailUrl=None, domainUrl=None, desc=None, message=None, ttl=0):
        """Send link to a User/Group with url.
            
        Args:
            linkUrl (str): Link url to send
            domainUrl (str): Main domain of Link to send (eg: github.com)
            thread_id (int | str): User/Group ID to send link to
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            thumbnailUrl (str): Thumbnail link url for card to send
            title (str): Title for card to send
            desc (str): Description for card to send
            message (Message): Message object to send with the link
            
        Returns:
            object: `User/Group` message id response
            dict: A dictionary containing error responses
            
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "msg": message.text if message else "" or "",
                "href": linkUrl,
                "src": domainUrl or "",
                "title": str(title),
                "desc": desc or "",
                "thumb": thumbnailUrl or "",
                "type": 0,
                "media": json.dumps({
                    "type": 0,
                    "count": 0,
                    "mediaTitle": "",
                    "artist": "",
                    "streamUrl": "",
                    "stream_icon": ""
                }),
                "ttl": ttl,
                "clientId": _util.now()
            }
        }
        
        if message and message.mention:
            payload["params"]["mentionInfo"] = message.mention
        
        if thread_type == ThreadType.USER:
            url = "https://tt-chat4-wpa.chat.zalo.me/api/message/link"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/sendlink"
            payload["params"]["imei"] = self._imei
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def makeCall(self,uid):
            callId=int(time.time()) 
            params = {
                "params": self._encode({
                    'calleeId': str(uid),
                    'callId': callId,
                    'codec': '[]\n',
                    'typeRequest': 1,
                    'imei': self._imei
                }),
                "zpw_ver": 650,
                "zpw_type": 24
            }
            response = self._get("https://voicecall-wpa.chat.zalo.me/api/voicecall/requestcall", params=params)
            data = response.json()
            if data.get("error_code") == 0:
                decoded_data = self._decode(data.get("data"))
                data_fainal = decoded_data.get("data", {})
                data_fainal["callId"] = callId
                return data_fainal
            return None


    def makeCallRequest(self,uid, data_call):
            params = {
                "params": self._encode({
                    'calleeId': str(uid),
                    'rtcpAddress': data_call['rtpIP'],
                    'rtpAddress': data_call['rtpIP'],
                    'codec': json.dumps([{
                        'dynamicFptime': 0,
                        'frmPtime': 20,
                        'name': f"opus/{data_call['zrtc_config']['audioSampleRate']}/{data_call['zrtc_config']['audioChannel']}",
                        'payload': 112
                    }]),
                    'session': data_call['sessId'],
                    'callId': data_call['callId'],
                    'imei': self._imei,
                    'extendData': json.dumps({
                        'supportCallBusy': data_call['settings']['supportCallBusy'],
                        'tpType': 0,
                        "video":json.dumps({"codec":[{"name":"h264","payload":97}]})
                    }),
                    'subCommand': 3
                }),
                "zpw_ver": 650,
                "zpw_type": 24
            }
            response = self._get("https://voicecall-wpa.chat.zalo.me/api/voicecall/request", params=params)
            data = response.json()
            if data.get("error_code") == 0:
                decoded_data = self._decode(data.get("data"))
                return decoded_data.get("data")
            return None
    
    def newlink(self, grid):
            params_data = {
                "grid": grid
            }

            params = {
                "zpw_ver": 650,
                "zpw_type": 30,
                "params": self._encode(params_data)
            }

            response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/link/new", data=params)
            data = response.json()

            if data.get("error_code") == 0:
                new_link_info = self._decode(data.get("data"))
                if new_link_info and new_link_info.get("link"):
                    return {"success": True, "new_link": new_link_info.get("link")}
                else:
                    return {"success": False, "error_code": 1337, "error_message": "Không tìm thấy liên kết mới."}
            else:
                error_code = data.get("error_code")
                error_message = data.get("error_message", "Lỗi không xác định từ API.")
                return {"success": False, "error_code": error_code, "error_message": error_message}

    def dislink(self, grid):
            params_data = {
                "grid": grid
            }

            params = {
                "zpw_ver": 650,
                "zpw_type": 30,
                "params": self._encode(params_data)
            }

            response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/link/disable", data=params)
            data = response.json()

            if data.get("error_code") == 0:
                return {"success": True, "message": "Đã vô hiệu hóa liên kết nhóm thành công."}
            else:
                error_code = data.get("error_code")
                error_message = data.get("error_message", "Lỗi không xác định từ API.")
                return {"success": False, "error_code": error_code, "error_message": error_message}

    def getQRLink(self, userId):
            """Lấy Link QR của người dùng.
            
            Args:
                userId (int | str): ID người dùng cần lấy QR code
                
            Returns:
                dict: Dictionary chứa QR code URL của người dùng
                dict: Dictionary chứa error_code và response nếu thất bại
                
            Raises:
                ZaloAPIException: Nếu request thất bại
            """
            params = {
                "zpw_ver": 641,
                "zpw_type": 30
            }
            
            payload = {
                "params": self._encode({
                    "fids": [str(userId)]
                })
            }
            
            response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/mget-qr", params=params, data=payload)
            data = response.json()
            results = data.get("data") if data.get("error_code") == 0 else None
            if results:
                results = self._decode(results)
                results = results.get("data") if results.get("data") else results
                if results == None:
                    results = {"error_code": 1337, "error_message": "Data is None"}
                
                if isinstance(results, str):
                    try:
                        results = json.loads(results)
                    except:
                        results = {"error_code": 1337, "error_message": results}
                
                return results
                
            error_code = data.get("error_code")
            error_message = data.get("error_message") or data.get("data")
            raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

    def remove_blocked_member(self, grid, member_ids):
        params_data = {
            "grid": grid,
            "members": member_ids
        }

        params = {
            "zpw_ver": 650,
            "zpw_type": 30,
            "params": self._encode(params_data)
        }

        response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/blockedmems/remove", params=params)
        data = response.json()

        if data.get("error_code") == 0:
            return {"success": True, "message": "Xóa thành viên bị chặn thành công."}
        else:
            error_code = data.get("error_code")
            error_message = data.get("error_message", "Lỗi không xác định từ API.")
            return {"success": False, "error_code": error_code, "error_message": error_message}

    def TaoIDCall(self):
        return ''.join([str(random.randint(0, 9)) for _ in range(9)])
    def sendCall(self, target_id, callid_random):
        payload = {
            "params": {
                "calleeId": target_id,
                "callId": callid_random,
                "codec": "[]\n",
                "typeRequest": 1,
                "imei": self._imei
            }
        }
        payload["params"] = self._encode(payload["params"])
        call_url1 = 'https://voicecall-wpa.chat.zalo.me/api/voicecall/requestcall?zpw_ver=646&zpw_type=24'
        response = self._post(call_url1, params=payload["params"], data=payload)
        json_data = json.loads(response.text)
        call_payload = {
                "params": {
                    'calleeId': target_id,
                    'rtcpAddress': "171.244.25.88:4601",
                    'rtpAddress': "171.244.25.88:4601",
                    'codec': '[{"dynamicFptime":0,"frmPtime":20,"name":"opus/16000/1","payload":112}]\n',
                    'session': callid_random,
                    'callId': callid_random,
                    'imei': self._imei,
                    'subCommand': 3
                }
        }
        call_payload["params"] = self._encode(call_payload["params"])
        call_url2 = 'https://voicecall-wpa.chat.zalo.me/api/voicecall/request?zpw_ver=646&zpw_type=24'
        response = self._post(call_url2, params=call_payload["params"], data=call_payload)

    def get_blocked_members(self, grid, page=1, count=50):
        params_data = {
            "grid": grid,
            "page": page,
            "count": count
        }

        params = {
            "zpw_ver": 650,
            "zpw_type": 30,
            "params": self._encode(params_data)
        }

        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/blockedmems/list", params=params)
        data = response.json()

        if data.get("error_code") == 0:
            blocked_list = self._decode(data.get("data"))
            return {"success": True, "blocked_members": blocked_list}
        else:
            error_code = data.get("error_code")
            error_message = data.get("error_message", "Lỗi không xác định từ API.")
            return {"success": False, "error_code": error_code, "error_message": error_message}

    def checkGroup(self, link):
        params = {
        "params": self._encode({
        "link": link,
        "avatar_size": 120,
        "member_avatar_size": 120,
        "mpage": 1
        }),
        "zpw_ver": 650,
        "zpw_type": 30
        }

        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/link/ginfo", params=params)
        data = response.json()

        if data.get("error_code") == 0:
            decoded_data = self._decode(data.get("data"))
            if decoded_data and decoded_data.get("data"):
                return decoded_data.get("data")
            else:
                return {"error_code": 1337, "error_message": "Không tìm thấy dữ liệu nhóm."}
        else:
            error_code = data.get("error_code")
            error_message = data.get("error_message", "Lỗi không xác định từ API.")
        return {"error_code": error_code, "error_message": error_message}

    def unfriendUser(self, userId, language="vi"):
        """Unfriend a user by ID.
        
        Args:
            userId (int | str): User ID to unfriend.
            language (str): Response language or Zalo interface language.

        Returns:
            dict: A dictionary containing the unfriend status information.
        
        Raises:
            ZaloAPIException: If request failed.
        """
        params = {
            "zpw_ver": 641,
            "zpw_type": 30
        }
        
        payload = {
            "params": self._encode({
                "fid": str(userId),
                "language": language
            })
        }
        
        response = self._post("https://tt-friend-wpa.chat.zalo.me/api/friend/remove", 
                            params=params, data=payload)
        data = response.json()

        if data.get("error_code") == 0:
            return {"status": "success", "message": "Unfriended successfully."}
        else:
            error_code = data.get("error_code")
            error_message = data.get("error_message") or data.get("data")
            raise ZaloAPIException(f"Error #{error_code} when unfriending: {error_message}")
        
    def joinGroup(self, groupLink):
        payload = {
            "link": groupLink,
            "clientLang": "vi"
        }
        
        params = {
            "params": self._encode(payload),
            "zpw_ver": 647,
            "zpw_type": 30
        }
        
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/link/join", params=params)
        
        data = response.json()
        if data.get("error_code") == 0:
            decoded_data = self._decode(data.get("data"))
            return decoded_data
        
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def getIDsGroup(self, url):
        params = {
            "zpw_ver": 648,
            "zpw_type": 30
        }
        payload = {
            "params": self._encode({
                "link": str(url),
                "clientLang": "vi"
            })
        }

        try:
            response = self._post("https://tt-group-wpa.chat.zalo.me/api/group/link/ginfo",
                                    params=params,
                                    data=payload)

            data = response.json()
            results = data.get("data") if data.get("error_code") == 0 else None

            if results:
                results = self._decode(results)
                results = results.get("data") if results.get("data") else results

                if results is None:
                    results = {"error_code": 1337, "error_message": "Data is None"}

                if isinstance(results, str):
                    try:
                        results = json.loads(results)
                    except:
                        results = {"error_code": 1337, "error_message": results}

                return results

            error_code = data.get("error_code")
            error_message = data.get("error_message") or data.get("data")
            raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")

        except ZaloAPIException as e:
            raise e
        except Exception as e:
            raise ZaloAPIException(f"An unexpected error occurred: {e}")
                       
    def leaveGroup(self, grid, imei, silent=1, language="vi"):
        payload = {
            "grids": [grid],
            "imei": imei,
            "silent": silent,
            "language": language
        }
        params = {
            "params": self._encode(payload),
            "zpw_ver": 647,
            "zpw_type": 30
        }
        response = self._get("https://tt-group-wpa.chat.zalo.me/api/group/leave", params=params)
        data = response.json()
        if data.get("error_code") == 0:
            decoded_data = self._decode(data.get("data"))
            return decoded_data
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error {error_code} when sending requests: {error_message}")
    
    def sendToDo(self, message_object, content, assignees, thread_id, thread_type, due_date=-1, description=""):
        """Gửi một todo đến người dùng hoặc nhóm.
        
        Args:
            message_object (Message): Message object gốc
            content (str): Nội dung todo
            assignees (list): Danh sách ID người nhận
            thread_id (str): ID của thread 
            thread_type (ThreadType): Loại thread (USER/GROUP)
            due_date (int): Thời hạn (-1 nếu không có)
            description (str): Mô tả (có thể trống)
            
        Returns:
            object: Kết quả từ API
            
        Raises:
            ZaloAPIException: Nếu request thất bại
        """
        if not content:
            raise ZaloAPIException("Missing todo content")
        if not assignees:
            raise ZaloAPIException("Missing assignees")

        params = {
            "zpw_ver": 641,
            "zpw_type": 30
        }

        is_group = thread_type == ThreadType.GROUP

        payload = {
            "params": {
                "assignees": json.dumps(assignees),
                "dueDate": due_date,
                "content": content,
                "description": description,
                "extra": json.dumps({
                    "msgId": message_object.msgId,
                    "toUid": thread_id,
                    "isGroup": is_group,
                    "cliMsgId": message_object.cliMsgId,
                    "msgType": 1,
                    "mention": [],
                    "ownerMsgUId": self.uid,
                    "message": content
                }),
                "dateDefaultType": 0,
                "status": -1, 
                "watchers": "[]",
                "schedule": None,
                "src": 5,
                "imei": self._imei
            }
        }

        payload["params"] = self._encode(payload["params"])

        response = self._post("https://board-wpa.chat.zalo.me/api/board/personal/todo/create", 
                            params=params, 
                            data=payload)
        
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            
            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return results

        error_code = data.get("error_code") 
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    def sendProduct(
        self,
        product_id,
        product_name,
        product_price,
        thumbnail_url,
        thread_id,
        thread_type,
        thumbnail_width=500,
        thumbnail_height=500,
        message=None,
        ttl=0
    ):
        """Send a product from a Zalo Catalog.

        This is a specialized version of sendLink for sending product cards.

        Args:
            product_id (str): The unique ID of the product from your Zalo Catalog.
                              (e.g., '514a456f512ab874e13b')
            product_name (str): The name of the product to display on the card.
            product_price (str or int): The price to display (e.g., "50,000 VND" or 50000).
            thumbnail_url (str): A direct URL to the product's image thumbnail.
            thread_id (int | str): User/Group ID to send the product to.
            thread_type (ThreadType): The type of thread (USER or GROUP).
            thumbnail_width (int): The width of the thumbnail. Defaults to 500.
            thumbnail_height (int): The height of the thumbnail. Defaults to 500.
            message (Message): An optional Message object to send along with the product card.
            ttl (int): Time-to-live for the message in seconds (0 for permanent).

        Returns:
            object: `User/Group` object with the message ID response.
            dict: A dictionary containing error responses.

        Raises:
            ZaloAPIException: If the request fails.
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }

        # The payload is similar to sendLink, but with specific types and a media object for products.
        payload = {
            "params": {
                "msg": message.text if message and message.text else "",
                "href": f"https://catalog.zalo.me/?pid={product_id}",
                "src": "catalog.zalo.me",
                "title": str(product_name),  # Product name is the main title
                "desc": str(product_price), # Product price is the description
                "thumb": thumbnail_url,
                "type": 7,  # Type 7 indicates a special link, likely for products/catalogs
                "media": json.dumps({
                    "type": 7,
                    "linkType": 7,
                    "mediaTitle": str(product_name),
                    "tWidth": thumbnail_width,
                    "tHeight": thumbnail_height,
                    # These fields are from the generic link structure and can be empty
                    "artist": "",
                    "streamUrl": "",
                    "stream_icon": ""
                }),
                "ttl": ttl,
                "clientId": _util.now()
            }
        }

        if message and message.mention:
            payload["params"]["mentionInfo"] = message.mention

        if thread_type == ThreadType.USER:
            url = "https://tt-chat4-wpa.chat.zalo.me/api/message/link"
            payload["params"]["toid"] = str(thread_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/sendlink"
            payload["params"]["imei"] = self._imei
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")

        payload["params"] = self._encode(payload["params"])

        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results is None:
                results = {"error_code": 1337, "error_message": "Data is None"}

            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}

            return (
                Group.fromDict(results, None)
                if thread_type == ThreadType.GROUP else
                User.fromDict(results, None)
            )

        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
        
    def sendReport(self, user_id, reason=0, content=None):
        """Send report to Zalo.
        
        Args:
            reason (int): Reason for reporting
                1 = Nội dung nhạy cảm
                2 = Làm phiền
                3 = Lừa đảo
                0 = custom
            content (str): Report content (work if reason = custom)
            user_id (int | str): User ID to report
        
        Returns:
            object: `User` send report response
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "idTo": str(user_id),
                "objId": "person.profile"
            }
        }
        
        content = content if content and not reason else "" if not content and not reason else ""
        if content:
            payload["params"]["content"] = content
        
        payload["params"]["reason"] = str( random.randint(1, 3) if not content else reason )
        payload["params"] = self._encode(payload["params"])
        
        response = self._post("https://tt-profile-wpa.chat.zalo.me/api/report/abuse-v2", params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def sendBusinessCard(self, userId, qrCodeUrl, thread_id, thread_type, phone=None, ttl=0):
        """Send business card by user ID.
            
        Args:
            userId (int | str): Business card user ID
            qrCodeUrl (str): QR Code link with business card profile information
            phone (int | str): Send business card with phone number
            thread_id (int | str): User/Group ID to change status in
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
        
        Returns:
            object: `User/Group` send business card response
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "ttl": ttl,
                "msgType": 6,
                "clientId": str(_util.now() *60),
                "msgInfo": {
                    "contactUid": str(userId),
                    "qrCodeUrl": str(qrCodeUrl)
                }
            }
        }
        
        if phone:
            payload["params"]["msgInfo"]["phone"] = str(phone)
        
        if thread_type == ThreadType.USER:
            url = "https://tt-files-wpa.chat.zalo.me/api/message/forward"
            payload["params"]["toId"] = str(thread_id)
            payload["params"]["imei"] = self._imei
        else:
            url = "https://tt-files-wpa.chat.zalo.me/api/group/forward"
            payload["params"]["visibility"] = 0
            payload["params"]["grid"] = str(thread_id)
        
        payload["params"]["msgInfo"] = json.dumps(payload["params"]["msgInfo"])
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            results = results.get("data") if results.get("data") else results
            if results == None:
                results = {"error_code": 1337, "error_message": "Data is None"}
            
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except:
                    results = {"error_code": 1337, "error_message": results}
            
            return (
                Group.fromDict(results, None) 
                if thread_type == ThreadType.GROUP else 
                User.fromDict(results, None)
            )
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    """
    END SEND METHODS
    """
    
    def setTyping(self, thread_id, thread_type):
        """Set users typing status.
            
        Args:
            thread_id: User/Group ID to change status in.
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
        
        Raises:
            ZaloAPIException: If request failed
        """
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "imei": self._imei
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-chat1-wpa.chat.zalo.me/api/message/typing"
            payload["params"]["toid"] = str(thread_id)
            payload["params"]["destType"] = 3
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/typing"
            payload["params"]["grid"] = str(thread_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            results = self._decode(results)
            return True
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def markAsDelivered(
        self,
        msgId,
        cliMsgId,
        senderId,
        thread_id,
        thread_type,
        seen=0,
        method="webchat"
    ):
        """Mark a message as delivered.
        
        Args:
            cliMsgId (int | str): Client message ID
            msgId (int | str): Message ID to set as delivered
            senderId (int | str): Message sender Id
            thread_id (int | str): User/Group ID to mark as delivered
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            bool: True
            
        Raises:
            ZaloAPIException: If request failed
        """
        destination_id = "0" if thread_type == ThreadType.USER else thread_id
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30
        }
        
        payload = {
            "params": {
                "msgInfos": {
                    "seen": 0,
                    "data": [{
                        "cmi": str(cliMsgId),
                        "gmi": str(msgId),
                        "si": str(senderId),
                        "di": str(destination_id),
                        "mt": method,
                        "st": 3,
                        "at": 0,
                        "ts": str(_util.now())
                    }]
                }
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-chat3-wpa.chat.zalo.me/api/message/deliveredv2"
            payload["params"]["msgInfos"]["data"][0]["cmd"] = 501
        else:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/deliveredv2"
            payload["params"]["msgInfos"]["data"][0]["cmd"] = 521
            payload["params"]["msgInfos"]["grid"] = str(destination_id)
            payload["params"]["imei"] = self._imei
        
        payload["params"]["msgInfos"] = json.dumps(payload["params"]["msgInfos"])
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            self.onMessageDelivered(msgId, thread_id, thread_type, _util.now())
            return True
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    def markAsRead(
        self,
        msgId,
        cliMsgId,
        senderId,
        thread_id,
        thread_type,
        method="webchat"
    ):
        """Mark a message as read.
        
        Args:
            cliMsgId (int | str): Client message ID
            msgId (int | str): Message ID to set as delivered
            senderId (int | str): Message sender Id
            thread_id (int | str): User/Group ID to mark as read
            thread_type (ThreadType): ThreadType.USER, ThreadType.GROUP
            
        Returns:
            bool: True
            
        Raises:
            ZaloAPIException: If request failed
        """
        destination_id = "0" if thread_type == ThreadType.USER else thread_id
        
        params = {
            "zpw_ver": 645,
            "zpw_type": 30,
            "nretry": 0
        }
        
        payload = {
            "params": {
                "msgInfos": {
                    "data": [{
                        "cmi": str(cliMsgId),
                        "gmi": str(msgId),
                        "si": str(senderId),
                        "di": str(destination_id),
                        "mt": method,
                        "st": 3,
                        "ts": str(_util.now())
                    }]
                },
                "imei": self._imei
            }
        }
        
        if thread_type == ThreadType.USER:
            url = "https://tt-chat1-wpa.chat.zalo.me/api/message/seenv2"
            payload["params"]["msgInfos"]["data"][0]["at"] = 7
            payload["params"]["msgInfos"]["data"][0]["cmd"] = 501
            payload["params"]["senderId"] = str(destination_id)
        elif thread_type == ThreadType.GROUP:
            url = "https://tt-group-wpa.chat.zalo.me/api/group/seenv2"
            payload["params"]["msgInfos"]["data"][0]["at"] = 0
            payload["params"]["msgInfos"]["data"][0]["cmd"] = 511
            payload["params"]["grid"] = str(destination_id)
        else:
            raise ZaloUserError("Thread type is invalid")
        
        payload["params"]["msgInfos"] = json.dumps(payload["params"]["msgInfos"])
        payload["params"] = self._encode(payload["params"])
        
        response = self._post(url, params=params, data=payload)
        data = response.json()
        results = data.get("data") if data.get("error_code") == 0 else None
        if results:
            self.onMarkedSeen(msgId, thread_id, thread_type, _util.now())
            return True
            
        error_code = data.get("error_code")
        error_message = data.get("error_message") or data.get("data")
        raise ZaloAPIException(f"Error #{error_code} when sending requests: {error_message}")
    
    """
    LISTEN METHODS
    """
    
    def _listen_req(self, delay=1, thread=False, reconnect=5):
        self._condition.clear()
        HasRead = set()
        
        try:
            self.onListening()
            self._listening = True
            
            while not self._condition.is_set():
                ListenTime = int((time.time() - 10) * 1000)
                
                if len(HasRead) > 10000000:
                    HasRead.clear()
                
                messages = self.getLastMsgs()
                groupmsg = messages.groupMsgs
                messages = messages.msgs
                
                for message in messages + groupmsg:
                    if int(message["ts"]) >= ListenTime and message["msgId"] not in HasRead:
                        HasRead.add(message["msgId"])
                        msgObj = MessageObject.fromDict(message, None)
                        if message in messages:
                            
                            [
                                pool.submit(self.onMessage, msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.uidFrom) or msgObj.idTo), ThreadType.USER)
                                if thread else
                                self.onMessage(msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.uidFrom) or msgObj.idTo), ThreadType.USER)
                            ]
                        
                        else:
                            
                            [
                                pool.submit(self.onMessage, msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.idTo) or self.uid), ThreadType.GROUP)
                                if thread else
                                self.onMessage(msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.idTo) or self.uid), ThreadType.GROUP)
                            ]
                
                time.sleep(delay)
        
        except KeyboardInterrupt:
            self._condition.set()
            print("\x1b[1K")
            logger.warning("Stop Listen Because KeyboardInterrupt Exception!")
            pid = os.getpid()
            os.kill(pid, signal.SIGTERM)
        
        except Exception as e:
            self._condition.set()
            self._listening = False
            self.onErrorCallBack(e)
            if self.run_forever:
                while not self._listening:
                    try:
                        logger.debug("Run forever mode is enabled, trying to reconnect...")
                        self._listen_req(delay, thread, reconnect)
                    except:
                        pass
                    
                    time.sleep(reconnect)
        
        finally:
            self._listening = False
    
    def _fix_recv(self):
        old_timestamp = int(time.time())
        time.sleep(50 * 60)
        self._start_fix = True
        self._condition.set()
    
    def _listen_ws(self, thread=False, reconnect=5):
        self._condition.clear()
        params = {"zpw_ver": 645, "zpw_type": 30, "t": _util.now()}
        url = self._state._config["zpw_ws"][0] + "?" + urllib.parse.urlencode(params)
        
        user_agent = self._state._headers.get("User-Agent") or _util.HEADERS["User-Agent"]
        raw_cookies = _util.dict_to_raw_cookies(self._state.get_cookies())
        
        if not raw_cookies:
            raise ZaloUserError("Unable to load cookies! Probably due to incorrect cookie format (cookies must be dict)")
        
        headers = {
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Connection": "Upgrade",
            "Host": urllib.parse.urlparse(url).netloc,
            "Origin": "https://chat.zalo.me",
            "Pargma": "no-cache",
            "Sec-Websocket-Extensions": "permessage-deflate; client_max_window_bits",
            "Sec-Websocket-Version": "13",
            "Upgrade": "websocket",
            "User-Agent": user_agent,
            "Cookie": raw_cookies
        }
        
        with connect(url, additional_headers=headers) as ws:
            pool.submit(self._fix_recv)
            self.onListening()
            self._listening = True
            while not self._condition.is_set():
                try:
                    data = ws.recv()
                    if not isinstance(data, bytes):
                        continue
                    
                    encodedHeader = data[:4]
                    n, cmd, s = _util.getHeader(encodedHeader)
                    
                    dataToDecode = data[4:]
                    decodedData = dataToDecode.decode("utf-8")
                    if not decodedData:
                        continue
                    
                    parsed = json.loads(decodedData)
                    if n == 1 and cmd == 1 and s == 1 and "key" in parsed:
                        self.ws_key = parsed["key"]
                        continue
                    
                    if not hasattr(self, "ws_key"):
                        logger.error("Unable to decrypt data because key not found")
                        continue
                    
                    parsedData = _util.zws_decode(parsed, self.ws_key)
                    if n == 1 and cmd == 3000 and s == 0:
                        logger.warning("Another connection is opened, closing this one")
                        ws.close()
                    
                    elif n == 1 and cmd == 501 and s == 0:
                        parsedData = _util.zws_decode(parsed, self.ws_key)
                        userMsgs = parsedData["data"]["msgs"]
                        
                        for message in userMsgs:
                            msgObj = MessageObject.fromDict(message, None)
                            [
                                pool.submit(self.onMessage, msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.uidFrom) or msgObj.idTo), ThreadType.USER)
                                if thread else
                                self.onMessage(msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.uidFrom) or msgObj.idTo), ThreadType.USER)
                            ]
                    
                    elif n == 1 and cmd == 521 and s == 0:
                        groupMsgs = parsedData["data"]["groupMsgs"]
                        
                        try:
                            for message in groupMsgs:
                                messages = self.getRecentGroup(message["idTo"])["groupMsgs"]
                                message = next((msg for msg in messages if msg["msgId"] == message["msgId"]), message)
                        except:
                            pass
                            
                        msgObj = MessageObject.fromDict(message, None)
                        [
                            pool.submit(self.onMessage, msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.idTo) or self.uid), ThreadType.GROUP)
                            if thread else
                            self.onMessage(msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.idTo) or self.uid), ThreadType.GROUP)
                        ]
                    
                    elif n == 1 and cmd in [502, 522, 504, 524] and s == 0:
                        # Delivereds, Seen, Clear Unread, ...
                        continue
                    
                    elif n == 1 and cmd in [502, 522, 504, 524] and s == 0:
                        # Delivereds, Seen, Clear Unread, ...
                        continue
                    
                    elif n == 1 and cmd == 602 and s == 0:
                        # Typing Event
                        continue
                    
                    elif n == 1 and cmd == 601 and s == 0:
                        controls = parsedData["data"].get("controls", [])
                        for control in controls:
                            if control["content"]["act_type"] == "file_done":
                                pool.submit(self.fileEvent, control)
                            if control["content"]["act_type"] == "group":
                                if control["content"]["act"] == "join_reject":
                                    continue
                                
                                groupEventData = json.loads(control["content"]["data"]) if isinstance(control["content"]["data"], str) else control["content"]["data"]
                                groupEventType = _util.getGroupEventType(control["content"]["act"])
                                event_data = EventObject.fromDict(groupEventData)
                                event_type = groupEventType
                                [
                                    pool.submit(self.onEvent, event_data, event_type)
                                    if thread else
                                    self.onEvent(event_data, event_type)
                                ]
                        
                        continue
                    
                    elif cmd == 612:
                        reacts = parsedData["data"].get("reacts", [])
                        reactGroups = parsedData["data"].get("reactGroups", [])
                        
                        for react in reacts:
                            react["content"] = json.loads(react["content"])
                            msgObj = MessageObject.fromDict(react, None)
                            [
                                pool.submit(self.onMessage, msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.uidFrom) or msgObj.idTo), ThreadType.USER)
                                if thread else
                                self.onMessage(msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.uidFrom) or msgObj.idTo), ThreadType.USER)
                            ]
                        
                        for reactGroup in reactGroups:
                            reactGroup["content"] = json.loads(reactGroup["content"])
                            msgObj = MessageObject.fromDict(reactGroup, None)
                            [
                                pool.submit(self.onMessage, msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.idTo) or self.uid), ThreadType.GROUP)
                                if thread else
                                self.onMessage(msgObj.msgId, str(int(msgObj.uidFrom) or self.uid), msgObj.content, msgObj, str(int(msgObj.idTo) or self.uid), ThreadType.GROUP)
                            ]
                    
                    else:
                        continue
                
                except KeyboardInterrupt:
                    self._condition.set()
                    ws.close()
                    print("\x1b[1K")
                    logger.warning("Stop Listen Because KeyboardInterrupt Exception!")
                    pid = os.getpid()
                    os.kill(pid, signal.SIGTERM)
                
                except (websockets.ConnectionClosedOK, websockets.exceptions.ConnectionClosedOK):
                    self._condition.set()
                    ws.close()
                    break
                
                except (websockets.ConnectionClosedError, websockets.exceptions.ConnectionClosedError):
                    self._start_fix = True
                    self._condition.set()
                    ws.close()
                
                except Exception as e:
                    if str(e) == "sent 1000 (OK); then received 1000 (OK) NORMAL_CLOSURE":
                        pass
                    
                    else:
                        self._listening = False
                        self._start_fix = False
                        self._condition.set()
                        ws.close()
                        self.onErrorCallBack(e)
                        if self.run_forever:
                            while not self._listening:
                                try:
                                    logger.debug("Run forever mode is enabled, trying to reconnect...")
                                    self._listen_ws(thread, reconnect)
                                except:
                                    pass
                                
                                time.sleep(reconnect)
                
                finally:
                    self._listening = False
        
        if self._start_fix:
            logger.debug("Reconnecting websocket because of interruption...")
            self._start_fix = False
            self._listen_ws(thread, reconnect)
    
    def startListening(self, delay=1, thread=False, type="websocket", reconnect=5):
        """Start listening from an external event loop.
        
        Args:
            delay (int): Delay time each time fetching a message
            thread (bool): Handle messages within the thread (Default: False)
            type (str): Type of listening (Default: websocket)
            reconnect (int): Delay interval when reconnecting
        
        Raises:
            ZaloAPIException: If request failed
        """
        if str(type).lower() == "websocket":
            
            if self._state._config.get("zpw_ws"):
                self._listen_ws(thread, reconnect)
                
            else:
                logger.debug("WebSocket url not found. Listen will switch to `requests` mode")
                self._listen_req(delay, thread)
        
        elif str(type).lower() == "requests":
            self._listen_req(delay, thread)
        
        else:
            raise ZaloUserError("Invalid listen type, only `websocket` or `requests`")
    
    def stopListening(self):
        """Stop the listening loop in a thread-safe manner."""
        if not self.listening:
            logger.warning("Listener is not running.")
            return

        self.listening = False
        self._condition.set()

        if hasattr(self, "_ws") and self._ws:
            try:
                self._ws.close()
                logger.debug("WebSocket connection closed.")
            except Exception as e:
                logger.error(f"Error while closing WebSocket: {e}")

        if self._listen_thread and self._listen_thread.is_alive():
            self._listen_thread.join()
            self._listen_thread = None

        if hasattr(self, "_threads") and self._threads:
            for thread_name, thread in list(self._threads.items()):
                if thread.is_alive():
                    self._thread_events[thread_name].set()
                    thread.join()
                    logger.debug(f"Thread '{thread_name}' stopped.")
            self._threads.clear()
            self._thread_events.clear()

        logger.debug("Listening loop stopped.")
    
    def listen(self, delay=1, thread=False, type="websocket", run_forever=False, reconnect=5):
        """Initialize and runs the listening loop continually.
        
        Args:
            delay (int): Delay time for each message fetch (Default: 1)
            thread (bool): Handle messages within the thread (Default: False)
            type (str): Type of listening (Default: websocket)
            reconnect (int): Delay interval when reconnecting
        """
        self.run_forever = run_forever
        self.startListening(delay, thread, type, reconnect)
        
    """
    END LISTEN METHODS
    """
    
    """
    EVENTS
    """
    
    def onLoggingIn(self, phone=None):
        """Called when the client is logging in.
            
        Args:
            phone: The phone number of the client
        """
        logger.debug("Logging in {}...".format(phone))
        
    def onLoggedIn(self, phone=None):
        """Called when the client is successfully logged in.
            
        Args:
            phone: The phone number of the client
        """
        logger.login("Login of {} successful.".format(phone))
    
    def onListening(self):
        """Called when the client is listening."""
        logger.debug("Listening...")
    
    def onMessage(
        self,
        mid=None,
        author_id=None,
        message=None,
        message_object=None,
        thread_id=None,
        thread_type=ThreadType.USER
    ):
        """Called when the client is listening, and somebody sends a message.

        Args:
            mid: The message ID
            author_id: The ID of the author
            message: The message content of the author
            message_object: The message (As a `Message` object)
            thread_id: Thread ID that the message was sent to.
            thread_type (ThreadType): Type of thread that the message was sent to.
        """
        logger.info("{} from {} in {}".format(message, thread_id, thread_type.name))
    
    def onEvent(self, event_data, event_type):
        """Called when the client listening, and some events occurred.

        Args:
            event_data (EventObject): Event data (As a `EventObject` object)
            event_type (EventType/GroupEventType): Event Type
        """
    
    def onMessageDelivered(
        self,
        msg_ids=None,
        thread_id=None,
        thread_type=ThreadType.USER,
        ts=None
    ):
        """Called when the client is listening, and the client has successfully marked messages as delivered.
        
        Args:
            msg_ids: The messages that are marked as delivered
            thread_id: Thread ID that the action was sent to
            thread_type (ThreadType): Type of thread that the action was sent to
            ts: A timestamp of the action
        """
        logger.info(
            "Marked messages {} as delivered in [({}, {})] at {}.".format(
                msg_ids, thread_id, thread_type.name, int(ts / 1000)
            )
        )

    def onMarkedSeen(
        self,
        msg_ids=None,
        thread_id=None,
        thread_type=ThreadType.USER,
        ts=None
    ):
        """Called when the client is listening, and the client has successfully marked messages as read/seen.
        
        Args:
            msg_ids: The messages that are marked as read/seen
            thread_id: Thread ID that the action was sent to
            thread_type (ThreadType): Type of thread that the action was sent to
            ts: A timestamp of the action
        """
        logger.info(
            "Marked messages {} as seen in [({}, {})] at {}.".format(
                msg_ids, thread_id, thread_type.name, int(ts / 1000)
            )
        )
    
    def onErrorCallBack(self, error, ts=int(time.time())):
        """Called when the module has some error.
        
        Args:
            error: Description of the error
            ts: A timestamp of the error (Default: auto)
        """
        logger.error(f"An error occurred at {ts}: {error}")
        print(traceback.format_exc())
    
    """
    END EVENTS
    """