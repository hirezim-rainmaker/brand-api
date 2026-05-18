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
NAVY  = (13,  27,  64)
BLUE  = (30,  91, 181)
WHITE = (255, 255, 255)
GREY  = (102, 102, 102)

# ─── FONTS ──────────────────────────────────────────────────────────────────
FONT_DIR = "/tmp/fonts"
os.makedirs(FONT_DIR, exist_ok=True)
FONT_PATHS = {}

def _dl(name, url):
    p = os.path.join(FONT_DIR, name)
    if not os.path.exists(p):
        try:
            urllib.request.urlretrieve(url, p)
        except Exception as e:
            print(f"Font download error ({name}): {e}")
            return None
    return p

def init_fonts():
    base = "https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/"
    FONT_PATHS["bold"]     = _dl("Montserrat-Bold.ttf",     base + "Montserrat-Bold.ttf")
    FONT_PATHS["semibold"] = _dl("Montserrat-SemiBold.ttf", base + "Montserrat-SemiBold.ttf")
    FONT_PATHS["regular"]  = _dl("Montserrat-Regular.ttf",  base + "Montserrat-Regular.ttf")

init_fonts()

def font(size, style="regular"):
    p = FONT_PATHS.get(style) or FONT_PATHS.get("regular")
    if p:
        try:
            return ImageFont.truetype(p, size)
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

def composite_circle(base, raw_photo, cx, cy, radius):
    """
    Crop raw_photo into a circle and paste it into the base image
    at the given centre (cx, cy) with the given radius.
    Works even when the circle extends beyond the canvas edge.
    """
    d = radius * 2
    photo = raw_photo.convert("RGB")

    # Scale photo to fill the circle diameter
    ratio = photo.width / photo.height
    if ratio >= 1:
        nw, nh = int(d * ratio), d
    else:
        nw, nh = d, int(d / ratio)
    photo = photo.resize((nw, nh), Image.LANCZOS)

    # Centre-crop to exactly d×d
    left = (nw - d) // 2
    top  = (nh - d) // 2
    photo = photo.crop((left, top, left + d, top + d))

    # Circular mask
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, d - 1, d - 1], fill=255)
    photo_rgba = photo.convert("RGBA")
    photo_rgba.putalpha(mask)

    # Paste (may extend beyond canvas — PIL clips automatically)
    paste_x = cx - radius
    paste_y = cy - radius
    base.paste(photo_rgba, (paste_x, paste_y), photo_rgba)
    return base

def cover(draw, x, y, w, h, color=WHITE):
    """Paint a solid rectangle to erase existing content."""
    draw.rectangle([x, y, x + w, y + h], fill=color)

def write_two_word_heading(draw, x, y, word1, word2, size):
    """
    word1 → dark navy (bold)
    word2 → blue (bold)
    Returns the y-coordinate immediately below the heading block.
    """
    f = font(size, "bold")
    draw.text((x, y), word1.upper(), fill=NAVY, font=f)
    bb1 = draw.textbbox((x, y), word1.upper(), font=f)
    y2 = bb1[3] + 5
    draw.text((x, y2), word2.upper(), fill=BLUE, font=f)
    bb2 = draw.textbbox((x, y2), word2.upper(), font=f)
    return bb2[3]

def write_feature_left(draw, icon_x, icon_y, label, subtitle, icon_sz=52):
    """
    Left-column feature point: blue filled circle + bold label + grey subtitle.
    Paints white over the existing text area first.
    """
    text_x = icon_x + icon_sz + 14
    cover(draw, text_x, icon_y, 420, icon_sz + 6)
    draw.text((text_x, icon_y + 6),  label.upper(),    fill=NAVY, font=font(19, "bold"))
    draw.text((text_x, icon_y + 29), subtitle.upper(), fill=GREY, font=font(14, "regular"))

def write_feature_centered(draw, cx, y, label, subtitle, col_w=360):
    """
    Bottom-centred feature (Template 4 style).
    """
    x0 = cx - col_w // 2
    cover(draw, x0, y + 88, col_w, 70)
    lf = font(19, "bold")
    lb = draw.textbbox((0, 0), label.upper(), font=lf)
    draw.text((cx - (lb[2] - lb[0]) // 2, y + 90),
              label.upper(), fill=NAVY, font=lf)
    sf = font(14, "regular")
    sb = draw.textbbox((0, 0), subtitle, font=sf)
    draw.text((cx - (sb[2] - sb[0]) // 2, y + 114),
              subtitle, fill=GREY, font=sf)


# ─── TEMPLATE COORDINATE MAP ────────────────────────────────────────────────
#
# All images are assumed to be 1080×1080 px.
#
# "circle"          → centre (cx,cy) and radius of the photo frame
# "logo_cover"      → [x, y, w, h] white rectangle to erase the existing logo
#                     (set to None if no logo in this template)
# "heading_cover"   → [x, y, w, h] white rectangle to erase the existing heading
# "heading"         → {x, y, size}  where to write the new heading
# "subtext_cover"   → [x, y, w, h] erase the tagline / subtext row
# "features"        → list of feature configs (see write_feature_* above)
# "feature_style"   → "left" or "bottom"
# "icon_size"       → icon circle diameter for left-style features
#
CONFIGS = {
    # ── Template 3 — Basement Waterproofing (standard template) ─────────────
    3: {
        "circle":        {"cx": 868, "cy": 385, "r": 368},
        "logo_cover":    [38, 28, 365, 190],
        "heading_cover": [38, 255, 520, 205],
        "heading":       {"x": 45, "y": 268, "size": 68},
        "subtext_cover": [38, 450, 520, 50],
        "features": [
            {"icon_x": 45, "icon_y": 495},
            {"icon_x": 45, "icon_y": 567},
            {"icon_x": 45, "icon_y": 639},
        ],
        "feature_style": "left",
        "icon_size": 52,
    },

    # ── Template 4 — Foundation Repair (larger circle, 3 bottom icons) ──────
    4: {
        "circle":        {"cx": 900, "cy": 398, "r": 398},
        "logo_cover":    [38, 24, 365, 188],
        "heading_cover": [38, 258, 520, 215],
        "heading":       {"x": 45, "y": 272, "size": 74},
        "subtext_cover": [38, 466, 520, 52],
        "features": [
            {"cx": 180, "icon_y": 758},
            {"cx": 540, "icon_y": 758},
            {"cx": 900, "icon_y": 758},
        ],
        "feature_style": "bottom",
        "icon_size": 80,
    },

    # ── Template 5 — Sump Pump Solutions (heading at top, 3 left features) ──
    5: {
        "circle":        {"cx": 868, "cy": 415, "r": 352},
        "logo_cover":    None,
        "heading_cover": [38, 32, 520, 215],
        "heading":       {"x": 45, "y": 45, "size": 70},
        "subtext_cover": [38, 245, 520, 52],
        "features": [
            {"icon_x": 45, "icon_y": 310},
            {"icon_x": 45, "icon_y": 395},
            {"icon_x": 45, "icon_y": 480},
        ],
        "feature_style": "left",
        "icon_size": 52,
    },

    # ── Templates 1 & 2 reuse Template 3 coordinate system ──────────────────
    1: None,
    2: None,
}
# Map templates 1 and 2 to template 3's config
CONFIGS[1] = CONFIGS[3]
CONFIGS[2] = CONFIGS[3]


# ─── CORE COMPOSITING FUNCTION ───────────────────────────────────────────────

def apply_template(base_img, raw_photo, heading, features, cfg):
    """
    Composite raw_photo into base_img (the branded reference) and
    overlay dynamic text.  Returns a PIL RGB image.

    features: list of (label, subtitle) tuples — up to 3 items.
    """
    base = base_img.convert("RGBA")
    draw = ImageDraw.Draw(base)

    # 1. Composite photo into the circle
    c = cfg["circle"]
    composite_circle(base, raw_photo, c["cx"], c["cy"], c["r"])

    # Re-acquire draw after paste operations
    draw = ImageDraw.Draw(base)

    # 2. Erase existing logo
    if cfg.get("logo_cover"):
        lc = cfg["logo_cover"]
        cover(draw, lc[0], lc[1], lc[2], lc[3])

    # 3. Erase existing heading and write new one
    hc = cfg["heading_cover"]
    cover(draw, hc[0], hc[1], hc[2], hc[3])
    words = heading.upper().split()
    w1 = words[0] if len(words) > 0 else "BRAND"
    w2 = words[1] if len(words) > 1 else "IMAGE"
    h = cfg["heading"]
    write_two_word_heading(draw, h["x"], h["y"], w1, w2, h["size"])

    # 4. Erase subtext row
    sc = cfg["subtext_cover"]
    cover(draw, sc[0], sc[1], sc[2], sc[3])

    # 5. Write feature points
    style   = cfg.get("feature_style", "left")
    icon_sz = cfg.get("icon_size", 52)
    fp_cfgs = cfg.get("features", [])

    for i, (label, subtitle) in enumerate(features[:3]):
        if i >= len(fp_cfgs):
            break
        fp = fp_cfgs[i]

        if style == "left":
            write_feature_left(draw,
                               fp["icon_x"], fp["icon_y"],
                               label, subtitle, icon_sz)
        else:  # bottom-centred (Template 4)
            write_feature_centered(draw,
                                   fp["cx"], fp["icon_y"],
                                   label, subtitle)

    return base.convert("RGB")


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


@app.route('/brand', methods=['POST'])
def brand_image():
    """
    Existing logo-placement endpoint — unchanged.
    Accepts: raw_url, logo_url, logo_x, logo_y, logo_width
    """
    try:
        data    = request.get_json()
        raw_img = ImageOps.exif_transpose(
            download_image(data['raw_url'])
        ).convert("RGBA")
        logo = remove_black_bg(download_image(data['logo_url']))

        raw_w, raw_h = raw_img.size
        if raw_w > raw_h:
            raw_img  = raw_img.rotate(90, expand=True)
            raw_w, raw_h = raw_img.size

        logo_w = int(data.get('logo_width',  int(raw_w * 0.20)))
        logo_h = int(data.get('logo_height', int(logo.height * (logo_w / logo.width))))
        logo   = logo.resize((logo_w, logo_h), Image.LANCZOS)

        pos_x = int(data.get('logo_x', 40))
        pos_y = int(data.get('logo_y', 40))
        raw_img.paste(logo, (pos_x, pos_y), logo)

        out = io.BytesIO()
        raw_img.convert("RGB").save(out, format="JPEG", quality=95)
        return jsonify({
            "success": True,
            "branded_image": base64.b64encode(out.getvalue()).decode()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/template', methods=['POST'])
def template_endpoint():
    """
    Branded template compositing endpoint.

    Uses the actual branded reference image as the base — preserving
    all real brand design — then composites the raw photo into the
    circular frame and overlays dynamic text.

    Expected JSON body:
    {
        "raw_url":           "https://...",   // raw photo (Google Drive direct link)
        "template_url":      "https://...",   // branded reference image (Google Drive)
        "template_id":       3,               // 1-5  (selects coordinate config)
        "heading":           "CLEAN SPACE",   // exactly 2 words
        "feature_1_label":   "STOP MOISTURE",
        "feature_1_subtitle":"Keep crawlspace dry",
        "feature_2_label":   "PROTECT HOME",
        "feature_2_subtitle":"Prevent costly damage",
        "feature_3_label":   "BUILT TO LAST",
        "feature_3_subtitle":"Reliable solutions"
    }

    Returns:
    { "success": true, "branded_image": "<base64 JPEG>" }
    """
    try:
        data = request.get_json()

        raw   = ImageOps.exif_transpose(
            download_image(data['raw_url'])
        ).convert("RGBA")

        base  = ImageOps.exif_transpose(
            download_image(data['template_url'])
        ).convert("RGBA")

        # Resize base to 1080×1080 if needed
        if base.size != (1080, 1080):
            base = base.resize((1080, 1080), Image.LANCZOS)

        template_id = int(data.get('template_id', 3))
        cfg         = CONFIGS.get(template_id, CONFIGS[3])

        heading  = data.get('heading', 'BRAND IMAGE')
        features = [
            (data.get('feature_1_label', 'FEATURE ONE'),
             data.get('feature_1_subtitle', '')),
            (data.get('feature_2_label', 'FEATURE TWO'),
             data.get('feature_2_subtitle', '')),
            (data.get('feature_3_label', 'FEATURE THREE'),
             data.get('feature_3_subtitle', '')),
        ]

        result = apply_template(base, raw, heading, features, cfg)

        # Optional logo placement — only runs if logo_url is provided
        logo_url = data.get('logo_url')
        if logo_url:
            result_rgba = result.convert("RGBA")
            logo = remove_black_bg(download_image(logo_url))
            img_w, img_h = result_rgba.size
            logo_w = int(data.get('logo_width', int(img_w * 0.20)))
            logo_h = int(logo.height * (logo_w / logo.width))
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
            pos_x = int(data.get('logo_x', 20))
            pos_y = int(data.get('logo_y', 20))
            result_rgba.paste(logo, (pos_x, pos_y), logo)
            result = result_rgba.convert("RGB")

        out = io.BytesIO()
        result.save(out, format="JPEG", quality=95)
        return jsonify({
            "success": True,
            "branded_image": base64.b64encode(out.getvalue()).decode()
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
