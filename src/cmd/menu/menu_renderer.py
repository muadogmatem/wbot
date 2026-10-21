import os
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "asset", "fonts")

PERM_TEXT = {
    1: "TV",
    2: "AD",
    3: "SU",
    4: "OW",
    5: "SV"
}


def _get_font(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except:
        return ImageFont.load_default()


def _convert_perm(perm):
    if isinstance(perm, int):
        return perm
    if isinstance(perm, str):
        if perm == "admin":
            return 3
        elif perm == "all":
            return 1
        try:
            return int(perm)
        except:
            return 1
    return 1


def _create_background(width, height):
    img = Image.new('RGB', (width, height), (12, 12, 20))
    
    colors = [
        (255, 120, 180, 50),
        (100, 200, 255, 45),
        (255, 200, 100, 40),
        (180, 130, 255, 45),
        (120, 255, 200, 40),
    ]
    
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    for _ in range(random.randint(6, 10)):
        x = random.randint(-50, width + 50)
        y = random.randint(-50, height + 50)
        color = random.choice(colors)
        size = random.randint(120, 280)
        
        for r in range(size, 0, -4):
            alpha = int(color[3] * (r / size) ** 0.6)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(color[0], color[1], color[2], alpha))
    
    overlay = overlay.filter(ImageFilter.GaussianBlur(50))
    img = Image.alpha_composite(img.convert('RGBA'), overlay)
    
    return img


def _draw_cmd_card(img, x, y, w, h, name, perm=1, is_on=True):
    card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card)
    
    if is_on:
        fill_color = (255, 255, 255, 15)
        border_color = (255, 255, 255, 40)
        text_color = (255, 255, 255)
        perm_color = (180, 180, 180)
    else:
        fill_color = (255, 255, 255, 8)
        border_color = (255, 255, 255, 20)
        text_color = (100, 100, 100)
        perm_color = (80, 80, 80)
    
    card_draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=16, fill=fill_color, outline=border_color, width=1)
    
    font_cmd = _get_font("vnpbold.ttf", 15)
    font_perm = _get_font("Darley-sans.otf", 11)
    
    cmd_text = name.upper()
    max_w = w - 24
    text_w = font_cmd.getlength(cmd_text)
    
    if text_w > max_w:
        while font_cmd.getlength(cmd_text + "..") > max_w and len(cmd_text) > 2:
            cmd_text = cmd_text[:-1]
        cmd_text += ".."
    
    card_draw.text((12, 12), cmd_text, font=font_cmd, fill=text_color)
    
    perm_text = PERM_TEXT.get(perm, "?")
    perm_w = font_perm.getlength(perm_text)
    
    card_draw.text((w - perm_w - 12, h - 24), perm_text, font=font_perm, fill=perm_color)
    
    img.paste(card, (x, y), card)
    return img


def draw_menu_page(entries, page, total_pages, bot_name="ConMeo"):
    COLS = 5
    ROWS = 3
    CARD_W = 140
    CARD_H = 75
    GAP_X = 12
    GAP_Y = 12
    PADDING = 25
    HEADER_H = 70
    FOOTER_H = 15
    
    WIDTH = COLS * CARD_W + (COLS - 1) * GAP_X + PADDING * 2
    HEIGHT = HEADER_H + ROWS * CARD_H + (ROWS - 1) * GAP_Y + PADDING + FOOTER_H
    
    img = _create_background(WIDTH, HEIGHT)
    draw = ImageDraw.Draw(img)
    
    font_name = _get_font("Dela-gothic-one.ttf", 26)
    font_page = _get_font("Dela-gothic-one.ttf", 13)
    
    name_w = font_name.getlength(bot_name)
    draw.text(((WIDTH - name_w) / 2, 16), bot_name, font=font_name, fill=(255, 255, 255))
    
    page_text = f"{page} / {total_pages}"
    page_w = font_page.getlength(page_text)
    draw.text(((WIDTH - page_w) / 2, 46), page_text, font=font_page, fill=(150, 150, 160))
    
    for idx, (name, entry) in enumerate(entries):
        row = idx // COLS
        col = idx % COLS
        
        x = PADDING + col * (CARD_W + GAP_X)
        y = HEADER_H + row * (CARD_H + GAP_Y)
        
        perm = _convert_perm(entry.get("perm", 1))
        is_on = entry.get("on", True)
        img = _draw_cmd_card(img, x, y, CARD_W, CARD_H, name, perm, is_on)
    
    return img


def save_menu_image(img, unique_id):
    cache_dir = os.path.join(os.path.dirname(__file__), "cache", "menu")
    os.makedirs(cache_dir, exist_ok=True)
    
    file_path = os.path.join(cache_dir, f"menu_{unique_id}.png")
    img.save(file_path, format="PNG", optimize=True)
    
    return file_path