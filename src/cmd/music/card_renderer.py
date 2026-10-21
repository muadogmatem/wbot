import os
import random
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "asset", "fonts")

PLATFORM_NAMES = {
    "nhaccuatui": "NhacCuaTui",
    "soundcloud": "SoundCloud",
    "youtube": "YouTube",
    "spotify": "Spotify",
    "zing": "ZingMP3",
}


def _get_font(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except:
        return ImageFont.load_default()


def _load_cover(url):
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        r.raise_for_status()
        cover = Image.open(BytesIO(r.content)).convert("RGBA")
        size = min(cover.width, cover.height)
        left = (cover.width - size) // 2
        top = (cover.height - size) // 2
        return cover.crop((left, top, left + size, top + size))
    except:
        return None


def _format_duration(sec):
    if not sec:
        return "0:00"
    return f"{sec // 60}:{sec % 60:02d}"


def _detect_platform(track):
    if track.get("platform"):
        return track["platform"]
    if track.get("songKey"):
        return "nhaccuatui"
    if track.get("playback_count") is not None or track.get("likes_count") is not None:
        return "soundcloud"
    track_id = str(track.get("id", ""))
    if "soundcloud.com" in track_id:
        return "soundcloud"
    if "nhaccuatui" in track_id:
        return "nhaccuatui"
    return "unknown"


def _create_background(width, height):
    img = Image.new('RGB', (width, height), (18, 18, 28))
    
    colors = [
        (255, 100, 150, 45),
        (100, 180, 255, 40),
        (255, 180, 100, 35),
        (180, 120, 255, 40),
        (100, 255, 180, 35),
        (255, 130, 80, 38),
        (120, 200, 255, 42),
    ]
    
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    num_orbs = random.randint(4, 7)
    
    for _ in range(num_orbs):
        x = random.randint(0, width)
        y = random.randint(0, height)
        color = random.choice(colors)
        size = random.randint(120, 300)
        
        for r in range(size, 0, -3):
            alpha = int(color[3] * (r / size) ** 0.5)
            draw.ellipse(
                [x - r, y - r, x + r, y + r],
                fill=(color[0], color[1], color[2], alpha)
            )
    
    overlay = overlay.filter(ImageFilter.GaussianBlur(60))
    img = Image.alpha_composite(img.convert('RGBA'), overlay)
    
    return img


def _draw_glass_card(img, x, y, w, h, radius=20):
    card_area = img.crop((x, y, x + w, y + h))
    blurred = card_area.filter(ImageFilter.GaussianBlur(10))
    
    tint = Image.new('RGBA', (w, h), (255, 255, 255, 22))
    blurred = Image.alpha_composite(blurred.convert('RGBA'), tint)
    
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    
    border = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=radius,
        outline=(255, 255, 255, 50), width=1
    )
    blurred = Image.alpha_composite(blurred, border)
    
    result = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    result.paste(blurred, (0, 0), mask)
    
    img.paste(result, (x, y), result)
    return img


def _draw_rounded_cover(img, cover, x, y, size, radius=12):
    if not cover:
        return img
    
    cover = cover.resize((size, size), Image.LANCZOS)
    
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    
    img.paste(cover, (x, y), mask)
    return img


def draw_search_card(songs, keyword, cache_ttl=60):
    CARD_W, CARD_H = 620, 110
    PADDING = 30
    HEADER_H = 80
    FOOTER_H = 55
    GAP = 16
    COVER_SIZE = 80
    
    COLS = 1 if len(songs) <= 5 else 2
    ROWS = (len(songs) + COLS - 1) // COLS
    
    WIDTH = CARD_W * COLS + PADDING * (COLS + 1)
    HEIGHT = HEADER_H + (CARD_H + GAP) * ROWS + FOOTER_H + PADDING
    
    font_header = _get_font("BeVietnamPro-Bold.ttf", 30)
    font_title = _get_font("BeVietnamPro-SemiBold.ttf", 19)
    font_sub = _get_font("BeVietnamPro-Regular.ttf", 15)
    font_small = _get_font("BeVietnamPro-Regular.ttf", 14)
    font_index = _get_font("BeVietnamPro-Bold.ttf", 20)
    
    img = _create_background(WIDTH, HEIGHT)
    draw = ImageDraw.Draw(img)
    
    header_text = keyword.upper()
    header_w = font_header.getlength(header_text)
    draw.text(
        ((WIDTH - header_w) / 2, 22),
        header_text, font=font_header, fill=(255, 255, 255)
    )
    
    sub_text = f"{len(songs)} kết quả"
    sub_w = font_small.getlength(sub_text)
    draw.text(
        ((WIDTH - sub_w) / 2, 56),
        sub_text, font=font_small, fill=(180, 180, 200)
    )
    
    for idx, s in enumerate(songs):
        row = idx // COLS
        col = idx % COLS
        cx = PADDING + col * (CARD_W + PADDING)
        cy = HEADER_H + row * (CARD_H + GAP)
        
        img = _draw_glass_card(img, cx, cy, CARD_W, CARD_H, radius=18)
        draw = ImageDraw.Draw(img)
        
        cover = _load_cover(s.get("thumbnail", ""))
        cover_x = cx + 15
        cover_y = cy + (CARD_H - COVER_SIZE) // 2
        img = _draw_rounded_cover(img, cover, cover_x, cover_y, COVER_SIZE, radius=14)
        draw = ImageDraw.Draw(img)
        
        text_x = cover_x + COVER_SIZE + 20
        text_w = CARD_W - COVER_SIZE - 100
        
        title_h = 24
        sub_h = 20
        total_text_h = title_h + sub_h + 8
        text_start_y = cy + (CARD_H - total_text_h) // 2
        
        title = s["title"]
        if font_title.getlength(title) > text_w:
            while font_title.getlength(title + "...") > text_w and len(title) > 0:
                title = title[:-1]
            title += "..."
        
        draw.text((text_x, text_start_y), title, font=font_title, fill=(255, 255, 255))
        
        artist = s["artist"]
        dur = _format_duration(s.get("duration", 0))
        info = f"{artist}  •  {dur}"
        
        if font_sub.getlength(info) > text_w:
            while font_sub.getlength(artist + "...  •  " + dur) > text_w and len(artist) > 0:
                artist = artist[:-1]
            info = f"{artist}...  •  {dur}"
        
        draw.text((text_x, text_start_y + title_h + 8), info, font=font_sub, fill=(160, 160, 180))
        
        idx_text = str(idx + 1)
        idx_w = font_index.getlength(idx_text)
        idx_x = cx + CARD_W - 38
        idx_y = cy + (CARD_H - 24) // 2
        draw.text((idx_x - idx_w / 2, idx_y), idx_text, font=font_index, fill=(200, 200, 220))
    
    footer_y = HEIGHT - FOOTER_H + 10
    footer_text = f"Reply số để chọn  •  Hết hạn {cache_ttl}s"
    footer_w = font_small.getlength(footer_text)
    draw.text(
        ((WIDTH - footer_w) / 2, footer_y),
        footer_text, font=font_small, fill=(140, 140, 160)
    )
    
    return img


def draw_detail_card(track, cover_url):
    WIDTH, HEIGHT = 580, 240
    PADDING = 30
    COVER_SIZE = 140
    
    font_title = _get_font("BeVietnamPro-Bold.ttf", 26)
    font_artist = _get_font("BeVietnamPro-Medium.ttf", 18)
    font_info = _get_font("BeVietnamPro-Regular.ttf", 15)
    
    img = _create_background(WIDTH, HEIGHT)
    
    card_x = PADDING
    card_y = PADDING
    card_w = WIDTH - PADDING * 2
    card_h = HEIGHT - PADDING * 2
    
    img = _draw_glass_card(img, card_x, card_y, card_w, card_h, radius=22)
    draw = ImageDraw.Draw(img)
    
    cover = _load_cover(cover_url)
    cover_x = card_x + 22
    cover_y = card_y + (card_h - COVER_SIZE) // 2
    img = _draw_rounded_cover(img, cover, cover_x, cover_y, COVER_SIZE, radius=16)
    draw = ImageDraw.Draw(img)
    
    text_x = cover_x + COVER_SIZE + 25
    text_w = card_w - COVER_SIZE - 70
    
    title_h = 32
    artist_h = 24
    gap = 10
    content_h = title_h + artist_h + gap
    content_start_y = card_y + (card_h - content_h - 40) // 2
    
    title = track["title"]
    if font_title.getlength(title) > text_w:
        while font_title.getlength(title + "...") > text_w and len(title) > 0:
            title = title[:-1]
        title += "..."
    
    draw.text((text_x, content_start_y), title, font=font_title, fill=(255, 255, 255))
    
    artist = track["artist"]
    if font_artist.getlength(artist) > text_w:
        while font_artist.getlength(artist + "...") > text_w and len(artist) > 0:
            artist = artist[:-1]
        artist += "..."
    
    draw.text((text_x, content_start_y + title_h + gap), artist, font=font_artist, fill=(200, 200, 220))
    
    dur = _format_duration(track.get("duration", 0))
    dur_y = card_y + card_h - 35
    draw.text((text_x, dur_y), dur, font=font_info, fill=(150, 150, 170))
    
    platform_key = _detect_platform(track)
    platform = PLATFORM_NAMES.get(platform_key, platform_key.capitalize())
    platform_w = font_info.getlength(platform)
    platform_x = card_x + card_w - platform_w - 22
    draw.text((platform_x, dur_y), platform, font=font_info, fill=(150, 150, 170))
    
    return img