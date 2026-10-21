import os
import requests
from .sticker_utils import detect_file_type, get_temp_dir


def download_media(url, unique_id, prefix="media"):
    temp_dir = get_temp_dir()
    temp_file = os.path.join(temp_dir, f"{prefix}_{unique_id}.tmp")
    
    try:
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        with open(temp_file, "wb") as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
        
        file_type = detect_file_type(temp_file)
        ext_map = {
            "webp": ".webp",
            "gif": ".gif",
            "png": ".png",
            "jpg": ".jpg",
            "mp4": ".mp4"
        }
        ext = ext_map.get(file_type, ".webp")
        final_file = os.path.join(temp_dir, f"{prefix}_{unique_id}{ext}")
        
        os.rename(temp_file, final_file)
        return final_file
        
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise Exception(f"Lỗi khi download media: {str(e)}")