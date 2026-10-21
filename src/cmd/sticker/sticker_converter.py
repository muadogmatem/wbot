import os
import subprocess
import requests
from io import BytesIO
from PIL import Image
from .sticker_utils import (
    get_temp_dir, detect_file_type, check_ffmpeg_support, cleanup_files
)
from .sticker_effects import create_spin_effect


REMBG_API_KEY = "eLkEKH9t13BZ61iA5bkK1KyQ"
MAX_DURATION = 60
MAX_FPS = 30
MAX_FRAMES = 1800
QUALITY = 80


class StickerConverter:
    def __init__(self):
        self.temp_dir = get_temp_dir()
    
    def convert_sticker_to_webp(self, input_path, unique_id, spread=False, remove_bg=False):
        temp_webp = os.path.join(self.temp_dir, f"clone_{unique_id}.webp")
        rbg_file = None
        
        try:
            working_file = input_path
            
            if remove_bg:
                try:
                    rbg_file = self._remove_background(input_path, unique_id)
                    if rbg_file:
                        working_file = rbg_file
                except:
                    pass
            
            is_animated = self._check_animated(working_file)
            
            if is_animated and not remove_bg:
                success = self._convert_animated(working_file, temp_webp, spread)
            else:
                success = self._convert_static(working_file, temp_webp, spread)
            
            if not success or not os.path.exists(temp_webp):
                raise Exception("Không thể convert file")
            
            with Image.open(temp_webp) as img:
                width, height = img.size
            
            return temp_webp, width, height
            
        except Exception as e:
            cleanup_files(temp_webp)
            raise e
        finally:
            if rbg_file and rbg_file != input_path:
                cleanup_files(rbg_file)
    
    def convert_media_to_webp(self, media_url, file_type, unique_id, spread=False, remove_bg=False):
        temp_input = os.path.join(self.temp_dir, f"input_{unique_id}.tmp")
        temp_webp = os.path.join(self.temp_dir, f"output_{unique_id}.webp")
        rbg_file = None
        
        try:
            response = requests.get(media_url, stream=True, timeout=60)
            response.raise_for_status()
            with open(temp_input, "wb") as f:
                for chunk in response.iter_content(8192):
                    f.write(chunk)
            
            working_file = temp_input
            
            if remove_bg:
                try:
                    rbg_file = self._remove_background(temp_input, unique_id)
                    if rbg_file:
                        working_file = rbg_file
                except:
                    pass
            
            real_type = detect_file_type(working_file)
            is_animated = self._check_animated(working_file)
            
            if remove_bg or (real_type not in ["gif", "mp4"] and not is_animated and file_type != "video"):
                success = self._convert_static(working_file, temp_webp, spread)
            else:
                success = self._convert_animated(working_file, temp_webp, spread)
            
            if not success or not os.path.exists(temp_webp):
                raise Exception("Không thể convert file")
            
            with Image.open(temp_webp) as img:
                width, height = img.size
            
            cleanup_files(temp_input)
            return temp_webp, width, height
            
        except Exception as e:
            cleanup_files(temp_input, temp_webp)
            raise e
        finally:
            if rbg_file and rbg_file != temp_input:
                cleanup_files(rbg_file)
    
    def create_spin_from_url(self, media_url, unique_id, remove_bg=False):
        temp_input = os.path.join(self.temp_dir, f"spin_input_{unique_id}")
        
        try:
            response = requests.get(media_url, stream=True, timeout=60)
            response.raise_for_status()
            with open(temp_input, "wb") as f:
                for chunk in response.iter_content(8192):
                    f.write(chunk)
            
            result = self.create_spin_from_file(temp_input, unique_id, remove_bg)
            cleanup_files(temp_input)
            return result
            
        except Exception as e:
            cleanup_files(temp_input)
            raise e
    
    def create_spin_from_file(self, input_file, unique_id, remove_bg=False):
        from .sticker_effects import create_spin_effect
        return create_spin_effect(input_file, unique_id, remove_bg)
    
    def _check_animated(self, file_path):
        file_type = detect_file_type(file_path)
        
        if file_type in ["gif", "mp4"]:
            return True
        
        if file_type == "webp":
            try:
                with Image.open(file_path) as img:
                    return getattr(img, 'n_frames', 1) > 1
            except:
                return False
        
        return False
    
    def _convert_static(self, input_path, output_path, spread=False):
        try:
            with Image.open(input_path).convert("RGBA") as img:
                if spread:
                    w, h = img.size
                    crop_size = min(w, h)
                    left = (w - crop_size) // 2
                    top = (h - crop_size) // 2
                    img = img.crop((left, top, left + crop_size, top + crop_size))
                    img = img.resize((512, 512), Image.Resampling.LANCZOS)
                else:
                    img.thumbnail((512, 512), Image.Resampling.LANCZOS)
                
                img.save(output_path, format="WEBP", quality=QUALITY, lossless=False)
            return True
        except Exception as e:
            print(f"Static convert error: {e}")
            return False
    
    def _convert_animated(self, input_path, output_path, spread=False):
        if not check_ffmpeg_support():
            return self._convert_animated_pil(input_path, output_path, spread)
        
        try:
            if spread:
                vf_filter = f"crop='min(iw,ih)':'min(iw,ih)',scale=512:512:flags=lanczos,fps={MAX_FPS}"
            else:
                vf_filter = f"scale='min(512,iw)':'min(512,ih)':force_original_aspect_ratio=decrease,fps={MAX_FPS}"
            
            cmd = [
                "ffmpeg", "-y",
                "-i", input_path,
                "-t", str(MAX_DURATION),
                "-vf", vf_filter,
                "-c:v", "libwebp_anim",
                "-loop", "0", "-an",
                "-lossless", "0", "-q:v", str(QUALITY),
                "-compression_level", "4",
                "-loglevel", "error",
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return True
            
            return self._convert_animated_pil(input_path, output_path, spread)
            
        except Exception as e:
            print(f"FFmpeg error: {e}")
            return self._convert_animated_pil(input_path, output_path, spread)
    
    def _convert_animated_pil(self, input_path, output_path, spread=False):
        try:
            with Image.open(input_path) as img:
                if not hasattr(img, 'n_frames') or img.n_frames <= 1:
                    return self._convert_static(input_path, output_path, spread)
                
                frames = []
                durations = []
                
                total_frames = min(img.n_frames, MAX_FRAMES)
                
                for i in range(total_frames):
                    img.seek(i)
                    frame = img.copy().convert("RGBA")
                    
                    if spread:
                        w, h = frame.size
                        crop_size = min(w, h)
                        left = (w - crop_size) // 2
                        top = (h - crop_size) // 2
                        frame = frame.crop((left, top, left + crop_size, top + crop_size))
                        frame = frame.resize((512, 512), Image.Resampling.LANCZOS)
                    else:
                        frame.thumbnail((512, 512), Image.Resampling.LANCZOS)
                    
                    frames.append(frame)
                    durations.append(img.info.get('duration', 33))
                
                if len(frames) > 1:
                    frames[0].save(
                        output_path, format="WEBP", save_all=True,
                        append_images=frames[1:], duration=durations,
                        loop=0, quality=QUALITY
                    )
                else:
                    frames[0].save(output_path, format="WEBP", quality=QUALITY)
                
                return True
        except Exception as e:
            print(f"PIL convert error: {e}")
            return False
    
    def _remove_background(self, input_path, unique_id):
        if not REMBG_API_KEY or REMBG_API_KEY == "YOUR_API_KEY_HERE":
            raise Exception("Chưa cấu hình API key cho remove.bg")
        
        output_path = os.path.join(self.temp_dir, f"rbg_{unique_id}.png")
        
        try:
            if self._check_animated(input_path):
                with Image.open(input_path) as img:
                    first_frame = img.convert("RGBA")
                    temp_static = os.path.join(self.temp_dir, f"rbg_temp_{unique_id}.png")
                    first_frame.save(temp_static, format="PNG")
                    result = self._call_removebg_api(temp_static, output_path)
                    cleanup_files(temp_static)
                    return result
            else:
                return self._call_removebg_api(input_path, output_path)
                
        except Exception as e:
            cleanup_files(output_path)
            raise e
    
    def _call_removebg_api(self, input_path, output_path):
        try:
            with open(input_path, 'rb') as f:
                img_bytes = f.read()
            
            headers = {"X-API-Key": REMBG_API_KEY}
            files = {"image_file": ("image.png", img_bytes)}
            
            response = requests.post(
                "https://api.remove.bg/v1.0/removebg",
                headers=headers,
                files=files,
                timeout=60
            )
            
            if response.status_code != 200:
                error_msg = response.text[:200] if response.text else "Unknown error"
                raise Exception(f"Remove.bg API error {response.status_code}: {error_msg}")
            
            img = Image.open(BytesIO(response.content)).convert("RGBA")
            img.save(output_path, format="PNG")
            return output_path
            
        except Exception as e:
            raise Exception(f"Lỗi khi xóa nền: {str(e)}")