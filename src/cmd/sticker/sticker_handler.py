import os
import urllib.parse
from .sticker_utils import (
    is_sticker_attach, is_video_attach, get_media_url,
    get_temp_dir, generate_unique_id, cleanup_files
)
from .sticker_converter import StickerConverter
from .sticker_downloader import download_media


class StickerHandler:
    def __init__(self, bot, mo, tid, tt, uid):
        self.bot = bot
        self.mo = mo
        self.tid = tid
        self.tt = tt
        self.uid = uid
        self.converter = StickerConverter()
    
    def process(self, attach_data, flags):
        sticker_type = flags['sticker_type']
        spread = flags['has_spr']
        remove_bg = flags['has_rbg']
        is_sticker = is_sticker_attach(attach_data)
        
        try:
            if flags['has_spin']:
                if flags['has_clone'] and is_sticker:
                    self._handle_spin_clone(attach_data, sticker_type, remove_bg)
                else:
                    self._handle_spin(attach_data, sticker_type, remove_bg)
            elif flags['has_clone'] or is_sticker:
                self._handle_clone(attach_data, sticker_type, spread, remove_bg)
            else:
                self._handle_create(attach_data, sticker_type, spread, remove_bg)
                
        except Exception as e:
            self.bot.style.reply_error(
                f"sticker bj die hoac do m ngoo",
                self.mo, self.tid, self.tt, self.uid, ttl=30000
            )
    
    def _handle_clone(self, attach_data, sticker_type, spread, remove_bg):
        media_url = get_media_url(attach_data)
        if not media_url:
            raise Exception("Không tìm thấy URL của sticker")
        
        if attach_data.get('id') and attach_data.get('catId') and not media_url:
            raise Exception("Sticker Zalo gốc không thể clone. Chỉ hỗ trợ Custom Sticker.")
        
        media_url = urllib.parse.unquote(media_url.replace("\\/", "/"))
        unique_id = generate_unique_id(self.tid)
        temp_file = None
        converted_file = None
        
        try:
            temp_file = download_media(media_url, unique_id, "clone")
            if not temp_file:
                raise Exception("Không thể tải sticker")
            
            converted_file, width, height = self.converter.convert_sticker_to_webp(
                temp_file, unique_id, spread=spread, remove_bg=remove_bg
            )
            
            self._upload_and_send(converted_file, width, height, sticker_type)
            
        finally:
            cleanup_files(temp_file, converted_file)
    
    def _handle_create(self, attach_data, sticker_type, spread, remove_bg):
        media_url = get_media_url(attach_data)
        if not media_url:
            raise Exception("Không tìm thấy URL của media")
        
        media_url = urllib.parse.unquote(media_url.replace("\\/", "/"))
        if "jxl" in media_url:
            media_url = media_url.replace("jxl", "jpg")
        
        unique_id = generate_unique_id(self.tid)
        temp_webp = None
        
        try:
            file_type = "video" if is_video_attach(attach_data) else "image"
            
            temp_webp, width, height = self.converter.convert_media_to_webp(
                media_url, file_type, unique_id, spread=spread, remove_bg=remove_bg
            )
            
            self._upload_and_send(temp_webp, width, height, sticker_type)
            
        finally:
            cleanup_files(temp_webp)
    
    def _handle_spin(self, attach_data, sticker_type, remove_bg):
        media_url = get_media_url(attach_data)
        if not media_url:
            raise Exception("Không tìm thấy URL của media")
        
        media_url = urllib.parse.unquote(media_url.replace("\\/", "/"))
        if "jxl" in media_url:
            media_url = media_url.replace("jxl", "jpg")
        
        unique_id = generate_unique_id(self.tid)
        temp_webp = None
        
        try:
            temp_webp, width, height = self.converter.create_spin_from_url(
                media_url, unique_id, remove_bg=remove_bg
            )
            
            self._upload_and_send(temp_webp, width, height, sticker_type)
            
        finally:
            cleanup_files(temp_webp)
    
    def _handle_spin_clone(self, attach_data, sticker_type, remove_bg):
        media_url = get_media_url(attach_data)
        if not media_url:
            raise Exception("Không tìm thấy URL của sticker")
        
        if attach_data.get('id') and attach_data.get('catId') and not media_url:
            raise Exception("Sticker Zalo gốc không thể clone")
        
        media_url = urllib.parse.unquote(media_url.replace("\\/", "/"))
        unique_id = generate_unique_id(self.tid)
        temp_sticker = None
        temp_webp = None
        
        try:
            temp_sticker = download_media(media_url, unique_id, "spinclone")
            if not temp_sticker:
                raise Exception("Không thể tải sticker")
            
            temp_webp, width, height = self.converter.create_spin_from_file(
                temp_sticker, unique_id, remove_bg=remove_bg
            )
            
            self._upload_and_send(temp_webp, width, height, sticker_type)
            
        finally:
            cleanup_files(temp_sticker, temp_webp)
    
    def _upload_and_send(self, file_path, width, height, sticker_type):
        from zlapi._threads import ThreadType
        
        cloud_id = self.bot._state._config.get("cloud_id")
        if not cloud_id:
            raise Exception("Không tìm thấy cloud_id trong config")
        
        upload_result = self.bot.uploadFile(file_path, cloud_id, ThreadType.USER)
        file_url = upload_result.get("fileUrl")
        if not file_url:
            raise Exception("Không lấy được fileUrl sau khi upload")
        
        sticker_url = f"{file_url}?stickerCreatedBy=LyHoangKhang.ConMeo"
        
        self.bot.sendCustomStickerAI(
            staticImgUrl=sticker_url,
            animationImgUrl=sticker_url,
            width=width,
            height=height,
            thread_id=self.tid,
            thread_type=self.tt,
            pStickerType=sticker_type
        )