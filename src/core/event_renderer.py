import os
import random
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "asset", "fonts")

def _get_font(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
    except:
        return ImageFont.load_default()

def _load_image(url):
    if not url:
        return None
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        size = min(img.width, img.height)
        left = (img.width - size) // 2
        top = (img.height - size) // 2
        return img.crop((left, top, left + size, top + size))
    except:
        return None

def _create_background(width, height, event_type):
    themes = {
        "join": [(100, 180, 255), (180, 120, 255)],
        "leave": [(255, 100, 150), (255, 180, 100)],
        "kick": [(255, 80, 80), (200, 50, 50)],
        "block": [(180, 50, 50), (120, 30, 30)],
        "admin": [(255, 215, 0), (255, 160, 0)]
    }
    
    event_key = "admin" if "admin" in event_type else event_type
    theme_colors = themes.get(event_key, [(150, 150, 150), (100, 100, 100)])
    
    img = Image.new('RGB', (width, height), (18, 18, 28))
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    for _ in range(6):
        x = random.randint(0, width)
        y = random.randint(0, height)
        base_color = random.choice(theme_colors)
        color = (base_color[0], base_color[1], base_color[2], 40)
        size = random.randint(150, 350)
        
        for r in range(size, 0, -4):
            alpha = int(color[3] * (r / size) ** 0.5)
            draw.ellipse(
                [x - r, y - r, x + r, y + r],
                fill=(color[0], color[1], color[2], alpha)
            )
    
    overlay = overlay.filter(ImageFilter.GaussianBlur(50))
    img = Image.alpha_composite(img.convert('RGBA'), overlay)
    return img

def _draw_glass_card(img, x, y, w, h, radius=25):
    card_area = img.crop((x, y, x + w, y + h))
    blurred = card_area.filter(ImageFilter.GaussianBlur(15))
    
    tint = Image.new('RGBA', (w, h), (255, 255, 255, 15))
    blurred = Image.alpha_composite(blurred.convert('RGBA'), tint)
    
    mask = Image.new('L', (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w, h], radius=radius, fill=255)
    
    border = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        [0, 0, w - 1, h - 1], radius=radius,
        outline=(255, 255, 255, 40), width=1
    )
    blurred = Image.alpha_composite(blurred, border)
    
    result = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    result.paste(blurred, (0, 0), mask)
    img.paste(result, (x, y), result)
    return img

def _draw_rounded_image(img, source, x, y, size, radius=20):
    if not source:
        source = Image.new('RGBA', (size, size), (50, 50, 70, 255))
    
    source = source.resize((size, size), Image.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    
    img.paste(source, (x, y), mask)
    return img

def draw_event_card(event_type, user_name, user_avatar, group_name, additional_text=""):
    WIDTH, HEIGHT = 720, 280
    CARD_PADDING = 30
    AVATAR_SIZE = 160
    
    font_title = _get_font("BeVietnamPro-Bold.ttf", 32)
    font_name = _get_font("BeVietnamPro-SemiBold.ttf", 26)
    font_sub = _get_font("BeVietnamPro-Regular.ttf", 18)
    font_footer = _get_font("BeVietnamPro-Medium.ttf", 16)
    
    img = _create_background(WIDTH, HEIGHT, event_type)
    card_x, card_y = CARD_PADDING, CARD_PADDING
    card_w, card_h = WIDTH - CARD_PADDING*2, HEIGHT - CARD_PADDING*2
    
    img = _draw_glass_card(img, card_x, card_y, card_w, card_h, radius=28)
    draw = ImageDraw.Draw(img)
    
    avatar = _load_image(user_avatar)
    avatar_x = card_x + 30
    avatar_y = card_y + (card_h - AVATAR_SIZE) // 2
    img = _draw_rounded_image(img, avatar, avatar_x, avatar_y, AVATAR_SIZE, radius=22)
    
    text_x = avatar_x + AVATAR_SIZE + 35
    text_w = card_w - AVATAR_SIZE - 80
    
    event_titles = {
        "join": "WELCOME",
        "leave": "GOODBYE",
        "kick": "KICKED",
        "block": "BLOCKED",  
        "add_admin": "NEW ADMIN",
        "remove_admin": "REVOKED"
    }
    
    title = event_titles.get(event_type, "EVENT").upper()
    draw.text((text_x, card_y + 50), title, font=font_title, fill=(255, 255, 255))
    
    display_name = user_name
    if font_name.getlength(display_name) > text_w:
        while font_name.getlength(display_name + "...") > text_w:
            display_name = display_name[:-1]
        display_name += "..."
    draw.text((text_x, card_y + 95), display_name, font=font_name, fill=(255, 255, 255))
    
    if additional_text:
        draw.text((text_x, card_y + 140), additional_text, font=font_sub, fill=(180, 180, 210))
    
    group_text = f"@{group_name}"
    group_w = font_footer.getlength(group_text)
    draw.text((card_x + card_w - group_w - 30, card_y + card_h - 40), group_text, font=font_footer, fill=(140, 140, 160))
    
    return img

def render_welcome(user_name, user_avatar, user_cover, group_name, adder_name=None):
    additional = f"Được thêm bởi {adder_name}" if adder_name else "Vừa gia nhập nhóm"
    return draw_event_card("join", user_name, user_avatar, group_name, additional)

def render_leave(user_name, user_avatar, user_cover, group_name):
    return draw_event_card("leave", user_name, user_avatar, group_name, "Hẹn gặp lại bạn nhé!")

def render_kick(user_name, user_avatar, user_cover, group_name, kicker_name):
    return draw_event_card("kick", user_name, user_avatar, group_name, f"Bởi quản trị viên {kicker_name}")

def render_block(user_name, user_avatar, user_cover, group_name, blocker_name):
    return draw_event_card("block", user_name, user_avatar, group_name, f"Bị chặn bởi {blocker_name}")

def render_add_admin(user_name, user_avatar, user_cover, group_name, adder_name):
    return draw_event_card("add_admin", user_name, user_avatar, group_name, f"Bổ nhiệm bởi {adder_name}")

def render_remove_admin(user_name, user_avatar, user_cover, group_name, remover_name):
    return draw_event_card("remove_admin", user_name, user_avatar, group_name, f"Gỡ quyền bởi {remover_name}")