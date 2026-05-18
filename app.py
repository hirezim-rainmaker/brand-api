from flask import Flask, request, jsonify
from PIL import Image, ImageOps, ImageDraw, ImageFont
import io
import base64
import requests
import numpy as np
import os
import urllib.request

app = Flask(__name__)

# ─── COLOURS ────────────────────────────────────────────────────────────────
NAVY        = (13,  27,  64)
BLUE        = (30,  91, 181)
WHITE       = (255, 255, 255)
GREY        = (102, 102, 102)
LIGHT_BG    = (238, 242, 255)
STRIP_BLUE  = (30,  91, 181)

# ─── FONTS ──────────────────────────────────────────────────────────────────
FONT_DIR = "/tmp/fonts"
os.makedirs(FONT_DIR, exist_ok=True)

FONT_PATHS = {}

def _dl_font(name, url):
    path = os.path.join(FONT_DIR, name)
    if not os.path.exists(path):
        try:
            urllib.request.urlretrieve(url, path)
        except Exception as e:
            print(f"Font download failed ({name}): {e}")
            return None
    return path

def init_fonts():
    base = "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/"
    FONT_PATHS["bold"]     = _dl_font("Montserrat-Bold.ttf",     base + "Montserrat-Bold.ttf")
    FONT_PATHS["semibold"] = _dl_font("Montserrat-SemiBold.ttf", base + "Montserrat-SemiBold.ttf")
    FONT_PATHS["regular"]  = _dl_font("Montserrat-Regular.ttf",  base + "Montserrat-Regular.ttf")

init_fonts()

def font(size, style="regular"):
    path = FONT_PATHS.get(style) or FONT_PATHS.get("regular")
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

# ─── HELPERS ────────────────────────────────────────────────────────────────

def download_image(url):
    r = requests.get(url, stream=True, allow_redirects=True, timeout=20)
    return Image.open(io.BytesIO(r.content))

def remove_black_bg(logo):
    logo = logo.convert("RGBA")
    data = np.array(logo)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    data[:,:,3] = np.where((r < 40) & (g < 40) & (b < 40), 0, 255)
    result = Image.fromarray(data)
    bbox = result.getbbox()
    return result.crop(bbox) if bbox else result

def circle_photo(photo, diameter, border=9, color=BLUE):
    """Crop photo into a circle with a coloured border ring."""
    photo = photo.convert("RGB")
    # Scale photo to fill circle
    ratio = photo.width / photo.height
    nw = diameter if ratio <= 1 else int(diameter * ratio)
    nh = diameter if ratio >= 1 else int(diameter / ratio)
    photo = photo.resize((nw, nh), Image.LANCZOS)
    left = (nw - diameter) // 2
    top  = (nh - diameter) // 2
    photo = photo.crop((left, top, left + diameter, top + diameter))

    # Circular mask
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, diameter - 1, diameter - 1], fill=255)
    photo_rgba = photo.convert("RGBA")
    photo_rgba.putalpha(mask)

    # Bordered ring
    total = diameter + border * 2
    ring = Image.new("RGBA", (total, total), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, total - 1, total - 1], fill=color + (255,))
    ring.paste(photo_rgba, (border, border), photo_rgba)
    return ring

def draw_strip(draw, W, H, strip_h, website, phone):
    """Blue strip at bottom with website | phone."""
    y0 = H - strip_h
    draw.rectangle([0, y0, W, H], fill=STRIP_BLUE)
    mid = W // 2
    draw.rectangle([mid - 1, y0 + 18, mid + 1, H - 18], fill=WHITE)
    f = font(22, "semibold")
    # Website
    draw.text((70, y0 + strip_h // 2 - 13), f"\u2022  {website}", fill=WHITE, font=f)
    # Phone
    draw.text((mid + 40, y0 + strip_h // 2 - 13), f"\u2022  {phone}", fill=WHITE, font=f)

def draw_feature(draw, x, y, label, subtitle, icon_sz=55):
    """Single feature point: blue circle + bold label + grey subtitle."""
    draw.ellipse([x, y, x + icon_sz, y + icon_sz], fill=BLUE)
    draw.text((x + icon_sz + 16, y + 6),  label.upper(),    fill=NAVY, font=font(20, "bold"))
    draw.text((x + icon_sz + 16, y + 30), subtitle.upper(), fill=GREY, font=font(15, "regular"))
    return y + icon_sz + 22

def draw_icon_row(draw, W, y0, row_h, labels):
    """Light-bg band with 4 evenly-spaced icon + label columns."""
    draw.rectangle([0, y0, W, y0 + row_h], fill=LIGHT_BG)
    col_w  = W // len(labels)
    icon_r = 22
    for i, lbl in enumerate(labels):
        cx = i * col_w + col_w // 2
        # Separator
        if i > 0:
            draw.rectangle([i * col_w - 1, y0 + 14, i * col_w + 1, y0 + row_h - 14],
                           fill=(200, 210, 230))
        # Icon circle (outline only)
        draw.ellipse([cx - icon_r, y0 + 14, cx + icon_r, y0 + 14 + icon_r * 2],
                     outline=BLUE, width=2)
        # Label (may be two lines)
        lf = font(14, "bold")
        for j, part in enumerate(lbl.split("\n")):
            bbox = draw.textbbox((0, 0), part, font=lf)
            tw = bbox[2] - bbox[0]
            draw.text((cx - tw // 2, y0 + 14 + icon_r * 2 + 8 + j * 18),
                      part, fill=NAVY, font=lf)

def heading_block(draw, x, y, word1, word2, big=72):
    """Two-word heading: word1 in navy, word2 in blue, divider below."""
    f = font(big, "bold")
    draw.text((x, y), word1, fill=NAVY, font=f)
    bb1 = draw.textbbox((x, y), word1, font=f)
    y2 = bb1[3] + 6
    draw.text((x, y2), word2, fill=BLUE, font=f)
    bb2 = draw.textbbox((x, y2), word2, font=f)
    div_y = bb2[3] + 14
    draw.rectangle([x, div_y, x + 90, div_y + 4], fill=BLUE)
    return div_y + 20   # next y after divider

# ─── FIVE TEMPLATE BUILDERS ─────────────────────────────────────────────────

ICON_LABELS = ["WATER\nCONTROL", "HOME\nPROTECTION", "LONG TERM\nSOLUTIONS", "TRUSTED\nEXPERTS"]

def template_3(photo, heading, features, website, phone):
    """
    Standard: large circle right (half cropped), 3 feature points left,
    4-icon row, blue strip.  — matches branded Image 3.
    """
    W, H = 1080, 1080
    canvas = Image.new("RGBA", (W, H), WHITE + (255,))
    draw   = ImageDraw.Draw(canvas)

    # Circle — centre at right edge so only left half shows
    d = 780
    c = circle_photo(photo, d)
    canvas.paste(c, (W - d // 2 - 9, 30), c)

    # Heading
    words = heading.upper().split()
    w1, w2 = (words + [""])[:2]
    fp_start = heading_block(draw, 50, 220, w1, w2, big=70)

    # Feature points
    y = fp_start + 10
    for lbl, sub in features[:3]:
        y = draw_feature(draw, 50, y, lbl, sub)

    # Icon row
    draw_icon_row(draw, W, 790, 115, ICON_LABELS)

    # Strip
    draw_strip(draw, W, H, 90, website, phone)

    return canvas.convert("RGB")


def template_4(photo, heading, features, website, phone):
    """
    Foundation-repair style: large circle right, minimal left content,
    3 icons centred near bottom (no 4-icon row).  — matches branded Image 4.
    """
    W, H = 1080, 1080
    canvas = Image.new("RGBA", (W, H), WHITE + (255,))
    draw   = ImageDraw.Draw(canvas)

    d = 840
    c = circle_photo(photo, d)
    canvas.paste(c, (W - d // 2 - 9, 20), c)

    words = heading.upper().split()
    w1, w2 = (words + [""])[:2]
    fp_start = heading_block(draw, 50, 250, w1, w2, big=76)

    # 3 icons centred near bottom
    icon_y = 760
    icon_sz = 80
    col_w = W // 3
    for i, (lbl, sub) in enumerate(features[:3]):
        cx = i * col_w + col_w // 2
        if i > 0:
            draw.rectangle([i * col_w - 1, icon_y, i * col_w + 1, icon_y + 180],
                           fill=(200, 210, 230))
        draw.ellipse([cx - icon_sz // 2, icon_y,
                      cx + icon_sz // 2, icon_y + icon_sz], fill=BLUE)
        lf = font(20, "bold")
        bb = draw.textbbox((0, 0), lbl.upper(), font=lf)
        draw.text((cx - (bb[2]-bb[0])//2, icon_y + icon_sz + 12),
                  lbl.upper(), fill=NAVY, font=lf)
        sf = font(15, "regular")
        bb2 = draw.textbbox((0, 0), sub, font=sf)
        draw.text((cx - (bb2[2]-bb2[0])//2, icon_y + icon_sz + 38),
                  sub, fill=GREY, font=sf)

    draw_strip(draw, W, H, 90, website, phone)
    return canvas.convert("RGB")


def template_5(photo, heading, features, website, phone):
    """
    Sump-pump style: circle right, 4 feature points with light icon circles,
    no icon row.  — matches branded Image 5.
    """
    W, H = 1080, 1080
    canvas = Image.new("RGBA", (W, H), WHITE + (255,))
    draw   = ImageDraw.Draw(canvas)

    d = 720
    c = circle_photo(photo, d)
    canvas.paste(c, (W - d // 2 - 9, 40), c)

    words = heading.upper().split()
    w1, w2 = (words + [""])[:2]
    y = heading_block(draw, 50, 200, w1, w2, big=68)

    # 4 feature points with light-bg circles
    fp_all = (features * 2)[:4]
    icon_sz = 52
    for lbl, sub in fp_all:
        draw.rectangle([50, y - 8, 500, y - 7], fill=(220, 225, 240))  # separator
        draw.ellipse([50, y, 50 + icon_sz, y + icon_sz],
                     fill=(235, 240, 255), outline=BLUE, width=2)
        draw.text((118, y + 6),  lbl.upper(), fill=BLUE, font=font(18, "bold"))
        draw.text((118, y + 28), sub,         fill=GREY, font=font(14, "regular"))
        y += icon_sz + 20

    draw_strip(draw, W, H, 90, website, phone)
    return canvas.convert("RGB")


def template_1(photo, heading, features, website, phone):
    """
    Infographic style (Image 1): uses template_3 layout as base —
    consistent brand output across all templates.
    """
    return template_3(photo, heading, features, website, phone)


def template_2(photo, heading, features, website, phone):
    """
    Services-grid style (Image 2): uses template_3 layout as base.
    """
    return template_3(photo, heading, features, website, phone)


BUILDERS = {1: template_1, 2: template_2, 3: template_3,
            4: template_4, 5: template_5}

# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


@app.route('/brand', methods=['POST'])
def brand_image():
    """Existing logo-placement endpoint — unchanged."""
    try:
        data    = request.get_json()
        raw_img = ImageOps.exif_transpose(download_image(data['raw_url'])).convert("RGBA")
        logo    = remove_black_bg(download_image(data['logo_url']))

        raw_w, raw_h = raw_img.size
        if raw_w > raw_h:
            raw_img = raw_img.rotate(90, expand=True)
            raw_w, raw_h = raw_img.size

        logo_w = int(data.get('logo_width',  int(raw_w * 0.20)))
        logo_h = int(data.get('logo_height', int(logo.height * (logo_w / logo.width))))
        logo   = logo.resize((logo_w, logo_h), Image.LANCZOS)

        pos_x = int(data.get('logo_x', 40))
        pos_y = int(data.get('logo_y', 40))
        raw_img.paste(logo, (pos_x, pos_y), logo)

        out = io.BytesIO()
        raw_img.convert("RGB").save(out, format="JPEG", quality=95)
        return jsonify({"success": True,
                        "branded_image": base64.b64encode(out.getvalue()).decode()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/template', methods=['POST'])
def apply_template():
    """
    New endpoint: full branded template compositing.

    Expected JSON body:
    {
        "raw_url":           "https://...",   // raw photo URL
        "template_id":       3,               // 1-5
        "heading":           "CLEAN SPACE",   // exactly 2 words
        "feature_1_label":   "STOP MOISTURE",
        "feature_1_subtitle":"Keep crawlspace dry",
        "feature_2_label":   "PROTECT HOME",
        "feature_2_subtitle":"Prevent costly damage",
        "feature_3_label":   "BUILT TO LAST",
        "feature_3_subtitle":"Reliable solutions",
        "website":           "www.sundahlwaterproofing.com",
        "phone":             "(914) 834-9212"
    }

    Returns:
    { "success": true, "branded_image": "<base64 JPEG>" }
    """
    try:
        data = request.get_json()

        raw = ImageOps.exif_transpose(
            download_image(data['raw_url'])
        ).convert("RGBA")

        template_id = int(data.get('template_id', 3))
        heading     = data.get('heading', 'BRAND IMAGE')
        website     = data.get('website', 'www.example.com')
        phone       = data.get('phone',   '(000) 000-0000')

        features = [
            (data.get('feature_1_label', 'FEATURE ONE'),
             data.get('feature_1_subtitle', '')),
            (data.get('feature_2_label', 'FEATURE TWO'),
             data.get('feature_2_subtitle', '')),
            (data.get('feature_3_label', 'FEATURE THREE'),
             data.get('feature_3_subtitle', '')),
        ]

        builder = BUILDERS.get(template_id, template_3)
        result  = builder(raw, heading, features, website, phone)

        out = io.BytesIO()
        result.save(out, format="JPEG", quality=95)
        return jsonify({"success": True,
                        "branded_image": base64.b64encode(out.getvalue()).decode()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
