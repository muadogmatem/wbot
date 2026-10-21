import os
import random
import requests
from io import BytesIO
from math import ceil
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "asset", "fonts")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "asset", "temp")
os.makedirs(TEMP_DIR, exist_ok=True)


def _get_font(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except:
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, "arial.ttf"), size)
        except:
            return ImageFont.load_default()


def _font(size, bold=False):
    if bold:
        names = ["BeVietnamPro-Bold.ttf", "vnpbold.ttf", "arial.ttf"]
    else:
        names = ["BeVietnamPro-Regular.ttf", "Roboto-Regular.ttf", "arial.ttf"]
    for n in names:
        p = os.path.join(FONT_DIR, n)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except:
                pass
    return ImageFont.load_default()


def _text_width(draw, text, font):
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]
    except:
        try:
            return int(font.getlength(text))
        except:
            return len(text) * 10


def _fit_text(draw, text, font, max_w):
    if _text_width(draw, text, font) <= max_w:
        return text
    for i in range(len(text), 0, -1):
        t = text[:i] + ".."
        if _text_width(draw, t, font) <= max_w:
            return t
    return text[:3] + ".."


def _create_background(width, height):
    img = Image.new("RGB", (width, height), (18, 18, 28))
    colors = [
        (255, 100, 150, 45), (100, 180, 255, 40), (255, 180, 100, 35),
        (180, 120, 255, 40), (100, 255, 180, 35), (255, 130, 80, 38),
        (120, 200, 255, 42),
    ]
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(random.randint(4, 7)):
        x = random.randint(0, width)
        y = random.randint(0, height)
        color = random.choice(colors)
        size = random.randint(120, 300)
        for r in range(size, 0, -3):
            alpha = int(color[3] * (r / size) ** 0.5)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(color[0], color[1], color[2], alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(60))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _draw_glass_card(img, x, y, w, h, radius=20):
    card_area = img.crop((x, y, x + w, y + h))
    blurred = card_area.filter(ImageFilter.GaussianBlur(10))
    tint = Image.new("RGBA", (w, h), (255, 255, 255, 22))
    blurred = Image.alpha_composite(blurred.convert("RGBA"), tint)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    border = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, outline=(255, 255, 255, 50), width=1)
    blurred = Image.alpha_composite(blurred, border)
    result = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    result.paste(blurred, (0, 0), mask)
    img.paste(result, (x, y), result)
    return img


def _zalo_webpc_url(item, size=130):
    sticker_id = item.get("id") or item.get("stickerId") or item.get("eid")
    if not sticker_id:
        return None
    return f"https://zalo-api.zadn.vn/api/emoticon/sticker/webpc?eid={sticker_id}&size={size}"


def _sticker_url_candidates(item):
    urls = []
    for sz in [130, 100]:
        url = _zalo_webpc_url(item, sz)
        if url:
            urls.append(url)
    for key in ["url", "spriteUrl", "sUrl", "stickerUrl"]:
        v = item.get(key)
        if v and isinstance(v, str) and v.startswith("http"):
            urls.append(v)
    return urls


def _download_sticker_image(url, size):
    try:
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        return img
    except:
        return None


def draw_sticker_list_canvas(stickers, cid, save_path):
    visible = stickers
    count = max(1, len(visible))

    if count <= 20:
        cols, card_w = 5, 220
    else:
        cols = max(6, min(12, ceil(count ** 0.5)))
        card_w = max(92, min(180, int(1320 / cols)))

    card_h = card_w
    gap = max(10, int(card_w * 0.14))
    margin = max(28, int(card_w * 0.32))
    header_h = max(110, int(card_w * 0.86))
    rows = max(1, ceil(len(visible) / cols))
    width = margin * 2 + cols * card_w + (cols - 1) * gap
    height = margin + header_h + rows * card_h + (rows - 1) * gap + margin

    canvas = _create_background(width, height)
    draw = ImageDraw.Draw(canvas)

    title_font = _font(max(42, min(74, int(card_w * 0.34))), True)
    sub_font = _font(max(18, min(28, int(card_w * 0.13))))
    number_font = _font(max(15, min(23, int(card_w * 0.105))), True)

    title = "STICKER LIST"
    tw = _text_width(draw, title, title_font)
    draw.text(((width - tw) // 2 + 3, margin + 3), title, font=title_font, fill=(0, 0, 0, 60))
    draw.text(((width - tw) // 2, margin), title, font=title_font, fill=(255, 255, 255, 255))

    subtitle = f"Reply so de gui sticker | Pack {cid} | Total {len(stickers)} | 0 de huy"
    sw = _text_width(draw, subtitle, sub_font)
    draw.text(((width - sw) // 2, margin + int(card_w * 0.45)), subtitle, font=sub_font, fill=(180, 180, 200, 255))

    for idx, item in enumerate(visible):
        col, row = idx % cols, idx // cols
        x = margin + col * (card_w + gap)
        y = margin + header_h + row * (card_h + gap)

        canvas = _draw_glass_card(canvas, x, y, card_w, card_h, radius=max(18, int(card_w * 0.15)))
        draw = ImageDraw.Draw(canvas)

        thumb_size = int(card_w * 0.8)
        thumb_x = x + (card_w - thumb_size) // 2
        thumb_y = y + (card_h - thumb_size) // 2

        img = None
        for candidate in _sticker_url_candidates(item):
            img = _download_sticker_image(candidate, max(80, int(thumb_size * 0.84)))
            if img:
                break
        if img:
            canvas.alpha_composite(img, (thumb_x + (thumb_size - img.width) // 2, thumb_y + (thumb_size - img.height) // 2))
        else:
            sid = str(item.get("id") or item.get("stickerId") or item.get("eid") or "?")
            tiny_font = _font(max(12, int(card_w * 0.09)), True)
            label = _fit_text(draw, sid, tiny_font, thumb_size - 18)
            lw = _text_width(draw, label, tiny_font)
            draw.text((thumb_x + (thumb_size - lw) / 2, thumb_y + thumb_size / 2 - 12), label, font=tiny_font, fill=(200, 200, 220, 230))

        badge = str(idx + 1)
        badge_size = max(24, int(card_w * 0.155))
        draw.rounded_rectangle(
            (x + 10, y + 10, x + 10 + badge_size, y + 10 + badge_size),
            max(8, badge_size // 3), fill=(60, 130, 240, 225)
        )
        bw = _text_width(draw, badge, number_font)
        draw.text(
            (x + 10 + badge_size / 2 - bw / 2, y + 10 + badge_size * 0.12),
            badge, font=number_font, fill=(255, 255, 255, 255)
        )

    d = os.path.dirname(save_path)
    if d:
        os.makedirs(d, exist_ok=True)
    canvas.convert("RGB").save(save_path, "PNG", quality=95)
    return width, height


def cleanup(*paths):
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except:
            pass