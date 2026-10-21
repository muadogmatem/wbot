import os
import re
import subprocess
import json

def parse_stk_flags(message):
    message_lower = message.lower().strip()
    
    flags = {
        'has_clone': False,
        'has_spin': False,
        'has_nor': False,
        'has_spr': False,
        'has_rbg': False,
        'sticker_type': 1
    }
    
    if "clone" in message_lower:
        flags['has_clone'] = True
    if "spin" in message_lower:
        flags['has_spin'] = True
    if "nor" in message_lower:
        flags['has_nor'] = True
        flags['sticker_type'] = 0
    if "spr" in message_lower:
        flags['has_spr'] = True
    if "rbg" in message_lower:
        flags['has_rbg'] = True
    
    return flags


def check_ffmpeg_support():
    try:
        result = subprocess.run(
            ["ffmpeg", "-codecs"], 
            capture_output=True, 
            text=True, 
            check=True,
            timeout=5
        )
        return "libwebp_anim" in result.stdout or "libwebp" in result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def detect_file_type(file_path):
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)
        
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            return "webp"
        elif header[:6] in (b'GIF87a', b'GIF89a'):
            return "gif"
        elif header[:8] == b'\x89PNG\r\n\x1a\n':
            return "png"
        elif header[:3] == b'\xff\xd8\xff':
            return "jpg"
        elif header[4:8] == b'ftyp':
            return "mp4"
        else:
            return "unknown"
    except:
        return "unknown"


def is_sticker_attach(attach_data):
    if not attach_data:
        return False
    if attach_data.get('id') and attach_data.get('catId'):
        return True
    url = attach_data.get('hdUrl') or attach_data.get('href') or attach_data.get('oriUrl') or ''
    url_lower = url.lower()
    if '.webp' in url_lower or 'sticker' in url_lower:
        return True
    return False


def is_video_attach(attach_data):
    if not attach_data:
        return False
    url = attach_data.get('hdUrl') or attach_data.get('href') or attach_data.get('oriUrl') or ''
    url_lower = url.lower()
    params_str = str(attach_data.get("params", "")).lower()
    if ".mp4" in url_lower or "video" in params_str or "video" in url_lower:
        return True
    return False


def get_media_url(attach_data):
    return attach_data.get('hdUrl') or attach_data.get('oriUrl') or attach_data.get('href')


def get_temp_dir():
    script_dir = os.path.dirname(__file__)
    temp_dir = os.path.join(script_dir, 'cache', 'temp')
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def generate_unique_id(thread_id):
    import time
    import random
    return f"{thread_id}_{int(time.time())}_{random.randint(1000, 9999)}"


def cleanup_files(*files):
    for file in files:
        if file and os.path.exists(file):
            try:
                os.remove(file)
            except:
                pass