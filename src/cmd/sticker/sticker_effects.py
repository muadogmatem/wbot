import os
import math
import colorsys
import subprocess
from PIL import Image, ImageDraw, ImageFilter
from .sticker_utils import get_temp_dir, cleanup_files


MAX_FPS = 30
QUALITY = 80


def create_circular_mask(size):
    scale = 4
    large_size = size * scale
    mask = Image.new("L", (large_size, large_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, large_size - 1, large_size - 1), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    return mask


def create_rainbow_border(size, border_width):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = img.load()
    center = size / 2
    outer_radius = size / 2
    inner_radius = size / 2 - border_width
    
    for y in range(size):
        for x in range(size):
            dx = x - center + 0.5
            dy = y - center + 0.5
            distance = math.sqrt(dx * dx + dy * dy)
            
            if inner_radius - 1 <= distance <= outer_radius + 1:
                angle = math.atan2(dy, dx)
                hue = (angle + math.pi) / (2 * math.pi)
                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                
                if distance > outer_radius - 0.5:
                    alpha = max(0, min(255, int(255 * (outer_radius + 0.5 - distance))))
                elif distance < inner_radius + 0.5:
                    alpha = max(0, min(255, int(255 * (distance - inner_radius + 0.5))))
                else:
                    alpha = 255
                
                pixels[x, y] = (int(r * 255), int(g * 255), int(b * 255), alpha)
    
    return img


def create_spin_effect(input_file, unique_id, remove_bg=False):
    from .sticker_converter import StickerConverter
    
    temp_dir = get_temp_dir()
    temp_png = os.path.join(temp_dir, f"spin_{unique_id}.png")
    temp_webp = os.path.join(temp_dir, f"spin_{unique_id}.webp")
    rbg_file = None
    
    canvas_size = 256
    total_size = 240
    border_width = 8
    img_size = total_size - border_width
    
    try:
        working_file = input_file
        
        if remove_bg:
            try:
                converter = StickerConverter()
                rbg_file = converter._remove_background(input_file, f"spin_{unique_id}")
                if rbg_file:
                    working_file = rbg_file
            except:
                pass
        
        img = Image.open(working_file).convert("RGBA")
        w, h = img.size
        crop_size = min(w, h)
        left = (w - crop_size) // 2
        top = (h - crop_size) // 2
        img = img.crop((left, top, left + crop_size, top + crop_size))
        img = img.resize((img_size, img_size), Image.Resampling.LANCZOS)
        
        img_mask = create_circular_mask(img_size)
        img.putalpha(img_mask)
        
        final_img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
        
        rainbow_border = create_rainbow_border(total_size, border_width)
        border_offset = (canvas_size - total_size) // 2
        final_img.paste(rainbow_border, (border_offset, border_offset), rainbow_border)
        
        shadow_size = img_size + 10
        shadow = Image.new("RGBA", (shadow_size, shadow_size), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.ellipse((2, 4, shadow_size - 2, shadow_size), fill=(0, 0, 0, 80))
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        shadow_offset = (canvas_size - shadow_size) // 2
        final_img.paste(shadow, (shadow_offset, shadow_offset), shadow)
        
        img_offset = (canvas_size - img_size) // 2
        final_img.paste(img, (img_offset, img_offset), img)
        final_img.save(temp_png, format="PNG")
        
        result = subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", temp_png,
            "-vf", f"rotate=2*PI*t/4:ow={canvas_size}:oh={canvas_size}:c=none",
            "-t", "4", "-r", str(MAX_FPS),
            "-c:v", "libwebp_anim", "-loop", "0", "-q:v", str(QUALITY),
            "-loglevel", "error",
            temp_webp
        ], capture_output=True, text=True, timeout=120)
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        
        cleanup_files(temp_png)
        return temp_webp, canvas_size, canvas_size
        
    except Exception as e:
        cleanup_files(temp_png, temp_webp)
        raise e
    finally:
        if rbg_file and rbg_file != input_file:
            cleanup_files(rbg_file)